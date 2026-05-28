import subprocess, sys
import os
from pathlib import Path
from PySide6.QtGui import QDesktopServices
import json
import ctypes
from ctypes import wintypes
import random
import time
import copy
import re
import winsound
import queue
from PySide6 import QtWidgets, QtCore, QtGui
import sys
import win32gui, win32con, win32api
import threading
import pyautogui
from Config.Manager import AppConfig, ConfigManager, SettingDisplay
from Core.Input import NativeClickController, get_click_engine_bridge
from Core.Setup import SetupManager, ActiveSetupManager
from Core.Updater_Module import UpdateCheckWorker, UpdateDownloadWorker, parse_numeric_version_text
from Core.Utils import ASSETS_DIR, BASE_DIR
from UI.components.animations import WindowAnimator
from UI.components.spinbox import HorizontalStepSpinBox
from Modes._SharedUtils.Worker_helper import SharedWorkerHelper

pyautogui.PAUSE = 0
pyautogui.FAILSAFE = False


def _event_global_pos(event):
    if hasattr(event, "globalPosition"):
        return event.globalPosition().toPoint()
    return event.globalPos()


def _input_host_widget(widget):
    current = widget
    while isinstance(current, QtWidgets.QWidget):
        if isinstance(current, (QtWidgets.QLineEdit, QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit, QtWidgets.QAbstractSpinBox, QtWidgets.QComboBox)):
            return current
        current = current.parentWidget()
    return None


def _clear_input_visual_state(widget):
    host = _input_host_widget(widget)
    if host is None:
        return
    if isinstance(host, QtWidgets.QLineEdit):
        host.deselect()
        return
    if isinstance(host, QtWidgets.QAbstractSpinBox):
        editor = host.lineEdit()
        if editor is not None:
            editor.deselect()
        return
    if isinstance(host, QtWidgets.QComboBox):
        if host.isEditable() and host.lineEdit() is not None:
            host.lineEdit().deselect()
        return
    if isinstance(host, (QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit)):
        cursor = host.textCursor()
        if cursor.hasSelection():
            cursor.clearSelection()
            host.setTextCursor(cursor)
        host.viewport().update()


class _AppInputFocusManager(QtCore.QObject):
    def __init__(self, app):
        super().__init__(app)
        self._app = app
        self._app.installEventFilter(self)
        self._app.focusChanged.connect(self._on_focus_changed)

    def _on_focus_changed(self, old, _new):
        if old is not None:
            _clear_input_visual_state(old)

    def eventFilter(self, obj, event):
        if event.type() != QtCore.QEvent.MouseButtonPress:
            return False
        focus_widget = self._app.focusWidget()
        if focus_widget is None or _input_host_widget(focus_widget) is None:
            return False
        clicked_widget = obj if isinstance(obj, QtWidgets.QWidget) else None
        if clicked_widget is None:
            try:
                clicked_widget = self._app.widgetAt(_event_global_pos(event))
            except Exception:
                clicked_widget = None
        if _input_host_widget(clicked_widget) is not None:
            return False
        _clear_input_visual_state(focus_widget)
        focus_widget.clearFocus()
        return False


_APP_INPUT_FOCUS_MANAGER = None


def ensure_app_input_focus_manager():
    global _APP_INPUT_FOCUS_MANAGER
    app = QtWidgets.QApplication.instance()
    if app is None:
        return
    if _APP_INPUT_FOCUS_MANAGER is None:
        _APP_INPUT_FOCUS_MANAGER = _AppInputFocusManager(app)


def _strip_native_window_frame(hwnd):
    try:
        style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
        style &= ~(
            win32con.WS_CAPTION
            | win32con.WS_THICKFRAME
            | win32con.WS_BORDER
            | win32con.WS_DLGFRAME
        )
        style |= win32con.WS_POPUP
        win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)
        win32gui.SetWindowPos(
            hwnd,
            0,
            0,
            0,
            0,
            0,
            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE | win32con.SWP_FRAMECHANGED,
        )
    except Exception:
        pass


def _suppress_native_window_chrome(hwnd):
    _strip_native_window_frame(hwnd)
    try:
        ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        ex_style |= win32con.WS_EX_TOOLWINDOW | win32con.WS_EX_LAYERED | win32con.WS_EX_NOACTIVATE
        win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex_style)
    except Exception:
        pass
    try:
        DWMWA_NCRENDERING_ENABLED = 1
        DWMWA_NCRENDERING_POLICY = 2
        DWMWA_TRANSITIONS_FORCEDISABLED = 3
        DWMWA_WINDOW_CORNER_PREFERENCE = 33
        DWMNCRP_DISABLED = 1
        DWMWCP_DONOTROUND = 1
        DWMWA_BORDER_COLOR = 34
        DWM_COLOR_NONE = 0xFFFFFFFE
        disabled = ctypes.c_int(0)
        policy = ctypes.c_int(DWMNCRP_DISABLED)
        force_disabled = ctypes.c_int(1)
        corner_preference = ctypes.c_int(DWMWCP_DONOTROUND)
        none_color = ctypes.c_int(DWM_COLOR_NONE)
        dwmapi = ctypes.windll.dwmapi
        dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_NCRENDERING_ENABLED, ctypes.byref(disabled), ctypes.sizeof(disabled))
        dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_NCRENDERING_POLICY, ctypes.byref(policy), ctypes.sizeof(policy))
        dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_TRANSITIONS_FORCEDISABLED, ctypes.byref(force_disabled), ctypes.sizeof(force_disabled))
        dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, ctypes.byref(corner_preference), ctypes.sizeof(corner_preference))
        dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_BORDER_COLOR, ctypes.byref(none_color), ctypes.sizeof(none_color))
    except Exception:
        pass


def _make_passive_overlay_window(widget):
    try:
        hwnd = int(widget.winId())
        _suppress_native_window_chrome(hwnd)
        ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        ex_style |= (
            win32con.WS_EX_TOOLWINDOW
            | win32con.WS_EX_LAYERED
            | win32con.WS_EX_NOACTIVATE
            | win32con.WS_EX_TRANSPARENT
        )
        win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex_style)
        win32gui.SetWindowPos(
            hwnd,
            win32con.HWND_TOPMOST,
            0,
            0,
            0,
            0,
            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE | win32con.SWP_FRAMECHANGED,
        )
    except Exception:
        pass


def atomic_json_write(path, data):
    directory = os.path.dirname(path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory)
    tmp = path + ".tmp"
    payload = json.dumps(data, indent=4)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(payload)

    for _ in range(8):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.05)

    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(payload)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


UPDATE_RELEASE_API_URL = AppConfig.UPDATE_RELEASE_API_URL
UPDATE_RELEASE_PAGE_URL = AppConfig.UPDATE_RELEASE_PAGE_URL


def make_noactivate_topmost(widget):
    try:
        hwnd = int(widget.winId())
        _suppress_native_window_chrome(hwnd)
        ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        win32gui.SetWindowLong(
            hwnd,
            win32con.GWL_EXSTYLE,
            ex_style | win32con.WS_EX_TOOLWINDOW | win32con.WS_EX_LAYERED | win32con.WS_EX_NOACTIVATE,
        )
        win32gui.SetWindowPos(
            hwnd,
            win32con.HWND_TOPMOST,
            0,
            0,
            0,
            0,
            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE | win32con.SWP_FRAMECHANGED,
        )
    except Exception:
        pass


myappid = f"XPR.{AppConfig.APP_FULL}"  # 🔥 unique ID
ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)


def qt_key_to_binding_name(key: int):
    if QtCore.Qt.Key_A <= key <= QtCore.Qt.Key_Z:
        return chr(key)
    if QtCore.Qt.Key_0 <= key <= QtCore.Qt.Key_9:
        return chr(key)

    key_map = {
        QtCore.Qt.Key_F1: "F1",
        QtCore.Qt.Key_F2: "F2",
        QtCore.Qt.Key_F3: "F3",
        QtCore.Qt.Key_F4: "F4",
        QtCore.Qt.Key_F5: "F5",
        QtCore.Qt.Key_F6: "F6",
        QtCore.Qt.Key_F7: "F7",
        QtCore.Qt.Key_F8: "F8",
        QtCore.Qt.Key_F9: "F9",
        QtCore.Qt.Key_F10: "F10",
        QtCore.Qt.Key_F11: "F11",
        QtCore.Qt.Key_F12: "F12",
        QtCore.Qt.Key_Delete: "DELETE",
        QtCore.Qt.Key_Insert: "INSERT",
        QtCore.Qt.Key_Home: "HOME",
        QtCore.Qt.Key_End: "END",
        QtCore.Qt.Key_PageUp: "PAGEUP",
        QtCore.Qt.Key_PageDown: "PAGEDOWN",
        QtCore.Qt.Key_Space: "SPACE",
        QtCore.Qt.Key_Tab: "TAB",
        QtCore.Qt.Key_Return: "ENTER",
        QtCore.Qt.Key_Enter: "ENTER",
        QtCore.Qt.Key_Escape: "ESC",
        QtCore.Qt.Key_Up: "UP",
        QtCore.Qt.Key_Down: "DOWN",
        QtCore.Qt.Key_Left: "LEFT",
        QtCore.Qt.Key_Right: "RIGHT",
        QtCore.Qt.Key_QuoteLeft: "`",
        QtCore.Qt.Key_Minus: "-",
        QtCore.Qt.Key_Equal: "=",
        QtCore.Qt.Key_BracketLeft: "[",
        QtCore.Qt.Key_BracketRight: "]",
        QtCore.Qt.Key_Backslash: "\\",
        QtCore.Qt.Key_Semicolon: ";",
        QtCore.Qt.Key_Apostrophe: "'",
        QtCore.Qt.Key_Comma: ",",
        QtCore.Qt.Key_Period: ".",
        QtCore.Qt.Key_Slash: "/",
        QtCore.Qt.Key_Plus: "PLUS",
        QtCore.Qt.Key_Asterisk: "ASTERISK",
    }
    return key_map.get(key)


def split_keybind(binding_text: str):
    parts = [part.strip().upper() for part in str(binding_text).split("+") if part.strip()]
    modifiers = [part for part in parts if part in ("CTRL", "ALT", "SHIFT")]
    main_key = next((part for part in reversed(parts) if part not in ("CTRL", "ALT", "SHIFT")), "")
    return modifiers, main_key


CLICK_RANDOMNESS_KEY = "click_randomness"
LEGACY_CLICK_RANDOMNESS_KEY = "anti_detection"
STARTER_CLICK_RANDOMNESS_KEY = ConfigManager.STARTER_CLICK_RANDOMNESS_KEY
LEGACY_STARTER_CLICK_RANDOMNESS_KEY = ConfigManager.LEGACY_STARTER_CLICK_RANDOMNESS_KEY
MOUSE_BEHAVIOR_KEY = "mouse_behavior"
MOUSE_BEHAVIOR_DEFAULT = "default"
MOUSE_BEHAVIOR_TELEPORT = "teleport"
MOUSE_BEHAVIOR_PYTHON = "python"


def read_click_randomness(source, default=True):
    if not isinstance(source, dict):
        return bool(default)
    if CLICK_RANDOMNESS_KEY in source:
        return bool(source.get(CLICK_RANDOMNESS_KEY, default))
    if LEGACY_CLICK_RANDOMNESS_KEY in source:
        return bool(source.get(LEGACY_CLICK_RANDOMNESS_KEY, default))
    return bool(default)


def write_click_randomness(target, value):
    if not isinstance(target, dict):
        return
    target[CLICK_RANDOMNESS_KEY] = bool(value)
    target.pop(LEGACY_CLICK_RANDOMNESS_KEY, None)


def read_mouse_behavior(source, default=MOUSE_BEHAVIOR_DEFAULT):
    if not isinstance(source, dict):
        return default
    value = str(source.get(MOUSE_BEHAVIOR_KEY, "") or "").strip().lower()
    if value == "background":
        value = MOUSE_BEHAVIOR_PYTHON
    if value in (MOUSE_BEHAVIOR_DEFAULT, MOUSE_BEHAVIOR_TELEPORT, MOUSE_BEHAVIOR_PYTHON):
        return value
    if "teleport_mouse" in source:
        return MOUSE_BEHAVIOR_TELEPORT if bool(source.get("teleport_mouse", False)) else MOUSE_BEHAVIOR_PYTHON
    return default


def read_starter_click_randomness(source, default=True):
    if not isinstance(source, dict):
        return bool(default)
    if STARTER_CLICK_RANDOMNESS_KEY in source:
        return bool(source.get(STARTER_CLICK_RANDOMNESS_KEY, default))
    if LEGACY_STARTER_CLICK_RANDOMNESS_KEY in source:
        return bool(source.get(LEGACY_STARTER_CLICK_RANDOMNESS_KEY, default))
    return bool(default)


