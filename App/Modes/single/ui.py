from PySide6 import QtWidgets, QtCore, QtGui
import importlib
import time

from Config.Manager import ConfigManager
from Core.timing import (
    TIMING_MODE_CYCLE,
    TIMING_MODE_FREQUENCY,
    normalize_timing_config,
)
from Modes.single.logic import (
    CLICK_TARGET_FOLLOW,
    CLICK_TARGET_MARKER,
    CLICK_TARGET_POINTER,
)
from UI.components.spinbox import HorizontalStepSpinBox


def _main_window_module():
    return importlib.import_module("UI.main_window")


def _failsafe_editor_dialog_type():
    return _main_window_module().ScreenEdgeFailsafeEditorDialog


def read_click_randomness(source, default=True):
    return _main_window_module().read_click_randomness(source, default)


def write_click_randomness(target, value):
    return _main_window_module().write_click_randomness(target, value)


def read_starter_click_randomness(source, default=True):
    return _main_window_module().read_starter_click_randomness(source, default)


def _native_click_controller_type():
    return importlib.import_module("Core.Input").NativeClickController


def _event_global_pos(event):
    if hasattr(event, "globalPosition"):
        return event.globalPosition().toPoint()
    return event.globalPos()


class SingleModeUIMixin:
    def _single_spin_style(self, text_color="white"):
        return f"""
            QSpinBox {{
                color: {text_color};
                background: rgba(0,0,0,92);
                border: none;
                border-radius: 4px;
                font: 8pt 'Times New Roman';
                padding: 3px 5px;
            }}
        """

    def _single_combo_style(self):
        return """
            QComboBox {
                color: white;
                background: rgba(0,0,0,92);
                border: none;
                border-radius: 4px;
                font: 8pt 'Times New Roman';
                padding: 3px 22px 3px 6px;
            }
            QComboBox QAbstractItemView {
                color: white;
                background: rgba(18,10,40,235);
                selection-background-color: rgba(122,0,255,150);
                border: none;
            }
        """

    def _timing_card_style(self):
        return """
            QWidget#timingCard {
                background: rgba(118, 0, 190, 62);
                border: 1px solid rgba(255,255,255,34);
                border-radius: 10px;
            }
        """

    def _timing_mode_button_style(self):
        return """
            QPushButton {
                color: rgba(255,255,255,210);
                background: transparent;
                border: none;
                border-radius: 11px;
                font: bold 9.5pt 'Times New Roman';
                padding: 5px 10px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,12);
            }
            QPushButton:checked {
                color: white;
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(192,78,255,255),
                    stop:1 rgba(124,0,255,235)
                );
                border: 1px solid rgba(255,255,255,95);
            }
            QPushButton:checked:hover {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(206,98,255,255),
                    stop:1 rgba(142,28,255,245)
                );
            }
        """

    def _target_mode_button_style(self):
        return """
            QPushButton {
                color: rgba(255,255,255,210);
                background: transparent;
                border: none;
                border-radius: 10px;
                font: bold 8.6pt 'Times New Roman';
                padding: 5px 8px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,12);
            }
            QPushButton:checked {
                color: white;
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(192,78,255,255),
                    stop:1 rgba(124,0,255,235)
                );
                border: 1px solid rgba(255,255,255,95);
            }
        """

    def _timing_spin_style(self):
        return """
            QSpinBox {
                color: white;
                background: rgba(0,0,0,92);
                border: 1px solid rgba(255,255,255,50);
                border-radius: 8px;
                font: bold 9.5pt 'Times New Roman';
                padding: 2px 26px 2px 8px;
                min-height: 20px;
            }
            QSpinBox:disabled {
                color: rgba(255,255,255,120);
                background: rgba(0,0,0,52);
            }
        """

    def _timing_unit_combo_style(self):
        return """
            QComboBox {
                color: white;
                background: rgba(0,0,0,92);
                border: 1px solid rgba(255,255,255,50);
                border-radius: 8px;
                font: bold 9.5pt 'Times New Roman';
                padding: 4px 22px 4px 8px;
                min-height: 24px;
            }
            QComboBox:hover {
                background: rgba(12,12,12,110);
            }
            QComboBox::drop-down {
                border: none;
                width: 22px;
            }
            QComboBox::down-arrow {
                image: none;
                width: 0;
                height: 0;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 7px solid rgba(255,255,255,210);
                margin-right: 8px;
            }
            QComboBox QAbstractItemView {
                color: white;
                background: rgba(34, 8, 62, 240);
                selection-background-color: rgba(145, 56, 255, 180);
                border: 1px solid rgba(255,255,255,45);
                outline: none;
            }
        """

    def _timing_part_style(self):
        return """
            QSpinBox {
                color: white;
                background: rgba(0,0,0,92);
                border: 1px solid rgba(255,255,255,50);
                border-radius: 7px;
                font: bold 9.5pt 'Times New Roman';
                padding: 2px 14px 2px 6px;
                min-height: 18px;
            }
        """

    def build_ui(self):
        # build_ui is called by BaseSetupUI.__init__ before SingleModeUI.__init__
        # can run _init_data_structure(), so we do it here first.
        cfg = ConfigManager.load()
        starter = cfg.get("starter_values", {})
        default_px = max(0, int(cfg.get("general", {}).get("Default_Screen_Failsafe_PX", 50)))
        self.data.setdefault("position", {"x": 0, "y": 0})
        self.data.setdefault("settings", {})
        settings = self.data["settings"]
        normalize_timing_config(settings, default_interval_ms=max(1, starter.get("Default_Auto_Click_Delay_MS", 100)))
        settings.setdefault("mouse_hold_ms", max(0, starter.get("Default_Mouse_Hold_MS", 100)))
        write_click_randomness(settings, read_click_randomness(settings, read_starter_click_randomness(starter, True)))
        if hasattr(self, "_write_click_target_mode"):
            if "click_target_mode" not in settings:
                self._write_click_target_mode(
                    settings,
                    CLICK_TARGET_FOLLOW if starter.get("Default_Always_Follow_Mouse", False) else CLICK_TARGET_MARKER,
                )
            else:
                self._write_click_target_mode(settings, settings.get("click_target_mode"))
        else:
            settings.setdefault("always_follow_mouse", starter.get("Default_Always_Follow_Mouse", False))
        settings.setdefault("repeat_mode", "until_stop")
        settings.setdefault("repeat_times_target", 100)
        settings.setdefault("repeat_timer_seconds", 60)
        settings.setdefault("input_type", "mouse")
        settings.setdefault("mouse_button", "left")
        settings.setdefault("scroll_direction", "up")
        settings.setdefault("scroll_time_ms", 100)
        settings.setdefault("keyboard_key_name", "")
        settings.setdefault("keyboard_key_vk", 0)
        settings.setdefault("keyboard_uppercase", False)
        self.data["failsafe"] = self._sanitize_failsafe(self.data.get("failsafe", {
            "enabled": True,
            "top_px": default_px,
            "bottom_px": default_px,
            "left_px": default_px,
            "right_px": default_px,
        }))
        self.data["mode"] = "single"

        kb    = cfg.get("keybinds", {})

        lbl   = "color: rgba(255,255,255,200); font: 8pt 'Times New Roman';"
        sub   = "color: rgba(255,255,255,110); font: 8pt 'Times New Roman';"
        spin_style = self._single_spin_style()
        chk_style = """
            QCheckBox { color: rgba(255,255,255,0); }
            QCheckBox::indicator {
                width: 14px; height: 14px;
                border-radius: 3px;
                border: 1px solid rgba(255,255,255,85);
                background: rgba(0,0,0,92);
            }
            QCheckBox::indicator:checked {
                background: #7a00ff;
                border: 1px solid #c18dff;
            }
        """
        text_chk_style = """
            QCheckBox {
                color: rgba(255,255,255,210);
                font: 8pt 'Times New Roman';
                spacing: 6px;
            }
            QCheckBox::indicator {
                width: 14px; height: 14px;
                border-radius: 3px;
                border: 1px solid rgba(255,255,255,85);
                background: rgba(0,0,0,92);
            }
            QCheckBox::indicator:checked {
                background: #7a00ff;
                border: 1px solid #c18dff;
            }
        """

        def divider():
            ln = QtWidgets.QFrame()
            ln.setFrameShape(QtWidgets.QFrame.HLine)
            ln.setStyleSheet("color: rgba(255,255,255,55);")
            ln.setFixedHeight(2)
            return ln

        def vdivider():
            ln = QtWidgets.QFrame()
            ln.setFrameShape(QtWidgets.QFrame.VLine)
            ln.setStyleSheet("color: rgba(255,255,255,60);")
            ln.setFixedWidth(2)
            return ln

        def row(left_widget, right_widget):
            h = QtWidgets.QHBoxLayout()
            h.setSpacing(2)
            if isinstance(left_widget, QtWidgets.QLabel):
                left_widget.setFixedWidth(130)

            h.addWidget(left_widget)
            h.addStretch()
            h.addWidget(right_widget)

            return h

        def compact_row(left_widget, right_widget):
            h = QtWidgets.QHBoxLayout()
            h.setSpacing(4)
            h.addWidget(left_widget)
            h.addWidget(right_widget)
            return h

        def input_row(left_widget, right_widget):
            """Input Type rows: 45% label, 5% gutter, 50% control."""
            h = QtWidgets.QHBoxLayout()
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(0)
            gutter = QtWidgets.QWidget()
            gutter.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
            left_widget.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
            right_widget.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            h.addWidget(left_widget, 45)
            h.addWidget(gutter, 5)
            h.addWidget(right_widget, 50)
            return h

        self._timing_cache = {
            "frequency": dict(settings.get("frequency", {"value": 10, "unit": "CPS"})),
        }

        # ── Position ──────────────────────────────────────────────────
        pos_lbl = QtWidgets.QLabel("Position:")
        pos_lbl.setStyleSheet(lbl)

        self._pos_display = QtWidgets.QLabel("Not Set")
        self._pos_display.setStyleSheet(sub)
        self._pos_display.setFixedWidth(86)
        self._pos_display.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)

        reg_key = kb.get("Register_Click_Position", "F3")

        pos_row = row(pos_lbl, self._pos_display)

        # ── Settings ──────────────────────────────────────────────────
        self._timing_card = QtWidgets.QFrame()
        self._timing_card.setObjectName("timingCard")
        self._timing_card.setStyleSheet(self._timing_card_style())
        self._timing_card.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self._timing_card.setMaximumHeight(72)
        timing_card_layout = QtWidgets.QVBoxLayout(self._timing_card)
        timing_card_layout.setContentsMargins(0, 0, 0, 1)
        timing_card_layout.setSpacing(2)

        timing_mode_row = QtWidgets.QHBoxLayout()
        timing_mode_row.setSpacing(4)
        timing_mode_row.setContentsMargins(0, 0, 0, 1)

        self._cycle_mode_btn = QtWidgets.QPushButton("Cycle")
        self._frequency_mode_btn = QtWidgets.QPushButton("Frequency")
        for btn in (self._cycle_mode_btn, self._frequency_mode_btn):
            btn.setCheckable(True)
            btn.setCursor(QtCore.Qt.PointingHandCursor)
            btn.setStyleSheet(self._timing_mode_button_style())
            timing_mode_row.addWidget(btn, 1)
        self._cycle_mode_btn.clicked.connect(lambda checked: self._on_timing_mode_selected(TIMING_MODE_CYCLE, checked))
        self._frequency_mode_btn.clicked.connect(lambda checked: self._on_timing_mode_selected(TIMING_MODE_FREQUENCY, checked))

        timing_divider = QtWidgets.QFrame()
        timing_divider.setFrameShape(QtWidgets.QFrame.HLine)
        timing_divider.setStyleSheet("color: rgba(255,255,255,55);")
        timing_divider.setFixedHeight(2)

        self._timing_stack = QtWidgets.QStackedWidget()
        self._timing_stack.setStyleSheet("background: transparent;")
        self._timing_stack.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self._timing_stack.setMaximumHeight(42)

        cycle_page = QtWidgets.QWidget()
        cycle_layout = QtWidgets.QHBoxLayout(cycle_page)
        cycle_layout.setContentsMargins(8, 1, 8, 0)
        cycle_layout.setSpacing(4)
        self._cycle_h_spin = HorizontalStepSpinBox()
        self._cycle_m_spin = HorizontalStepSpinBox()
        self._cycle_s_spin = HorizontalStepSpinBox()
        self._cycle_ms_spin = HorizontalStepSpinBox()
        cycle_parts = (
            (self._cycle_h_spin, 0, 999, "Hour"),
            (self._cycle_m_spin, 0, 59, "Min."),
            (self._cycle_s_spin, 0, 59, "Sec."),
            (self._cycle_ms_spin, 0, 999, "Milli Sec."),
        )
        for spin, low, high, label_text in cycle_parts:
            spin.setRange(low, high)
            spin.setMinimumWidth(0)
            spin.setFixedHeight(24)
            spin.setButtonLayout("vertical")
            spin.setStyleSheet(self._timing_part_style())
            spin.valueChanged.connect(self._on_timing_value_changed)
            host = QtWidgets.QWidget()
            host_layout = QtWidgets.QVBoxLayout(host)
            host_layout.setContentsMargins(0, 0, 0, 0)
            host_layout.setSpacing(1)
            host_layout.addWidget(spin)
            part_lbl = QtWidgets.QLabel(label_text)
            part_lbl.setAlignment(QtCore.Qt.AlignCenter)
            part_lbl.setStyleSheet("color: rgba(255,255,255,170); font: 5.6pt 'Times New Roman'; padding-top: 1px;")
            host_layout.addWidget(part_lbl)
            cycle_layout.addWidget(host, 1)

        frequency_page = QtWidgets.QWidget()
        frequency_layout = QtWidgets.QHBoxLayout(frequency_page)
        frequency_layout.setContentsMargins(8, 2, 8, 0)
        frequency_layout.setSpacing(4)

        self._timing_value_spin = HorizontalStepSpinBox()
        self._timing_value_spin.setRange(1, 999999)
        self._timing_value_spin.setMinimumWidth(0)
        self._timing_value_spin.setFixedHeight(24)
        self._timing_value_spin.setStyleSheet(self._timing_spin_style())
        self._timing_value_spin.valueChanged.connect(self._on_timing_value_changed)
        self._delay_spin = self._timing_value_spin

        self._timing_frequency_slash = QtWidgets.QLabel("/")
        self._timing_frequency_slash.setAlignment(QtCore.Qt.AlignCenter)
        self._timing_frequency_slash.setFixedWidth(10)
        self._timing_frequency_slash.setStyleSheet("color: rgba(255,255,255,220); font: 12pt 'Times New Roman';")

        self._timing_unit_combo = QtWidgets.QComboBox()
        self._timing_unit_combo.setMinimumWidth(0)
        self._timing_unit_combo.setFixedHeight(24)
        self._timing_unit_combo.setStyleSheet(self._single_combo_style())
        self._timing_unit_combo.currentIndexChanged.connect(self._on_timing_unit_changed)

        frequency_layout.addWidget(self._timing_value_spin, 1)
        frequency_layout.addWidget(self._timing_frequency_slash)
        frequency_layout.addWidget(self._timing_unit_combo, 1)

        self._timing_stack.addWidget(cycle_page)
        self._timing_stack.addWidget(frequency_page)

        timing_card_layout.addLayout(timing_mode_row)
        timing_card_layout.addWidget(timing_divider)
        timing_card_layout.addWidget(self._timing_stack)

        self._timing_mode_title = QtWidgets.QLabel("Timing Mode")
        self._timing_mode_title.setAlignment(QtCore.Qt.AlignCenter)
        self._timing_mode_title.setStyleSheet("color: rgba(255,255,255,220); font: bold 8pt 'Times New Roman';")

        hold_lbl = QtWidgets.QLabel("Mouse Hold (ms):")
        hold_lbl.setStyleSheet(lbl)

        self._hold_spin = HorizontalStepSpinBox()
        self._hold_spin.setRange(0, 99999)
        self._hold_spin.setValue(max(0, self.data["settings"].get("mouse_hold_ms", starter.get("Default_Mouse_Hold_MS", 100))))
        self._hold_spin.setMinimumWidth(0)
        self._hold_spin.setMaximumWidth(16777215)
        self._hold_spin.setFixedHeight(24)
        self._hold_spin.setStyleSheet(spin_style)
        self._hold_spin.valueChanged.connect(self._on_settings_changed)

        anti_lbl = QtWidgets.QLabel("Click Randomness:")
        anti_lbl.setStyleSheet(lbl)

        self._anti_check = QtWidgets.QCheckBox()
        self._anti_check.setChecked(read_click_randomness(self.data["settings"], True))
        self._anti_check.setStyleSheet(chk_style)
        self._anti_check.stateChanged.connect(self._on_settings_changed)

        input_type_title = QtWidgets.QLabel("Input Type")
        input_type_title.setAlignment(QtCore.Qt.AlignCenter)
        input_type_title.setStyleSheet("color: rgba(255,255,255,220); font: bold 8pt 'Times New Roman';")

        self._input_type_card = QtWidgets.QFrame()
        self._input_type_card.setObjectName("timingCard")
        self._input_type_card.setStyleSheet(self._timing_card_style())
        input_card_layout = QtWidgets.QVBoxLayout(self._input_type_card)
        input_card_layout.setContentsMargins(4, 2, 4, 3)
        input_card_layout.setSpacing(3)
        input_type_row = QtWidgets.QHBoxLayout()
        input_type_row.setSpacing(3)
        self._mouse_input_btn = QtWidgets.QPushButton("Mouse")
        self._scroll_input_btn = QtWidgets.QPushButton("Scroll Wheel")
        self._keyboard_input_btn = QtWidgets.QPushButton("Keyboard")
        for btn in (self._mouse_input_btn, self._scroll_input_btn, self._keyboard_input_btn):
            btn.setCheckable(True)
            btn.setCursor(QtCore.Qt.PointingHandCursor)
            btn.setFixedHeight(22)
            btn.setStyleSheet(self._target_mode_button_style())
            input_type_row.addWidget(btn, 1)
            btn.clicked.connect(self._on_input_type_changed)
        input_card_layout.addLayout(input_type_row)
        input_divider = QtWidgets.QFrame()
        input_divider.setFrameShape(QtWidgets.QFrame.HLine)
        input_divider.setStyleSheet("color: rgba(255,255,255,55);")
        input_card_layout.addWidget(input_divider)

        self._input_stack = QtWidgets.QStackedWidget()
        self._input_stack.setStyleSheet("background: transparent;")
        self._input_stack.setMinimumHeight(62)

        mouse_page = QtWidgets.QWidget()
        mouse_layout = QtWidgets.QVBoxLayout(mouse_page)
        mouse_layout.setContentsMargins(4, 0, 4, 0)
        mouse_layout.setSpacing(2)
        mouse_button_lbl = QtWidgets.QLabel("Mouse Button")
        mouse_button_lbl.setStyleSheet(lbl)
        self._mouse_button_combo = QtWidgets.QComboBox()
        for label, value in (("Left", "left"), ("Right", "right"), ("Middle", "middle"), ("M4", "x1"), ("M5", "x2")):
            self._mouse_button_combo.addItem(label, value)
        self._mouse_button_combo.setFixedHeight(24)
        self._mouse_button_combo.setStyleSheet(self._single_combo_style())
        self._mouse_button_combo.currentIndexChanged.connect(self._on_settings_changed)
        mouse_button_row = input_row(mouse_button_lbl, self._mouse_button_combo)
        mouse_layout.addLayout(mouse_button_row)
        mouse_layout.addLayout(input_row(hold_lbl, self._hold_spin))
        mouse_layout.addLayout(input_row(anti_lbl, self._anti_check))

        scroll_page = QtWidgets.QWidget()
        scroll_layout = QtWidgets.QVBoxLayout(scroll_page)
        scroll_layout.setContentsMargins(4, 2, 4, 2)
        scroll_layout.setSpacing(2)
        scroll_label = QtWidgets.QLabel("Input Direction")
        scroll_label.setStyleSheet(lbl)
        self._scroll_direction_combo = QtWidgets.QComboBox()
        for label, value in (("Up", "up"), ("Down", "down"), ("Left", "left"), ("Right", "right")):
            self._scroll_direction_combo.addItem(label, value)
        self._scroll_direction_combo.setFixedHeight(24)
        self._scroll_direction_combo.setStyleSheet(self._single_combo_style())
        self._scroll_direction_combo.currentIndexChanged.connect(self._on_settings_changed)
        scroll_layout.addLayout(input_row(scroll_label, self._scroll_direction_combo))
        scroll_time_label = QtWidgets.QLabel("Scroll Time (ms)")
        scroll_time_label.setStyleSheet(lbl)
        self._scroll_time_spin = HorizontalStepSpinBox()
        self._scroll_time_spin.setRange(0, 99999)
        self._scroll_time_spin.setValue(max(0, int(settings.get("scroll_time_ms", 100))))
        self._scroll_time_spin.setFixedHeight(24)
        self._scroll_time_spin.setStyleSheet(spin_style)
        self._scroll_time_spin.valueChanged.connect(self._on_settings_changed)
        scroll_layout.addLayout(input_row(scroll_time_label, self._scroll_time_spin))

        keyboard_page = QtWidgets.QWidget()
        keyboard_layout = QtWidgets.QVBoxLayout(keyboard_page)
        keyboard_layout.setContentsMargins(4, 2, 4, 2)
        keyboard_layout.setSpacing(2)
        key_row = QtWidgets.QHBoxLayout()
        key_row.setContentsMargins(0, 0, 0, 0)
        key_row.setSpacing(0)
        key_label = QtWidgets.QLabel("Key:")
        key_label.setStyleSheet(lbl)
        self._record_key_btn = QtWidgets.QPushButton("Record Key")
        self._record_key_btn.setFixedHeight(24)
        self._record_key_btn.setStyleSheet("""
            QPushButton {
                color: white;
                background: rgba(0, 0, 0, 153);
                border: 1px solid rgba(255,255,255,45);
                border-radius: 6px;
                font: 8pt 'Times New Roman';
                padding: 3px 8px;
            }
            QPushButton:hover { background: rgba(55, 25, 90, 190); }
        """)
        self._record_key_btn.clicked.connect(self._record_single_key)
        self._uppercase_check = QtWidgets.QCheckBox("Uppercase")
        self._uppercase_check.setStyleSheet(text_chk_style)
        self._uppercase_check.stateChanged.connect(self._on_settings_changed)
        key_gutter = QtWidgets.QWidget()
        key_gutter.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        key_row.addWidget(key_label, 45)
        key_row.addWidget(key_gutter, 5)
        key_row.addWidget(self._record_key_btn, 50)
        keyboard_layout.addLayout(key_row)
        keyboard_layout.addWidget(self._uppercase_check)

        for page in (mouse_page, scroll_page, keyboard_page):
            self._input_stack.addWidget(page)
        input_card_layout.addWidget(self._input_stack)

        self._click_target_card = QtWidgets.QFrame()
        self._click_target_card.setObjectName("timingCard")
        self._click_target_card.setStyleSheet(self._timing_card_style())
        self._click_target_card.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self._click_target_card.setFixedHeight(84)
        click_target_layout = QtWidgets.QVBoxLayout(self._click_target_card)
        click_target_layout.setContentsMargins(0, 0, 0, 2)
        click_target_layout.setSpacing(2)

        click_target_mode_row = QtWidgets.QHBoxLayout()
        click_target_mode_row.setSpacing(3)
        click_target_mode_row.setContentsMargins(0, 0, 0, 1)

        self._follow_mode_btn = QtWidgets.QPushButton("Follow")
        self._marker_mode_btn = QtWidgets.QPushButton("Marker")
        self._pointer_mode_btn = QtWidgets.QPushButton("Pointer")
        for btn in (self._follow_mode_btn, self._marker_mode_btn, self._pointer_mode_btn):
            btn.setCheckable(True)
            btn.setCursor(QtCore.Qt.PointingHandCursor)
            btn.setStyleSheet(self._target_mode_button_style())
            click_target_mode_row.addWidget(btn, 1)
        self._follow_mode_btn.clicked.connect(lambda checked: self._on_click_target_selected(CLICK_TARGET_FOLLOW, checked))
        self._marker_mode_btn.clicked.connect(lambda checked: self._on_click_target_selected(CLICK_TARGET_MARKER, checked))
        self._pointer_mode_btn.clicked.connect(lambda checked: self._on_click_target_selected(CLICK_TARGET_POINTER, checked))

        click_target_divider = QtWidgets.QFrame()
        click_target_divider.setFrameShape(QtWidgets.QFrame.HLine)
        click_target_divider.setStyleSheet("color: rgba(255,255,255,55);")
        click_target_divider.setFixedHeight(2)

        self._click_target_info_lbl = QtWidgets.QLabel("")
        self._click_target_info_lbl.setWordWrap(True)
        self._click_target_info_lbl.setTextFormat(QtCore.Qt.RichText)
        self._click_target_info_lbl.setStyleSheet("color: rgba(255,255,255,210); font: 8.2pt 'Times New Roman'; padding: 0px 6px 1px 6px;")
        self._click_target_info_lbl.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop)
        self._click_target_info_lbl.setFixedHeight(44)

        click_target_layout.addLayout(click_target_mode_row)
        click_target_layout.addWidget(click_target_divider)
        click_target_layout.addWidget(self._click_target_info_lbl)

        self._execute_mode_blocker = QtWidgets.QFrame()
        self._execute_mode_blocker.setObjectName("executeModeBlocker")
        self._execute_mode_blocker.setStyleSheet("""
            QFrame#executeModeBlocker {
                background: rgba(0, 0, 0, 128);
                border: 1px solid rgba(255,255,255,35);
                border-radius: 10px;
            }
            QLabel {
                color: rgba(255,255,255,220);
                font: bold 8pt 'Times New Roman';
            }
        """)
        self._execute_mode_blocker.setFixedHeight(84)
        blocker_layout = QtWidgets.QVBoxLayout(self._execute_mode_blocker)
        blocker_label = QtWidgets.QLabel("ONLY FOR MOUSE INPUT")
        blocker_label.setAlignment(QtCore.Qt.AlignCenter)
        blocker_layout.addWidget(blocker_label)
        self._execute_mode_stack = QtWidgets.QStackedWidget()
        self._execute_mode_stack.setFixedHeight(84)
        self._execute_mode_stack.addWidget(self._click_target_card)
        self._execute_mode_stack.addWidget(self._execute_mode_blocker)
        self._execute_mode_stack.setCurrentIndex(0)

        self._execute_mode_title = QtWidgets.QLabel("Execute Mode")
        self._execute_mode_title.setAlignment(QtCore.Qt.AlignCenter)
        self._execute_mode_title.setStyleSheet("color: rgba(255,255,255,220); font: bold 8pt 'Times New Roman';")

        self._repeat_card = QtWidgets.QFrame()
        self._repeat_card.setObjectName("timingCard")
        self._repeat_card.setStyleSheet(self._timing_card_style())
        self._repeat_card.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self._repeat_card.setMaximumHeight(70)
        repeat_card_layout = QtWidgets.QVBoxLayout(self._repeat_card)
        repeat_card_layout.setContentsMargins(0, 0, 0, 1)
        repeat_card_layout.setSpacing(2)

        repeat_mode_row = QtWidgets.QHBoxLayout()
        repeat_mode_row.setSpacing(3)
        repeat_mode_row.setContentsMargins(0, 0, 0, 0)

        self._repeat_times_check = QtWidgets.QPushButton("Target")
        self._repeat_timer_check = QtWidgets.QPushButton("Timer")
        self._until_stop_check = QtWidgets.QPushButton("Until Stop")
        for btn in (self._repeat_times_check, self._repeat_timer_check, self._until_stop_check):
            btn.setCheckable(True)
            btn.setCursor(QtCore.Qt.PointingHandCursor)
            btn.setFixedHeight(22)
            btn.setStyleSheet(self._target_mode_button_style())
            repeat_mode_row.addWidget(btn, 1)
            btn.clicked.connect(self._on_repeat_mode_changed)

        repeat_divider = QtWidgets.QFrame()
        repeat_divider.setFrameShape(QtWidgets.QFrame.HLine)
        repeat_divider.setStyleSheet("color: rgba(255,255,255,55);")
        repeat_divider.setFixedHeight(2)

        self._repeat_value_stack = QtWidgets.QStackedWidget()
        self._repeat_value_stack.setStyleSheet("background: transparent;")
        self._repeat_value_stack.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self._repeat_value_stack.setMaximumHeight(34)

        repeat_target_page = QtWidgets.QWidget()
        repeat_target_layout = QtWidgets.QHBoxLayout(repeat_target_page)
        repeat_target_layout.setContentsMargins(8, 1, 8, 0)
        repeat_target_layout.setSpacing(5)
        self._repeat_target_spin = HorizontalStepSpinBox()
        self._repeat_target_spin.setRange(1, 999999999)
        self._repeat_target_spin.setValue(max(1, int(settings.get("repeat_times_target", 100))))
        self._repeat_target_spin.setFixedHeight(24)
        self._repeat_target_spin.setStyleSheet(self._timing_spin_style())
        self._repeat_target_spin.valueChanged.connect(self._on_repeat_target_changed)
        repeat_target_label = QtWidgets.QLabel("clicks")
        repeat_target_label.setStyleSheet(sub)
        repeat_target_layout.addWidget(self._repeat_target_spin, 1)
        repeat_target_layout.addWidget(repeat_target_label)

        repeat_timer_page = QtWidgets.QWidget()
        repeat_timer_layout = QtWidgets.QHBoxLayout(repeat_timer_page)
        repeat_timer_layout.setContentsMargins(8, 1, 8, 0)
        repeat_timer_layout.setSpacing(4)
        self._repeat_timer_h_spin = HorizontalStepSpinBox()
        self._repeat_timer_m_spin = HorizontalStepSpinBox()
        self._repeat_timer_s_spin = HorizontalStepSpinBox()
        for spin, low, high, label_text in (
            (self._repeat_timer_h_spin, 0, 999, "H"),
            (self._repeat_timer_m_spin, 0, 59, "M"),
            (self._repeat_timer_s_spin, 0, 59, "S"),
        ):
            spin.setRange(low, high)
            spin.setFixedHeight(24)
            spin.setButtonLayout("vertical")
            spin.setStyleSheet(self._timing_part_style())
            spin.valueChanged.connect(self._on_repeat_timer_changed)
            host = QtWidgets.QWidget()
            host_layout = QtWidgets.QVBoxLayout(host)
            host_layout.setContentsMargins(0, 0, 0, 0)
            host_layout.setSpacing(1)
            host_layout.addWidget(spin)
            part_label = QtWidgets.QLabel(label_text)
            part_label.setAlignment(QtCore.Qt.AlignCenter)
            part_label.setStyleSheet("color: rgba(255,255,255,170); font: 5.6pt 'Times New Roman';")
            host_layout.addWidget(part_label)
            repeat_timer_layout.addWidget(host, 1)

        repeat_until_page = QtWidgets.QWidget()
        repeat_until_layout = QtWidgets.QHBoxLayout(repeat_until_page)
        repeat_until_layout.setContentsMargins(8, 1, 8, 0)
        repeat_until_value = QtWidgets.QLabel("Run until Stop is pressed")
        repeat_until_value.setAlignment(QtCore.Qt.AlignCenter)
        repeat_until_value.setStyleSheet(sub)
        repeat_until_layout.addWidget(repeat_until_value)

        self._repeat_value_stack.addWidget(repeat_target_page)
        self._repeat_value_stack.addWidget(repeat_timer_page)
        self._repeat_value_stack.addWidget(repeat_until_page)
        repeat_card_layout.addLayout(repeat_mode_row)
        repeat_card_layout.addWidget(repeat_divider)
        repeat_card_layout.addWidget(self._repeat_value_stack)

        # Compatibility aliases used by execution-state controls.
        self._repeat_times_edit_btn = self._repeat_target_spin
        self._repeat_timer_edit_btn = self._repeat_value_stack

        self._failsafe_edit_btn = QtWidgets.QPushButton("Edit")
        self._failsafe_edit_btn.setFixedHeight(22)
        self._failsafe_edit_btn.setFixedWidth(52)
        self._failsafe_edit_btn.setFont(QtGui.QFont("Times New Roman", 8))
        self._failsafe_edit_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,16);
                color: white;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover { background: rgba(255,255,255,28); }
            QPushButton:disabled {
                background: rgba(255,255,255,10);
                color: rgba(255,255,255,51);
                border: none;
            }
        """)
        self._failsafe_edit_btn.clicked.connect(self._open_failsafe_editor)
        self._failsafe_enabled_check = QtWidgets.QCheckBox()
        self._failsafe_enabled_check.setStyleSheet(chk_style)
        self._failsafe_enabled_check.stateChanged.connect(self._on_failsafe_enabled_changed)
        self._failsafe_summary = QtWidgets.QLabel("")
        self._failsafe_summary.setWordWrap(True)
        self._failsafe_summary.setStyleSheet(sub)

        # ── Execute / Stop ────────────────────────────────────────────
        exec_key = kb.get("Execute", "F1")
        stop_key = kb.get("Stop", "F2")

        self._exec_btn = QtWidgets.QPushButton("▶  Execute")
        self._stop_btn = QtWidgets.QPushButton("■  Stop")
        self._info_btn = QtWidgets.QPushButton("i")

        for btn in (self._exec_btn, self._stop_btn, self._info_btn):
            btn.setFixedHeight(24)
            btn.setFont(QtGui.QFont("Times New Roman", 9))

        self._exec_btn.setStyleSheet("""
            QPushButton {
                background: #6200cc; color: white;
                border-radius: 5px;
            }
            QPushButton:hover   { background: #8a1fff; }
            QPushButton:disabled {
                background: rgba(80,0,140,70);
                color: rgba(255,255,255,50);
            }
        """)
        self._stop_btn.setStyleSheet("""
            QPushButton {
                background: rgba(160,25,25,180); color: white;
                border-radius: 5px;
            }
            QPushButton:hover   { background: rgba(210,40,40,210); }
            QPushButton:disabled {
                background: rgba(80,10,10,70);
                color: rgba(255,255,255,50);
            }
        """)
        self._info_btn.setFixedWidth(28)
        self._info_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,22); color: white;
                border-radius: 5px;
                border: none;
                font: bold 10pt 'Times New Roman';
            }
            QPushButton:hover { background: rgba(255,255,255,36); }
            QPushButton:disabled {
                background: rgba(255,255,255,10);
                color: rgba(255,255,255,60);
                border-color: transparent;
            }
        """)

        self._exec_btn.clicked.connect(self._on_execute)
        self._stop_btn.clicked.connect(self._on_stop)
        self._info_btn.clicked.connect(self._toggle_setup_info)
        self._stop_btn.setEnabled(False)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.setSpacing(6)
        btn_row.addWidget(self._exec_btn)
        btn_row.addWidget(self._stop_btn)
        btn_row.addWidget(self._info_btn)

        # ── Status label ──────────────────────────────────────────────
        self._status_lbl = QtWidgets.QLabel("")
        self._status_lbl.setAlignment(QtCore.Qt.AlignCenter)
        self._status_lbl.setStyleSheet("color: rgba(255,255,255,150); font: 7.4pt 'Times New Roman';")
        self._status_lbl.setFixedHeight(12)

        # ── Keybind hints (upper execute button) ──────────────────────────────
        self._hint_lbl = QtWidgets.QLabel(self._format_hint_text(kb))
        self._hint_lbl.setAlignment(QtCore.Qt.AlignCenter)
        self._hint_lbl.setStyleSheet(
            "color: rgba(255,255,255,180); font: italic 7.5pt 'Times New Roman';"
        )
        self._hint_lbl.setFixedHeight(30)

        left_col = QtWidgets.QVBoxLayout()
        left_col.setSpacing(0)

        left_col.setSpacing(1)
        left_col.setContentsMargins(0, 1, 0, 1)

        left_col.addSpacing(1)
        left_col.addLayout(pos_row)
        left_col.addSpacing(1)
        left_col.addWidget(divider())
        left_col.addSpacing(1)
        left_col.addWidget(self._timing_mode_title)
        left_col.addSpacing(1)
        left_col.addWidget(self._timing_card)
        left_col.addSpacing(3)
        left_col.addWidget(divider())
        left_col.addSpacing(1)
        left_col.addWidget(self._execute_mode_title)
        left_col.addSpacing(1)
