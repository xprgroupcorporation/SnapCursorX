from PySide6 import QtWidgets, QtCore
import copy
import ctypes
from ctypes import wintypes
import importlib
import time
import winsound
import win32api

from Config.Manager import ConfigManager
from Core.Setup import ActiveSetupManager
from Core.timing import (
    TIMING_MODE_CYCLE,
    TIMING_MODE_FREQUENCY,
    apply_cycle_timing,
    apply_frequency_timing,
    cycle_to_interval_ms,
    normalize_timing_config,
)
from UI.components.animations import WindowAnimator


def _main_window_module():
    return importlib.import_module("UI.main_window")


def _native_click_controller_type():
    return importlib.import_module("Core.Input").NativeClickController


def get_click_engine_bridge():
    return importlib.import_module("Core.Input").get_click_engine_bridge()


def _overlay_type():
    return _main_window_module()._overlay_type()


def _overlay_widget_types():
    return _main_window_module()._overlay_widget_types()


def read_click_randomness(source, default=True):
    return _main_window_module().read_click_randomness(source, default)


def write_click_randomness(target, value):
    return _main_window_module().write_click_randomness(target, value)


def read_starter_click_randomness(source, default=True):
    return _main_window_module().read_starter_click_randomness(source, default)


def _editor_spinbox_style():
    return """
        QSpinBox, QTimeEdit {
            color: white;
            background: rgba(0,0,0,100);
            border: none;
            border-radius: 3px;
            font: 9pt 'Times New Roman';
            padding: 2px 28px 2px 8px;
        }
        QSpinBox::up-button, QTimeEdit::up-button {
            subcontrol-origin: border;
            subcontrol-position: center right;
            width: 14px;
            height: 100%;
            right: 14px;
            border: none;
            background: rgba(255,255,255,16);
        }
        QSpinBox::down-button, QTimeEdit::down-button {
            subcontrol-origin: border;
            subcontrol-position: center right;
            width: 14px;
            height: 100%;
            right: 0px;
            border: none;
            background: rgba(255,255,255,24);
        }
        QSpinBox::up-arrow, QTimeEdit::up-arrow {
            image: none;
            width: 0;
            height: 0;
            border-top: 4px solid transparent;
            border-bottom: 4px solid transparent;
            border-left: 5px solid rgba(255,255,255,190);
        }
        QSpinBox::down-arrow, QTimeEdit::down-arrow {
            image: none;
            width: 0;
            height: 0;
            border-top: 4px solid transparent;
            border-bottom: 4px solid transparent;
            border-right: 5px solid rgba(255,255,255,190);
        }
    """


CLICK_TARGET_MODE_KEY = "click_target_mode"
CLICK_TARGET_FOLLOW = "follow"
CLICK_TARGET_MARKER = "marker"
CLICK_TARGET_POINTER = "pointer"
FOLLOW_POSITION_KEY = "follow_position"
FIXED_POSITION_KEY = "fixed_position"