class KeybindCaptureDialog(QtWidgets.QDialog):
    def __init__(self, current_binding="", parent=None):
        super().__init__(parent)
        self._captured = current_binding or ""

        self.setWindowTitle("Edit Keybind")
        self.setModal(True)
        self.setWindowFlags(
            QtCore.Qt.Dialog |
            QtCore.Qt.FramelessWindowHint |
            QtCore.Qt.NoDropShadowWindowHint |
            QtCore.Qt.WindowStaysOnTopHint
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.resize(320, 170)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        frame = QtWidgets.QFrame(self)
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

        title = QtWidgets.QLabel("Listening for keybind input")
        title.setAlignment(QtCore.Qt.AlignCenter)
        title.setStyleSheet("font: 10pt 'Times New Roman'; color: rgba(255,255,255,220);")
        layout.addWidget(title)

        note = QtWidgets.QLabel("Hold Ctrl / Alt / Shift if needed, then press any key.")
        note.setAlignment(QtCore.Qt.AlignCenter)
        note.setWordWrap(True)
        note.setStyleSheet("font: 8pt 'Times New Roman'; color: rgba(255,255,255,150);")
        layout.addWidget(note)

        self._value_label = QtWidgets.QLabel("")
        self._value_label.setAlignment(QtCore.Qt.AlignCenter)
        self._value_label.setFixedHeight(28)
        self._value_label.setStyleSheet("font: 10pt 'Consolas'; color: rgba(255,255,255,230); background: rgba(0,0,0,70); border: none; border-radius: 4px;")
        layout.addWidget(self._value_label)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()
        self.retry_btn = QtWidgets.QPushButton("Retry")
        self.confirm_btn = QtWidgets.QPushButton("Confirm")
        self.cancel_btn = QtWidgets.QPushButton("Cancel")
        for btn in (self.retry_btn, self.confirm_btn, self.cancel_btn):
            btn.setFixedSize(68, 24)
            btn.setAutoDefault(False)
            btn.setDefault(False)
            btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255,255,255,16);
                    color: white;
                    border: none;
                    border-radius: 4px;
                }
                QPushButton:hover { background: rgba(255,255,255,28); }
            """)
        self.retry_btn.clicked.connect(self._retry)
        self.confirm_btn.clicked.connect(self._confirm_binding)
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.retry_btn)
        btn_row.addWidget(self.confirm_btn)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self._retry()

    def _retry(self):
        self._captured = ""
        self._value_label.setText("Press a key...")
        self.confirm_btn.setEnabled(True)

    def _confirm_binding(self):
        if not self.confirm_btn.isEnabled() or not self._captured.strip():
            try:
                winsound.MessageBeep()
            except Exception:
                try:
                    winsound.Beep(920, 180)
                except Exception:
                    pass
            self.flash_warning()
            return
        self.accept()

    def keyPressEvent(self, event):
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            self._confirm_binding()
            event.accept()
            return
        if event.key() == QtCore.Qt.Key_Backspace:
            self._retry()
            event.accept()
            return

        key_name = qt_key_to_binding_name(event.key())
        if not key_name:
            event.accept()
            return

        modifiers = []
        mods = event.modifiers()
        if mods & QtCore.Qt.KeypadModifier:
            keypad_map = {
                "0": "NUM0",
                "1": "NUM1",
                "2": "NUM2",
                "3": "NUM3",
                "4": "NUM4",
                "5": "NUM5",
                "6": "NUM6",
                "7": "NUM7",
                "8": "NUM8",
                "9": "NUM9",
                "PLUS": "NUMPLUS",
                "-": "NUMMINUS",
                "ASTERISK": "NUMASTERISK",
                "/": "NUMSLASH",
                ".": "NUMDOT",
                "ENTER": "NUMENTER",
            }
            key_name = keypad_map.get(key_name, key_name)
        if mods & QtCore.Qt.ControlModifier:
            modifiers.append("CTRL")
        if mods & QtCore.Qt.AltModifier:
            modifiers.append("ALT")
        if mods & QtCore.Qt.ShiftModifier:
            modifiers.append("SHIFT")

        self._captured = "+".join(modifiers + [key_name]) if modifiers else key_name
        self._value_label.setText(self._captured)
        event.accept()

    def binding_text(self):
        return self._captured

    def flash_warning(self):
        base_pos = self.pos()
        anim = QtCore.QSequentialAnimationGroup(self)

        for offset in (-8, 8, -6, 6, -3, 3, 0):
            move_anim = QtCore.QPropertyAnimation(self, b"pos")
            move_anim.setDuration(36)
            move_anim.setStartValue(self.pos())
            move_anim.setEndValue(base_pos + QtCore.QPoint(offset, 0))
            anim.addAnimation(move_anim)

        self._warn_anim = anim
        anim.start()
    
class ClickEffect(QtWidgets.QWidget):
    def __init__(self, x, y, size, parent=None):
        super().__init__(parent)
        self._progress = 0.0
        self._pressed = False
        self._size = max(10, int(size))
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        if parent is None:
            flags = (
                QtCore.Qt.Tool |
                QtCore.Qt.FramelessWindowHint |
                QtCore.Qt.BypassWindowManagerHint |
                QtCore.Qt.NoDropShadowWindowHint |
                QtCore.Qt.WindowStaysOnTopHint
            )
            if hasattr(QtCore.Qt, "WindowTransparentForInput"):
                flags |= QtCore.Qt.WindowTransparentForInput
            self.setWindowFlags(flags)
            self.setWindowFlag(QtCore.Qt.WindowDoesNotAcceptFocus)
        self.setGeometry(
            int(x - self._size / 2),
            int(y - self._size / 2),
            self._size,
            self._size,
        )

        self._press_anim = QtCore.QVariantAnimation(self)
        self._press_anim.setDuration(110)
        self._press_anim.setStartValue(0.0)
        self._press_anim.setEndValue(0.5)
        self._press_anim.valueChanged.connect(self._on_value_changed)

        self._release_anim = QtCore.QVariantAnimation(self)
        self._release_anim.setDuration(110)
        self._release_anim.setStartValue(0.5)
        self._release_anim.setEndValue(1.0)
        self._release_anim.valueChanged.connect(self._on_value_changed)
        self._release_anim.finished.connect(self.deleteLater)

        self._cleanup_timer = QtCore.QTimer(self)
        self._cleanup_timer.setSingleShot(True)
        self._cleanup_timer.timeout.connect(self._force_cleanup)

        self._apply_shape()
        self.show()
        self.start_press()

    def move_center(self, x: int, y: int):
        if self.parentWidget() is None:
            _make_passive_overlay_window(self)
        self.move(int(x - self.width() / 2), int(y - self.height() / 2))

    def _apply_shape(self):
        self.setMask(QtGui.QRegion(self.rect(), QtGui.QRegion.Ellipse))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_shape()

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_shape()
        if self.parentWidget() is None:
            _make_passive_overlay_window(self)

    def _on_value_changed(self, value):
        self._progress = float(value)
        self.update()

    def start_press(self):
        self._pressed = True
        self._release_anim.stop()
        self._press_anim.stop()
        self._press_anim.start()
        self._cleanup_timer.start(1800)

    def finish_release(self):
        if not self._pressed:
            return
        self._pressed = False
        self._cleanup_timer.stop()
        current = max(0.5, self._progress)
        self._release_anim.stop()
        self._release_anim.setStartValue(current)
        self._release_anim.start()

    def _force_cleanup(self):
        if self._release_anim.state() == QtCore.QAbstractAnimation.Running:
            return
        if self._pressed:
            self._pressed = False
            current = max(0.5, self._progress)
            self._release_anim.stop()
            self._release_anim.setStartValue(current)
            self._release_anim.start()
        else:
            self.deleteLater()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        outer_margin = 3
        diameter = max(8, int((self.width() - outer_margin * 2) * self._progress))
        x = (self.width() - diameter) // 2
        y = (self.height() - diameter) // 2

        ring_alpha = max(0, int(190 * (1.0 - self._progress)))
        fill_alpha = max(0, int(90 * (1.0 - self._progress)))

        painter.setPen(QtGui.QPen(QtGui.QColor(255, 45, 45, ring_alpha), 3))
        painter.setBrush(QtGui.QColor(255, 45, 45, fill_alpha))
        painter.drawEllipse(x, y, diameter, diameter)


class CursorFollowIndicator(QtWidgets.QWidget):
    def __init__(self, size=40, parent=None):
        super().__init__(parent)
        self._size = max(12, int(size))
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        if parent is None:
            flags = (
                QtCore.Qt.Tool |
                QtCore.Qt.FramelessWindowHint |
                QtCore.Qt.BypassWindowManagerHint |
                QtCore.Qt.NoDropShadowWindowHint |
                QtCore.Qt.WindowStaysOnTopHint
            )
            if hasattr(QtCore.Qt, "WindowTransparentForInput"):
                flags |= QtCore.Qt.WindowTransparentForInput
            self.setWindowFlags(flags)
            self.setWindowFlag(QtCore.Qt.WindowDoesNotAcceptFocus)
        self.resize(self._size, self._size)

    def move_center(self, x, y):
        if self.parentWidget() is None:
            _make_passive_overlay_window(self)
        self.move(int(x - self.width() / 2), int(y - self.height() / 2))
        if not self.isVisible():
            self.show()

    def _apply_shape(self):
        self.setMask(QtGui.QRegion(self.rect(), QtGui.QRegion.Ellipse))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_shape()

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_shape()
        if self.parentWidget() is None:
            _make_passive_overlay_window(self)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = self.rect().adjusted(4, 4, -4, -4)
        painter.setBrush(QtGui.QColor(255, 0, 0, 28))
        painter.setPen(QtGui.QPen(QtGui.QColor(255, 45, 45, 255), 2))
        painter.drawEllipse(rect)


class ExecutionMarkerIndicator(QtWidgets.QWidget):
    def __init__(self, size=40, parent=None):
        super().__init__(parent)
        self._size = max(12, int(size))
        self._label_text = ""
        self._display_mode = "ring"
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        if parent is None:
            flags = (
                QtCore.Qt.Tool |
                QtCore.Qt.FramelessWindowHint |
                QtCore.Qt.BypassWindowManagerHint |
                QtCore.Qt.NoDropShadowWindowHint |
                QtCore.Qt.WindowStaysOnTopHint
            )
            if hasattr(QtCore.Qt, "WindowTransparentForInput"):
                flags |= QtCore.Qt.WindowTransparentForInput
            self.setWindowFlags(flags)
            self.setWindowFlag(QtCore.Qt.WindowDoesNotAcceptFocus)
        self.resize(self._size, self._size)

    def set_base_size(self, size: int):
        self._size = max(12, int(size))
        self.set_label_text(self._label_text)

    def set_display_mode(self, mode: str):
        self._display_mode = mode or "ring"
        self.set_label_text(self._label_text)

    def set_label_text(self, text: str):
        self._label_text = (text or "").strip()
        if self._display_mode == "dot_only":
            dot_size = max(12, min(self._size, 20))
            if dot_size % 2 != 0:
                dot_size += 1
            self.resize(dot_size, dot_size)
        elif self._label_text:
            font = QtGui.QFont("Times New Roman", 8, QtGui.QFont.Bold)
            metrics = QtGui.QFontMetrics(font)
            padding = 12 if self._display_mode == "text_only" else 18
            base_size = self._size if self._display_mode != "text_only" else 12
            diameter = max(base_size, metrics.horizontalAdvance(self._label_text) + padding, metrics.height() + padding)
            if diameter % 2 != 0:
                diameter += 1
            self.resize(diameter, diameter)
        else:
            self.resize(self._size, self._size)
        self._apply_shape()
        self.update()

    def move_center(self, x, y):
        if self.parentWidget() is None:
            _make_passive_overlay_window(self)
        self.move(int(round(x - self.width() / 2.0)), int(round(y - self.height() / 2.0)))
        if not self.isVisible():
            self.show()

    def _apply_shape(self):
        if self._display_mode == "text_only" and self._label_text:
            self.clearMask()
            return
        self.setMask(QtGui.QRegion(self.rect(), QtGui.QRegion.Ellipse))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_shape()

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_shape()
        if self.parentWidget() is None:
            _make_passive_overlay_window(self)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        margin = 4
        diameter = min(self.width(), self.height()) - margin * 2
        ellipse_rect = QtCore.QRect(
            int((self.width() - diameter) / 2),
            int((self.height() - diameter) / 2),
            int(diameter),
            int(diameter),
        )
        if self._display_mode == "dot_only":
            dot_size = max(6, min(diameter, 10))
            dot_rect = QtCore.QRect(
                int((self.width() - dot_size) / 2),
                int((self.height() - dot_size) / 2),
                int(dot_size),
                int(dot_size),
            )
            painter.setBrush(QtGui.QColor(255, 40, 40, 235))
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawEllipse(dot_rect)
            return
        if self._label_text:
            if self._display_mode != "text_only":
                painter.setBrush(QtGui.QColor(255, 40, 40, 20))
                painter.setPen(QtGui.QPen(QtGui.QColor(255, 60, 60, 235), 2))
                painter.drawEllipse(ellipse_rect)
            font = QtGui.QFont("Times New Roman", 8)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 235), 1))
            painter.drawText(self.rect(), QtCore.Qt.AlignCenter, self._label_text)
            return
        painter.setBrush(QtGui.QColor(255, 40, 40, 18))
        painter.setPen(QtGui.QPen(QtGui.QColor(255, 60, 60, 235), 2))
        painter.drawEllipse(ellipse_rect)


def _overlay_window_hwnds():
    app = QtWidgets.QApplication.instance()
    if app is None:
        return set()

    hwnds = set()
    overlay_types = _overlay_widget_types()
    for widget in app.topLevelWidgets():
        if isinstance(widget, overlay_types):
            try:
                hwnds.add(int(widget.winId()))
            except Exception:
                pass
    return hwnds


def app_top_level_windows():
    app = QtWidgets.QApplication.instance()
    if app is None:
        return []

    ignored_types = _overlay_widget_types() + (_file_menu_popup_type(),)
    windows = []
    for widget in app.topLevelWidgets():
        if isinstance(widget, ignored_types):
            continue
        if not isinstance(widget, (QtWidgets.QMainWindow, QtWidgets.QDialog, QtWidgets.QWidget)):
            continue
        parent_obj = getattr(widget, "parent", None)
        if callable(parent_obj):
            parent_obj = parent_obj()
        if parent_obj is not None:
            continue
        windows.append(widget)
    return windows


def _overlay_widget_types():
    from UI.overlay.overlay import Overlay

    return (Overlay, ExecutionMarkerIndicator, ClickEffect, CursorFollowIndicator, SandboxLineOverlay, SandboxHandleWidget)


def _overlay_type():
    from UI.overlay.overlay import Overlay

    return Overlay


def _titlebar_type():
    from UI.components.titlebar import TitleBar

    return TitleBar


def _file_menu_popup_type():
    from UI.components.popup import FileMenuPopup

    return FileMenuPopup


# ---------------- Control Panel ----------------
class ControlPanel(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        ensure_app_input_focus_manager()
        TitleBar = _titlebar_type()
        from UI.overlay.overlay import Overlay

        self.setWindowTitle(f"XPR.{AppConfig.APP_FULL}") 
        self._animating = False
        self.setWindowFlags(
            QtCore.Qt.FramelessWindowHint |
            QtCore.Qt.NoDropShadowWindowHint |
            QtCore.Qt.WindowStaysOnTopHint |
            QtCore.Qt.WindowMinimizeButtonHint
        )

        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self._set_panel_size(580, 360)

        screen = QtWidgets.QApplication.primaryScreen().availableGeometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2

        self.move(x, y)
        self._base_pos = self.pos()  # important for your animations

        central = QtWidgets.QWidget(self)
        central.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setCentralWidget(central)

        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(3)

        # Title bar
        self.title_bar = TitleBar(self)
        layout.addWidget(self.title_bar)

        # -------- STACK SYSTEM --------
        self.stack = QtWidgets.QStackedWidget()
        layout.addWidget(self.stack)

        # Pages
        self.home_page = QtWidgets.QWidget()
        self.credits_page = QtWidgets.QWidget()

        self.stack.addWidget(self.home_page)
        self.stack.addWidget(self.credits_page)

        self.settings_page = QtWidgets.QWidget()
        self.stack.addWidget(self.settings_page)
        self.build_settings_page()

        self.active_setup_page = QtWidgets.QWidget()
        self.stack.addWidget(self.active_setup_page)
        self.build_active_setup_page()

        # Build pages
        self.build_home_page()
        self.build_credits_page()

        # Overlay — marker starts hidden until a position is registered
        self.overlay = Overlay()
        self.overlay.new(500, 300)
        self.overlay.markers[0]["marker"].hide()
        self.overlay.update_hit_region()
        self.overlay.show()

        kb = ConfigManager.load().get("keybinds", {})
        self._app_keybind_listener = KeybindListener(
            {
                "Quick_Save": kb.get("Quick_Save", "F7"),
                "Recover_Window_Position": kb.get("Recover_Window_Position", "F8"),
                "Save_Close_Setup": kb.get("Save_Close_Setup", "F9"),
                "Kill_Switch": kb.get("Kill_Switch", "F10"),
            },
            parent=self,
        )
        self._app_keybind_listener.triggered.connect(self._on_app_keybind)
        self._update_status = {
            "status": "idle",
            "label": "(Latest ver)",
            "latest_version": parse_numeric_version_text(AppConfig.VERSION),
            "release_page_url": UPDATE_RELEASE_PAGE_URL,
            "assets": {},
        }
        self._update_check_thread = None
        self._update_check_worker = None
        self._stale_update_check_threads = []
        self._update_check_timeout_timer = None
        self._update_check_request_id = 0
        self._update_download_thread = None
        self._update_download_worker = None
        self._update_progress_dialog = None
        self._active_update_asset_kind = ""
        self._update_check_started = False

    def _set_panel_size(self, width: int, height: int):
        self.setMinimumSize(width, height)
        self.setMaximumSize(width, height)
        self.resize(width, height)

    def show_with_anim(self):
        sender_win = self.sender()
        if sender_win and hasattr(sender_win, "pos"):
            base = sender_win.pos() - QtCore.QPoint(50, 50)
            self.move(base)

            WindowAnimator.slide(
                self,
                base + QtCore.QPoint(0, 20),
                base
            )

        self.show()
        WindowAnimator.fade_in(self)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._update_check_started:
            self._update_check_started = True
            QtCore.QTimer.singleShot(1200, self._start_update_check)

    def closeEvent(self, event):
        event.ignore()

        if getattr(self, "_closing", False):
            event.accept()
            return

        self._closing = True

        def finish():
            self.overlay.close()
            QtWidgets.QApplication.quit()

        WindowAnimator.fade_out(self, callback=finish)

    def minimize_with_anim(self):
        self._base_pos = self.pos()  # store position

        def do_minimize():
            self.showMinimized()

        # animate BEFORE minimize
        WindowAnimator.slide(
            self,
            self.pos(),
            self.pos() + QtCore.QPoint(0, 20)
        )

        QtCore.QTimer.singleShot(120, do_minimize)

    def changeEvent(self, event):
        if event.type() == QtCore.QEvent.WindowStateChange:
            if self.windowState() & QtCore.Qt.WindowMinimized:
                self._was_minimized = True

            elif getattr(self, "_was_minimized", False):
                self._was_minimized = False

                self.setWindowState(QtCore.Qt.WindowNoState)
                self.show()
                self.raise_()
                self.activateWindow()

                WindowAnimator.restore(self)

        super().changeEvent(event)

    # ---------------- PAINT ----------------
    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        rect = self.rect()

        grad = QtGui.QLinearGradient(0, 0, self.width(), self.height())
        grad.setColorAt(0, QtGui.QColor("#0f0c29"))
        grad.setColorAt(0.45, QtGui.QColor("#400071"))
        grad.setColorAt(1, QtGui.QColor("#24243e"))

        painter.setBrush(grad)
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRoundedRect(rect, 14, 14)

    def close_all(self):
        def finish():
            self.overlay.close()
            QtWidgets.QApplication.quit()

        WindowAnimator.fade_out(self, callback=finish)

    def _on_app_keybind(self, action: str):
        if action == "Quick_Save":
            self._quick_save_active_setup()
        elif action == "Recover_Window_Position":
            self._toggle_minimize_windows()
        elif action == "Save_Close_Setup":
            self._save_and_close_active_setup()
        elif action == "Kill_Switch":
            self._kill_switch()

    def _active_setup_windows(self):
        return [w for w in app_top_level_windows() if isinstance(w, BaseSetupUI)]

    def _quick_save_active_setup(self):
        saved = False
        for window in self._active_setup_windows():
            try:
                window.save()
                saved = True
            except Exception:
                pass
        if saved:
            try:
                winsound.MessageBeep()
            except Exception:
                pass

    def _save_and_close_active_setup(self):
        closed = False
        for window in list(self._active_setup_windows()):
            try:
                window.save()
                if hasattr(window, "_allow_close_without_save"):
                    window._allow_close_without_save = True
                window.close()
                closed = True
            except Exception:
                pass
        if closed:
            try:
                winsound.MessageBeep()
            except Exception:
                pass

    def _recover_window_positions(self):
        screen = QtWidgets.QApplication.primaryScreen()
        if not screen:
            return
        available_rect = screen.availableGeometry()
        windows = [w for w in app_top_level_windows() if w is not self]
        restore_positions = {}

        for window in windows:
            try:
                target_pos = getattr(window, "_base_pos", None)
                if target_pos is None:
                    target_pos = window.pos()
                restore_positions[window] = QtCore.QPoint(target_pos)
            except Exception:
                pass

        # Step 1: force every app window out of minimized state first.
        for window in windows:
            try:
                window.setWindowState(QtCore.Qt.WindowNoState)
                if hasattr(window, "showNormal"):
                    window.showNormal()
                window.show()
                if hasattr(window, "_was_minimized"):
                    window._was_minimized = False
            except Exception:
                pass

        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.processEvents(QtCore.QEventLoop.AllEvents, 100)

        # Step 2: after all windows are restored, recover their positions.
        for window in windows:
            try:
                target_pos = restore_positions.get(window)
                if target_pos is None:
                    target_x = available_rect.center().x() - window.width() // 2
                    target_y = available_rect.center().y() - window.height() // 2
                    target_pos = QtCore.QPoint(target_x, target_y)
                window.move(target_pos)
                if hasattr(window, "_base_pos"):
                    window._base_pos = QtCore.QPoint(target_pos)
                window.raise_()
            except Exception:
                pass

    def _toggle_minimize_windows(self):
        windows = []
        for window in app_top_level_windows():
            # Skip the main window - F8 should never interact with it
            if window is self:
                continue
            try:
                if hasattr(window, "stack") and hasattr(window, "active_setup_page"):
                    if window.stack.currentWidget() is window.active_setup_page:
                        continue
            except Exception:
                pass
            windows.append(window)
        restorable = []
        visible_normal = False

        for window in windows:
            try:
                if window.isMinimized():
                    restorable.append(window)
                else:
                    visible_normal = True
            except Exception:
                continue

        if visible_normal:
            for window in windows:
                try:
                    if hasattr(window, "_was_minimized"):
                        window._was_minimized = True
                    if hasattr(window, "minimize_with_anim"):
                        window.minimize_with_anim()
                    else:
                        window.showMinimized()
                except Exception:
                    continue
            return

        if restorable:
            self._recover_window_positions()

    def _kill_switch(self):
        try:
            self.overlay.close()
        except Exception:
            pass
        os._exit(0)
    
    def moveEvent(self, event):
        self._base_pos = self.pos()
        super().moveEvent(event)

  # ---------------- SETTINGS PAGE ----------------
    def save_settings(self):
        for section_name in ("general", "visual", "starter_values"):
            widgets = getattr(self, f"{section_name}_widgets", {})
            self.config.setdefault(section_name, {})
            for key, widget in widgets.items():
                if isinstance(widget, QtWidgets.QCheckBox):
                    self.config[section_name][key] = widget.isChecked()
                elif isinstance(widget, QtWidgets.QSpinBox):
                    self.config[section_name][key] = widget.value()
                else:
                    self.config[section_name][key] = widget.text()

        # Keybinds
        for key, widget in self.keybind_widgets.items():
            self.config["keybinds"][key] = widget.text()

        ConfigManager.save(self.config)
        for w in QtWidgets.QApplication.instance().topLevelWidgets():
            if hasattr(w, "overlay") and hasattr(w.overlay, "refresh_marker_sizes"):
                try:
                    w.overlay.refresh_marker_sizes()
                except Exception:
                    pass
            if hasattr(w, "_overlay_controller") and hasattr(w, "data") and isinstance(getattr(w, "data", None), dict):
                sandbox = w.data.get("sandbox")
                if sandbox is not None:
                    try:
                        w._overlay_controller.sync(sandbox)
                    except Exception:
                        pass

        # ── Live keybind propagation ──────────────────────────────────
        # Any open setup window gets its listener updated immediately so
        # new bindings work without restarting the program.
        new_kb = self.config.get("keybinds", {})
        for w in QtWidgets.QApplication.instance().topLevelWidgets():
            if hasattr(w, "_keybind_listener") and hasattr(w, "refresh_keybind_hints"):
                relevant = {
                    "Execute":                 new_kb.get("Execute",                 "F1"),
                    "Stop":                    new_kb.get("Stop",                    "F2"),
                    "Register_Click_Position": new_kb.get("Register_Click_Position", "F3"),
                    "See_Setup_Info":          new_kb.get("See_Setup_Info",          "F1"),
                }
                w._keybind_listener.update_keybinds(relevant)
                w.refresh_keybind_hints(new_kb)
            if hasattr(w, "_setup_keybind_listener"):
                setup_relevant = {
                    "Execute": new_kb.get("Execute", "F2"),
                    "Stop": new_kb.get("Stop", "F3"),
                    "Register_Click_Position": new_kb.get("Register_Click_Position", "F4"),
                    "See_Setup_Info": new_kb.get("See_Setup_Info", "F1"),
                    "New_Marker_Sandbox": new_kb.get("New_Marker_Sandbox", "F5"),
                    "New_Keybind_Sandbox": new_kb.get("New_Keybind_Sandbox", "F6"),
                }
                w._setup_keybind_listener.update_keybinds(setup_relevant)
                if hasattr(w, "_refresh_bottom_bar"):
                    try:
                        w._refresh_bottom_bar()
                    except Exception:
                        pass
            if hasattr(w, "_app_keybind_listener"):
                app_relevant = {
                    "Quick_Save": new_kb.get("Quick_Save", "F7"),
                    "Recover_Window_Position": new_kb.get("Recover_Window_Position", "F8"),
                    "Save_Close_Setup": new_kb.get("Save_Close_Setup", "F9"),
                    "Kill_Switch": new_kb.get("Kill_Switch", "F10"),
                }
                w._app_keybind_listener.update_keybinds(app_relevant)


    def show_settings(self):
        center = self.geometry().center()
        self._set_panel_size(580, 460)
        rect = self.geometry()
        rect.moveCenter(center)
        self.move(rect.topLeft())
        self.stack.setCurrentWidget(self.settings_page)


    # ---------------- ROW BUILDER ----------------
    def create_setting_label_block(self, key):
        wrapper = QtWidgets.QWidget()
        wrapper.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)

        layout = QtWidgets.QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        title = QtWidgets.QLabel(SettingDisplay.get(key))
        title.setWordWrap(True)
        title.setStyleSheet("color: rgba(255,255,255,220); font: 11pt 'Times New Roman';")
        layout.addWidget(title)

        description_text = SettingDisplay.description(key)
        if description_text:
            description = QtWidgets.QLabel(description_text)
            description.setWordWrap(True)
            description.setStyleSheet("color: rgba(255,255,255,135); font: 8.5pt 'Times New Roman';")
            layout.addWidget(description)

        return wrapper

    def _settings_spinbox_style(self):
        return """
            QSpinBox {
                color: white;
                background: rgba(0,0,0,92);
                border: none;
                border-radius: 4px;
                font: 8pt 'Times New Roman';
                padding: 3px 5px;
            }
        """

    def _settings_combo_style(self):
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

    def create_setting_row(self, key, value, checkbox_style, store_dict):
        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        # Label (Left)
        label_block = self.create_setting_label_block(key)

        # Widget (Right)
        if isinstance(value, bool):
            widget = QtWidgets.QCheckBox()
            widget.setChecked(value)
            widget.setStyleSheet(checkbox_style)
            widget.setFixedWidth(74)

        elif isinstance(value, int):
            widget = HorizontalStepSpinBox()
            if key == "Marker_Size_Multiplier_Percent":
                widget.setRange(5, 100)
                widget.setSingleStep(5)
                widget.setSuffix("%")
            else:
                widget.setMaximum(999999)
            widget.setValue(value)
            widget.setFixedWidth(84)
            widget.setStyleSheet(self._settings_spinbox_style())
           
        else:
            widget = QtWidgets.QLineEdit(str(value))
            widget.setFixedWidth(84)

        # Store reference
        store_dict[key] = widget

        # Layout
        row.addWidget(label_block, 1)
        row.addWidget(widget)

        return row


    # ---------------- GENERAL ----------------
    def build_settings_category(self, layout, checkbox_style, section_name, store_dict):
        for key, value in self.config.get(section_name, {}).items():
            row = self.create_setting_row(key, value, checkbox_style, store_dict)
            layout.addLayout(row)
            layout.addSpacing(6)

    def build_starter_settings(self, layout, checkbox_style):
        starter = self.config.get("starter_values", {})

        def add_group(title_text, keys):
            title = QtWidgets.QLabel(title_text)
            title.setStyleSheet("color: rgba(255,255,255,220); font: bold 11pt 'Times New Roman';")
            layout.addWidget(title)
            layout.addSpacing(6)
            for key in keys:
                if key not in starter:
                    continue
                row = self.create_setting_row(key, starter.get(key), checkbox_style, self.starter_values_widgets)
                layout.addLayout(row)
                layout.addSpacing(6)
            layout.addSpacing(10)

        add_group(
            "Shared Defaults",
            (
                "Default_Mouse_Hold_MS",
                "Default_Always_Follow_Mouse",
                ConfigManager.STARTER_CLICK_RANDOMNESS_KEY,
                "Default_Screen_Failsafe_PX",
            ),
        )
        add_group(
            "Sandbox Mode",
            (
                "Default_Drag_Duration_MS",
                "Default_Delay_Before_Next_Target_MS",
            ),
        )


    # ---------------- KEYBINDS ----------------
    def build_keybind_settings(self, layout):
        self.keybind_widgets = {}

        for key, value in self.config["keybinds"].items():
            row = QtWidgets.QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)

            label_block = self.create_setting_label_block(key)

            value_label = QtWidgets.QLabel(value)
            value_label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
            value_label.setFixedWidth(92)
            value_label.setStyleSheet("color: rgba(255,255,255,230); font: 9pt 'Consolas';")

            edit_btn = QtWidgets.QPushButton("Edit")
            edit_btn.setFixedSize(52, 24)
            edit_btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255,255,255,16);
                    color: white;
                    border: none;
                    border-radius: 4px;
                    font: 9pt 'Times New Roman';
                }
                QPushButton:hover { background: rgba(255,255,255,28); }
            """)

            def open_editor(_checked=False, key_name=key, display=value_label):
                try:
                    winsound.MessageBeep()
                except Exception:
                    try:
                        winsound.Beep(760, 140)
                    except Exception:
                        pass
                dialog = KeybindCaptureDialog(display.text(), self)
                while True:
                    if dialog.exec() != QtWidgets.QDialog.Accepted:
                        break
                    binding = dialog.binding_text()
                    if not binding:
                        break
                    duplicate = False
                    for other_key, other_widget in self.keybind_widgets.items():
                        if other_key != key_name and other_widget.text().upper() == binding.upper():
                            duplicate = True
                            break
                    if duplicate:
                        try:
                            winsound.MessageBeep()
                        except Exception:
                            try:
                                winsound.Beep(920, 180)
                            except Exception:
                                pass
                        dialog.flash_warning()
                        dialog._retry()
                        continue
                    display.setText(binding)
                    break

            edit_btn.clicked.connect(open_editor)

            self.keybind_widgets[key] = value_label

            row.addWidget(label_block, 1)
            row.addWidget(value_label)
            row.addWidget(edit_btn)

            layout.addLayout(row)
            layout.addSpacing(6)


    # ---------------- MAIN SETTINGS PAGE ----------------
    def build_settings_page(self):
        self.config = ConfigManager.load()
        self.general_widgets = {}
        self.visual_widgets = {}
        self.starter_values_widgets = {}

        main_layout = QtWidgets.QVBoxLayout(self.settings_page)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # ---------------- TOP MENU ----------------
        top_bar = QtWidgets.QHBoxLayout()
        top_bar.setContentsMargins(0, 5, 0, 5)

        top_container = QtWidgets.QHBoxLayout()
        top_container.addStretch()

        self.tab_general = QtWidgets.QPushButton("General")
        self.tab_visual = QtWidgets.QPushButton("Visual")
        self.tab_starter = QtWidgets.QPushButton("Starter Values")
        self.tab_keybind = QtWidgets.QPushButton("Keybind")

        for btn in (self.tab_general, self.tab_visual, self.tab_starter, self.tab_keybind):
            btn.setFixedHeight(30)
            btn.setFixedWidth(120)
            btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255,255,255,25);
                    color: white;
                    border-radius: 8px;
                    font: 11pt "Times New Roman";
                }
                QPushButton:hover {
                    background: rgba(255,255,255,60);
                }
            """)

        self.tab_general.clicked.connect(lambda: self.settings_stack.setCurrentIndex(0))
        self.tab_visual.clicked.connect(lambda: self.settings_stack.setCurrentIndex(1))
        self.tab_starter.clicked.connect(lambda: self.settings_stack.setCurrentIndex(2))
        self.tab_keybind.clicked.connect(lambda: self.settings_stack.setCurrentIndex(3))

        top_container.addWidget(self.tab_general)
        top_container.addWidget(self.tab_visual)
        top_container.addWidget(self.tab_starter)
        top_container.addWidget(self.tab_keybind)
        top_container.addStretch()

        top_bar.addLayout(top_container)

        # ---------------- STYLES ----------------
        scroll_style = """
        QScrollArea {
            background: rgba(0, 0, 0, 128);
            border-radius: 6px;
            border: none;
        }

        QScrollArea > QWidget > QWidget {
            background: transparent;
        }

        QScrollBar:vertical {
            background: rgba(0,0,0,120);
            width: 8px;
            margin: 2px;
            border-radius: 4px;
        }
        QScrollBar::handle:vertical {
            background: rgba(255,255,255,140);
            border-radius: 4px;
        }
        """

        checkbox_style = """
        QCheckBox::indicator {
            width: 16px;
            height: 16px;
            border-radius: 4px;
            border: 1px solid rgba(255,255,255,85);
            background: rgba(0,0,0,92);
        }

        QCheckBox::indicator:checked {
            background: #7a00ff;
            border: 1px solid #c18dff;
        }
        """

        # ---------------- STACK ----------------
        self.settings_stack = QtWidgets.QStackedWidget()

        def make_settings_tab(builder):
            page = QtWidgets.QWidget()
            page_layout = QtWidgets.QVBoxLayout(page)
            scroll = QtWidgets.QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
            scroll.setStyleSheet(scroll_style)

            scroll_content = QtWidgets.QWidget()
            scroll_content.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
            scroll_layout = QtWidgets.QVBoxLayout(scroll_content)
            scroll_layout.setContentsMargins(10, 10, 10, 10)
            builder(scroll_layout)
            scroll_layout.addStretch()
            scroll.setWidget(scroll_content)
            page_layout.addWidget(scroll)
            return page

        general_widget = make_settings_tab(
            lambda layout: self.build_settings_category(layout, checkbox_style, "general", self.general_widgets)
        )
        visual_widget = make_settings_tab(
            lambda layout: self.build_settings_category(layout, checkbox_style, "visual", self.visual_widgets)
        )
        starter_widget = make_settings_tab(
            lambda layout: self.build_starter_settings(layout, checkbox_style)
        )
        keybind_widget = make_settings_tab(self.build_keybind_settings)

        # Add tabs
        self.settings_stack.addWidget(general_widget)
        self.settings_stack.addWidget(visual_widget)
        self.settings_stack.addWidget(starter_widget)
        self.settings_stack.addWidget(keybind_widget)

        # ---------------- SAVE BUTTON ----------------
        bottom = QtWidgets.QHBoxLayout()
        bottom.addStretch()

        save_btn = QtWidgets.QPushButton("Save && Return")
        save_btn.setFixedHeight(34)
        save_btn.setFixedWidth(250)

        save_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,30);
                color: white;
                border-radius: 12px;
                padding: 8px 16px;
                font: 11pt "Times New Roman";
            }
            QPushButton:hover {
                background: rgba(255,255,255,60);
            }
        """)

        def save_and_return():
            self.save_settings()
            self.show_home()

        save_btn.clicked.connect(save_and_return)

        bottom.addWidget(save_btn)
        bottom.addStretch()

        # ---------------- FINAL ----------------
        main_layout.addLayout(top_bar)
        main_layout.addWidget(self.settings_stack)
        main_layout.addLayout(bottom)

    # ---------------- HOME PAGE ----------------
    def build_home_page(self):
        layout = QtWidgets.QHBoxLayout(self.home_page)
        layout.setContentsMargins(0, 0, 0, 0)

        left = self.create_info_section(self.home_page)
        right = self.create_right_panel(self.home_page)

        layout.addWidget(left, 76)
        layout.addWidget(right, 24)

  # ---------------- ACTIVE SETUP PAGE ----------------
    def build_active_setup_page(self):
        layout = QtWidgets.QVBoxLayout(self.active_setup_page)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        title = QtWidgets.QLabel("A setup is currently running")
        title.setAlignment(QtCore.Qt.AlignCenter)
        title.setStyleSheet("color: white; font-weight: bold;")
        title.setFont(QtGui.QFont("Times New Roman", 16))

        info = QtWidgets.QLabel(
            "Currently, we only support 1 setup at a time. \n"
            "You can minimize this window while working on your amazing setup.\n"
            "Multiple setups support soon. GL!\n"
        )
        info.setAlignment(QtCore.Qt.AlignCenter)
        info.setStyleSheet("color: rgba(255,255,255,200);")
        info.setFont(QtGui.QFont("Times New Roman", 10))
        info.setWordWrap(True)

        warning = QtWidgets.QLabel(
            "⚠️ DO NOT X this window, it will terminate the program."
        )
        warning.setAlignment(QtCore.Qt.AlignCenter)
        warning.setStyleSheet("color: #ff4d4d; font-weight: bold;")
        warning.setFont(QtGui.QFont("Times New Roman", 9.5))
        warning.setWordWrap(True)

        layout.addStretch()
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(info)
        layout.addWidget(warning)
        layout.addStretch()

    def show_active_setup(self):
        self.stack.setCurrentWidget(self.active_setup_page)
        
        center = self.geometry().center()
        self._set_panel_size(525, 265)
        
        rect = self.geometry()
        rect.moveCenter(center)
        self.move(rect.topLeft())


  # ---------------- CREDITS PAGE ----------------
    def open_email(self):
        url = f"https://mail.google.com/mail/?view=cm&fs=1&to={AppConfig.EMAIL}"
        if not QtGui.QDesktopServices.openUrl(QtCore.QUrl(url)):
            # Fallback if Gmail fails
            QtGui.QDesktopServices.openUrl(QtCore.QUrl(f"mailto:{AppConfig.EMAIL}"))

    def open_discord(self):
        QtGui.QDesktopServices.openUrl(QtCore.QUrl(AppConfig.DISCORD))

    def open_github(self):
        QtGui.QDesktopServices.openUrl(QtCore.QUrl(AppConfig.GITHUB))

    def open_about_us(self):
        QtGui.QDesktopServices.openUrl(QtCore.QUrl(AppConfig.ABOUTUS))


    def copy_to_clipboard(self, text):
        QtWidgets.QApplication.clipboard().setText(text)


    def build_credits_page(self):
        layout = QtWidgets.QVBoxLayout(self.credits_page)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        # ---------------- TITLE ----------------
        title = QtWidgets.QLabel("Credits")
        title.setStyleSheet("color: white; font-weight: bold;")
        title.setFont(QtGui.QFont("Times New Roman", 13))

        # ---------------- TOP SECTION (LOGO + INFO) ----------------
        top_row = QtWidgets.QHBoxLayout()
        top_row.setSpacing(15)

        # ---- LOGO (LEFT, SQUARE) ----
        logo_label = QtWidgets.QLabel()
        logo_label.setFixedSize(60, 60)  # 🔥 square

        logo_path = ASSETS_DIR / "XPR_Group_Alt.png"
        pixmap = QtGui.QPixmap(str(logo_path))

        if not pixmap.isNull():
            pixmap = pixmap.scaled(
                60, 60,
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation
            )
            logo_label.setPixmap(pixmap)

        logo_label.setAlignment(QtCore.Qt.AlignCenter)

        # ---- INFO (RIGHT) ----
        info = QtWidgets.QLabel(
            f"{AppConfig.APP_FULL}\n"
            f"{AppConfig.COPYRIGHT} {AppConfig.COMPANY} — All Rights Reserved\n\n"
            "System & UI Design by AC4 (Founder)\n"
        )
        info.setStyleSheet("color: rgba(255,255,255,200);")
        info.setFont(QtGui.QFont("Times New Roman", 10))
        info.setWordWrap(True)

        # Layout combine
        top_row.addWidget(logo_label)
        top_row.addWidget(info, 1)  # stretch

        # ---------------- CONTACT LABEL ----------------
        contact_label = QtWidgets.QLabel(
            "Contact, Feedback & Community           <span style='font-size:6.5pt;'>(Right-click to copy info)</span>"
        )
        contact_label.setStyleSheet("color: white; font-weight: bold;")
        contact_label.setFont(QtGui.QFont("Times New Roman", 12))

        # ---------------- BUTTON STYLE ----------------
        btn_style = """
        QPushButton {
            background: rgba(255,255,255,15);
            color: white;
            border-radius: 8px;
            padding: 6px;
            text-align: left;
            font: 9pt "Times New Roman";
        }
        QPushButton:hover {
            background: rgba(255,255,255,40);
        }
        QPushButton:pressed {
            background: rgba(255,255,255,70);
        }
        """

        def make_contact_button(text, icon_name, on_click, copy_value):
            button = QtWidgets.QPushButton(f"   {text}")
            button.setStyleSheet(btn_style)
            button.setCursor(QtCore.Qt.PointingHandCursor)
            button.setMinimumHeight(40)
            button.setIcon(QtGui.QIcon(str(ASSETS_DIR / icon_name)))
            button.setIconSize(QtCore.QSize(20, 20))
            button.clicked.connect(on_click)
            button.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            button.customContextMenuRequested.connect(
                lambda _pos, value=copy_value: self.copy_to_clipboard(value)
            )
            return button

        email_btn = make_contact_button(
            f"Email: {AppConfig.EMAIL}",
            "Gmail.png",
            self.open_email,
            AppConfig.EMAIL,
        )
        about_btn = make_contact_button(
            "About Us, What is XPR?",
            "XPR_Group_Alt.png",
            self.open_about_us,
            AppConfig.ABOUTUS,
        )
        discord_btn = make_contact_button(
            "Discord Community",
            "Discord.png",
            self.open_discord,
            AppConfig.DISCORD,
        )
        github_btn = make_contact_button(
            "GitHub Page",
            "XPR_Group_Alt.png",
            self.open_github,
            AppConfig.GITHUB,
        )

        button_grid = QtWidgets.QGridLayout()
        button_grid.setHorizontalSpacing(10)
        button_grid.setVerticalSpacing(10)
        button_grid.addWidget(email_btn, 0, 0)
        button_grid.addWidget(about_btn, 0, 1)
        button_grid.addWidget(discord_btn, 1, 0)
        button_grid.addWidget(github_btn, 1, 1)

        # ---------------- BACK BUTTON ----------------
        back_btn = QtWidgets.QPushButton("Home")
        back_btn.setFixedHeight(32)
        back_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,25);
                color: white;
                border-radius: 10px;
                font: 10pt "Times New Roman";
            }
            QPushButton:hover {
                background: rgba(255,255,255,60);
            }
        """)
        back_btn.clicked.connect(self.show_home)

        # ---------------- FINAL LAYOUT ----------------
        layout.addWidget(title)
        layout.addLayout(top_row)  # 🔥 NEW STRUCTURE

        layout.addSpacing(10)
        layout.addWidget(contact_label)
        layout.addLayout(button_grid)

        layout.addStretch()
        layout.addWidget(back_btn)

    # ---------------- PAGE SWITCH ----------------
      # ---------------- PAGE SWITCH ----------------
    def show_credits(self):
        center = self.geometry().center()
        self._set_panel_size(650, 480)
        rect = self.geometry()
        rect.moveCenter(center)
        self.move(rect.topLeft())
        self.stack.setCurrentWidget(self.credits_page)

    def _return_to_setup_minimized(self):
        center = self.geometry().center()
        self._set_panel_size(500, 280)

        rect = self.geometry()
        rect.moveCenter(center)
        self.move(rect.topLeft())

        self.show_active_setup()
        QtCore.QTimer.singleShot(
            0,
            self.minimize_with_anim if hasattr(self, "minimize_with_anim") else self.showMinimized,
        )

    def show_home(self):
        # 🔥 if coming from setup, go back to active setup instead
        if getattr(self, "_from_setup", False):
            self._from_setup = False
            self._return_to_setup_minimized()
            return

        # normal behavior
        if hasattr(self, "_load_setup_btn"):
            self._load_setup_btn.setEnabled(any(SetupManager.is_loadable(path) for path in SetupManager.list_setups()))
        self.stack.setCurrentWidget(self.home_page)
        
        center = self.geometry().center()
        self._set_panel_size(580, 360)
        
        rect = self.geometry()
        rect.moveCenter(center)
        self.move(rect.topLeft())

    # ---------------- LEFT ----------------
    def create_info_section(self, parent):
        container = QtWidgets.QWidget(parent)
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(8)

        block1_title = QtWidgets.QLabel("Command Every Movement")
        block1_title.setStyleSheet("color: white; font-weight: bold;")
        block1_title.setFont(QtGui.QFont("Times New Roman", 14))

        block1_desc = QtWidgets.QLabel(
            "We go beyond just basic auto clickers. \n"
            "From simple clicks to full workflow control. \n"
            "SnapCursorX lets you build, control, and execute.\n"
            "Fast to start. Powerful when you need it."
        )
        block1_desc.setStyleSheet("color: rgba(255,255,255,200);")
        block1_desc.setWordWrap(True)
        block1_desc.setFont(QtGui.QFont("Times New Roman", 10))

        block2_title = QtWidgets.QLabel("Design Actions Visually")
        block2_title.setStyleSheet("color: white; font-weight: bold;")
        block2_title.setFont(QtGui.QFont("Times New Roman", 14))

        block2_desc = QtWidgets.QLabel(
            "Fast & Easy with Visual logic & Markers.\n"
            "Flexible. No Coding. No Complexity."
        )
        block2_desc.setStyleSheet("color: rgba(255,255,255,200);")
        block2_desc.setWordWrap(True)
        block2_desc.setFont(QtGui.QFont("Times New Roman", 10))

        credit = QtWidgets.QLabel()
        credit.setText(
            f"<b><span style='font-size:8.8pt;'>{AppConfig.COMPANY}</span></b><br>"
            f"<span style='font-size:6.8pt;'>{AppConfig.TAGLINE}</span><br>"
            f"<span style='font-size:7.8pt;'>{AppConfig.COPYRIGHT} {AppConfig.APP_FULL}</span>"
        )
        credit.setStyleSheet("color: rgba(255,255,255,160);")
        credit.setFont(QtGui.QFont("Times New Roman"))
        credit.setWordWrap(True)

        layout.addWidget(block1_title)
        layout.addWidget(block1_desc)

        layout.addSpacing(9)

        layout.addWidget(block2_title)
        layout.addWidget(block2_desc)

        layout.addSpacing(12)

        layout.addStretch()
        layout.addWidget(credit)

        return container

    # ---------------- RIGHT ----------------
    def create_right_panel(self, parent):
        container = QtWidgets.QWidget(parent)
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 20, 10)
        layout.setSpacing(10)

        def make_button(text, func):
            btn = QtWidgets.QPushButton(text)
            btn.setFixedHeight(30)
            btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255,255,255,30);
                    color: white;
                    border-radius: 8px;
                    font: 10pt "Times New Roman";
                }
                QPushButton:hover {
                    background: rgba(255,255,255,60);
                }
                QPushButton:disabled {
                    background: rgba(255,255,255,12);
                    color: rgba(255,255,255,90);
                }
            """)
            btn.clicked.connect(func)
            return btn

        def open_new_setup():
            base_pos = self.pos()
            offset_pos = base_pos + QtCore.QPoint(50, 50)

            self.new_window = NewSetupWindow(self, offset_pos)

            def show_new():
                self.new_window.show()
                WindowAnimator.fade_in(self.new_window)
                WindowAnimator.slide(
                    self.new_window,
                    offset_pos + QtCore.QPoint(0, 20),  # slight drop effect
                    offset_pos
                )

            # fade out main, then open new
            WindowAnimator.fade_out(self, callback=lambda: (
                self.hide(),
                show_new()
            ))

            self.new_window.closed.connect(self.show_with_anim)

        def open_load_setup():
            base_pos = self.pos()
            offset_pos = base_pos + QtCore.QPoint(50, 50)

            self.load_window = LoadSetupWindow(self, offset_pos)

            def show_new():
                self.load_window.show()
                WindowAnimator.fade_in(self.load_window)
                WindowAnimator.slide(
                    self.load_window,
                    offset_pos + QtCore.QPoint(0, 20),
                    offset_pos
                )

            WindowAnimator.fade_out(self, callback=lambda: (
                self.hide(),
                show_new()
            ))

            self.load_window.closed.connect(self.show_with_anim)

        layout.addWidget(make_button("New Setup", open_new_setup))
        self._load_setup_btn = make_button("Load Setup", open_load_setup)
        self._load_setup_btn.setEnabled(any(SetupManager.is_loadable(path) for path in SetupManager.list_setups()))
        layout.addWidget(self._load_setup_btn)
        layout.addWidget(make_button("Settings", self.show_settings))
        layout.addWidget(make_button("Quit", self.close_all))

        layout.addStretch()
        layout.addSpacing(10)

        self._update_release_btn = make_button("Checking For\nUpdates...", self._on_update_release_clicked)
        self._update_release_btn.setFixedSize(120, 50)
        self._update_release_btn.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self._update_release_btn.setStyleSheet(self._update_button_style("checking"))
        layout.addWidget(self._update_release_btn)
        
        layout.addSpacing(2)

        layout.addWidget(make_button("About && Credits", self.show_credits))

        return container

    def _set_update_button_label(self, text):
        if hasattr(self, "_update_release_btn") and self._update_release_btn is not None:
            display_text, style_state = self._format_update_button_label(text)
            self._update_release_btn.setText(display_text)
            self._update_release_btn.setToolTip(self._raw_update_button_label(text))
            self._update_release_btn.setStyleSheet(self._update_button_style(style_state))

    def _update_button_style(self, state: str) -> str:
        colors = {
            "update": ("rgba(150,255,150,150)", "rgba(200,255,200,100)", "rgba(100,255,100,65)"),
            "checking": ("rgba(150,150,150,80)", "rgba(200,250,200,60)", "rgba(220,220,220,40)"),
            "failed": ("rgba(255,150,150,100)", "rgba(255,250,200,80)", "rgba(255,220,220,60)"),
            "latest": ("rgba(150,150,150,20)", "rgba(200,250,200,25)", "rgba(220,220,220,40)"),
        }
        bg, hover, pressed = colors.get(state, colors["latest"])
        return f"""
            QPushButton {{
                background: {bg};
                color: white;
                border-radius: 12px;
                padding: 6.5px 16px;
                font: 8pt "Times New Roman";
            }}
            QPushButton:hover {{
                background: {hover};
            }}
            QPushButton:pressed {{
                background: {pressed};
            }}
            QPushButton:disabled {{
                background: {bg};
            }}
        """

    def _raw_update_button_label(self, text) -> str:
        if isinstance(text, dict):
            return str(text.get("label") or text.get("status") or "").strip()
        return str(text or "").strip()

    def _format_update_button_label(self, text) -> tuple[str, str]:
        if isinstance(text, dict):
            status = str(text.get("status", "")).strip().lower()
            label = str(text.get("label", "")).strip()
            latest_version = parse_numeric_version_text(text.get("latest_version", ""))
            if status == "update_available":
                return f"New Update!\nVer{latest_version}", "update"
            if status == "latest":
                return "Latest Release\n(Click for info)", "latest"
            if status == "checking":
                return "Checking For\nUpdates...", "checking"
            if status in ("check_failed", "no_internet"):
                return "Check Failed\nTry Again", "failed"
            text = label or status

        raw_text = str(text or "").strip()
        normalized = " ".join(raw_text.split()).lower()
        if not raw_text:
            return "(Latest ver)", "latest"
        if normalized in ("check", "checking", "checking updates...", "checking for updates..."):
            return "Checking For\nUpdates...", "checking"
        if "new update" in normalized:
            latest_version = parse_numeric_version_text(raw_text)
            return (f"New Update!\nVer{latest_version}" if latest_version != "0.0.0" else "New Update!"), "update"
        if "latest" in normalized:
            return "(Latest ver)", "latest"
        if (
            "try again" in normalized
            or "check your connection" in normalized
            or "no internet" in normalized
            or "can't check" in normalized
            or "failed" in normalized
        ):
            return "Check Failed\nTry Again", "failed"
        return raw_text, "latest"

    def _start_update_check(self):
        if self._update_check_thread is not None:
            return
        self._update_check_started = True
        self._update_check_request_id += 1
        request_id = self._update_check_request_id
        self._update_status = {
            "request_id": request_id,
            "status": "checking",
            "label": "Checking for updates...",
            "latest_version": parse_numeric_version_text(AppConfig.VERSION),
            "release_page_url": UPDATE_RELEASE_PAGE_URL,
            "assets": {},
        }
        self._set_update_button_label(self._update_status)

        thread = QtCore.QThread(self)
        worker = UpdateCheckWorker(
            AppConfig.VERSION,
            UPDATE_RELEASE_API_URL,
            UPDATE_RELEASE_PAGE_URL,
            request_id=request_id,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_update_check_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(lambda t=thread: self._forget_stale_update_check_thread(t))
        self._update_check_thread = thread
        self._update_check_worker = worker
        self._start_update_check_timeout(request_id)
        thread.start()

    def _on_update_check_finished(self, result: dict):
        result = dict(result or {})
        if result.get("request_id") != self._update_check_request_id:
            return
        self._stop_update_check_timeout()
        self._update_status = result
        self._set_update_button_label(self._update_status)
        self._update_check_thread = None
        self._update_check_worker = None

    def _start_update_check_timeout(self, request_id: int):
        self._stop_update_check_timeout()
        timer = QtCore.QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self._on_update_check_timeout(request_id))
        self._update_check_timeout_timer = timer
        timer.start(9000)

    def _stop_update_check_timeout(self):
        if self._update_check_timeout_timer is not None:
            self._update_check_timeout_timer.stop()
            self._update_check_timeout_timer.deleteLater()
            self._update_check_timeout_timer = None

    def _on_update_check_timeout(self, request_id: int):
        if request_id != self._update_check_request_id:
            return
        self._update_check_request_id += 1
        self._update_status = {
            "request_id": self._update_check_request_id,
            "status": "check_failed",
            "label": "Check your connection and try again.",
            "latest_version": parse_numeric_version_text(AppConfig.VERSION),
            "release_page_url": UPDATE_RELEASE_PAGE_URL,
            "assets": {},
        }
        self._set_update_button_label(self._update_status)
        if self._update_check_thread is not None:
            self._stale_update_check_threads.append((self._update_check_thread, self._update_check_worker))
        self._update_check_thread = None
        self._update_check_worker = None
        self._stop_update_check_timeout()

    def _forget_stale_update_check_thread(self, thread):
        self._stale_update_check_threads = [
            pair for pair in self._stale_update_check_threads if pair[0] is not thread
        ]

    def _on_update_release_clicked(self):
        status = str(self._update_status.get("status", "idle"))
        if status in ("idle", "checking", "no_internet", "check_failed"):
            self._start_update_check()
            return
        if status != "update_available":
            QtGui.QDesktopServices.openUrl(QtCore.QUrl(self._update_status.get("release_page_url", UPDATE_RELEASE_PAGE_URL)))
            return

        assets = self._update_status.get("assets", {})
        installer_asset = assets.get("installer")
        portable_asset = assets.get("portable")
        latest_version = self._update_status.get("latest_version", "")
        recommended_kind = self._recommended_update_kind(installer_asset, portable_asset)
        recommended_asset = installer_asset if recommended_kind == "installer" else portable_asset

        msg = QtWidgets.QMessageBox(self)
        msg.setWindowTitle("Update Available")
        msg.setText(f"New Update!\nVer{latest_version}")
        msg.setInformativeText(
            "Recommended: "
            + ("Installer update detected." if recommended_kind == "installer" else "Portable update detected.")
            + "\n\nYou can still choose any available update type below."
        )
        recommended_btn = None
        installer_btn = None
        portable_btn = None
        if recommended_asset:
            recommended_label = "Recommended: Download Installer" if recommended_kind == "installer" else "Recommended: Download Portable"
            recommended_btn = msg.addButton(recommended_label, QtWidgets.QMessageBox.AcceptRole)
        if installer_asset and recommended_kind != "installer":
            installer_btn = msg.addButton("Download Installer", QtWidgets.QMessageBox.ActionRole)
        if portable_asset and recommended_kind != "portable":
            portable_btn = msg.addButton("Download Portable", QtWidgets.QMessageBox.ActionRole)
        release_btn = msg.addButton("Open Release Page", QtWidgets.QMessageBox.ActionRole)
        cancel_btn = msg.addButton(QtWidgets.QMessageBox.Cancel)
        if recommended_btn is not None:
            msg.setDefaultButton(recommended_btn)
        msg.exec()

        clicked = msg.clickedButton()
        if clicked == recommended_btn:
            self._start_update_download(recommended_kind, recommended_asset)
            return
        if clicked == installer_btn:
            self._start_update_download("installer", installer_asset)
            return
        if clicked == portable_btn:
            self._start_update_download("portable", portable_asset)
            return
        if clicked == release_btn:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl(self._update_status.get("release_page_url", UPDATE_RELEASE_PAGE_URL)))
            return
        if clicked == cancel_btn:
            return

    def _recommended_update_kind(self, installer_asset: dict | None, portable_asset: dict | None) -> str:
        if self._looks_like_installed_app() and installer_asset:
            return "installer"
        if portable_asset:
            return "portable"
        if installer_asset:
            return "installer"
        return "portable"

    def _looks_like_installed_app(self) -> bool:
        try:
            return (BASE_DIR / "uninstall.exe").exists()
        except Exception:
            return False

    def _start_update_download(self, asset_kind: str, asset: dict | None):
        if not asset:
            QtWidgets.QMessageBox.warning(self, "Update", "Selected update asset is not available.")
            return
        if self._update_download_thread is not None:
            return

        download_url = str(asset.get("url", ""))
        filename = str(asset.get("name", "SnapCursorX_Update.exe"))
        if not download_url:
            QtWidgets.QMessageBox.warning(self, "Update", "Download URL is empty. Replace the placeholder release URL first.")
            return

        target_dir = ""
        if asset_kind == "portable":
            downloads_dir = self._downloads_dir()
            reply = QtWidgets.QMessageBox.question(
                self,
                "Download Portable Update",
                "Download the new portable update to your Downloads folder?\n\n"
                f"Location:\n{downloads_dir}",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.Yes,
            )
            if reply != QtWidgets.QMessageBox.Yes:
                return
            target_dir = str(downloads_dir)

        progress = QtWidgets.QProgressDialog("Downloading update...", None, 0, 100, self)
        progress.setWindowTitle("Update")
        progress.setCancelButton(None)
        progress.setMinimumDuration(0)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.setWindowModality(QtCore.Qt.WindowModal)
        progress.setValue(0)
        progress.show()
        self._update_progress_dialog = progress
        self._active_update_asset_kind = asset_kind

        thread = QtCore.QThread(self)
        worker = UpdateDownloadWorker(download_url, filename, target_dir=target_dir)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(progress.setValue)
        worker.finished.connect(self._on_update_download_finished)
        worker.failed.connect(self._on_update_download_failed)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._update_download_thread = thread
        self._update_download_worker = worker
        thread.start()

    def _on_update_download_finished(self, downloaded_path: str):
        if self._update_progress_dialog is not None:
            self._update_progress_dialog.setValue(100)
            self._update_progress_dialog.close()
            self._update_progress_dialog = None

        self._update_download_thread = None
        self._update_download_worker = None

        path = str(downloaded_path or "").strip()
        if not path:
            QtWidgets.QMessageBox.warning(self, "Update", "Downloaded update path is empty.")
            return

        asset_kind = self._active_update_asset_kind
        self._active_update_asset_kind = ""

        try:
            if asset_kind == "installer" or path.lower().endswith(".msi"):
                self._launch_installer_update(Path(path))
                QtWidgets.QApplication.quit()
            else:
                download_path = Path(path)
                self._show_portable_update_ready_dialog(download_path)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "Update", f"Failed to launch update:\n{exc}")
            return

    def _downloads_dir(self) -> Path:
        return Path.home() / "Downloads"

    def _launch_installer_update(self, installer_path: Path):
        installer_path = Path(installer_path)
        install_dir = BASE_DIR if self._looks_like_installed_app() else None
        if installer_path.suffix.lower() == ".msi":
            install_target = f' INSTALLDIR="{install_dir}"' if install_dir else ""
            command = f'timeout /t 2 /nobreak >nul & msiexec.exe /i "{installer_path}" /quiet /norestart{install_target}'
        else:
            install_target = f" /D={install_dir}" if install_dir else ""
            command = f'timeout /t 2 /nobreak >nul & "{installer_path}" /S{install_target}'

        result = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            "cmd.exe",
            f'/c {command}',
            str(installer_path.parent),
            0,
        )
        if result <= 32:
            raise RuntimeError(f"[WinError {result}] The requested operation requires elevation")

    def _show_portable_update_ready_dialog(self, download_path: Path):
        QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(download_path.parent)))

        message = QtWidgets.QMessageBox(self)
        message.setWindowTitle("Portable Update Downloaded")
        message.setText("Downloaded new update.")
        message.setInformativeText(
            "Extract the zip and enjoy.\n\n"
            "Note: We only download latest releases from official GitHub. if you downloaded the program from the official source there should be no safety problems.\n\n"
            f"Saved to:\n{download_path}\n\n"
            "You can close SnapCursorX now and replace the old portable files, or continue using the current version."
        )
        close_btn = message.addButton("Close Program", QtWidgets.QMessageBox.AcceptRole)
        continue_btn = message.addButton("Continue Using", QtWidgets.QMessageBox.RejectRole)
        message.setDefaultButton(close_btn)
        message.exec()

        if message.clickedButton() == close_btn:
            QtWidgets.QApplication.quit()
        elif message.clickedButton() == continue_btn:
            return

    def _on_update_download_failed(self, message: str):
        if self._update_progress_dialog is not None:
            self._update_progress_dialog.close()
            self._update_progress_dialog = None
        self._update_download_thread = None
        self._update_download_worker = None
        self._active_update_asset_kind = ""
        QtWidgets.QMessageBox.warning(
            self,
            "Update",
            "Download failed.\n check your internet connection and try again or redownload from our github that listed in about & credit page.\n\n"
            f"Details: {message}",
        )
    
    def moveEvent(self, event):
        if not getattr(self, "_animating", False):
            self._base_pos = self.pos()
        super().moveEvent(event)
    