<<<<<<< HEAD
<<<<<<< HEAD
        left_col.addWidget(self._click_target_card)
        left_col.addSpacing(1)
        left_col.addLayout(row(anti_lbl, self._anti_check))
=======
        left_col.addWidget(self._execute_mode_stack)
>>>>>>> main
=======
        left_col.addWidget(self._execute_mode_stack)
>>>>>>> main
        left_col.addStretch()

        failsafe_lbl = QtWidgets.QLabel("Screen Edge Failsafe:")
        failsafe_lbl.setStyleSheet(lbl)

        failsafe_row = QtWidgets.QHBoxLayout()
        failsafe_row.setContentsMargins(0, 0, 0, 0)
        failsafe_row.addWidget(self._failsafe_enabled_check)
        failsafe_row.addWidget(failsafe_lbl)
        failsafe_row.addStretch()
        failsafe_row.addWidget(self._failsafe_edit_btn)

        right_col = QtWidgets.QVBoxLayout()
        right_col.setSpacing(0)

        right_col.setSpacing(1)
        right_col.setContentsMargins(0, 1, 0, 1)

        right_col.addSpacing(1)
        repeat_title = QtWidgets.QLabel("Repeat Mode")
        repeat_title.setAlignment(QtCore.Qt.AlignCenter)
        repeat_title.setStyleSheet("color: rgba(255,255,255,220); font: bold 8pt 'Times New Roman';")
        right_col.addWidget(repeat_title)
        right_col.addSpacing(1)
        right_col.addWidget(self._repeat_card)
        right_col.addSpacing(2)
        right_col.addWidget(divider())
        right_col.addSpacing(2)
        right_col.addLayout(failsafe_row)
        right_col.addWidget(self._failsafe_summary)
        right_col.addSpacing(2)
        right_col.addWidget(divider())
        right_col.addSpacing(2)