class SingleModeLogicMixin:
    def __init__(self, file_path, pos=None, parent=None):
        # State flags must exist before build_ui (called inside super().__init__)
        self._executing = False
        self._worker = None
        self._follow_timer = None
        self._follow_indicator = None
        self._click_effects_enabled = True
        self._hide_marker_on_execute = True
        self._last_follow_mouse_mode = None
        self._button_debounce_ms = 350
        self._button_debounce_until = 0.0
        self._execution_click_count = 0
        self._execution_estimated_cps = 0.0
        self._native_poll_last_count = None
        self._native_poll_last_time = None
        self._execution_started_at = None
        self._execution_duration_seconds = 0
        self._progress_timer = None
        self._stop_sound_played = False
        self._info_dialog = None
        self._failsafe_edit_active = False
        self._failsafe_runtime_monitor = None
        self._pending_stop_message = None
        self._last_failsafe_trigger_edge = ""
        self._pointer_lock_active = False

        super().__init__(file_path, pos, title="Single Mode", parent=parent)

        # Resize to fit full UI after base sets 280×80
        center = self.geometry().center()
        self.resize(480, 220)
        rect = self.geometry()
        rect.moveCenter(center)
        self.move(rect.topLeft())

        # Load global config once
        self._global_config = ConfigManager.load()

        # Ensure data has single-mode structure
        self._init_data_structure()
        self._saved_state = copy.deepcopy(self.data)

        # Keybind listener (only the 3 actions we need)
        kb = self._global_config.get("keybinds", {})
        self._keybind_listener = _main_window_module().KeybindListener(
            {
                "Execute":               kb.get("Execute", "F1"),
                "Stop":                  kb.get("Stop", "F2"),
                "Register_Click_Position": kb.get("Register_Click_Position", "F3"),
                "See_Setup_Info":        kb.get("See_Setup_Info", "F1"),
            },
            parent=self,
        )
        self._keybind_listener.triggered.connect(self._on_keybind)

        # Sync widgets & marker to loaded data
        overlay = self._get_overlay()
        if overlay:
            overlay.on_marker_moved = self._on_marker_dragged
        self._sync_ui()

    def _init_data_structure(self):
        """Guarantee single-mode JSON fields exist; fill from Meta.json defaults."""
        starter = self._global_config.get("starter_values", {})
        default_px = self._default_failsafe_px()
        self.data.setdefault("position", {"x": 0, "y": 0})
        self.data.setdefault("settings", {})
        settings = self.data["settings"]
        normalize_timing_config(settings, default_interval_ms=max(1, starter.get("Default_Auto_Click_Delay_MS", 100)))
        settings.setdefault("mouse_hold_ms", max(0, starter.get("Default_Mouse_Hold_MS", 100)))
        write_click_randomness(settings, read_click_randomness(settings, read_starter_click_randomness(starter, True)))
        if CLICK_TARGET_MODE_KEY not in settings:
            self._write_click_target_mode(
                settings,
                CLICK_TARGET_FOLLOW if starter.get("Default_Always_Follow_Mouse", False) else CLICK_TARGET_MARKER,
            )
        else:
            self._write_click_target_mode(settings, settings.get(CLICK_TARGET_MODE_KEY))
        settings.setdefault("repeat_mode", "until_stop")
        settings.setdefault("repeat_times_target", 100)
        settings.setdefault("repeat_timer_seconds", 60)
        settings.setdefault("mouse_button", "left")
        self._ensure_click_target_positions(settings)
        self._load_position_for_mode(self._read_click_target_mode(settings), persist=False)
        self.data["failsafe"] = self._sanitize_failsafe(self.data.get("failsafe", {
            "enabled": True,
            "top_px": default_px,
            "bottom_px": default_px,
            "left_px": default_px,
            "right_px": default_px,
        }))
        self.data["mode"] = "single"

    def _default_failsafe_px(self):
        try:
            return max(0, int(ConfigManager.load().get("general", {}).get("Default_Screen_Failsafe_PX", 50)))
        except Exception:
            return 50

    def _primary_screen_size(self):
        screen = QtWidgets.QApplication.primaryScreen()
        if screen is None:
            return 1920, 1080
        geom = screen.geometry()
        return max(1, geom.width()), max(1, geom.height())

    def _primary_screen_geometry(self):
        screen = QtWidgets.QApplication.primaryScreen()
        if screen is None:
            return QtCore.QRect(0, 0, 1920, 1080)
        return QtCore.QRect(screen.geometry())

    def _normalize_click_target_mode(self, value):
        normalized = str(value or "").strip().lower()
        if normalized in (CLICK_TARGET_FOLLOW, CLICK_TARGET_MARKER, CLICK_TARGET_POINTER):
            return normalized
        return CLICK_TARGET_MARKER

    def _read_click_target_mode(self, settings: dict | None):
        if not isinstance(settings, dict):
            return CLICK_TARGET_MARKER
        if CLICK_TARGET_MODE_KEY in settings:
            return self._normalize_click_target_mode(settings.get(CLICK_TARGET_MODE_KEY))
        return CLICK_TARGET_FOLLOW if bool(settings.get("always_follow_mouse", False)) else CLICK_TARGET_MARKER

    def _write_click_target_mode(self, settings: dict, mode: str):
        normalized = self._normalize_click_target_mode(mode)
        settings[CLICK_TARGET_MODE_KEY] = normalized
        settings["always_follow_mouse"] = bool(normalized == CLICK_TARGET_FOLLOW)
        return normalized

    def _click_target_is_follow(self):
        return self._read_click_target_mode(self.data.get("settings", {})) == CLICK_TARGET_FOLLOW

    def _click_target_is_pointer(self):
        return self._read_click_target_mode(self.data.get("settings", {})) == CLICK_TARGET_POINTER

    def _sanitize_position_value(self, value):
        if not isinstance(value, dict):
            return {"x": 0, "y": 0}
        try:
            return {"x": int(value.get("x", 0)), "y": int(value.get("y", 0))}
        except Exception:
            return {"x": 0, "y": 0}

    def _position_store_key_for_mode(self, mode: str):
        normalized = self._normalize_click_target_mode(mode)
        return FOLLOW_POSITION_KEY if normalized == CLICK_TARGET_FOLLOW else FIXED_POSITION_KEY

    def _ensure_click_target_positions(self, settings: dict):
        if not isinstance(settings, dict):
            return
        base_position = self._sanitize_position_value(self.data.get("position", {}))
        settings[FOLLOW_POSITION_KEY] = self._sanitize_position_value(settings.get(FOLLOW_POSITION_KEY, base_position))
        settings[FIXED_POSITION_KEY] = self._sanitize_position_value(settings.get(FIXED_POSITION_KEY, base_position))

    def _stored_position_for_mode(self, mode: str):
        settings = self.data.setdefault("settings", {})
        self._ensure_click_target_positions(settings)
        return dict(settings.get(self._position_store_key_for_mode(mode), {"x": 0, "y": 0}))

    def _write_position_for_mode(self, mode: str, x: int, y: int):
        settings = self.data.setdefault("settings", {})
        self._ensure_click_target_positions(settings)
        settings[self._position_store_key_for_mode(mode)] = {"x": int(x), "y": int(y)}

    def _load_position_for_mode(self, mode: str, persist: bool):
        position = self._stored_position_for_mode(mode)
        self._apply_live_position(
            int(position.get("x", 0)),
            int(position.get("y", 0)),
            persist=persist,
            mode_override=mode,
        )

    def _clear_pointer_cursor_lock(self):
        if not self._pointer_lock_active:
            return
        try:
            ctypes.windll.user32.ClipCursor(None)
        except Exception:
            pass
        self._pointer_lock_active = False

    def _apply_pointer_cursor_lock(self, x: int, y: int):
        try:
            rect = wintypes.RECT(int(x), int(y), int(x) + 1, int(y) + 1)
            self._pointer_lock_active = bool(ctypes.windll.user32.ClipCursor(ctypes.byref(rect)))
        except Exception:
            self._pointer_lock_active = False

    def _sanitize_failsafe(self, failsafe: dict | None):
        width, height = self._primary_screen_size()
        values = dict(failsafe or {})
        return {
            "enabled": bool(values.get("enabled", True)),
            "top_px": max(0, min(height, int(values.get("top_px", self._default_failsafe_px())))),
            "bottom_px": max(0, min(height, int(values.get("bottom_px", self._default_failsafe_px())))),
            "left_px": max(0, min(width, int(values.get("left_px", self._default_failsafe_px())))),
            "right_px": max(0, min(width, int(values.get("right_px", self._default_failsafe_px())))),
        }

    def _failsafe_summary_text(self):
        failsafe = self._sanitize_failsafe(self.data.get("failsafe", {}))
        if not failsafe.get("enabled", True):
            return "Disabled"
        return (
            f"T {failsafe['top_px']}  "
            f"B {failsafe['bottom_px']}  "
            f"L {failsafe['left_px']}  "
            f"R {failsafe['right_px']}"
        )

    def _get_overlay(self):
        Overlay = _overlay_type()
        for w in QtWidgets.QApplication.instance().topLevelWidgets():
            if isinstance(w, Overlay):
                return w
        return None

    def _cached_overlay_hwnds(self):
        app = QtWidgets.QApplication.instance()
        if app is None:
            return frozenset()
        overlay_types = _overlay_widget_types()
        hwnds = []
        for widget in app.topLevelWidgets():
            if not isinstance(widget, overlay_types):
                continue
            try:
                hwnds.append(int(widget.winId()))
            except Exception:
                continue
        return frozenset(hwnds)

    def _has_position(self):
        pos = self.data.get("position", {})
        return not (pos.get("x", 0) == 0 and pos.get("y", 0) == 0)

    def _format_hint_text(self, keybinds: dict):
        exec_k = keybinds.get("Execute", "F1")
        stop_k = keybinds.get("Stop", "F2")
        reg_k = keybinds.get("Register_Click_Position", "F4")
        info_k = keybinds.get("See_Setup_Info", "F1")
        quick_k = keybinds.get("Quick_Save", "F7")
        recover_k = keybinds.get("Recover_Window_Position", "F8")
        hide_k = keybinds.get("Save_Close_Setup", "F9")
        kill_k = keybinds.get("Kill_Switch", "F10")
        return (
            f"Execute ({exec_k}) • Stop ({stop_k}) • Register ({reg_k}) • Info ({info_k})\n"
            f"Quick Save ({quick_k}) • Toggle Minimize ({recover_k}) • S&Close ({hide_k}) • Kill ({kill_k})"
        )

    def _on_failsafe_enabled_changed(self):
        failsafe = self._sanitize_failsafe(self.data.get("failsafe", {}))
        failsafe["enabled"] = self._failsafe_enabled_check.isChecked()
        self.data["failsafe"] = failsafe
        self._sync_ui()

    def _start_failsafe_monitor(self, failsafe: dict):
        self._stop_failsafe_monitor()
        sanitized = self._sanitize_failsafe(failsafe)
        self._failsafe_runtime_monitor = _main_window_module().ScreenEdgeFailsafeMonitor(sanitized, self)
        self._failsafe_runtime_monitor.triggered.connect(self._on_failsafe_triggered)
        self._failsafe_runtime_monitor.start()

    def _stop_failsafe_monitor(self):
        if not self._failsafe_runtime_monitor:
            return
        self._failsafe_runtime_monitor.stop()
        self._failsafe_runtime_monitor.wait(100)
        self._failsafe_runtime_monitor = None

    def _on_failsafe_triggered(self, edge: str):
        if not self._executing:
            return
        self._last_failsafe_trigger_edge = str(edge or "").lower()
        edge_label = self._last_failsafe_trigger_edge.capitalize() if self._last_failsafe_trigger_edge else "Edge"
        self._pending_stop_message = (f"Failsafe triggered: {edge_label} edge", "#ffb86c")
        self._set_status(self._pending_stop_message[0], self._pending_stop_message[1])
        self._on_stop(force=True)

    def _register_position(self):
        """Capture cursor position now and store it."""
        x, y = win32api.GetCursorPos()
        self._apply_live_position(x, y, persist=not self._executing)
        self._sync_ui()
        self._set_status(f"Registered  ({x}, {y})", "#a64dff")

    def _on_marker_dragged(self, x: int, y: int):
        """Called by Overlay whenever the marker is dragged to a new position.
        Updates position data in memory and refreshes the display immediately.
        No manual re-register step needed — drag = new registered position."""
        self._apply_live_position(x, y, persist=False)
        # Update display label only (don't reposition the marker — it moved itself)
        if hasattr(self, "_pos_display"):
            self._pos_display.setText(f"{x},  {y}")
            self._pos_display.setStyleSheet(
                "color: rgba(255,255,255,210); font: 8pt 'Times New Roman';"
            )
        self._set_status(f"Position updated  ({x}, {y})", "#a64dff")

    def refresh_keybind_hints(self, keybinds: dict):
        """Called by ControlPanel.save_settings() to push new bindings live."""
        if hasattr(self, "_hint_lbl"):
            self._hint_lbl.setText(self._format_hint_text(keybinds))

    def _on_settings_changed(self):
        if not hasattr(self, "_timing_value_spin"):
            return
        self._apply_timing_from_widgets()
        self.data["settings"]["mouse_hold_ms"] = self._hold_spin.value()
        write_click_randomness(self.data["settings"], self._anti_check.isChecked())
        if hasattr(self, "_selected_click_target_mode"):
            self._write_click_target_mode(self.data["settings"], self._selected_click_target_mode())
        self.data["settings"]["mouse_button"] = self._mouse_button_combo.currentData() or "left"
        self._sync_ui()
        self._update_follow_mouse_state()
        self._update_click_mode_warning()

    def _format_repeat_time(self, seconds: int):
        seconds = max(0, int(seconds))
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def _on_repeat_mode_changed(self):
        sender = self.sender()
        if sender == self._repeat_times_check and self._repeat_times_check.isChecked():
            mode = "repeat_times"
        elif sender == self._repeat_timer_check and self._repeat_timer_check.isChecked():
            mode = "repeat_timer"
        elif sender == self._until_stop_check and self._until_stop_check.isChecked():
            mode = "until_stop"
        elif self._repeat_times_check.isChecked():
            mode = "repeat_times"
        elif self._repeat_timer_check.isChecked():
            mode = "repeat_timer"
        else:
            mode = "until_stop"
        self.data["settings"]["repeat_mode"] = mode
        self._sync_repeat_mode_widgets()

    def _edit_repeat_times(self):
        spin = QtWidgets.QSpinBox()
        spin.setRange(1, 999999999)
        spin.setValue(max(1, int(self.data["settings"].get("repeat_times_target", 100))))
        spin.setStyleSheet(_editor_spinbox_style())
        value = self._prompt_edit_dialog("Repeat Times", "Set the target number of clicks.", spin, spin.value)
        if value is None:
            return
        self.data["settings"]["repeat_times_target"] = int(value)
        self.data["settings"]["repeat_mode"] = "repeat_times"
        self._sync_repeat_mode_widgets()

    def _edit_repeat_timer(self):
        time_edit = QtWidgets.QTimeEdit()
        time_edit.setDisplayFormat("HH:mm:ss")
        time_edit.setTime(QtCore.QTime(0, 0, 0).addSecs(max(1, int(self.data["settings"].get("repeat_timer_seconds", 60)))))
        time_edit.setStyleSheet(_editor_spinbox_style())
        value = self._prompt_edit_dialog(
            "Repeat Timer",
            "Set the total run duration in HH:MM:SS.",
            time_edit,
            lambda: QtCore.QTime(0, 0, 0).secsTo(time_edit.time()),
        )
        if value is None:
            return
        self.data["settings"]["repeat_timer_seconds"] = max(1, int(value))
        self.data["settings"]["repeat_mode"] = "repeat_timer"
        self._sync_repeat_mode_widgets()

    def _ensure_progress_timer(self):
        if self._progress_timer is None:
            self._progress_timer = QtCore.QTimer(self)
            self._progress_timer.timeout.connect(self._update_execution_progress)
            self._progress_timer.setInterval(250)

    def _ensure_follow_timer(self):
        if self._follow_timer is None:
            self._follow_timer = QtCore.QTimer(self)
            self._follow_timer.timeout.connect(self._follow_mouse_tick)
            self._follow_timer.setInterval(16)

    def _follow_timer_interval_ms(self):
        if not self._executing:
            return 8
        try:
            click_delay_ms = int(normalize_timing_config(self.data.get("settings", {})).get("click_delay_ms", 100))
        except Exception:
            click_delay_ms = 100
        if click_delay_ms > 50:
            return max(12, min(24, click_delay_ms // 4))
        return 16

    def _current_timing_mode(self):
        return str(self.data.get("settings", {}).get("click_mode", TIMING_MODE_CYCLE) or TIMING_MODE_CYCLE).lower()

    def _timing_units_for_mode(self, mode: str):
        if str(mode or "").lower() == TIMING_MODE_FREQUENCY:
            return (("Second", "CPS"), ("Minute", "CPM"), ("Hour", "CPH"))
        return ("ms",)

    def _effective_hold_ms(self, interval_ms: int, requested_hold_ms: int) -> int:
        interval_ms = max(1, int(interval_ms))
        requested_hold_ms = max(0, int(requested_hold_ms))
        return max(0, min(requested_hold_ms, interval_ms - 1))

    def _cycle_parts_to_total_ms(self):
        hours = int(getattr(self, "_cycle_h_spin").value()) if hasattr(self, "_cycle_h_spin") else 0
        minutes = int(getattr(self, "_cycle_m_spin").value()) if hasattr(self, "_cycle_m_spin") else 0
        seconds = int(getattr(self, "_cycle_s_spin").value()) if hasattr(self, "_cycle_s_spin") else 0
        millis = int(getattr(self, "_cycle_ms_spin").value()) if hasattr(self, "_cycle_ms_spin") else 0
        total = (((hours * 60) + minutes) * 60 + seconds) * 1000 + millis
        return max(1, int(total))

    def _set_cycle_parts_from_ms(self, total_ms: int):
        total_ms = max(1, int(total_ms))
        hours = total_ms // 3600000
        rem = total_ms % 3600000
        minutes = rem // 60000
        rem %= 60000
        seconds = rem // 1000
        millis = rem % 1000
        for widget, value in (
            (getattr(self, "_cycle_h_spin", None), hours),
            (getattr(self, "_cycle_m_spin", None), minutes),
            (getattr(self, "_cycle_s_spin", None), seconds),
            (getattr(self, "_cycle_ms_spin", None), millis),
        ):
            if widget is None:
                continue
            blocked = widget.blockSignals(True)
            widget.setValue(int(value))
            widget.blockSignals(blocked)

    def _cache_current_timing_widgets(self):
        if not hasattr(self, "_timing_cache") or not hasattr(self, "_timing_unit_combo"):
            return
        mode = self._current_timing_mode()
        if mode == TIMING_MODE_FREQUENCY:
            unit = self._timing_unit_combo.currentData() or self._timing_unit_combo.currentText()
            self._timing_cache[mode] = {
                "value": max(1, int(self._timing_value_spin.value())),
                "unit": unit,
            }
        else:
            self._timing_cache[mode] = {
                "value": max(1, int(self._cycle_parts_to_total_ms())),
                "unit": "ms",
            }

    def _apply_timing_from_widgets(self):
        settings = self.data.setdefault("settings", {})
        normalize_timing_config(settings)
        if hasattr(self, "_timing_cache"):
            self._cache_current_timing_widgets()
        mode = self._current_timing_mode()
        if str(mode or "").lower() == TIMING_MODE_FREQUENCY:
            current_value = max(1, int(self._timing_value_spin.value()))
            current_unit = self._timing_unit_combo.currentData() or self._timing_unit_combo.currentText()
            apply_frequency_timing(settings, current_value, current_unit)
        else:
            apply_cycle_timing(settings, self._cycle_parts_to_total_ms(), "ms")

    def _sync_timing_ui(self):
        if not hasattr(self, "_timing_value_spin"):
            return
        settings = self.data.setdefault("settings", {})
        normalize_timing_config(settings)
        mode = self._current_timing_mode()
        self._cycle_mode_btn.blockSignals(True)
        self._frequency_mode_btn.blockSignals(True)
        self._cycle_mode_btn.setChecked(mode == TIMING_MODE_CYCLE)
        self._frequency_mode_btn.setChecked(mode == TIMING_MODE_FREQUENCY)
        self._cycle_mode_btn.blockSignals(False)
        self._frequency_mode_btn.blockSignals(False)

        unit_options = self._timing_units_for_mode(mode)
        if hasattr(self, "_timing_cache"):
            self._timing_cache["cycle"] = dict(settings.get("cycle", self._timing_cache.get("cycle", {"value": 100, "unit": "ms"})))
            self._timing_cache["frequency"] = dict(settings.get("frequency", self._timing_cache.get("frequency", {"value": 10, "unit": "CPS"})))
            active_config = dict(self._timing_cache.get(mode, {})) if mode == TIMING_MODE_FREQUENCY else dict(settings.get("cycle", {}))
        else:
            active_config = dict(settings.get(mode, {}))

        if mode == TIMING_MODE_FREQUENCY:
            self._timing_stack.setCurrentIndex(1)
            default_unit = unit_options[0][1]
            unit = active_config.get("unit", default_unit)
            value = max(1, int(active_config.get("value", 10)))
            self._timing_value_spin.setRange(1, 1000)
            combo_blocked = self._timing_unit_combo.blockSignals(True)
            self._timing_unit_combo.clear()
            for option in unit_options:
                self._timing_unit_combo.addItem(option[0], option[1])
            idx = self._timing_unit_combo.findData(unit)
            self._timing_unit_combo.setCurrentIndex(0 if idx < 0 else idx)
            self._timing_unit_combo.blockSignals(combo_blocked)

            spin_blocked = self._timing_value_spin.blockSignals(True)
            self._timing_value_spin.setValue(value)
            self._timing_value_spin.blockSignals(spin_blocked)
        else:
            self._timing_stack.setCurrentIndex(0)
            self._timing_value_spin.setRange(1, 999999)
            cycle_value = active_config.get("value", 100)
            cycle_unit = active_config.get("unit", "ms")
            self._set_cycle_parts_from_ms(int(round(cycle_to_interval_ms(cycle_value, cycle_unit))))
        self._update_delay_visuals()

    def _set_timing_mode(self, mode: str):
        normalized_mode = TIMING_MODE_FREQUENCY if str(mode or "").lower() == TIMING_MODE_FREQUENCY else TIMING_MODE_CYCLE
        settings = self.data.setdefault("settings", {})
        normalize_timing_config(settings)
        if hasattr(self, "_timing_cache"):
            self._cache_current_timing_widgets()
        if normalized_mode == TIMING_MODE_FREQUENCY:
            cached = getattr(self, "_timing_cache", {}).get("frequency", settings.get("frequency", {"value": 10, "unit": "CPS"}))
            apply_frequency_timing(settings, cached.get("value", 10), cached.get("unit", "CPS"))
        else:
            cached = getattr(self, "_timing_cache", {}).get("cycle", settings.get("cycle", {"value": 100, "unit": "ms"}))
            apply_cycle_timing(settings, cached.get("value", 100), cached.get("unit", "ms"))
        self._sync_timing_ui()

    def _on_timing_mode_selected(self, mode: str, checked: bool):
        if not checked:
            same_btn = self._frequency_mode_btn if str(mode or "").lower() == TIMING_MODE_FREQUENCY else self._cycle_mode_btn
            same_btn.blockSignals(True)
            same_btn.setChecked(True)
            same_btn.blockSignals(False)
            return
        self._set_timing_mode(mode)
        self._on_settings_changed()

    def _on_timing_value_changed(self):
        self._on_settings_changed()

    def _on_timing_unit_changed(self):
        self._on_settings_changed()

    def _follow_visual_updates_enabled(self):
        if not self._click_target_is_follow():
            return False
        if self._executing and getattr(self, "_hide_marker_on_execute", False):
            return False
        return True

    def _follow_mouse_tick(self):
        x, y = win32api.GetCursorPos()
        if self.data["position"].get("x") == x and self.data["position"].get("y") == y:
            return
        self._apply_live_position(x, y, persist=False)
        if self._executing:
            self._sync_ui()
            return
        self._sync_follow_mouse_visuals(x, y)

    def _sync_follow_mouse_visuals(self, x: int, y: int):
        if hasattr(self, "_pos_display"):
            self._pos_display.setText(f"{x},  {y}")
            self._pos_display.setStyleSheet(
                "color: rgba(255,255,255,210); font: 8pt 'Times New Roman';"
            )

        overlay = self._get_overlay()
        if not overlay:
            return

        if overlay.markers:
            marker_info = overlay.markers[0]
            marker_widget = marker_info["marker"]
            marker_widget.hide()
            marker_info["x"] = x
            marker_info["y"] = y
            overlay.update_hit_region()

        overlay.show_position_indicator(x, y)

    def _apply_live_position(self, x: int, y: int, persist: bool, mode_override: str | None = None):
        mode = self._normalize_click_target_mode(mode_override or self._read_click_target_mode(self.data.get("settings", {})))
        self.data["position"]["x"] = x
        self.data["position"]["y"] = y
        self._write_position_for_mode(mode, x, y)
        if self._worker:
            self._worker.update_target(x, y)
        overlay = self._get_overlay()
        if overlay and self._executing and not self._hide_marker_on_execute:
            overlay.set_marker_execution_mode(True, keep_visible=True, x=x, y=y)
        if persist:
            self.save()

    def _capture_current_target_position(self, persist: bool):
        """Use the currently active visual target as the execution source of truth."""
        active_mode = self._read_click_target_mode(self.data.get("settings", {}))
        follow_enabled = active_mode == CLICK_TARGET_FOLLOW
        if follow_enabled:
            x, y = win32api.GetCursorPos()
            self._apply_live_position(x, y, persist=persist, mode_override=active_mode)
            return True

        # In fixed-position mode, the saved screen coordinates are the source of truth.
        # Reading marker.x()/y() here can return overlay-local widget coordinates, which
        # makes Execute overwrite a valid registered point until F4 re-registers it again.
        if self._has_position():
            pos = self.data.get("position", {})
            x = int(pos.get("x", 0))
            y = int(pos.get("y", 0))
            self._apply_live_position(x, y, persist=persist, mode_override=active_mode)
            return True

        overlay = self._get_overlay()
        if overlay and overlay.markers:
            marker = overlay.markers[0]["marker"]
            marker_center = marker.rect().center()
            global_center = marker.mapToGlobal(marker_center)
            x = int(global_center.x())
            y = int(global_center.y())
            self._apply_live_position(x, y, persist=persist, mode_override=active_mode)
            return True
        return False

    def _start_button_debounce(self):
        self._button_debounce_until = time.perf_counter() + (self._button_debounce_ms / 1000.0)

    def _button_debounce_active(self):
        return time.perf_counter() < self._button_debounce_until

    def _restore_stop_button_after_debounce(self):
        if self._executing and hasattr(self, "_stop_btn"):
            self._stop_btn.setEnabled(True)

    def _click_effects_allowed_for_delay(self, click_delay_ms: int | float):
        if not self._click_effects_enabled:
            return False
        try:
            trigger_ms = int(ConfigManager.load().get("general", {}).get("Performance_Mode_Trigger_MS", 20))
        except Exception:
            trigger_ms = 20
        trigger_ms = max(0, trigger_ms)
        try:
            click_delay_ms = int(click_delay_ms)
        except Exception:
            click_delay_ms = 0
        return click_delay_ms > trigger_ms

    def _on_worker_click_count(self, x: int, y: int):
        self._execution_click_count += 1

    def _on_worker_click_finished(self, x: int, y: int):
        self._on_worker_click_count(x, y)
        self._finish_click_effect(x, y)

    def _move_click_effect(self, x: int, y: int):
        if not self._click_effects_enabled:
            return
        overlay = self._get_overlay()
        if overlay:
            overlay.move_active_click_effect(x, y)

    def _play_system_sound(self, alias: str, fallback_freq: int):
        try:
            winsound.PlaySound(alias, winsound.SND_ALIAS | winsound.SND_ASYNC)
        except Exception:
            try:
                winsound.MessageBeep()
            except Exception:
                try:
                    winsound.Beep(fallback_freq, 160)
                except Exception:
                    pass

    def _on_keybind(self, action: str):
        if self._failsafe_edit_active:
            return
        if action == "Execute":
            self._on_execute()
        elif action == "Stop":
            self._on_stop()
        elif action == "Register_Click_Position":
            self._register_position()
        elif action == "See_Setup_Info":
            self._toggle_setup_info()

    def _on_execute(self):
        if self._executing or self._failsafe_edit_active:
            return
        if self._button_debounce_active():
            return

        captured = self._capture_current_target_position(persist=False)
        if not captured and not self._has_position():
            self._set_status("⚠️ Register a position first!", "#ff4d4d")
            QtCore.QTimer.singleShot(2500, lambda: self._set_status(""))
            return

        # Flush settings → data → disk (original save)
        self._on_settings_changed()
        self.save()

        # Write to Active folder (atomic, crash-safe)
        ActiveSetupManager.write(self.data.get("name", "setup"), self.data)

        self._executing = True
        self._execution_click_count = 0
        self._execution_estimated_cps = 0.0
        self._native_poll_last_count = None
        self._native_poll_last_time = None
        self._execution_started_at = time.perf_counter()
        self._stop_sound_played = False

        # Hide marker if configured
        cfg = ConfigManager.load()
        self._click_effects_enabled = bool(cfg.get("visual", {}).get("Click_Effects", True))
        self._hide_marker_on_execute = bool(cfg.get("visual", {}).get("Hide_Marker_On_Execute", True))
        self._pending_stop_message = None
        overlay = self._get_overlay()
        if self._hide_marker_on_execute:
            if overlay and overlay.markers:
                overlay.markers[0]["marker"].hide()
                overlay.update_hit_region()
            if overlay:
                overlay.hide_position_indicator()
        elif overlay:
            overlay.set_marker_execution_mode(
                True,
                keep_visible=True,
                x=self.data.get("position", {}).get("x", 0),
                y=self.data.get("position", {}).get("y", 0),
            )

        # Let overlay visibility/mask changes settle before the worker resolves the target HWND.
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.processEvents(QtCore.QEventLoop.AllEvents, 50)
        self._update_follow_mouse_state()

        # Lock settings UI during execution
        self._exec_btn.setEnabled(False)
        self._stop_btn.setEnabled(False)
        self._delay_spin.setEnabled(False)
        if hasattr(self, "_timing_card"):
            self._timing_card.setEnabled(False)
        self._hold_spin.setEnabled(False)
        self._anti_check.setEnabled(False)
        if hasattr(self, "_click_target_card"):
            self._click_target_card.setEnabled(False)
        for widget_name in ("_follow_mode_btn", "_marker_mode_btn", "_pointer_mode_btn"):
            widget = getattr(self, widget_name, None)
            if widget is not None:
                widget.setEnabled(False)
        self._info_btn.setEnabled(False)
        self._repeat_times_check.setEnabled(False)
        self._repeat_timer_check.setEnabled(False)
        self._until_stop_check.setEnabled(False)
        self._repeat_times_edit_btn.setEnabled(False)
        self._repeat_timer_edit_btn.setEnabled(False)
        self._mouse_button_combo.setEnabled(False)
        if hasattr(self, "_failsafe_edit_btn"):
            self._failsafe_edit_btn.setEnabled(False)
        self._start_button_debounce()
        QtCore.QTimer.singleShot(self._button_debounce_ms, self._restore_stop_button_after_debounce)

        try:
            # Read execution params from Active copy (ground truth)
            active = ActiveSetupManager.read(self.data.get("name", "setup")) or self.data
            settings  = active.get("settings", {})
            pos       = active.get("position", {})
            failsafe  = self._sanitize_failsafe(active.get("failsafe", {}))
            repeat_mode = settings.get("repeat_mode", "until_stop")
            repeat_duration_seconds = settings.get("repeat_timer_seconds", 60)
            self._execution_duration_seconds = int(repeat_duration_seconds)
            click_delay_ms = normalize_timing_config(settings).get("click_delay_ms", 100)
            self._click_effects_enabled = self._click_effects_allowed_for_delay(click_delay_ms)
            effective_hold_ms = self._effective_hold_ms(
                click_delay_ms,
                int(settings.get("mouse_hold_ms", cfg.get("starter_values", {}).get("Default_Mouse_Hold_MS", 100))),
            )
            self._click_effect_hold_ms = max(
                0,
                effective_hold_ms,
            )
            mouse_button = (settings.get("mouse_button", "left") or "left").lower()
            click_target_mode = self._read_click_target_mode(settings)
            follow_mouse = bool(click_target_mode == CLICK_TARGET_FOLLOW)
            pointer_mode = bool(click_target_mode == CLICK_TARGET_POINTER)
            click_randomness = read_click_randomness(settings, True)
            if follow_mouse:
                bridge = get_click_engine_bridge()
                if not bridge.available:
                    raise RuntimeError(f"ClickEngine DLL unavailable: {bridge.load_error}")
                try:
                    bridge.stop_clicking()
                except Exception:
                    pass

                if mouse_button != "left":
                    print(f"[SingleMode] Mouse button '{mouse_button}' selected, but native engine currently uses left-click SendInput.")

                print(f"[SingleMode] Native DLL path active: {bridge.dll_path}")
                self._worker = _native_click_controller_type()(
                    delay_us=max(1, int(click_delay_ms)) * 1000,
                    x=int(pos.get("x", 0)),
                    y=int(pos.get("y", 0)),
                    follow_mouse=True,
                    click_randomness=click_randomness,
                    hold_ms=self._click_effect_hold_ms,
                    mouse_button=mouse_button,
                    enable_click_feedback=self._click_effects_enabled,
                    parent=self,
                )
                if self._click_effects_enabled:
                    self._worker.click_started.connect(self._show_click_effect)
                    self._worker.click_progress.connect(self._move_click_effect)
                    self._worker.click_finished.connect(self._on_worker_click_finished)
                else:
                    self._worker.click_finished.connect(self._on_worker_click_count)
            elif pointer_mode:
                bridge = get_click_engine_bridge()
                if not bridge.available:
                    raise RuntimeError(f"ClickEngine DLL unavailable: {bridge.load_error}")
                try:
                    bridge.stop_clicking()
                except Exception:
                    pass

                print("[SingleMode] Native pointer path active.")
                self._worker = _native_click_controller_type()(
                    delay_us=max(1, int(click_delay_ms)) * 1000,
                    x=int(pos.get("x", 0)),
                    y=int(pos.get("y", 0)),
                    follow_mouse=False,
                    click_randomness=click_randomness,
                    hold_ms=self._click_effect_hold_ms,
                    mouse_button=mouse_button,
                    enable_click_feedback=self._click_effects_enabled,
                    parent=self,
                )
                if self._click_effects_enabled:
                    self._worker.click_started.connect(self._show_click_effect)
                    self._worker.click_finished.connect(self._on_worker_click_finished)
                else:
                    self._worker.click_finished.connect(self._on_worker_click_count)
                self._apply_pointer_cursor_lock(int(pos.get("x", 0)), int(pos.get("y", 0)))
            else:
                bridge = get_click_engine_bridge()
                if bridge.available:
                    try:
                        bridge.stop_clicking()
                    except Exception:
                        pass

                print("[SingleMode] Python marker compatibility path active.")
                self._worker = _main_window_module().AutoClickWorker(
                    x=pos.get("x", 0),
                    y=pos.get("y", 0),
                    click_delay_ms=click_delay_ms,
                    hold_ms=effective_hold_ms,
                    click_randomness=click_randomness,
                    use_real_click=False,
                    mouse_button=mouse_button,
                    repeat_mode=repeat_mode,
                    repeat_target=settings.get("repeat_times_target", 100),
                    repeat_duration_seconds=repeat_duration_seconds,
                    overlay_hwnds=self._cached_overlay_hwnds(),
                )
                if self._click_effects_enabled:
                    self._worker.click_started.connect(self._show_click_effect)
                    self._worker.click_finished.connect(self._on_worker_click_finished)
                else:
                    self._worker.click_finished.connect(self._on_worker_click_count)

            self._worker.stopped.connect(self._on_worker_stopped)
            self._set_status("Running", "#8be28b")

            self._ensure_progress_timer()
            self._progress_timer.start()
            self._update_execution_progress()
            if follow_mouse:
                self._start_failsafe_monitor(failsafe)
            else:
                self._stop_failsafe_monitor()
            self._worker.start()
            self._play_system_sound("SystemAsterisk", 980)
        except Exception as exc:
            print(f"[SingleMode] Execute failed: {exc}")
            self._stop_sound_played = True
            self._on_worker_stopped()
            self._set_status(str(exc), "#ff6b6b")
            QtCore.QTimer.singleShot(4000, lambda: self._set_status(""))

    def _on_stop(self, force: bool = False):
        if not self._executing:
            return
        if (not force) and self._button_debounce_active():
            return
        self._start_button_debounce()
        self._stop_btn.setEnabled(False)
        self._set_status("Stopping…", "#ffb86c")
        self._play_system_sound("SystemExclamation", 720)
        self._stop_sound_played = True
        self._stop_failsafe_monitor()
        self._clear_pointer_cursor_lock()
        if self._worker:
            self._worker.stop()
        else:
            self._on_worker_stopped()

    def _on_worker_stopped(self):
        self._executing = False
        self._worker    = None
        self._stop_failsafe_monitor()
        self._clear_pointer_cursor_lock()

        # Remove active file
        ActiveSetupManager.clear(self.data.get("name", "setup"))

        self._exec_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._delay_spin.setEnabled(True)
        if hasattr(self, "_timing_card"):
            self._timing_card.setEnabled(True)
        self._hold_spin.setEnabled(True)
        self._anti_check.setEnabled(True)
        if hasattr(self, "_click_target_card"):
            self._click_target_card.setEnabled(True)
        for widget_name in ("_follow_mode_btn", "_marker_mode_btn", "_pointer_mode_btn"):
            widget = getattr(self, widget_name, None)
            if widget is not None:
                widget.setEnabled(True)
        self._info_btn.setEnabled(True)
        self._repeat_times_check.setEnabled(True)
        self._repeat_timer_check.setEnabled(True)
        self._until_stop_check.setEnabled(True)
        self._repeat_times_edit_btn.setEnabled(True)
        self._repeat_timer_edit_btn.setEnabled(True)
        self._mouse_button_combo.setEnabled(True)
        self._failsafe_edit_btn.setEnabled(True)
        if self._progress_timer:
            self._progress_timer.stop()
        if not self._stop_sound_played:
            self._play_system_sound("SystemExclamation", 720)
        self._execution_started_at = None
        self._execution_duration_seconds = 0
        self._execution_estimated_cps = 0.0
        self._native_poll_last_count = None
        self._native_poll_last_time = None
        self._stop_sound_played = False
        if self._pending_stop_message:
            text, color = self._pending_stop_message
            self._set_status(text, color)
            QtCore.QTimer.singleShot(4000, lambda: self._set_status("") if not self._executing else None)
            self._pending_stop_message = None
        else:
            self._set_status("")

        # Restore marker
        overlay = self._get_overlay()
        if overlay:
            overlay.set_marker_execution_mode(False, keep_visible=False)
            overlay.hide_position_indicator()
        self._update_follow_mouse_state()
        self._sync_ui()

    def closeEvent(self, event):
        if not getattr(self, "_closing", False):
            if not self.prompt_save_before_close():
                event.ignore()
                return
            if self._executing and self._worker:
                self._worker.stop()
                self._worker.wait(600)
            if hasattr(self, "_keybind_listener"):
                self._keybind_listener.stop()
            if self._follow_timer:
                self._follow_timer.stop()
            if self._info_dialog:
                self._info_dialog.close()
            self._stop_failsafe_monitor()
            self._clear_pointer_cursor_lock()
            ActiveSetupManager.clear(self.data.get("name", "setup"))
            super().closeEvent(event)
            return

        overlay = self._get_overlay()
        if overlay:
            overlay.on_marker_moved = None
            overlay.set_marker_execution_mode(False, keep_visible=False)
            if overlay.markers:
                overlay.markers[0]["marker"].hide()
                overlay.update_hit_region()

        super().closeEvent(event)


class SingleMode:
    def __init__(self, main_window):
        self.main_window = main_window

    def start(self):
        path = getattr(self.main_window, "_mode_launch_path", "")
        if not path:
            return None

        from UI.main_window import SingleModeUI

        base_pos = self.main_window.pos()
        offset = base_pos + QtCore.QPoint(int(round(self.main_window.width() * 0.5)) + 10, 0)
        self.main_window.mode_window = SingleModeUI(path, offset, parent=None)

        if getattr(self.main_window, "parent", None):
            self.main_window.parent.show_active_setup()
            self.main_window.mode_window.closed.connect(self.main_window.parent.show_home)

        self.main_window.mode_window.show()
        WindowAnimator.fade_in(self.main_window.mode_window)
        WindowAnimator.slide(
            self.main_window.mode_window,
            offset + QtCore.QPoint(0, 20),
            offset,
        )
        return self.main_window.mode_window

    def stop(self):
        mode_window = getattr(self.main_window, "mode_window", None)
        if mode_window is None:
            return

        from UI.main_window import SingleModeUI

        if isinstance(mode_window, SingleModeUI):
            mode_window.close()