# ---------------- NEW SETUP WINDOW ----------------
class NewSetupWindow(QtWidgets.QMainWindow):
    closed = QtCore.Signal()

    def __init__(self, parent=None, pos=None):
        super().__init__()
        ensure_app_input_focus_manager()
        TitleBar = _titlebar_type()
        self.setWindowTitle(f"New Setup — {AppConfig.APP_FULL}")
        self._animating = False
        self.parent = parent
        self._was_minimized = False
        self._base_pos = self.pos()

        self.setWindowFlags(
            QtCore.Qt.FramelessWindowHint |
            QtCore.Qt.NoDropShadowWindowHint |
            QtCore.Qt.WindowStaysOnTopHint |
            QtCore.Qt.WindowMinimizeButtonHint
        )

        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        if pos:
            self.setGeometry(pos.x(), pos.y(), 480, 300)
        else:
            self.setGeometry(250, 200, 480, 300)

        # ---- CENTRAL ----
        central = QtWidgets.QWidget(self)
        central.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setCentralWidget(central)

        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(3)

        # ---- SAME TITLE BAR ----
        self.title_bar = TitleBar(
        self,
        title_text="New Setup",
        is_sub_window=True
        )
        layout.addWidget(self.title_bar)

        # 🔥 IMPORTANT: override close behavior
        self.title_bar.close_btn.clicked.disconnect()
        self.title_bar.close_btn.clicked.connect(self.close)

       # ---- STATE ----
        self.selected_mode = "single"  # default
        self.mode_window = None
        self._mode_launch_path = ""
        self.single_mode = SingleMode(self)
        self.sandbox_mode = SandboxMode(self)

        # ---- CONTENT ----
        content = QtWidgets.QVBoxLayout()
        content.setContentsMargins(20, 10, 20, 10)
        content.setSpacing(5)

        # ---------------- TITLE ----------------
        title = QtWidgets.QLabel("Setup Type")
        title.setAlignment(QtCore.Qt.AlignCenter)
        title.setStyleSheet("color: white; font-weight: bold;")
        title.setFont(QtGui.QFont("Times New Roman", 14))

        content.addWidget(title)
        content.setSpacing(10)

        # ---------------- MODE BUTTONS ----------------
        mode_layout = QtWidgets.QVBoxLayout()
        mode_layout.setSpacing(6)

        self.mode_buttons = {}

        def create_mode_button(key, title_text, desc_text):
            btn = QtWidgets.QPushButton()
            btn.setFixedHeight(42)

            btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255,255,255,20);
                    border-radius: 10px;
                }
                QPushButton:hover {
                    background: rgba(255,255,255,50);
                }
            """)

            # 🔥 INNER LAYOUT (REAL FIX)
            layout = QtWidgets.QVBoxLayout(btn)
            layout.setContentsMargins(10, 6, 10, 6)
            layout.setSpacing(5)

            title = QtWidgets.QLabel(title_text)
            title.setStyleSheet("color: white; font-weight: 600;")
            title.setFont(QtGui.QFont("Times New Roman", 11))

            desc = QtWidgets.QLabel(desc_text)
            desc.setStyleSheet("color: rgba(255,255,255,180);")
            desc.setFont(QtGui.QFont("Times New Roman", 9))

            layout.addWidget(title)
            layout.addWidget(desc)

            btn.clicked.connect(lambda: self.select_mode(key))

            self.mode_buttons[key] = btn
            return btn

        mode_layout.addWidget(create_mode_button(
            "single",
            "Single Mode",
            "Auto-clicker for single-point execution. Fast & Easy."
        ))

        mode_layout.addWidget(create_mode_button(
            "sandbox",
            "Sandbox Mode",
            "Build your own command flow. Structure and execute in your way."
        ))

        content.addLayout(mode_layout)

        # ---------------- NAME INPUT ----------------
        name_label = QtWidgets.QLabel("Setup Name")
        name_label.setAlignment(QtCore.Qt.AlignCenter)
        name_label.setStyleSheet("color: white; font-weight: bold;")
        name_label.setFont(QtGui.QFont("Times New Roman", 14))

        self.name_input = QtWidgets.QLineEdit()
        self.name_input.setPlaceholderText("Enter setup name...")
        self.name_input.setAlignment(QtCore.Qt.AlignCenter)
        self.name_input.setStyleSheet("""
            QLineEdit {
                background: rgba(0,0,0,120);
                color: white;
                border-radius: 6px;
                padding: 6px;
                border: none;
                font: 10pt "Times New Roman";
            }
        """)

        content.addSpacing(6)
        content.addWidget(name_label)
        content.addWidget(self.name_input)

        # ---------------- CREATE BUTTON ----------------
        content.addSpacing(6)
        create_btn = QtWidgets.QPushButton("Create Setup")
        create_btn.setFixedHeight(30)

        create_btn.setStyleSheet("""
            QPushButton {
                background: #7a00ff;
                color: white;
                border-radius: 10px;
                font: 11pt "Times New Roman";
            }
            QPushButton:hover {
                background: #9a2bff;
            }
        """)

        def create_setup():
            name = self.name_input.text().strip()
            if not name:
                print("Name required")
                return
            # 🔥 Create file
            path = SetupManager.create(name, self.selected_mode)
            created_name = os.path.splitext(os.path.basename(path))[0].replace("_", " ")
            self.name_input.setText(created_name)
            print(f"Created: {path}")
            # 🔥 Open correct UI
            self.open_mode_ui(path, self.selected_mode)
            self.close()

        create_btn.clicked.connect(create_setup)

        content.addWidget(create_btn)

        layout.addLayout(content)

        # 🔥 APPLY DEFAULT SELECTION
        self.select_mode("single")

    def open_mode_ui(self, path, mode):
        self._mode_launch_path = path

        if mode == "single":
            self.single_mode.start()
        elif mode == "sandbox":
            self.sandbox_mode.start()
        else:
            print("Unknown mode")
            return

    def select_mode(self, key):
        self.selected_mode = key

        for k, btn in self.mode_buttons.items():
            if k == key:
                btn.setStyleSheet("""
                    QPushButton {
                        background: #7a00ff;
                        color: white;
                        border-radius: 10px;
                        text-align: left;
                        padding: 10px;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background: rgba(255,255,255,20);
                        color: white;
                        border-radius: 10px;
                        text-align: left;
                        padding: 10px;
                    }
                    QPushButton:hover {
                        background: rgba(255,255,255,50);
                    }
                """)

    def moveEvent(self, event):
        self._base_pos = self.pos()
        super().moveEvent(event)

    def changeEvent(self, event):
        if event.type() == QtCore.QEvent.WindowStateChange:
            if self.windowState() & QtCore.Qt.WindowMinimized:
                self._was_minimized = True

            elif getattr(self, "_was_minimized", False):
                self._was_minimized = False

                self.setWindowState(QtCore.Qt.WindowNoState)
                self.show()
                self.raise_()
                self.activateWindow()

                WindowAnimator.restore(self)

        super().changeEvent(event)

    # ---- SAME GRADIENT ----
    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        rect = self.rect()

        grad = QtGui.QLinearGradient(0, 0, self.width(), self.height())
        grad.setColorAt(0, QtGui.QColor("#0f0c29"))
        grad.setColorAt(0.45, QtGui.QColor("#400071"))
        grad.setColorAt(1, QtGui.QColor("#24243e"))

        painter.setBrush(grad)
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRoundedRect(rect, 14, 14)

    # ---- RETURN TO HOME ----
    def closeEvent(self, event):
        if getattr(self, "_closing", False):
            event.accept()
            return
        event.ignore()
        self._closing = True  # 🔥 prevent loop
        def finish_close():
            self.closed.emit()
            self.close()  # now safe

        WindowAnimator.fade_out(self, callback=finish_close)

    def moveEvent(self, event):
        if not getattr(self, "_animating", False):
            self._base_pos = self.pos()
        super().moveEvent(event)

# ---------------- Real Functions Shared ----------------
class BaseSetupUI(QtWidgets.QMainWindow):
    closed = QtCore.Signal()

    def __init__(self, file_path, pos=None, title="Setup", parent=None):
        super().__init__(parent)
        ensure_app_input_focus_manager()
        FileMenuPopup = _file_menu_popup_type()
        self._closing = False
        self._allow_close_without_save = False

        self.file_path = file_path
        self.data = SetupManager.load(file_path)
        self._saved_state = copy.deepcopy(self.data)

        self.setWindowFlags(
            QtCore.Qt.Window |
            QtCore.Qt.FramelessWindowHint |
            QtCore.Qt.NoDropShadowWindowHint |
            QtCore.Qt.WindowStaysOnTopHint |
            QtCore.Qt.WindowMinimizeButtonHint
        )

        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)

        if pos:
            self.setGeometry(pos.x(), pos.y(), 280, 80)
        else:
            self.setGeometry(200, 200, 280, 80)

        # ---- UI ----
        central = QtWidgets.QWidget(self)
        central.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setCentralWidget(central)

        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(0)

        self.title_bar = QtWidgets.QWidget(self)
        self.title_bar.setFixedHeight(13)
        tb_layout = QtWidgets.QHBoxLayout(self.title_bar)
        tb_layout.setContentsMargins(6, 0, 6, 0)
        tb_layout.setSpacing(4)

        self._bg_logo_pixmap = None
        logo_path = ASSETS_DIR / "XPR_Developer_Network_Logo_Alt.png"
        pixmap = QtGui.QPixmap(str(logo_path))
        if not pixmap.isNull():
            self._bg_logo_pixmap = pixmap

        setup_name = self.data.get("name", "Unknown")
        setup_mode = f"[{self.data.get('mode', 'unknown')}]"

        self.setWindowTitle(f"{setup_name} — {AppConfig.APP_FULL}")

        self.file_btn = QtWidgets.QPushButton("File", self.title_bar)
        # Assuming height is constrained by title_bar height
        self.file_btn.setFixedHeight(12)
        self.file_btn.setFont(QtGui.QFont("Times New Roman", 8))
        self.file_btn.setStyleSheet("""
            QPushButton { background: transparent; color: white; border: none; padding-right: 4px; padding-left: 4px;}
            QPushButton:hover { background: rgba(255,255,255,60); border-radius: 2px; }
        """)
        tb_layout.addWidget(self.file_btn)

        # File menu popup
        self._file_menu = FileMenuPopup(self)
        self._file_menu_visible = False

        def toggle_file_menu():
            if self._file_menu.isVisible():
                self._file_menu.hide()
            else:
                btn_pos = self.file_btn.mapToGlobal(QtCore.QPoint(0, self.file_btn.height()))
                self._file_menu.move(btn_pos)
                self._file_menu.show()
                self._file_menu.raise_()

        self.file_btn.clicked.connect(toggle_file_menu)

        tb_layout.addStretch()

        self.tb_name = QtWidgets.QLabel(setup_name, self.title_bar)
        self.tb_name.setStyleSheet("color: white; font: 10pt 'Times New Roman';")
        tb_layout.addWidget(self.tb_name)

        self.tb_mode = QtWidgets.QLabel(setup_mode, self.title_bar)
        self.tb_mode.setStyleSheet("color: rgba(255,255,255,140); font: 9pt 'Times New Roman';")
        tb_layout.addWidget(self.tb_mode)

        tb_layout.addStretch()

        self.min_btn = QtWidgets.QPushButton("-", self.title_bar)
        self.close_btn = QtWidgets.QPushButton("X", self.title_bar)

        for btn in (self.min_btn, self.close_btn):
            btn.setFixedSize(12, 12)
            btn.setFont(QtGui.QFont("Times New Roman", 6))
            btn.setStyleSheet("""
                QPushButton { background: transparent; color: white; border: none; margin-bottom: 2px;}
                QPushButton:hover { background: rgba(255,255,255,60); border-radius: 2px; }
            """)
        
        self.min_btn.clicked.connect(self.showMinimized)
        self.close_btn.clicked.connect(self.close)
        tb_layout.addWidget(self.min_btn)
        tb_layout.addWidget(self.close_btn)

        self.title_bar.drag_pos = None
        def tb_mousePress(event):
            if event.button() == QtCore.Qt.LeftButton:
                target = self.title_bar.childAt(event.pos())
                if target not in (self.min_btn, self.close_btn):
                    self.title_bar.drag_pos = _event_global_pos(event)
        def tb_mouseMove(event):
            if event.buttons() == QtCore.Qt.LeftButton and getattr(self.title_bar, "drag_pos", None):
                self.move(self.pos() + _event_global_pos(event) - self.title_bar.drag_pos)
                self.title_bar.drag_pos = _event_global_pos(event)
        def tb_mouseRelease(event):
            self.title_bar.drag_pos = None

        self.title_bar.mousePressEvent = tb_mousePress
        self.title_bar.mouseMoveEvent = tb_mouseMove
        self.title_bar.mouseReleaseEvent = tb_mouseRelease

        layout.addWidget(self.title_bar)

        self.content = QtWidgets.QVBoxLayout()
        self.content.setContentsMargins(6, 2, 6, 6)
        layout.addLayout(self.content)
        self.content.setAlignment(QtCore.Qt.AlignTop)

        # 🔥 Placeholder hook
        self.build_ui()
        self._upgrade_title_bar_drag_region()

    def _upgrade_title_bar_drag_region(self):
        if not hasattr(self, "title_bar"):
            return
        self.title_bar.setFixedHeight(22)
        title_layout = self.title_bar.layout()
        if title_layout is not None:
            title_layout.setContentsMargins(6, 1, 6, 1)
            title_layout.setSpacing(4)

        for attr in ("tb_name", "tb_mode"):
            widget = getattr(self, attr, None)
            if widget is not None:
                widget.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, True)

        if hasattr(self, "file_btn"):
            self.file_btn.setFixedHeight(17)
            self.file_btn.setFont(QtGui.QFont("Times New Roman", 7))
        if hasattr(self, "tb_name"):
            self.tb_name.setStyleSheet("color: white; font: 7.5pt 'Times New Roman';")
        if hasattr(self, "tb_mode"):
            self.tb_mode.setStyleSheet("color: rgba(255,255,255,140); font: 6.8pt 'Times New Roman';")
        for attr in ("min_btn", "close_btn"):
            widget = getattr(self, attr, None)
            if widget is not None:
                widget.setFixedSize(17, 17)
                widget.setFont(QtGui.QFont("Times New Roman", 7))

        self.title_bar.drag_pos = None

        def tb_mouse_press(event):
            if event.button() != QtCore.Qt.LeftButton:
                return
            target = self.title_bar.childAt(event.pos())
            if isinstance(target, QtWidgets.QPushButton):
                return
            self.title_bar.drag_pos = _event_global_pos(event)
            event.accept()

        def tb_mouse_move(event):
            if event.buttons() == QtCore.Qt.LeftButton and getattr(self.title_bar, "drag_pos", None):
                self.move(self.pos() + _event_global_pos(event) - self.title_bar.drag_pos)
                self.title_bar.drag_pos = _event_global_pos(event)
                event.accept()

        def tb_mouse_release(event):
            self.title_bar.drag_pos = None
            event.accept()

        self.title_bar.mousePressEvent = tb_mouse_press
        self.title_bar.mouseMoveEvent = tb_mouse_move
        self.title_bar.mouseReleaseEvent = tb_mouse_release

    def build_ui(self):
        pass  # override

    def save(self):
        atomic_json_write(self.file_path, self.data)
        self._saved_state = copy.deepcopy(self.data)

    def _state_for_close_dirty_check(self, state):
        normalized = copy.deepcopy(state) if isinstance(state, dict) else state
        if not isinstance(normalized, dict):
            return normalized

        settings = normalized.get("settings", {})
        saved_settings = getattr(self, "_saved_state", {}).get("settings", {})
        
        # Determine if we're in follow mode by checking both click_target_mode and always_follow_mouse
        current_mode = str(settings.get("click_target_mode", "") or "").strip().lower()
        saved_mode = str(saved_settings.get("click_target_mode", "") or "").strip().lower()
        current_follow = current_mode == "follow" or bool(settings.get("always_follow_mouse", False))
        saved_follow = saved_mode == "follow" or bool(saved_settings.get("always_follow_mouse", False))
        
        # If both current and saved states are in follow mode, ignore only the
        # live follow-position drift. Fixed marker/pointer positions should
        # still count as unsaved changes.
        if current_follow and saved_follow and "position" in normalized:
            normalized.pop("position", None)
            if isinstance(settings, dict):
                settings.pop("follow_position", None)
        
        return normalized

    def has_unsaved_changes(self):
        current_state = self._state_for_close_dirty_check(self.data)
        saved_state = self._state_for_close_dirty_check(self._saved_state)
        return current_state != saved_state

    def prompt_save_before_close(self):
        if self._allow_close_without_save:
            return True
        if not self.has_unsaved_changes():
            return True

        try:
            winsound.MessageBeep()
        except Exception:
            try:
                winsound.Beep(880, 180)
            except Exception:
                pass

        result = QtWidgets.QMessageBox.question(
            self,
            "Unsaved Changes",
            "Data was changed. Save before quit?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No | QtWidgets.QMessageBox.Cancel,
            QtWidgets.QMessageBox.Yes,
        )

        if result == QtWidgets.QMessageBox.Cancel:
            return False
        if result == QtWidgets.QMessageBox.Yes:
            self.save()
        else:
            self._allow_close_without_save = True
        return True

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        grad = QtGui.QLinearGradient(0, 0, self.width(), self.height())
        grad.setColorAt(0, QtGui.QColor("#0f0c29"))
        grad.setColorAt(0.45, QtGui.QColor("#400071"))
        grad.setColorAt(1, QtGui.QColor("#24243e"))

        painter.setBrush(grad)
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRoundedRect(self.rect(), 4, 4)

        if getattr(self, "_bg_logo_pixmap", None) and not self._bg_logo_pixmap.isNull():
            painter.setOpacity(0.2)

            # 🔥 responsive scaling based on BOTH width & height
            max_w = self.width() * 0.95
            max_h = self.height() * 0.95

            scaled_pixmap = self._bg_logo_pixmap.scaled(
                int(max_w),
                int(max_h),
                QtCore.Qt.KeepAspectRatio,
                QtCore.Qt.SmoothTransformation
            )

            # center-left positioning (cleaner balance)
            x = int(self.width() * 0.05)
            y = (self.height() - scaled_pixmap.height()) // 2

            painter.drawPixmap(x, y, scaled_pixmap)

    def closeEvent(self, event):
        if getattr(self, "_closing", False):
            event.accept()
            return

        if not self.prompt_save_before_close():
            event.ignore()
            return

        event.ignore()
        self._closing = True

        # Restore ControlPanel and return it to Home when setup closes
        app = QtWidgets.QApplication.instance()
        control_panel = None
        for widget in app.topLevelWidgets():
            if hasattr(widget, 'show_active_setup') and hasattr(widget, 'show_home'):
                control_panel = widget
                break

        if control_panel:
            if control_panel.isMinimized():
                control_panel.setWindowState(QtCore.Qt.WindowNoState)
            if hasattr(control_panel, "_from_setup"):
                control_panel._from_setup = False
            control_panel.show()
            control_panel.raise_()
            control_panel.activateWindow()
            control_panel.show_home()

        def finish_close():
            self.closed.emit()
            self.close()

        WindowAnimator.fade_out(self, callback=finish_close)

# ---------------- Load Setup Class ----------------
class LoadSetupWindow(QtWidgets.QMainWindow):
    closed = QtCore.Signal()

    def __init__(self, parent=None, pos=None):
            TitleBar = _titlebar_type()
            super().__init__()
            ensure_app_input_focus_manager()
            self.setWindowTitle(f"Load Setup — {AppConfig.APP_FULL}")
            self.parent = parent
            self._closing = False
            self.mode_window = None
            self._mode_launch_path = ""
            self.single_mode = SingleMode(self)
            self.sandbox_mode = SandboxMode(self)

            self.setWindowFlags(
                QtCore.Qt.FramelessWindowHint |
                QtCore.Qt.NoDropShadowWindowHint |
                QtCore.Qt.WindowStaysOnTopHint |
                QtCore.Qt.WindowMinimizeButtonHint
            )

            self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
            self._base_pos = self.pos()

            if pos:
                self.setGeometry(pos.x(), pos.y(), 500, 360)
            else:
                self.setGeometry(250, 200, 500, 360)

            # ---- CENTRAL ----
            central = QtWidgets.QWidget(self)
            central.setAttribute(QtCore.Qt.WA_TranslucentBackground)
            self.setCentralWidget(central)

            layout = QtWidgets.QVBoxLayout(central)
            layout.setContentsMargins(10, 10, 10, 10)
            layout.setSpacing(3)

            # ---- TITLE BAR ----
            self.title_bar = TitleBar(self, title_text="Load Setup", is_sub_window=True)
            layout.addWidget(self.title_bar)

            self.title_bar.close_btn.clicked.disconnect()
            self.title_bar.close_btn.clicked.connect(self.close)

            # ---- CONTENT ----
            content = QtWidgets.QVBoxLayout()
            content.setContentsMargins(20, 10, 20, 10)
            content.setSpacing(3)

            note = QtWidgets.QLabel(
                    "All setups are stored inside the 'Data/Setups' folder inside this program.\nYou can manage files directly if needed."
            )
            note.setAlignment(QtCore.Qt.AlignCenter)
            note.setStyleSheet("color: rgba(255,255,255,180); font: 9pt 'Times New Roman';")

            content.addWidget(note)
            content.setSpacing(8)


            # ---- SCROLL ----
            self.scroll = QtWidgets.QScrollArea()
            self.scroll.setWidgetResizable(True)
            self.scroll.setStyleSheet("""
                QScrollArea {
                    background: rgba(0, 0, 0, 128);
                    border-radius: 6px;
                    border: none;
                }

                QScrollArea > QWidget > QWidget {
                    background: transparent;
                }

                QScrollBar:vertical {
                    background: rgba(0,0,0,120);
                    width: 8px;
                    margin: 2px;
                    border-radius: 4px;
                }
                QScrollBar::handle:vertical {
                    background: rgba(255,255,255,140);
                    border-radius: 4px;
                }
            """)

            self.container = QtWidgets.QWidget()
            self.scroll_layout = QtWidgets.QVBoxLayout(self.container)
            self.scroll_layout.setContentsMargins(10, 10, 10, 10)
            self.scroll_layout.setSpacing(6)

            self.scroll.setWidget(self.container)
            content.addWidget(self.scroll)

            layout.addLayout(content)

            self.refresh_list()

    # ---- SAME GRADIENT ----
    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        rect = self.rect()

        grad = QtGui.QLinearGradient(0, 0, self.width(), self.height())
        grad.setColorAt(0, QtGui.QColor("#0f0c29"))
        grad.setColorAt(0.45, QtGui.QColor("#400071"))
        grad.setColorAt(1, QtGui.QColor("#24243e"))

        painter.setBrush(grad)
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawRoundedRect(rect, 14, 14)

    def changeEvent(self, event):
        if event.type() == QtCore.QEvent.WindowStateChange:

            # --- when minimizing ---
            if self.windowState() & QtCore.Qt.WindowMinimized:
                self._was_minimized = True

            # --- when restoring ---
            elif getattr(self, "_was_minimized", False):
                self._was_minimized = False

                # 🔥 force proper restore (important for frameless)
                self.setWindowState(QtCore.Qt.WindowNoState)
                self.show()
                self.raise_()
                self.activateWindow()

                # 🔥 only animate if not closing
                if not getattr(self, "_closing", False):
                    WindowAnimator.restore(self)

        super().changeEvent(event)

    closed = QtCore.Signal()  # 🔥 ADD THIS

    def closeEvent(self, event):
        if getattr(self, "_closing", False):
            event.accept()
            return

        event.ignore()
        self._closing = True

        def finish_close():
            self.closed.emit()  # 🔥 RETURN TO MAIN
            self.close()

        WindowAnimator.fade_out(self, callback=finish_close)
        
    def refresh_list(self):
        # clear old
        for i in reversed(range(self.scroll_layout.count())):
            item = self.scroll_layout.itemAt(i).widget()
            if item:
                item.deleteLater()

        files = SetupManager.list_setups()

        if not files:
            empty = QtWidgets.QLabel("No setups found.")
            empty.setAlignment(QtCore.Qt.AlignCenter)
            empty.setStyleSheet("color: rgba(255,255,255,150);")
            self.scroll_layout.addWidget(empty)
            return

        for path in files:
            try:
                data = SetupManager.load(path)
            except Exception:
                data = {"name": os.path.splitext(os.path.basename(path))[0], "mode": "invalid"}
            self.scroll_layout.addWidget(self.create_item(path, data))

        self.scroll_layout.addStretch()


    def create_item(self, path, data):
        box = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(box)
        layout.setContentsMargins(10, 6, 10, 6)

        name = QtWidgets.QLabel(data.get("name", "Unknown"))
        name.setStyleSheet("color: white; font: 10pt 'Times New Roman';")

        loadable = SetupManager.is_loadable_data(data)
        mode_text = data.get("mode", "unknown") if loadable else "invalid"
        mode = QtWidgets.QLabel(f"[{mode_text}]")
        mode.setStyleSheet("color: rgba(255,255,255,140); font: 9pt;")

        load_btn = QtWidgets.QPushButton("Load")
        rename_btn = QtWidgets.QPushButton("Rename")
        delete_btn = QtWidgets.QPushButton("Delete")

        # 🔥 SAME STYLE AS YOUR UI
        for btn in (load_btn, rename_btn, delete_btn):
            btn.setFixedHeight(28)
            btn.setFixedWidth(50)
            btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255,255,255,30);
                    color: white;
                    border-radius: 6px;
                    font: 8pt "Times New Roman";
                }
                QPushButton:hover {
                    background: rgba(255,255,255,60);
                }
                QPushButton:disabled {
                    background: rgba(255,255,255,12);
                    color: rgba(255,255,255,90);
                }
            """)

        load_btn.setEnabled(loadable)
        load_btn.clicked.connect(lambda: self.load_setup(path, data))
        rename_btn.clicked.connect(lambda: self.rename_setup(path))
        delete_btn.clicked.connect(lambda: self.delete_setup(path))

        layout.addWidget(name)
        layout.addWidget(mode)
        layout.addStretch()
        layout.addWidget(load_btn)
        layout.addWidget(rename_btn)
        layout.addWidget(delete_btn)

        return box
    
    def load_setup(self, path, data):
        mode = data.get("mode")
        self._mode_launch_path = path

        if mode == "single":
            self.single_mode.start()
        elif mode == "sandbox":
            self.sandbox_mode.start()
        else:
            print("Invalid mode")
            return

        self.close()

    def delete_setup(self, path):
        SetupManager.delete(path)
        self.refresh_list()

    def _flash_warning(self):
        try:
            winsound.MessageBeep()
        except Exception:
            try:
                winsound.Beep(920, 180)
            except Exception:
                pass
        base_pos = self.pos()
        anim = QtCore.QSequentialAnimationGroup(self)
        for offset in (-8, 8, -6, 6, -3, 3, 0):
            move_anim = QtCore.QPropertyAnimation(self, b"pos")
            move_anim.setDuration(36)
            move_anim.setStartValue(self.pos())
            move_anim.setEndValue(base_pos + QtCore.QPoint(offset, 0))
            anim.addAnimation(move_anim)
        self._warn_anim = anim
        anim.start()

    def rename_setup(self, path):
        current_data = SetupManager.load(path)
        current_name = str(current_data.get("name", "")).strip()
        text, ok = QtWidgets.QInputDialog.getText(
            self,
            "Rename Setup",
            "New setup name:",
            QtWidgets.QLineEdit.Normal,
            current_name,
        )
        if not ok:
            return
        new_name = str(text or "").strip()
        if not new_name:
            self._flash_warning()
            return
        try:
            SetupManager.rename(path, new_name)
        except FileExistsError:
            self._flash_warning()
            return
        except Exception:
            self._flash_warning()
            return
        self.refresh_list()

    def moveEvent(self, event):
        if not getattr(self, "_animating", False):
            self._base_pos = self.pos()
        super().moveEvent(event)