<<<<<<< HEAD
<<<<<<< HEAD
        right_col.addLayout(row(mouse_button_lbl, self._mouse_button_combo))
        right_col.addSpacing(1)
        right_col.addLayout(row(hold_lbl, self._hold_spin))    
=======
        right_col.addWidget(input_type_title)
        right_col.addWidget(self._input_type_card)
>>>>>>> main
=======
        right_col.addWidget(input_type_title)
        right_col.addWidget(self._input_type_card)
>>>>>>> main
        right_col.addStretch()

        split_row = QtWidgets.QHBoxLayout()
        split_row.setSpacing(10)
        split_row.addLayout(left_col, 6)
        split_row.addWidget(vdivider())
        split_row.addLayout(right_col, 5)

        self.content.addLayout(split_row)
        self.content.addSpacing(5)
        self.content.addWidget(divider())
        self.content.addSpacing(4)
        self.content.addWidget(self._hint_lbl)
        self.content.addSpacing(6)
        self.content.addLayout(btn_row)
        self.content.addSpacing(4)
        self.content.addWidget(self._status_lbl)
        self._sync_timing_ui()

    def _sync_ui(self):
        """Push data → widgets and update marker visibility."""
        if not hasattr(self, "_pos_display"):
            return

        cfg = ConfigManager.load()
        pos  = self.data.get("position", {})
        x, y = pos.get("x", 0), pos.get("y", 0)

        normalize_timing_config(self.data["settings"], default_interval_ms=max(1, cfg.get("starter_values", {}).get("Default_Auto_Click_Delay_MS", 100)))
        if hasattr(self, "_timing_cache"):
            self._timing_cache["frequency"] = dict(self.data["settings"].get("frequency", self._timing_cache.get("frequency", {"value": 10, "unit": "CPS"})))
        if hasattr(self, "_delay_spin"):
            self._sync_timing_ui()
        if hasattr(self, "_hold_spin"):
            blocked = self._hold_spin.blockSignals(True)
            self._hold_spin.setValue(max(0, self.data["settings"].get("mouse_hold_ms", cfg.get("starter_values", {}).get("Default_Mouse_Hold_MS", 100))))
            self._hold_spin.blockSignals(blocked)
        if hasattr(self, "_anti_check"):
            blocked = self._anti_check.blockSignals(True)
            self._anti_check.setChecked(read_click_randomness(self.data["settings"], True))
            self._anti_check.blockSignals(blocked)
        if hasattr(self, "_input_stack"):
            input_type = str(self.data["settings"].get("input_type", "mouse") or "mouse").lower()
            input_type = input_type if input_type in ("mouse", "scroll", "keyboard") else "mouse"
            input_index = {"mouse": 0, "scroll": 1, "keyboard": 2}[input_type]
            self._input_stack.setCurrentIndex(input_index)
            for button, value in ((self._mouse_input_btn, "mouse"), (self._scroll_input_btn, "scroll"), (self._keyboard_input_btn, "keyboard")):
                blocked = button.blockSignals(True)
                button.setChecked(input_type == value)
                button.blockSignals(blocked)
            idx = self._scroll_direction_combo.findData(self.data["settings"].get("scroll_direction", "up"))
            blocked = self._scroll_direction_combo.blockSignals(True)
            self._scroll_direction_combo.setCurrentIndex(max(0, idx))
            self._scroll_direction_combo.blockSignals(blocked)
            blocked = self._uppercase_check.blockSignals(True)
            self._uppercase_check.setChecked(bool(self.data["settings"].get("keyboard_uppercase", False)))
            self._uppercase_check.blockSignals(blocked)
            blocked = self._scroll_time_spin.blockSignals(True)
            self._scroll_time_spin.setValue(max(0, int(self.data["settings"].get("scroll_time_ms", 100))))
            self._scroll_time_spin.blockSignals(blocked)
            key_name = self.data["settings"].get("keyboard_key_name", "") or "Record Key"
            uppercase = bool(self.data["settings"].get("keyboard_uppercase", False))
            self._record_key_btn.setText(key_name.upper() if uppercase else key_name.lower())
            mouse_input = input_type == "mouse"
            self._execute_mode_stack.setCurrentIndex(0 if mouse_input else 1)
        if hasattr(self, "_sync_click_target_mode_ui"):
            self._sync_click_target_mode_ui()
            self._last_follow_mouse_mode = None
            self._update_click_mode_warning()
        if hasattr(self, "_mouse_button_combo"):
            button_value = self.data["settings"].get("mouse_button", "left")
            idx = self._mouse_button_combo.findData(button_value)
            blocked = self._mouse_button_combo.blockSignals(True)
            self._mouse_button_combo.setCurrentIndex(0 if idx < 0 else idx)
            self._mouse_button_combo.blockSignals(blocked)
        self._sync_repeat_mode_widgets()
        self.data["failsafe"] = self._sanitize_failsafe(self.data.get("failsafe", {}))
        if hasattr(self, "_failsafe_enabled_check"):
            blocked = self._failsafe_enabled_check.blockSignals(True)
            self._failsafe_enabled_check.setChecked(bool(self.data["failsafe"].get("enabled", True)))
            self._failsafe_enabled_check.blockSignals(blocked)
        if hasattr(self, "_failsafe_summary"):
            self._failsafe_summary.setText(self._failsafe_summary_text())
        if hasattr(self, "_failsafe_edit_btn"):
            self._failsafe_edit_btn.setEnabled((not self._executing) and bool(self.data["failsafe"].get("enabled", True)))

        if self._has_position():
            self._pos_display.setText(f"{x},  {y}")
            self._pos_display.setStyleSheet(
                "color: rgba(255,255,255,210); font: 8pt 'Times New Roman';"
            )
        else:
            self._pos_display.setText("Not Set")
            self._pos_display.setStyleSheet(
                "color: rgba(255,255,255,110); font: 8pt 'Times New Roman';"
            )

        click_target_mode = self._read_click_target_mode(self.data["settings"]) if hasattr(self, "_read_click_target_mode") else (CLICK_TARGET_FOLLOW if self.data["settings"].get("always_follow_mouse", False) else CLICK_TARGET_MARKER)
        follow_enabled = click_target_mode == CLICK_TARGET_FOLLOW
        input_type = str(self.data["settings"].get("input_type", "mouse") or "mouse").lower()
        scroll_input = input_type == "scroll"
        keyboard_input = input_type == "keyboard"

        # Marker: visible only when position is set, not executing, and not in passive follow mode.
        overlay = self._get_overlay()
        if overlay and overlay.markers:
            marker_info   = overlay.markers[0]
            marker_widget = marker_info["marker"]