# ---------------- Virtual Key Map ----------------
VK_MAP = {
    "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73,
    "F5": 0x74, "F6": 0x75, "F7": 0x76, "F8": 0x77,
    "F9": 0x78, "F10": 0x79, "F11": 0x7A, "F12": 0x7B,
    "DELETE": 0x2E, "INSERT": 0x2D, "HOME": 0x24, "END": 0x23,
    "PAGEUP": 0x21, "PAGEDOWN": 0x22,
    "SPACE": 0x20, "TAB": 0x09, "ENTER": 0x0D, "ESC": 0x1B,
    "UP": 0x26, "DOWN": 0x28, "LEFT": 0x25, "RIGHT": 0x27,
    "`": 0xC0, "-": 0xBD, "=": 0xBB, "[": 0xDB, "]": 0xDD,
    "\\": 0xDC, ";": 0xBA, "'": 0xDE, ",": 0xBC, ".": 0xBE, "/": 0xBF,
    "PLUS": 0xBB, "ASTERISK": 0x6A,
    "NUM0": 0x60, "NUM1": 0x61, "NUM2": 0x62, "NUM3": 0x63, "NUM4": 0x64,
    "NUM5": 0x65, "NUM6": 0x66, "NUM7": 0x67, "NUM8": 0x68, "NUM9": 0x69,
    "NUMPLUS": 0x6B, "NUMMINUS": 0x6D, "NUMASTERISK": 0x6A, "NUMSLASH": 0x6F,
    "NUMDOT": 0x6E, "NUMENTER": 0x0D,
}

for i in range(10):
    VK_MAP[str(i)] = 0x30 + i

for i in range(26):
    VK_MAP[chr(ord("A") + i)] = 0x41 + i

MODIFIER_VK_MAP = {
    "CTRL": (0xA2, 0xA3),
    "ALT": (0xA4, 0xA5),
    "SHIFT": (0xA0, 0xA1),
}

# ---------------- Auto Click Worker ----------------
class AutoClickWorker(SharedWorkerHelper, QtCore.QThread):
    stopped = QtCore.Signal()
    clicked = QtCore.Signal(int, int)
    click_started = QtCore.Signal(int, int)
    click_finished = QtCore.Signal(int, int)

    def __init__(
        self,
        x,
        y,
        click_delay_ms,
        hold_ms,
        click_randomness,
        use_real_click=False,
        mouse_button="left",
        repeat_mode="until_stop",
        repeat_target=0,
        repeat_duration_seconds=0,
        overlay_hwnds=None,
    ):
        super().__init__()

        self._lock = threading.Lock()
        self.x = x
        self.y = y

        self.base_interval = max(1, click_delay_ms) / 1000.0
        self.hold_time = max(0, hold_ms) / 1000.0
        self.click_randomness = click_randomness
        self.use_real_click = use_real_click
        self.mouse_button = (mouse_button or "left").lower()
        self.repeat_mode = repeat_mode or "until_stop"
        self.repeat_target = max(0, int(repeat_target or 0))
        self.repeat_duration_seconds = max(0.0, float(repeat_duration_seconds or 0))
        self._overlay_hwnds = frozenset(overlay_hwnds or ())
        self._cached_hwnd = None
        self._cached_hwnd_pos = None
        self._background_move_toggle = False

        self._running = False

    def _button_messages(self):
        return super()._button_messages(self.mouse_button)

    def _resolve_target_hwnd(self, click_x: int, click_y: int):
        cached_hwnd = getattr(self, "_cached_hwnd", None)
        cached_pos = getattr(self, "_cached_hwnd_pos", None)
        if cached_hwnd and cached_pos is not None:
            try:
                if (
                    win32gui.IsWindow(cached_hwnd)
                    and win32gui.IsWindowVisible(cached_hwnd)
                    and abs(int(click_x) - int(cached_pos[0])) <= 24
                    and abs(int(click_y) - int(cached_pos[1])) <= 24
                ):
                    return cached_hwnd
            except Exception:
                self._cached_hwnd = None
                self._cached_hwnd_pos = None
        hwnd = super()._resolve_target_hwnd(click_x, click_y, ignored_hwnds=self._overlay_hwnds, descend_to_child=True)
        self._cached_hwnd = hwnd
        self._cached_hwnd_pos = (int(click_x), int(click_y)) if hwnd else None
        return hwnd

    def _post_click(self, click_x: int, click_y: int, hold_time: float):
        """Send a background click to the window under the marker without moving the real cursor."""
        try:
            hwnd = self._resolve_target_hwnd(click_x, click_y)
            if not hwnd:
                return False

            client_x, client_y = win32gui.ScreenToClient(hwnd, (click_x, click_y))
            lparam = ((client_y & 0xFFFF) << 16) | (client_x & 0xFFFF)
            down_msg, up_msg, modifier = self._button_messages()

            if self.click_randomness:
                win32gui.PostMessage(hwnd, win32con.WM_MOUSEMOVE, 0, lparam)
            else:
                # Some targets ignore repeated background clicks when the hover point never changes.
                # Nudge the hover by 1px and then move back so exact-position clicks still register.
                wiggle_dx = -1 if self._background_move_toggle else 1
                self._background_move_toggle = not self._background_move_toggle
                hover_x = click_x + wiggle_dx
                hover_y = click_y
                hover_client_x, hover_client_y = win32gui.ScreenToClient(hwnd, (hover_x, hover_y))
                hover_lparam = ((hover_client_y & 0xFFFF) << 16) | (hover_client_x & 0xFFFF)
                win32gui.PostMessage(hwnd, win32con.WM_MOUSEMOVE, 0, hover_lparam)
                win32gui.PostMessage(hwnd, win32con.WM_MOUSEMOVE, 0, lparam)
            self.click_started.emit(click_x, click_y)
            win32gui.PostMessage(
                hwnd,
                down_msg,
                modifier,
                lparam,
            )
            self._sleep_until(time.perf_counter() + hold_time)
            win32gui.PostMessage(hwnd, up_msg, 0, lparam)
            self.click_finished.emit(click_x, click_y)
            return True
        except Exception:
            return False

    def _real_click(self, click_x: int, click_y: int, hold_time: float):
        try:
            self.click_started.emit(click_x, click_y)
            pyautogui.mouseDown(button=self.mouse_button)
            self._sleep_until(time.perf_counter() + hold_time)
            if not self._running:
                pyautogui.mouseUp(button=self.mouse_button)
                self.click_finished.emit(click_x, click_y)
                return False
            pyautogui.mouseUp(button=self.mouse_button)
            self.click_finished.emit(click_x, click_y)
            return True
        except Exception:
            return False

    def _sleep_until(self, target_time: float):
        return super()._sleep_until(target_time, coarse_threshold=0.002, coarse_ratio=0.5, coarse_cap=0.01, fine_sleep=0.0005)

    def start_clicking(self):
        self._running = True
        if not self.isRunning():
            self.start()

    def stop_clicking(self):
        self._running = False

    def stop(self):
        self._running = False

    def update_target(self, x, y):
        with self._lock:
            self.x = x
            self.y = y
            self._cached_hwnd = None
            self._cached_hwnd_pos = None

    def run(self):
        self._running = True
        drift = 0.0
        completed_clicks = 0
        started_at = time.perf_counter()

        while self._running:
            if self.repeat_mode == "repeat_times" and self.repeat_target > 0 and completed_clicks >= self.repeat_target:
                break
            if self.repeat_mode == "repeat_timer" and self.repeat_duration_seconds > 0:
                if (time.perf_counter() - started_at) >= self.repeat_duration_seconds:
                    break

            cycle_start = time.perf_counter()

            if self.click_randomness:
                interval = self.base_interval * random.uniform(0.9, 1.1)
            else:
                interval = self.base_interval
            interval = max(0.001, interval)

            hold_time = max(0.0, self.hold_time)
            with self._lock:
                click_x = self.x
                click_y = self.y

            if self.click_randomness:
                click_x += random.randint(-4, 4)
                click_y += random.randint(-4, 4)

            if self.use_real_click:
                clicked = self._real_click(click_x, click_y, hold_time)
            else:
                clicked = self._post_click(click_x, click_y, hold_time)
            if not self._running:
                break
            if clicked:
                completed_clicks += 1
                self.clicked.emit(click_x, click_y)

            elapsed = time.perf_counter() - cycle_start
            sleep_for = max(0.001, interval - elapsed - drift)
            before_sleep = time.perf_counter()
            self._sleep_until(before_sleep + sleep_for)
            drift = (time.perf_counter() - before_sleep) - sleep_for

        # 🔥 IMPORTANT: notify UI when stopped
        self.stopped.emit()