<<<<<<< HEAD
            if keyboard_input:
                marker_widget.hide()
                overlay.update_hit_region()
                overlay.hide_position_indicator()
            elif scroll_input:
=======
            if keyboard_input or scroll_input:
>>>>>>> main
                marker_info["x"] = x
                marker_info["y"] = y
                marker_widget.set_interactive(False)
                marker_widget.set_execution_visual(False)
                marker_widget.hide()
                overlay.update_hit_region()
<<<<<<< HEAD
                # Reuse Mouse Follow's separate, click-through indicator.
=======
                # Use the same click-through follow indicator as other non-mouse inputs.
>>>>>>> main
                overlay.show_position_indicator(x, y)
            elif self._has_position() and not self._executing and not follow_enabled:
                marker_widget.move(x - marker_widget.radius,
                                   y - marker_widget.radius)
                marker_info["x"] = x
                marker_info["y"] = y
                marker_widget.set_interactive(True)
                marker_widget.set_execution_visual(False)
                overlay.update_hit_region()
                marker_widget.show()
            else:
                marker_widget.hide()
                overlay.update_hit_region()

        show_position_indicator = not cfg.get("visual", {}).get("Hide_Marker_On_Execute", True)

        if overlay and not keyboard_input and not scroll_input:
            show_mouse_indicator = self._has_position() and (
                follow_enabled if not self._executing else show_position_indicator
            )
            if show_mouse_indicator:
                overlay.show_position_indicator(x, y)
            else:
                overlay.hide_position_indicator()

        self._update_follow_mouse_state()

    def _update_delay_visuals(self):
        if not hasattr(self, "_timing_value_spin"):
            return

        fast_delay_warning_threshold_ms = 10
        delay_value = max(1, int(self.data["settings"].get("click_delay_ms", 100)))
        follow_mouse = bool(hasattr(self, "_selected_click_target_mode") and self._selected_click_target_mode() == CLICK_TARGET_FOLLOW)
        mode = str(self.data["settings"].get("click_mode", TIMING_MODE_CYCLE) or TIMING_MODE_CYCLE).lower()
        highlight = (
            "rgba(255,255,255,200)"
            if follow_mouse or delay_value >= fast_delay_warning_threshold_ms
            else "rgba(255,216,77,210)"
        )
        label_color = "rgba(255,255,255,200)" if mode == TIMING_MODE_FREQUENCY else highlight

        if hasattr(self, "_delay_lbl"):
            self._delay_lbl.setStyleSheet(f"color: {label_color}; font: 8pt 'Times New Roman';")

        self._timing_value_spin.setStyleSheet(self._timing_spin_style())

    def _on_input_type_changed(self, *_args):
        sender = self.sender()
        input_type = "mouse"
        if sender == self._scroll_input_btn:
            input_type = "scroll"
        elif sender == self._keyboard_input_btn:
            input_type = "keyboard"
        self.data["settings"]["input_type"] = input_type
        self._sync_ui()

    def _record_single_key(self):
        settings = self.data["settings"]
        dialog = _main_window_module().KeybindCaptureDialog(
            settings.get("keyboard_key_name", ""),
            self,
            single_key_only=True,
        )
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            settings["keyboard_key_name"] = dialog.binding_text().lower()
            settings["keyboard_key_vk"] = int(dialog.captured_vk or 0)
            self._sync_ui()
            self._on_settings_changed()

    def _set_status(self, text, color="rgba(255,255,255,130)"):
        if hasattr(self, "_status_lbl"):
            self._status_lbl.setStyleSheet(
                f"color: {color}; font: 7pt 'Times New Roman';"
            )
            self._status_lbl.setText(text)

    def _failsafe_edit_widgets(self):
        widgets = [
            getattr(self, name, None)
            for name in (
                "_delay_spin",
                "_timing_unit_combo",
                "_cycle_mode_btn",
                "_frequency_mode_btn",
                "_hold_spin",
                "_anti_check",
                "_follow_mode_btn",
                "_marker_mode_btn",
                "_pointer_mode_btn",
                "_repeat_times_check",
                "_repeat_timer_check",
                "_until_stop_check",
                "_repeat_times_edit_btn",
                "_repeat_timer_edit_btn",
                "_mouse_button_combo",
                "_mouse_input_btn",
                "_scroll_input_btn",
                "_keyboard_input_btn",
                "_scroll_direction_combo",
                "_scroll_time_spin",
                "_record_key_btn",
                "_uppercase_check",
                "_info_btn",
                "file_btn",
                "min_btn",
                "close_btn",
            )
        ]
        return [widget for widget in widgets if widget is not None]

    def _set_failsafe_edit_mode(self, active: bool):
        self._failsafe_edit_active = bool(active)
        self._exec_btn.setEnabled(False if active else (not self._executing))
        self._stop_btn.setEnabled(False if active else self._executing)
        self._failsafe_edit_btn.setEnabled((not self._executing) and (not active) and bool(self.data.get("failsafe", {}).get("enabled", True)))
        for widget in self._failsafe_edit_widgets():
            widget.setEnabled(not active)

    def _open_failsafe_editor(self):
        if self._executing or (not bool(self.data.get("failsafe", {}).get("enabled", True))):
            return
        self._set_failsafe_edit_mode(True)
        self._set_status("Editing Edge Failsafe.\nBlocked until done for safety.", "#8ecbff")
        dialog = _failsafe_editor_dialog_type()(
            self._primary_screen_geometry(),
            self._sanitize_failsafe(self.data.get("failsafe", {})),
            self._default_failsafe_px(),
            highlight_edge=self._last_failsafe_trigger_edge,
            parent=None,
        )
        try:
            if dialog.exec() == QtWidgets.QDialog.Accepted:
                self.data["failsafe"] = self._sanitize_failsafe(dialog.values())
                self._sync_ui()
                self._set_status("Failsafe updated for this session", "#8ecbff")
            else:
                self._set_status("")
        finally:
            self._set_failsafe_edit_mode(False)

    def _sync_repeat_mode_widgets(self):
        settings = self.data.get("settings", {})
        mode = settings.get("repeat_mode", "until_stop")
        times_target = max(1, int(settings.get("repeat_times_target", 100)))
        timer_seconds = max(1, int(settings.get("repeat_timer_seconds", 60)))
        settings["repeat_times_target"] = times_target
        settings["repeat_timer_seconds"] = timer_seconds
        settings["repeat_mode"] = mode

        for widget, checked in (
            (self._repeat_times_check, mode == "repeat_times"),
            (self._repeat_timer_check, mode == "repeat_timer"),
            (self._until_stop_check, mode == "until_stop"),
        ):
            blocked = widget.blockSignals(True)
            widget.setChecked(checked)
            widget.blockSignals(blocked)

        page_index = {
            "repeat_times": 0,
            "repeat_timer": 1,
            "until_stop": 2,
        }.get(mode, 2)
        self._repeat_value_stack.setCurrentIndex(page_index)

        blocked = self._repeat_target_spin.blockSignals(True)
        self._repeat_target_spin.setValue(times_target)
        self._repeat_target_spin.blockSignals(blocked)

        hours = timer_seconds // 3600
        minutes = (timer_seconds % 3600) // 60
        seconds = timer_seconds % 60
        for spin, value in (
            (self._repeat_timer_h_spin, hours),
            (self._repeat_timer_m_spin, minutes),
            (self._repeat_timer_s_spin, seconds),
        ):
            blocked = spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(blocked)

        enabled = not self._executing
        self._repeat_target_spin.setEnabled(enabled)
        self._repeat_value_stack.setEnabled(enabled)

    def _prompt_edit_dialog(self, title: str, body: str, editor: QtWidgets.QWidget, getter):
        self._play_system_sound("SystemQuestion", 760)
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setModal(True)
        dialog.setWindowFlags(
            QtCore.Qt.Dialog |
            QtCore.Qt.FramelessWindowHint |
            QtCore.Qt.WindowStaysOnTopHint
        )
        dialog.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        dialog.resize(260, 120)

        layout = QtWidgets.QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)

        frame = QtWidgets.QFrame(dialog)
        frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0f0c29, stop:0.45 #400071, stop:1 #24243e);
                border: none;
                border-radius: 8px;
            }
            QLabel { color: white; }
        """)
        layout.addWidget(frame)

        frame_layout = QtWidgets.QVBoxLayout(frame)
        frame_layout.setContentsMargins(14, 12, 14, 12)
        frame_layout.setSpacing(8)

        title_lbl = QtWidgets.QLabel(title)
        title_lbl.setAlignment(QtCore.Qt.AlignCenter)
        title_lbl.setStyleSheet("font: 10pt 'Times New Roman'; color: rgba(255,255,255,220);")
        frame_layout.addWidget(title_lbl)

        body_lbl = QtWidgets.QLabel(body)
        body_lbl.setAlignment(QtCore.Qt.AlignCenter)
        body_lbl.setStyleSheet("font: 8pt 'Times New Roman'; color: rgba(255,255,255,150);")
        frame_layout.addWidget(body_lbl)
        editor.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        editor_host = editor
        if isinstance(editor, (QtWidgets.QSpinBox, QtWidgets.QTimeEdit)):
            prev_btn = QtWidgets.QPushButton("-" if isinstance(editor, QtWidgets.QSpinBox) else "<")
            next_btn = QtWidgets.QPushButton("+" if isinstance(editor, QtWidgets.QSpinBox) else ">")
            for btn in (prev_btn, next_btn):
                btn.setFixedSize(28, 24)
                btn.setStyleSheet("""
                    QPushButton {
                        background: rgba(255,255,255,16);
                        color: white;
                        border: none;
                        border-radius: 4px;
                        font: bold 10pt 'Times New Roman';
                    }
                    QPushButton:hover { background: rgba(255,255,255,28); }
                """)
            prev_btn.clicked.connect(lambda: editor.stepBy(-1))
            next_btn.clicked.connect(lambda: editor.stepBy(1))
            host = QtWidgets.QWidget()
            host_layout = QtWidgets.QHBoxLayout(host)
            host_layout.setContentsMargins(0, 0, 0, 0)
            host_layout.setSpacing(6)
            host_layout.addWidget(prev_btn)
            host_layout.addWidget(editor, 1)
            host_layout.addWidget(next_btn)
            editor_host = host
        frame_layout.addWidget(editor_host)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()
        ok_btn = QtWidgets.QPushButton("OK")
        cancel_btn = QtWidgets.QPushButton("Cancel")
        for btn in (ok_btn, cancel_btn):
            btn.setFixedSize(64, 24)
            btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255,255,255,16);
                    color: white;
                    border: none;
                    border-radius: 4px;
                }
                QPushButton:hover { background: rgba(255,255,255,28); }
            """)
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        frame_layout.addLayout(btn_row)

        if dialog.exec() == QtWidgets.QDialog.Accepted:
            return getter()
        return None

    def _update_execution_progress(self):
        if not self._executing:
            return
        settings = self.data.get("settings", {})
        mode = settings.get("repeat_mode", "until_stop")
        native_active = isinstance(self._worker, _native_click_controller_type())
        elapsed_seconds = 0.0
        if self._execution_started_at is not None:
            elapsed_seconds = max(0.0, time.perf_counter() - self._execution_started_at)

        if native_active:
            try:
                native_count = int(self._worker.click_count())
                now = time.perf_counter()
                if self._native_poll_last_count is None or self._native_poll_last_time is None or native_count < self._native_poll_last_count:
                    self._native_poll_last_count = native_count
                    self._native_poll_last_time = now
                    self._execution_estimated_cps = 0.0
                else:
                    delta_count = native_count - self._native_poll_last_count
                    delta_time = max(0.0001, now - self._native_poll_last_time)
                    instant_cps = float(delta_count) / delta_time
                    if self._execution_estimated_cps <= 0.0:
                        self._execution_estimated_cps = instant_cps
                    else:
                        self._execution_estimated_cps = (self._execution_estimated_cps * 0.65) + (instant_cps * 0.35)
                    self._native_poll_last_count = native_count
                    self._native_poll_last_time = now
                self._execution_click_count = native_count
            except Exception:
                pass
            if mode == "repeat_times":
                target = max(1, int(settings.get("repeat_times_target", 1)))
                self._set_status(
                    f"{min(self._execution_click_count, target)} / {target} • ~{self._execution_estimated_cps:.1f} CPS",
                    "#50fa7b",
                )
                if self._execution_click_count >= target:
                    QtCore.QTimer.singleShot(0, self._on_stop)
            elif mode == "repeat_timer":
                total = max(1, int(self._execution_duration_seconds))
                elapsed = int(elapsed_seconds)
                self._set_status(
                    f"{self._format_repeat_time(min(elapsed, total))} / {self._format_repeat_time(total)} • ~{self._execution_estimated_cps:.1f} CPS",
                    "#50fa7b",
                )
                if elapsed >= total:
                    QtCore.QTimer.singleShot(0, self._on_stop)
            else:
                self._set_status(
                    f"Running • {self._execution_click_count} clicks • ~{self._execution_estimated_cps:.1f} CPS",
                    "#50fa7b",
                )
            return

        if mode == "repeat_times":
            target = max(1, int(settings.get("repeat_times_target", 1)))
            self._set_status(f"{self._execution_click_count} / {target}", "#50fa7b")
        elif mode == "repeat_timer":
            elapsed = int(elapsed_seconds)
            total = max(1, int(self._execution_duration_seconds))
            self._set_status(f"{self._format_repeat_time(min(elapsed, total))} / {self._format_repeat_time(total)}", "#50fa7b")
            if elapsed >= total:
                QtCore.QTimer.singleShot(0, self._on_stop)
        else:
            self._set_status(f"Running • {self._execution_click_count} clicks", "#50fa7b")

    def _update_follow_mouse_state(self):
        if not hasattr(self, "_follow_mode_btn"):
            return
        self._ensure_follow_timer()
        if self._follow_visual_updates_enabled():
            self._follow_timer.setInterval(self._follow_timer_interval_ms())
            self._follow_timer.start()
        else:
            self._follow_timer.stop()

    def _update_click_mode_warning(self):
        if not hasattr(self, "_click_target_info_lbl"):
            return

        settings = self.data.get("settings", {})
        delay_value = max(1, int(normalize_timing_config(settings).get("click_delay_ms", 100)))
        click_target_mode = self._selected_click_target_mode() if hasattr(self, "_selected_click_target_mode") else self._read_click_target_mode(settings)
        follow_mouse = click_target_mode == CLICK_TARGET_FOLLOW
        fast_delay_warning_threshold_ms = 10
        mode = str(settings.get("click_mode", TIMING_MODE_CYCLE) or TIMING_MODE_CYCLE).lower()

        info_map = {
            CLICK_TARGET_FOLLOW: "Real input click on your cursor.<br><span style=\"color: rgba(120,255,170,225);\">Note: Supports up to 1000 CPS (At max performance).</span>",
            CLICK_TARGET_MARKER: "Clicks on a draggable marker using Python input.",
            CLICK_TARGET_POINTER: "Locks the cursor to the marker on execution.",
        }
        if follow_mouse:
            warning = ""
        elif click_target_mode == CLICK_TARGET_POINTER:
            warning = "Note: Cursor lock while running. Hit stop keybind to unlock."
        elif delay_value < fast_delay_warning_threshold_ms:
            warning = "Warning: This mode may not be accurate at high speeds due to OS input limits."
        elif mode == TIMING_MODE_FREQUENCY:
            warning = "Note: Follow and Pointer modes are more stable for high CPS."
        else:
            warning = "Note: Click rate will soften at very high speed. <br>Note2: Some app can't detect clicks due to non-native input."

        parts = [f"<span style=\"color: rgba(255,255,255,210); font-size: 8pt;\">{info_map.get(click_target_mode, '')}</span>"]
        if warning:
            color = "rgba(255,110,110,225)" if warning.startswith("Warning:") else "rgba(255,220,150,210)"
            parts.append(f"<span style=\"color: {color}; font-size: 6.6pt;\">{warning}</span>")
        message = "<br>".join(part for part in parts if part)
        self._click_target_info_lbl.setText(message)
        self._click_target_info_lbl.setVisible(bool(message))
        if hasattr(self, "_mode_warning_lbl"):
            self._mode_warning_lbl.clear()
            self._mode_warning_lbl.setVisible(False)

    def _show_click_effect(self, x: int, y: int):
        if not self._click_effects_enabled:
            return
        overlay = self._get_overlay()
        if overlay:
            overlay.show_click_effect(x, y)

    def _finish_click_effect(self, x: int, y: int):
        if not self._click_effects_enabled:
            return
        overlay = self._get_overlay()
        if overlay:
            overlay.release_click_effect(x, y)

    def _selected_click_target_mode(self):
        if hasattr(self, "_follow_mode_btn") and self._follow_mode_btn.isChecked():
            return CLICK_TARGET_FOLLOW
        if hasattr(self, "_pointer_mode_btn") and self._pointer_mode_btn.isChecked():
            return CLICK_TARGET_POINTER
        return CLICK_TARGET_MARKER

    def _sync_click_target_mode_ui(self):
        if not hasattr(self, "_follow_mode_btn"):
            return
        mode = self._read_click_target_mode(self.data.get("settings", {}))
        mapping = {
            CLICK_TARGET_FOLLOW: self._follow_mode_btn,
            CLICK_TARGET_MARKER: self._marker_mode_btn,
            CLICK_TARGET_POINTER: self._pointer_mode_btn,
        }
        for key, button in mapping.items():
            blocked = button.blockSignals(True)
            button.setChecked(key == mode)
            button.blockSignals(blocked)
    def _on_click_target_selected(self, mode: str, checked: bool):
        button_map = {
            CLICK_TARGET_FOLLOW: getattr(self, "_follow_mode_btn", None),
            CLICK_TARGET_MARKER: getattr(self, "_marker_mode_btn", None),
            CLICK_TARGET_POINTER: getattr(self, "_pointer_mode_btn", None),
        }
        if not checked:
            current = button_map.get(mode)
            if current is not None:
                blocked = current.blockSignals(True)
                current.setChecked(True)
                current.blockSignals(blocked)
            return
        previous_mode = self._read_click_target_mode(self.data.setdefault("settings", {})) if hasattr(self, "_read_click_target_mode") else CLICK_TARGET_MARKER
        if hasattr(self, "_write_click_target_mode"):
            if hasattr(self, "_load_position_for_mode") and previous_mode != mode:
                self._load_position_for_mode(previous_mode, persist=False)
            self._write_click_target_mode(self.data.setdefault("settings", {}), mode)
            if hasattr(self, "_load_position_for_mode"):
                self._load_position_for_mode(mode, persist=False)
        self._sync_click_target_mode_ui()
        self._sync_ui()
        self._on_settings_changed()

    def _setup_info_text(self):
       return (
            "<b>Tips:</b>\n"
            "If a game hides your cursor, bugs, or feels inconsistent,\n"
            "Try Follow for live cursor syncing when you need the real pointer path on screen.\n"
            "This restores cursor feedback & reduces misclick frustration.\n\n"

            "<b>Position:</b>\n"
            "Use Register Position or drag the marker when Marker or Pointer is active.\n"
            "Marker and Pointer both use a fixed saved position instead of your live cursor.\n\n"

            "<b>Execution Behavior:</b>\n"
            "Marker uses simulated Python clicks, while Pointer uses the native click engine at the marked point.\n"
            "Pointer also locks the cursor to that marked spot until Stop is pressed.\n"
            "Some apps or games may detect cursor position differently.\n"
            "You may need to manually tune delay or hold values for accuracy.\n\n"

            "<b>Click Randomness:</b>\n"
            "This adds slight variation to timing and positioning.\n"
            "Clicks may become slightly less precise or slightly delayed.\n"
            "This helps reduce perfectly consistent patterns that some systems may flag.\n\n"

            "<b>Cursor & Game Issues:</b>\n"
            "Some games hide or lock the cursor, causing desync with marker clicks.\n"
            "UI scaling, effects, or camera movement may shift click alignment.\n"
            "Detection systems may ignore artificial input.\n\n"

            "<b>If you experience:</b> Missed clicks, Offset positions, Inconsistent behavior\n"
            "Try switching between Follow, Marker, and Pointer based on how the target app handles input.\n\n"

            "<b>Usage Mindset:</b>\n"
            "Explore the settings and adjust based on your use case.\n"
            "Different apps behave differently, so fine-tuning is expected.\n"
            "Use common sense when configuring delays, positions, and modes.\n\n"

            "<b>Notes:</b>\n"
            "Stop can interrupt execution at any time.\n"
            "Follow is the live cursor mode, Marker is the compatibility fixed-target mode, and Pointer is the native fixed-target mode."
        )

    def _create_setup_info_dialog(self):
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Single Mode Info")
        dialog.setModal(False)
        dialog.setWindowFlags(
            QtCore.Qt.Dialog |
            QtCore.Qt.FramelessWindowHint |
            QtCore.Qt.WindowStaysOnTopHint
        )
        dialog.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        dialog.resize(500, 280)

        root = QtWidgets.QVBoxLayout(dialog)
        root.setContentsMargins(0, 0, 0, 0)

        frame = QtWidgets.QFrame(dialog)
        frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0f0c29, stop:0.45 #400071, stop:1 #24243e);
                border: none;
                border-radius: 8px;
            }
            QLabel { color: white; }
        """)
        root.addWidget(frame)

        layout = QtWidgets.QVBoxLayout(frame)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        title = QtWidgets.QLabel("Single Mode Info")
        title.setAlignment(QtCore.Qt.AlignCenter)
        title.setStyleSheet("font: bold 10pt 'Times New Roman'; color: rgba(255,255,255,220);")
        layout.addWidget(title)

        dialog._drag_pos = None

        def dialog_mouse_press(event):
            if event.button() == QtCore.Qt.LeftButton and event.pos().y() <= 44:
                dialog._drag_pos = _event_global_pos(event)
                event.accept()
                return
            QtWidgets.QDialog.mousePressEvent(dialog, event)

        def dialog_mouse_move(event):
            if event.buttons() == QtCore.Qt.LeftButton and dialog._drag_pos is not None:
                dialog.move(dialog.pos() + _event_global_pos(event) - dialog._drag_pos)
                dialog._drag_pos = _event_global_pos(event)
                event.accept()
                return
            QtWidgets.QDialog.mouseMoveEvent(dialog, event)

        def dialog_mouse_release(event):
            dialog._drag_pos = None
            QtWidgets.QDialog.mouseReleaseEvent(dialog, event)

        dialog.mousePressEvent = dialog_mouse_press
        dialog.mouseMoveEvent = dialog_mouse_move
        dialog.mouseReleaseEvent = dialog_mouse_release

        info_text = self._setup_info_text()
        if "<" in info_text and ">" in info_text:
            info_text = info_text.replace("\n", "<br>")
        body = QtWidgets.QLabel(info_text)
        body.setTextFormat(QtCore.Qt.RichText)
        body.setWordWrap(True)
        body.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft)
        body.setStyleSheet("font: 9pt 'Times New Roman'; color: rgba(255,255,255,185);")
        layout.addWidget(body, 1)

        close_btn = QtWidgets.QPushButton("Close")
        close_btn.setFixedSize(72, 24)
        close_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,16);
                color: white;
                border: none;
                border-radius: 4px;
                font: 9pt 'Times New Roman';
            }
            QPushButton:hover { background: rgba(255,255,255,28); }
        """)
        close_btn.clicked.connect(dialog.close)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        return dialog

    def _toggle_setup_info(self):
        if self._info_dialog and self._info_dialog.isVisible():
            self._info_dialog.close()
            return

        if self._info_dialog is None:
            self._info_dialog = self._create_setup_info_dialog()

        self._play_system_sound("SystemQuestion", 760)
        self._info_dialog.move(self.frameGeometry().topRight() + QtCore.QPoint(10, 0))
        self._info_dialog.show()
        self._info_dialog.raise_()
        self._info_dialog.activateWindow()