# ---------------- Keybind Listener ----------------
class KeybindListener(QtCore.QObject):
    """Polls win32api.GetAsyncKeyState on a 30ms timer. Emits action name on key-down edge."""
    triggered = QtCore.Signal(str)

    def __init__(self, keybinds: dict, parent=None):
        super().__init__(parent)
        self.keybinds = keybinds   # {"Execute": "F1", ...}
        self._prev: dict = {}

        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.start(30)

    def _poll(self):
        for action, key_name in self.keybinds.items():
            modifiers, main_key = split_keybind(key_name)
            vk = VK_MAP.get(main_key.upper())
            if vk is None:
                continue
            modifiers_pressed = True
            for modifier in modifiers:
                vk_group = MODIFIER_VK_MAP.get(modifier)
                if not vk_group:
                    continue
                if not any(win32api.GetAsyncKeyState(mod_vk) & 0x8000 for mod_vk in vk_group):
                    modifiers_pressed = False
                    break

            pressed = modifiers_pressed and bool(win32api.GetAsyncKeyState(vk) & 0x8000)
            if pressed and not self._prev.get(action, False):
                self.triggered.emit(action)
            self._prev[action] = pressed

    def update_keybinds(self, keybinds: dict):
        self.keybinds = keybinds
        self._prev.clear()

    def stop(self):
        self._timer.stop()


class ScreenEdgeFailsafeMonitor(QtCore.QThread):
    triggered = QtCore.Signal(str)

    def __init__(self, failsafe: dict | None = None, parent=None):
        super().__init__(parent)
        self._lock = threading.Lock()
        self._failsafe = dict(failsafe or {})
        self._running = False

    def configure(self, failsafe: dict):
        with self._lock:
            self._failsafe = dict(failsafe or {})

    def stop(self):
        self._running = False

    def _monitor_bounds(self, x: int, y: int):
        try:
            handle = win32api.MonitorFromPoint((int(x), int(y)), win32con.MONITOR_DEFAULTTONEAREST)
            info = win32api.GetMonitorInfo(handle)
            left, top, right, bottom = info.get("Monitor", (0, 0, 1, 1))
            return int(left), int(top), int(right), int(bottom)
        except Exception:
            screen = QtWidgets.QApplication.primaryScreen()
            if screen is None:
                return 0, 0, 1, 1
            geom = screen.geometry()
            return geom.left(), geom.top(), geom.right() + 1, geom.bottom() + 1

    def run(self):
        self._running = True
        while self._running:
            with self._lock:
                failsafe = dict(self._failsafe)

            if not failsafe.get("enabled", True):
                self.msleep(25)
                continue

            try:
                x, y = win32api.GetCursorPos()
            except Exception:
                self.msleep(10)
                continue

            left, top, right, bottom = self._monitor_bounds(x, y)
            width = max(1, int(right - left))
            height = max(1, int(bottom - top))
            top_px = max(0, min(height, int(failsafe.get("top_px", 50))))
            bottom_px = max(0, min(height, int(failsafe.get("bottom_px", 50))))
            left_px = max(0, min(width, int(failsafe.get("left_px", 50))))
            right_px = max(0, min(width, int(failsafe.get("right_px", 50))))

            edge = ""
            if y <= (top + top_px):
                edge = "top"
            elif y >= ((bottom - 1) - bottom_px):
                edge = "bottom"
            elif x <= (left + left_px):
                edge = "left"
            elif x >= ((right - 1) - right_px):
                edge = "right"

            if edge:
                self._running = False
                self.triggered.emit(edge)
                break

            self.msleep(5)


class FailsafePreviewWidget(QtWidgets.QWidget):
    valuesChanged = QtCore.Signal(dict)

    def __init__(self, screen_width: int, screen_height: int, parent=None):
        super().__init__(parent)
        self._screen_width = max(1, int(screen_width))
        self._screen_height = max(1, int(screen_height))
        self._values = {
            "enabled": True,
            "top_px": 50,
            "bottom_px": 50,
            "left_px": 50,
            "right_px": 50,
        }
        self._drag_edge = ""
        self._highlight_edge = ""
        self._bar_thickness = 10
        self.setMinimumHeight(280)
        self.setMouseTracking(True)

    def _clamp_values(self, values: dict):
        return {
            "enabled": bool(values.get("enabled", True)),
            "top_px": max(0, min(self._screen_height, int(values.get("top_px", 50)))),
            "bottom_px": max(0, min(self._screen_height, int(values.get("bottom_px", 50)))),
            "left_px": max(0, min(self._screen_width, int(values.get("left_px", 50)))),
            "right_px": max(0, min(self._screen_width, int(values.get("right_px", 50)))),
        }

    def set_values(self, values: dict):
        self._values = self._clamp_values(values or {})
        self.update()

    def values(self):
        return dict(self._values)

    def set_enabled_state(self, enabled: bool):
        enabled = bool(enabled)
        if self._values.get("enabled", True) == enabled:
            return
        self._values["enabled"] = enabled
        self.valuesChanged.emit(self.values())
        self.update()

    def set_highlight_edge(self, edge: str):
        self._highlight_edge = str(edge or "").lower()
        self.update()

    def _preview_rect(self):
        margin = 26
        rect = self.rect().adjusted(margin, margin, -margin, -margin)
        target_ratio = self._screen_width / max(1, self._screen_height)
        width = rect.width()
        height = rect.height()
        current_ratio = width / max(1, height)
        if current_ratio > target_ratio:
            new_width = int(height * target_ratio)
            x = rect.center().x() - (new_width // 2)
            rect = QtCore.QRect(x, rect.top(), new_width, height)
        else:
            new_height = int(width / max(0.001, target_ratio))
            y = rect.center().y() - (new_height // 2)
            rect = QtCore.QRect(rect.left(), y, width, new_height)
        return rect

    def _scale(self):
        rect = self._preview_rect()
        return (
            rect,
            rect.width() / max(1, self._screen_width),
            rect.height() / max(1, self._screen_height),
        )

    def _bar_rect(self, edge: str):
        rect, scale_x, scale_y = self._scale()
        top_y = rect.top() + int(round(self._values["top_px"] * scale_y))
        bottom_y = rect.bottom() + 1 - int(round(self._values["bottom_px"] * scale_y))
        left_x = rect.left() + int(round(self._values["left_px"] * scale_x))
        right_x = rect.right() + 1 - int(round(self._values["right_px"] * scale_x))
        t = self._bar_thickness
        if edge == "top":
            return QtCore.QRect(rect.left(), top_y - (t // 2), rect.width(), t)
        if edge == "bottom":
            return QtCore.QRect(rect.left(), bottom_y - (t // 2), rect.width(), t)
        if edge == "left":
            return QtCore.QRect(left_x - (t // 2), rect.top(), t, rect.height())
        if edge == "right":
            return QtCore.QRect(right_x - (t // 2), rect.top(), t, rect.height())
        return QtCore.QRect()

    def _hit_edge(self, pos: QtCore.QPoint):
        for edge in ("top", "bottom", "left", "right"):
            if self._bar_rect(edge).adjusted(-8, -8, 8, 8).contains(pos):
                return edge
        return ""

    def _set_edge_value_from_pos(self, edge: str, pos: QtCore.QPoint):
        rect, scale_x, scale_y = self._scale()
        updated = self.values()
        if edge == "top":
            updated["top_px"] = max(0, min(self._screen_height, int(round((pos.y() - rect.top()) / max(0.001, scale_y)))))
        elif edge == "bottom":
            updated["bottom_px"] = max(0, min(self._screen_height, int(round((rect.bottom() + 1 - pos.y()) / max(0.001, scale_y)))))
        elif edge == "left":
            updated["left_px"] = max(0, min(self._screen_width, int(round((pos.x() - rect.left()) / max(0.001, scale_x)))))
        elif edge == "right":
            updated["right_px"] = max(0, min(self._screen_width, int(round((rect.right() + 1 - pos.x()) / max(0.001, scale_x)))))
        updated = self._clamp_values(updated)
        if updated != self._values:
            self._values = updated
            self.valuesChanged.emit(self.values())
            self.update()

    def mousePressEvent(self, event):
        if event.button() != QtCore.Qt.LeftButton or not self._values.get("enabled", True):
            return super().mousePressEvent(event)
        edge = self._hit_edge(event.pos())
        if edge:
            self._drag_edge = edge
            self._set_edge_value_from_pos(edge, event.pos())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_edge:
            self._set_edge_value_from_pos(self._drag_edge, event.pos())
            event.accept()
            return
        edge = self._hit_edge(event.pos()) if self._values.get("enabled", True) else ""
        if edge in ("top", "bottom"):
            self.setCursor(QtCore.Qt.SizeVerCursor)
        elif edge in ("left", "right"):
            self.setCursor(QtCore.Qt.SizeHorCursor)
        else:
            self.unsetCursor()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_edge = ""
        self.unsetCursor()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.fillRect(self.rect(), QtGui.QColor(0, 0, 0, 0))

        def draw_vertical_label(center_point, text, clockwise=True):
            painter.save()
            painter.translate(center_point)
            painter.rotate(90 if clockwise else -90)
            text_rect = QtCore.QRectF(-70, -12, 140, 24)
            painter.drawText(text_rect, QtCore.Qt.AlignCenter, text)
            painter.restore()

        preview = self._preview_rect()
        painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 36), 1))
        painter.setBrush(QtGui.QColor(16, 20, 34, 230))
        painter.drawRoundedRect(preview, 16, 16)

        if not self._values.get("enabled", True):
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(QtGui.QColor(120, 120, 120, 110))
            painter.drawRoundedRect(preview, 16, 16)
            painter.setPen(QtGui.QColor(255, 255, 255, 175))
            painter.setFont(QtGui.QFont("Times New Roman", 11, QtGui.QFont.Bold))
            painter.drawText(preview, QtCore.Qt.AlignCenter, "Failsafe Disabled")
            return

        rect, scale_x, scale_y = self._scale()
        top_h = int(round(self._values["top_px"] * scale_y))
        bottom_h = int(round(self._values["bottom_px"] * scale_y))
        left_w = int(round(self._values["left_px"] * scale_x))
        right_w = int(round(self._values["right_px"] * scale_x))

        safe_rect = rect.adjusted(left_w, top_h, -right_w, -bottom_h)
        blocked_color = QtGui.QColor(255, 72, 72, 78)
        safe_color = QtGui.QColor(84, 220, 150, 26)

        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(blocked_color)
        painter.drawRect(QtCore.QRect(rect.left(), rect.top(), rect.width(), top_h))
        painter.drawRect(QtCore.QRect(rect.left(), rect.bottom() + 1 - bottom_h, rect.width(), bottom_h))
        painter.drawRect(QtCore.QRect(rect.left(), rect.top(), left_w, rect.height()))
        painter.drawRect(QtCore.QRect(rect.right() + 1 - right_w, rect.top(), right_w, rect.height()))

        if safe_rect.width() > 0 and safe_rect.height() > 0:
            painter.setBrush(safe_color)
            painter.drawRoundedRect(safe_rect, 12, 12)

        label_font = QtGui.QFont("Consolas", 8)
        painter.setFont(label_font)
        painter.setPen(QtGui.QColor(255, 255, 255, 215))

        for edge in ("top", "bottom", "left", "right"):
            bar_rect = self._bar_rect(edge)
            active = edge == self._drag_edge or edge == self._highlight_edge
            fill = QtGui.QColor(255, 194, 86, 230) if active else QtGui.QColor(128, 213, 255, 220)
            painter.setBrush(fill)
            painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 180), 1))
            painter.drawRoundedRect(bar_rect, 6, 6)

        painter.setPen(QtGui.QColor(255, 255, 255, 225))
        painter.drawText(QtCore.QRect(rect.left(), rect.top() - 22, rect.width(), 18), QtCore.Qt.AlignCenter, f"{self._screen_width} x {self._screen_height}")
        painter.drawText(QtCore.QRect(rect.left(), rect.top() + top_h - 24, rect.width(), 18), QtCore.Qt.AlignCenter, f"Top {self._values['top_px']}px")
        painter.drawText(
            QtCore.QRect(rect.left(), rect.bottom() - bottom_h - 22, rect.width(), 18),
            QtCore.Qt.AlignCenter,
            f"Bottom {self._values['bottom_px']}px",
        )
        draw_vertical_label(
            QtCore.QPointF(rect.left() + max(16, left_w * 0.5), rect.center().y()),
            f"Left {self._values['left_px']}px",
            clockwise=False,
        )
        draw_vertical_label(
            QtCore.QPointF(rect.right() - max(16, right_w * 0.5), rect.center().y()),
            f"Right {self._values['right_px']}px",
            clockwise=True,
        )


class FailsafeEditOverlay(QtWidgets.QFrame):
    doneRequested = QtCore.Signal()
    valuesChanged = QtCore.Signal(dict)

    def __init__(self, screen_width: int, screen_height: int, default_px: int, parent=None):
        super().__init__(parent)
        self._default_px = max(0, int(default_px))
        self._current_values = {
            "enabled": True,
            "top_px": self._default_px,
            "bottom_px": self._default_px,
            "left_px": self._default_px,
            "right_px": self._default_px,
        }
        self.setObjectName("failsafeEditOverlay")
        self.setStyleSheet("""
            QFrame#failsafeEditOverlay {
                background: rgba(7, 10, 22, 238);
                border: none;
                border-radius: 16px;
            }
            QLabel {
                color: white;
            }
            QPushButton {
                background: rgba(255,255,255,18);
                color: white;
                border: none;
                border-radius: 6px;
                font: 9pt 'Times New Roman';
                padding: 5px 10px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,28);
            }
            QCheckBox {
                color: rgba(255,255,255,210);
                font: 9pt 'Times New Roman';
                spacing: 7px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: none;
                background: rgba(0,0,0,120);
            }
            QCheckBox::indicator:checked {
                background: #7a00ff;
                border: 1px solid #a64dff;
            }
        """)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(12)

        title = QtWidgets.QLabel("Screen Edge Failsafe")
        title.setStyleSheet("font: bold 15pt 'Times New Roman'; color: rgba(255,255,255,230);")
        root.addWidget(title)

        subtitle = QtWidgets.QLabel("Drag any edge inward to define the trigger zone. Entering a shaded edge zone during Single Mode execution will stop immediately.")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("font: 9pt 'Times New Roman'; color: rgba(255,255,255,168);")
        root.addWidget(subtitle)

        top_row = QtWidgets.QHBoxLayout()
        top_row.setSpacing(10)
        self._enabled_check = QtWidgets.QCheckBox("Enabled")
        self._enabled_check.setChecked(True)
        self._enabled_check.stateChanged.connect(self._on_enabled_changed)
        top_row.addWidget(self._enabled_check)
        top_row.addStretch()
        self._summary_label = QtWidgets.QLabel("")
        self._summary_label.setStyleSheet("font: 8.5pt 'Consolas'; color: rgba(255,255,255,188);")
        top_row.addWidget(self._summary_label)
        root.addLayout(top_row)

        self._preview = FailsafePreviewWidget(screen_width, screen_height, self)
        self._preview.valuesChanged.connect(self._on_preview_values_changed)
        root.addWidget(self._preview, 1)

        metrics = QtWidgets.QHBoxLayout()
        metrics.setSpacing(10)
        self._top_value = QtWidgets.QLabel("")
        self._bottom_value = QtWidgets.QLabel("")
        self._left_value = QtWidgets.QLabel("")
        self._right_value = QtWidgets.QLabel("")
        for label in (self._top_value, self._bottom_value, self._left_value, self._right_value):
            label.setAlignment(QtCore.Qt.AlignCenter)
            label.setMinimumHeight(26)
            label.setStyleSheet("background: rgba(255,255,255,12); border: none; border-radius: 6px; font: 8.5pt 'Consolas'; color: rgba(255,255,255,205);")
            metrics.addWidget(label)
        root.addLayout(metrics)

        button_row = QtWidgets.QHBoxLayout()
        button_row.setSpacing(8)
        button_row.addStretch()
        self._reset_btn = QtWidgets.QPushButton("Reset To Default")
        self._done_btn = QtWidgets.QPushButton("Done")
        self._reset_btn.clicked.connect(self._reset_defaults)
        self._done_btn.clicked.connect(self.doneRequested.emit)
        button_row.addWidget(self._reset_btn)
        button_row.addWidget(self._done_btn)
        root.addLayout(button_row)

        self._refresh_labels()

    def _refresh_labels(self):
        self._summary_label.setText(
            f"{'ON' if self._current_values.get('enabled', True) else 'OFF'}  |  "
            f"T {self._current_values['top_px']}  B {self._current_values['bottom_px']}  "
            f"L {self._current_values['left_px']}  R {self._current_values['right_px']}"
        )
        self._top_value.setText(f"Top: {self._current_values['top_px']}px")
        self._bottom_value.setText(f"Bottom: {self._current_values['bottom_px']}px")
        self._left_value.setText(f"Left: {self._current_values['left_px']}px")
        self._right_value.setText(f"Right: {self._current_values['right_px']}px")

    def _emit_values(self):
        self.valuesChanged.emit(self.values())

    def values(self):
        return dict(self._current_values)

    def set_values(self, values: dict):
        self._current_values = self._preview._clamp_values(values or {})
        blocked = self._enabled_check.blockSignals(True)
        self._enabled_check.setChecked(self._current_values.get("enabled", True))
        self._enabled_check.blockSignals(blocked)
        self._preview.set_values(self._current_values)
        self._refresh_labels()

    def set_highlight_edge(self, edge: str):
        self._preview.set_highlight_edge(edge)

    def _on_enabled_changed(self):
        self._current_values["enabled"] = self._enabled_check.isChecked()
        self._preview.set_enabled_state(self._current_values["enabled"])
        self._refresh_labels()
        self._emit_values()

    def _on_preview_values_changed(self, values: dict):
        self._current_values = dict(values)
        blocked = self._enabled_check.blockSignals(True)
        self._enabled_check.setChecked(self._current_values.get("enabled", True))
        self._enabled_check.blockSignals(blocked)
        self._refresh_labels()
        self._emit_values()

    def _reset_defaults(self):
        self.set_values({
            "enabled": True,
            "top_px": self._default_px,
            "bottom_px": self._default_px,
            "left_px": self._default_px,
            "right_px": self._default_px,
        })
        self._emit_values()


class ScreenEdgeFailsafeEditorDialog(QtWidgets.QDialog):
    def __init__(self, screen_geometry: QtCore.QRect, values: dict, default_px: int, highlight_edge: str = "", parent=None):
        super().__init__(parent)
        self._screen_geometry = QtCore.QRect(screen_geometry)
        self._screen_width = max(1, self._screen_geometry.width())
        self._screen_height = max(1, self._screen_geometry.height())
        self._default_px = max(0, int(default_px))
        self._values = self._clamp_values(values or {})
        self._original_values = dict(self._values)
        self._drag_edge = ""
        self._highlight_edge = str(highlight_edge or "").lower()
        self._bar_thickness = 14

        self.setModal(True)
        self.setWindowFlags(
            QtCore.Qt.Dialog |
            QtCore.Qt.FramelessWindowHint |
            QtCore.Qt.NoDropShadowWindowHint |
            QtCore.Qt.WindowStaysOnTopHint |
            QtCore.Qt.Tool
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setGeometry(self._screen_geometry)
        self.setMouseTracking(True)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)

        panel = QtWidgets.QFrame(self)
        panel.setObjectName("failsafeScreenPanel")
        panel.setStyleSheet("""
            QFrame#failsafeScreenPanel {
                background: rgba(8, 10, 24, 220);
                border: none;
                border-radius: 10px;
            }
            QLabel {
                color: white;
            }
            QPushButton {
                background: rgba(255,255,255,18);
                color: white;
                border: none;
                border-radius: 6px;
                font: 9pt 'Times New Roman';
                padding: 5px 12px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,28);
            }
        """)
        panel_width = min(760, max(520, self.width() - 120))
        panel.setGeometry(max(8, (self.width() - panel_width) // 2), 8, panel_width, 108)

        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(6)
        top_row = QtWidgets.QHBoxLayout()
        top_row.setSpacing(16)
        left_col = QtWidgets.QVBoxLayout()
        left_col.setSpacing(2)
        title = QtWidgets.QLabel("Editing Screen Failsafe")
        title.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        title.setStyleSheet("font: bold 13pt 'Times New Roman'; color: rgba(255,255,255,230);")
        left_col.addWidget(title)
        info = QtWidgets.QLabel("Drag the highlighted screen edges to set the new failsafe zone.")
        info.setWordWrap(True)
        info.setStyleSheet("font: 10pt 'Times New Roman'; color: rgba(255,255,255,200);")
        left_col.addWidget(info)
        top_row.addLayout(left_col, 1)
        button_row = QtWidgets.QGridLayout()
        button_row.setHorizontalSpacing(8)
        button_row.setVerticalSpacing(6)
        self._done_btn = QtWidgets.QPushButton("Done (Enter)")
        self._cancel_btn = QtWidgets.QPushButton("Cancel (Esc)")
        self._reset_btn = QtWidgets.QPushButton("Undo Changes (Alt)")
        self._default_btn = QtWidgets.QPushButton("Set Default (Ctrl)")
        for button in (self._done_btn, self._cancel_btn, self._reset_btn, self._default_btn):
            button.setFixedSize(130, 30)
        self._done_btn.clicked.connect(self.accept)
        self._cancel_btn.clicked.connect(self.reject)
        self._reset_btn.clicked.connect(self._reset_to_original)
        self._default_btn.clicked.connect(self._set_defaults)
        button_row.addWidget(self._done_btn, 0, 0)
        button_row.addWidget(self._cancel_btn, 0, 1)
        button_row.addWidget(self._reset_btn, 1, 0)
        button_row.addWidget(self._default_btn, 1, 1)
        top_row.addLayout(button_row, 0)
        layout.addLayout(top_row)

    def _clamp_values(self, values: dict):
        return {
            "enabled": bool(values.get("enabled", True)),
            "top_px": max(0, min(self._screen_height, int(values.get("top_px", 50)))),
            "bottom_px": max(0, min(self._screen_height, int(values.get("bottom_px", 50)))),
            "left_px": max(0, min(self._screen_width, int(values.get("left_px", 50)))),
            "right_px": max(0, min(self._screen_width, int(values.get("right_px", 50)))),
        }

    def values(self):
        return dict(self._values)

    def _bar_rect(self, edge: str):
        top_y = int(self._values["top_px"])
        bottom_y = self.height() - int(self._values["bottom_px"])
        left_x = int(self._values["left_px"])
        right_x = self.width() - int(self._values["right_px"])
        t = self._bar_thickness
        if edge == "top":
            return QtCore.QRect(0, max(0, top_y - (t // 2)), self.width(), t)
        if edge == "bottom":
            return QtCore.QRect(0, max(0, bottom_y - (t // 2)), self.width(), t)
        if edge == "left":
            return QtCore.QRect(max(0, left_x - (t // 2)), 0, t, self.height())
        if edge == "right":
            return QtCore.QRect(max(0, right_x - (t // 2)), 0, t, self.height())
        return QtCore.QRect()

    def _hit_edge(self, pos: QtCore.QPoint):
        for edge in ("top", "bottom", "left", "right"):
            if self._bar_rect(edge).adjusted(-10, -10, 10, 10).contains(pos):
                return edge
        return ""

    def _set_edge_value(self, edge: str, pos: QtCore.QPoint):
        updated = self.values()
        if edge == "top":
            updated["top_px"] = max(0, min(self._screen_height, pos.y()))
        elif edge == "bottom":
            updated["bottom_px"] = max(0, min(self._screen_height, self.height() - pos.y()))
        elif edge == "left":
            updated["left_px"] = max(0, min(self._screen_width, pos.x()))
        elif edge == "right":
            updated["right_px"] = max(0, min(self._screen_width, self.width() - pos.x()))
        updated = self._clamp_values(updated)
        if updated != self._values:
            self._values = updated
            self.update()

    def mousePressEvent(self, event):
        if not self._values.get("enabled", True):
            return super().mousePressEvent(event)
        if event.button() == QtCore.Qt.LeftButton:
            edge = self._hit_edge(event.pos())
            if edge:
                self._drag_edge = edge
                self._set_edge_value(edge, event.pos())
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_edge:
            self._set_edge_value(self._drag_edge, event.pos())
            event.accept()
            return
        edge = self._hit_edge(event.pos()) if self._values.get("enabled", True) else ""
        if edge in ("top", "bottom"):
            self.setCursor(QtCore.Qt.SizeVerCursor)
        elif edge in ("left", "right"):
            self.setCursor(QtCore.Qt.SizeHorCursor)
        else:
            self.unsetCursor()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_edge = ""
        self.unsetCursor()
        super().mouseReleaseEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        self.raise_()
        self.activateWindow()
        self.setFocus(QtCore.Qt.ActiveWindowFocusReason)
        QtCore.QTimer.singleShot(0, lambda: self.setFocus(QtCore.Qt.ActiveWindowFocusReason))

    def keyPressEvent(self, event):
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter):
            self.accept()
            return
        if event.key() == QtCore.Qt.Key_Escape:
            self.reject()
            return
        if event.key() == QtCore.Qt.Key_Alt:
            self._reset_to_original()
            event.accept()
            return
        if event.key() == QtCore.Qt.Key_Control:
            self._set_defaults()
            event.accept()
            return
        super().keyPressEvent(event)

    def reject(self):
        self._values = dict(self._original_values)
        super().reject()

    def _reset_to_original(self):
        self._values = dict(self._original_values)
        self.update()

    def _set_defaults(self):
        enabled = bool(self._values.get("enabled", True))
        self._values = {
            "enabled": enabled,
            "top_px": self._default_px,
            "bottom_px": self._default_px,
            "left_px": self._default_px,
            "right_px": self._default_px,
        }
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.fillRect(self.rect(), QtGui.QColor(0, 0, 0, 0))

        def draw_vertical_label(center_point, text, rotation):
            painter.save()
            painter.translate(center_point)
            painter.rotate(rotation)
            painter.drawText(QtCore.QRectF(-90, -14, 180, 28), QtCore.Qt.AlignCenter, text)
            painter.restore()

        if not self._values.get("enabled", True):
            painter.fillRect(self.rect(), QtGui.QColor(20, 24, 36, 110))
            painter.setPen(QtGui.QColor(255, 255, 255, 215))
            painter.setFont(QtGui.QFont("Times New Roman", 18, QtGui.QFont.Bold))
            painter.drawText(self.rect(), QtCore.Qt.AlignCenter, "Failsafe Disabled")
            return

        top_h = int(self._values["top_px"])
        bottom_h = int(self._values["bottom_px"])
        left_w = int(self._values["left_px"])
        right_w = int(self._values["right_px"])
        safe_rect = self.rect().adjusted(left_w, top_h, -right_w, -bottom_h)

        blocked_color = QtGui.QColor(255, 76, 76, 78)
        safe_color = QtGui.QColor(96, 220, 162, 26)
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(blocked_color)
        painter.drawRect(0, 0, self.width(), top_h)
        painter.drawRect(0, self.height() - bottom_h, self.width(), bottom_h)
        painter.drawRect(0, 0, left_w, self.height())
        painter.drawRect(self.width() - right_w, 0, right_w, self.height())

        if safe_rect.width() > 0 and safe_rect.height() > 0:
            painter.setBrush(safe_color)
            painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 55), 2, QtCore.Qt.DashLine))
            painter.drawRect(safe_rect)

        painter.setFont(QtGui.QFont("Consolas", 10))
        for edge in ("top", "bottom", "left", "right"):
            bar_rect = self._bar_rect(edge)
            active = edge == self._drag_edge or edge == self._highlight_edge
            painter.setBrush(QtGui.QColor(255, 196, 88, 230) if active else QtGui.QColor(126, 214, 255, 220))
            painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 200), 1))
            painter.drawRoundedRect(bar_rect, 8, 8)

        painter.setPen(QtGui.QColor(255, 255, 255, 225))
        painter.drawText(QtCore.QRect(20, max(96, top_h + 8), self.width() - 40, 24), QtCore.Qt.AlignCenter, f"Top {top_h}px")
        painter.drawText(
            QtCore.QRect(20, max(96, self.height() - bottom_h - 34), self.width() - 40, 24),
            QtCore.Qt.AlignCenter,
            f"Bottom {bottom_h}px",
        )
        draw_vertical_label(
            QtCore.QPointF(max(22, left_w + 18), self.height() / 2),
            f"Left {left_w}px",
            -90,
        )
        draw_vertical_label(
            QtCore.QPointF(self.width() - max(22, right_w + 18), self.height() / 2),
            f"Right {right_w}px",
            90,
        )


class FailsafePropertiesDialog(QtWidgets.QDialog):
    def __init__(self, values: dict, default_px: int, screen_geometry: QtCore.QRect, highlight_edge: str = "", parent=None):
        super().__init__(parent)
        self._values = dict(values or {})
        self._default_px = max(0, int(default_px))
        self._screen_geometry = QtCore.QRect(screen_geometry)
        self._highlight_edge = str(highlight_edge or "").lower()

        self.setModal(True)
        self.setWindowTitle("Screen Edge Failsafe")
        self.setWindowFlags(
            QtCore.Qt.Dialog |
            QtCore.Qt.FramelessWindowHint |
            QtCore.Qt.NoDropShadowWindowHint |
            QtCore.Qt.WindowStaysOnTopHint
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.resize(360, 250)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        frame = QtWidgets.QFrame(self)
        frame.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0f0c29, stop:0.45 #400071, stop:1 #24243e);
                border: none;
                border-radius: 10px;
            }
            QLabel { color: white; }
            QPushButton {
                background: rgba(255,255,255,16);
                color: white;
                border: none;
                border-radius: 4px;
                font: 9pt 'Times New Roman';
                padding: 4px 10px;
            }
            QPushButton:hover { background: rgba(255,255,255,28); }
            QCheckBox {
                color: rgba(255,255,255,210);
                font: 9pt 'Times New Roman';
                spacing: 6px;
            }
            QCheckBox::indicator {
                width: 14px; height: 14px;
                border-radius: 3px;
                border: none;
                background: rgba(0,0,0,100);
            }
            QCheckBox::indicator:checked {
                background: #7a00ff;
                border: 1px solid #a64dff;
            }
        """)
        root.addWidget(frame)

        layout = QtWidgets.QVBoxLayout(frame)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        title = QtWidgets.QLabel("Screen Edge Failsafe")
        title.setAlignment(QtCore.Qt.AlignCenter)
        title.setStyleSheet("font: bold 11pt 'Times New Roman'; color: rgba(255,255,255,230);")
        layout.addWidget(title)

        hint = QtWidgets.QLabel("Use on-screen editing to drag the real screen edges.")
        hint.setWordWrap(True)
        hint.setAlignment(QtCore.Qt.AlignCenter)
        hint.setStyleSheet("font: 8.5pt 'Times New Roman'; color: rgba(255,255,255,170);")
        layout.addWidget(hint)

        self._summary = QtWidgets.QLabel("")
        self._summary.setAlignment(QtCore.Qt.AlignCenter)
        self._summary.setWordWrap(True)
        self._summary.setStyleSheet("font: 9pt 'Consolas'; color: rgba(255,255,255,205);")
        layout.addWidget(self._summary)

        button_row = QtWidgets.QHBoxLayout()
        button_row.setSpacing(8)
        self._screen_btn = QtWidgets.QPushButton("Edit On Screen")
        self._reset_btn = QtWidgets.QPushButton("Reset")
        self._done_btn = QtWidgets.QPushButton("Done")
        self._cancel_btn = QtWidgets.QPushButton("Cancel")
        self._screen_btn.clicked.connect(self._edit_on_screen)
        self._reset_btn.clicked.connect(self._reset_defaults)
        self._done_btn.clicked.connect(self.accept)
        self._cancel_btn.clicked.connect(self.reject)
        button_row.addWidget(self._screen_btn)
        button_row.addWidget(self._reset_btn)
        button_row.addStretch()
        button_row.addWidget(self._cancel_btn)
        button_row.addWidget(self._done_btn)
        layout.addLayout(button_row)

        self._refresh_summary()

    def values(self):
        return dict(self._values)

    def _refresh_summary(self):
        self._summary.setText(
            f"Top {int(self._values.get('top_px', 0))}px\n"
            f"Bottom {int(self._values.get('bottom_px', 0))}px\n"
            f"Left {int(self._values.get('left_px', 0))}px\n"
            f"Right {int(self._values.get('right_px', 0))}px"
        )

    def _reset_defaults(self):
        enabled = bool(self._values.get("enabled", True))
        self._values = {
            "enabled": enabled,
            "top_px": self._default_px,
            "bottom_px": self._default_px,
            "left_px": self._default_px,
            "right_px": self._default_px,
        }
        self._refresh_summary()

    def _edit_on_screen(self):
        editor = ScreenEdgeFailsafeEditorDialog(
            self._screen_geometry,
            self._values,
            self._default_px,
            highlight_edge=self._highlight_edge,
            parent=None,
        )
        if editor.exec() == QtWidgets.QDialog.Accepted:
            self._values = editor.values()
            self._refresh_summary()


# ---------------- Single Mode UI ----------------
from Modes.single.logic import SingleMode, SingleModeLogicMixin
from Modes.single.ui import SingleModeUIMixin
from Modes.sandbox.logic import SandboxDataModel, SandboxExecutionWorker, SandboxMode, SandboxModeLogicMixin
from Modes.sandbox.ui import (
    SandboxCreateObjectDialog,
    SandboxHandleWidget,
    SandboxLineOverlay,
    SandboxModeUIMixin,
    SandboxOverlayController,
)


class SingleModeUI(SingleModeLogicMixin, SingleModeUIMixin, BaseSetupUI):
    pass


class SandboxModeUI(SandboxModeLogicMixin, SandboxModeUIMixin, BaseSetupUI):
    pass

