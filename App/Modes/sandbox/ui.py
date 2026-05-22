from PySide6 import QtWidgets, QtCore, QtGui
import copy
import ctypes
import importlib
import time
import win32api
import win32con
import win32gui

from Config.Manager import ConfigManager
from UI.components.spinbox import HorizontalStepSpinBox


CLICK_RANDOMNESS_KEY = "click_randomness"
MOUSE_BEHAVIOR_KEY = "mouse_behavior"
MOUSE_BEHAVIOR_OPTIONS = [
    ("Default", "default"),
    ("Teleport", "teleport"),
    ("Background", "python"),
]


def _event_global_pos(event):
    if hasattr(event, "globalPosition"):
        return event.globalPosition().toPoint()
    return event.globalPos()


def _suppress_native_window_chrome(hwnd):
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
        ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        ex_style |= win32con.WS_EX_TOOLWINDOW | win32con.WS_EX_LAYERED | win32con.WS_EX_NOACTIVATE
        win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex_style)
        win32gui.SetWindowPos(
            hwnd,
            0,
            0,
            0,
            0,
            0,
            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE | win32con.SWP_FRAMECHANGED,
        )
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


def _main_window_module():
    return importlib.import_module("UI.main_window")


def make_noactivate_topmost(widget):
    return _main_window_module().make_noactivate_topmost(widget)


def _keybind_capture_dialog_type():
    return _main_window_module().KeybindCaptureDialog


def read_click_randomness(source, default=True):
    return _main_window_module().read_click_randomness(source, default)


def read_mouse_behavior(source, default="default"):
    return _main_window_module().read_mouse_behavior(source, default)


class InspectorSplitterHandle(QtWidgets.QSplitterHandle):
    def __init__(self, orientation, parent):
        super().__init__(orientation, parent)
        self.setAttribute(QtCore.Qt.WA_Hover, True)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 10, 0, 10)
        layout.setSpacing(3)
        layout.addStretch()

        self._grip = QtWidgets.QLabel("||", self)
        self._grip.setAlignment(QtCore.Qt.AlignCenter)
        self._grip.setStyleSheet("""
            QLabel {
                color: rgba(255,255,255,180);
                font: bold 9pt 'Consolas';
                background: rgba(0,0,0,45);
                border: none;
                border-radius: 6px;
                padding: 4px 1px;
            }
        """)
        self._grip.setToolTip("Drag to resize panels")
        layout.addWidget(self._grip, 0, QtCore.Qt.AlignCenter)
        layout.addStretch()


class InspectorSplitter(QtWidgets.QSplitter):
    def createHandle(self):
        return InspectorSplitterHandle(self.orientation(), self)


class SandboxCreateObjectDialog(QtWidgets.QDialog):
    def __init__(self, allowed_types, target_options=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create Object")
        self.setModal(True)
        self.setWindowFlags(QtCore.Qt.Dialog | QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.resize(330, 330)
        self._target_options = list(target_options or [])

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        frame = QtWidgets.QFrame(self)
        frame.setStyleSheet("QFrame { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0f0c29, stop:0.45 #400071, stop:1 #24243e); border: none; border-radius: 8px; } QLabel { color: white; }")
        root.addWidget(frame)
        layout = QtWidgets.QVBoxLayout(frame)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)
        title = QtWidgets.QLabel("Create New Object")
        title.setAlignment(QtCore.Qt.AlignCenter)
        title.setStyleSheet("font: bold 10pt 'Times New Roman';")
        layout.addWidget(title)
        self._type_combo = QtWidgets.QComboBox()
        self._type_combo.setStyleSheet("color: white; background: rgba(0,0,0,90); border: none; border-radius: 4px; padding: 4px;")
        for node_type in allowed_types:
            self._type_combo.addItem(node_type.title(), node_type)
        layout.addWidget(self._type_combo)
        self._name_edit = QtWidgets.QLineEdit()
        self._name_edit.setPlaceholderText("Object name")
        self._name_edit.setStyleSheet("color: white; background: rgba(0,0,0,90); border: none; border-radius: 4px; padding: 5px;")
        layout.addWidget(self._name_edit)

        self._form = QtWidgets.QFormLayout()
        self._form.setContentsMargins(0, 0, 0, 0)
        self._form.setSpacing(6)
        self._form.setLabelAlignment(QtCore.Qt.AlignLeft)
        layout.addLayout(self._form)

        self._type_combo.currentIndexChanged.connect(self._rebuild_form)
        self._rebuild_form()

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()
        create_btn = QtWidgets.QPushButton("Create")
        cancel_btn = QtWidgets.QPushButton("Cancel")
        for btn in (create_btn, cancel_btn):
            btn.setStyleSheet("QPushButton { background: rgba(255,255,255,16); color: white; border: none; border-radius: 4px; padding: 4px 8px; } QPushButton:hover { background: rgba(255,255,255,28); }")
        create_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(create_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _editor_style(self):
        return "color: white; background: rgba(0,0,0,90); border: none; border-radius: 4px; padding: 4px;"

    def _make_spin(self, value=0, minimum=0, maximum=99999):
        spin = HorizontalStepSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(int(value))
        spin.setStyleSheet(self._editor_style())
        return spin

    def _make_combo(self, items):
        combo = QtWidgets.QComboBox()
        combo.setStyleSheet(self._editor_style())
        for label, value in items:
            combo.addItem(label, value)
        return combo

    def _make_check(self, checked=False):
        box = QtWidgets.QCheckBox()
        box.setChecked(bool(checked))
        box.setStyleSheet("QCheckBox { color: white; }")
        return box

    def _clear_form(self):
        while self._form.rowCount():
            self._form.removeRow(0)

    def _add_form_row(self, label_text, widget):
        label = QtWidgets.QLabel(label_text)
        label.setStyleSheet("color: rgba(255,255,255,200); font: 8pt 'Times New Roman';")
        self._form.addRow(label, widget)

    def _rebuild_form(self):
        self._clear_form()
        node_type = self._type_combo.currentData() or "marker"
        self._extra_widgets = {}

        if node_type == "keybind":
            keybind_value = QtWidgets.QLabel("Not Set")
            keybind_value.setAlignment(QtCore.Qt.AlignCenter)
            keybind_value.setStyleSheet("color: white; background: rgba(0,0,0,92); border: none; border-radius: 4px; font: 8pt 'Consolas'; padding: 4px 6px;")
            keybind_btn = QtWidgets.QPushButton("Edit")
            keybind_btn.setFixedWidth(52)
            keybind_btn.setStyleSheet("QPushButton { background: rgba(255,255,255,16); color: white; border: none; border-radius: 4px; padding: 3px 8px; } QPushButton:hover { background: rgba(255,255,255,28); }")

            def open_keybind_capture():
                dialog = _keybind_capture_dialog_type()("", self)
                if dialog.exec() == QtWidgets.QDialog.Accepted and dialog.binding_text().strip():
                    keybind_value.setText(dialog.binding_text().strip())

            keybind_btn.clicked.connect(open_keybind_capture)
            keybind_host = QtWidgets.QWidget()
            keybind_layout = QtWidgets.QHBoxLayout(keybind_host)
            keybind_layout.setContentsMargins(0, 0, 0, 0)
            keybind_layout.setSpacing(6)
            keybind_layout.addWidget(keybind_value, 1)
            keybind_layout.addWidget(keybind_btn)
            desc = QtWidgets.QLineEdit()
            desc.setPlaceholderText("Description")
            desc.setStyleSheet(self._editor_style())
            target = self._make_combo([("None", "")] + self._target_options)
            teleport_back = self._make_check(True)
            self._extra_widgets = {
                "keybind": keybind_value,
                "description": desc,
                "target_id": target,
                "teleport_back": teleport_back,
            }
            self._add_form_row("Keybind", keybind_host)
            self._add_form_row("Description", desc)
            self._add_form_row("Target", target)
            self._add_form_row("Teleport Back", teleport_back)
            return

        if node_type == "marker":
            x, y = win32api.GetCursorPos()
            widgets = {
                "x": self._make_spin(x),
                "y": self._make_spin(y),
                "click_delay_ms": self._make_spin(200, 1),
                "mouse_hold_ms": self._make_spin(100, 0),
                "click_randomness": self._make_check(True),
                "mouse_button": self._make_combo([("Left", "left"), ("Right", "right"), ("Middle", "middle")]),
                MOUSE_BEHAVIOR_KEY: self._make_combo(MOUSE_BEHAVIOR_OPTIONS),
            }
            widgets[MOUSE_BEHAVIOR_KEY].setCurrentIndex(max(0, widgets[MOUSE_BEHAVIOR_KEY].findData("default")))
            self._extra_widgets = widgets
            self._add_form_row("Position X", widgets["x"])
            self._add_form_row("Position Y", widgets["y"])
            self._add_form_row("Delay", widgets["click_delay_ms"])
            self._add_form_row("Hold", widgets["mouse_hold_ms"])
            self._add_form_row("Click Randomness", widgets["click_randomness"])
            self._add_form_row("Mouse Button", widgets["mouse_button"])
            self._add_form_row("Mouse Behavoir", widgets[MOUSE_BEHAVIOR_KEY])
            return

        start_x, start_y = win32api.GetCursorPos()
        widgets = {
            "start_x": self._make_spin(start_x),
            "start_y": self._make_spin(start_y),
            "end_x": self._make_spin(start_x + 120),
            "end_y": self._make_spin(start_y),
            "click_delay_ms": self._make_spin(200, 1),
            "mouse_hold_ms": self._make_spin(100, 0),
            "mouse_button": self._make_combo([("Left", "left"), ("Right", "right"), ("Middle", "middle")]),
            MOUSE_BEHAVIOR_KEY: self._make_combo(MOUSE_BEHAVIOR_OPTIONS),
        }
        widgets[MOUSE_BEHAVIOR_KEY].setCurrentIndex(max(0, widgets[MOUSE_BEHAVIOR_KEY].findData("default")))
        self._extra_widgets = widgets
        self._add_form_row("Start X", widgets["start_x"])
        self._add_form_row("Start Y", widgets["start_y"])
        self._add_form_row("End X", widgets["end_x"])
        self._add_form_row("End Y", widgets["end_y"])
        self._add_form_row("Delay", widgets["click_delay_ms"])
        self._add_form_row("Hold", widgets["mouse_hold_ms"])
        self._add_form_row("Mouse Button", widgets["mouse_button"])
        self._add_form_row("Mouse Behavoir", widgets[MOUSE_BEHAVIOR_KEY])

    def values(self):
        node_type = self._type_combo.currentData() or "marker"
        extra = {}
        for key, widget in getattr(self, "_extra_widgets", {}).items():
            if isinstance(widget, QtWidgets.QSpinBox):
                extra[key] = int(widget.value())
            elif isinstance(widget, QtWidgets.QComboBox):
                extra[key] = widget.currentData()
            elif isinstance(widget, QtWidgets.QCheckBox):
                extra[key] = widget.isChecked()
            elif isinstance(widget, QtWidgets.QLabel):
                extra[key] = "" if widget.text() == "Not Set" else widget.text().strip()
            else:
                extra[key] = widget.text().strip()
        return (node_type, self._name_edit.text().strip(), extra)


class SandboxLineOverlay(QtWidgets.QWidget):
    def __init__(self):
        super().__init__(None)
        self._lines = []
        flags = QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint | QtCore.Qt.NoDropShadowWindowHint | QtCore.Qt.WindowStaysOnTopHint
        if hasattr(QtCore.Qt, "WindowTransparentForInput"):
            flags |= QtCore.Qt.WindowTransparentForInput
        self.setWindowFlags(flags)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.setWindowFlag(QtCore.Qt.WindowDoesNotAcceptFocus)
        self.setGeometry(QtWidgets.QApplication.primaryScreen().geometry())
        make_noactivate_topmost(self)

    def set_lines(self, lines):
        self._lines = list(lines)
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        for line in self._lines:
            start = QtCore.QPointF(line["start_x"], line["start_y"])
            end = QtCore.QPointF(line["end_x"], line["end_y"])
            grad = QtGui.QLinearGradient(start, end)
            grad.setColorAt(0.0, QtGui.QColor(255, 60, 60, 235))
            grad.setColorAt(0.55, QtGui.QColor(255, 120, 60, 170))
            grad.setColorAt(1.0, QtGui.QColor(255, 140, 60, 55))
            painter.setPen(QtGui.QPen(QtGui.QBrush(grad), 3.0, QtCore.Qt.SolidLine, QtCore.Qt.RoundCap))
            painter.drawLine(start, end)


class SandboxHandleWidget(QtWidgets.QWidget):
    moved = QtCore.Signal(str, str, int, int)
    clicked = QtCore.Signal(str, str)

    def __init__(self, node_id: str, point_key: str, color: QtGui.QColor, label_text: str):
        super().__init__(None)
        self.node_id = node_id
        self.point_key = point_key
        self._color = QtGui.QColor(color)
        self._label_text = label_text
        self._drag_pos = None
        self._interactive = True
        self._selected = False
        self._point_selected = False
        self._small_label = False
        self.resize(44, 44)
        self.setWindowFlags(QtCore.Qt.Tool | QtCore.Qt.FramelessWindowHint | QtCore.Qt.NoDropShadowWindowHint | QtCore.Qt.WindowStaysOnTopHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
        self.setWindowFlag(QtCore.Qt.WindowDoesNotAcceptFocus)
        make_noactivate_topmost(self)
        self._apply_shape()
        self._sync_window_style()

    def update_visual(self, color: QtGui.QColor, label_text: str, small_label: bool = False):
        center_x, center_y = self.center_pos()
        self._color = QtGui.QColor(color)
        self._label_text = label_text or ""
        self._small_label = bool(small_label)
        if self.point_key == "end":
            base_diameter = 34
        elif self.point_key == "start":
            base_diameter = 44 if self._small_label else 48
        else:
            base_diameter = 37 if self._small_label else 44
        diameter = ConfigManager.scale_marker_size(base_diameter)
        self.resize(diameter, diameter)
        self._apply_shape()
        self.move_center(center_x, center_y)
        self.setToolTip(self._label_text if self._label_text else "")
        self.update()

    def set_interactive(self, enabled: bool):
        self._interactive = enabled
        if not enabled:
            self._drag_pos = None
            try:
                self.releaseMouse()
            except Exception:
                pass
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, not enabled)
        self._sync_window_style()

    def set_selected(self, selected: bool, point_selected: bool = False):
        self._selected = bool(selected)
        self._point_selected = bool(point_selected)
        self.update()

    def move_center(self, x: int, y: int):
        self.move(int(round(x - self.width() / 2.0)), int(round(y - self.height() / 2.0)))

    def center_pos(self):
        return int(round(self.x() + self.width() / 2.0)), int(round(self.y() + self.height() / 2.0))

    def _apply_shape(self):
        region = QtGui.QRegion(self.rect().adjusted(1, 1, -1, -1), QtGui.QRegion.Ellipse)
        self.setMask(region)

    def _sync_window_style(self):
        try:
            hwnd = int(self.winId())
            _suppress_native_window_chrome(hwnd)
            ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            ex_style |= win32con.WS_EX_LAYERED | win32con.WS_EX_NOACTIVATE
            if self._interactive:
                ex_style &= ~win32con.WS_EX_TRANSPARENT
            else:
                ex_style |= win32con.WS_EX_TRANSPARENT
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

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = self.rect().adjusted(3, 3, -3, -3)

        if self._point_selected:
            ring_color = QtGui.QColor(255, 230, 120)
        elif self._selected:
            ring_color = QtGui.QColor(80, 220, 120)
        else:
            ring_color = QtGui.QColor(255, 60, 60)
        fill_color = QtGui.QColor(255, 60, 60)
        if self._point_selected:
            fill_color.setAlpha(90)
        else:
            fill_color.setAlpha(60 if not self._selected else 45)
        painter.setBrush(fill_color)
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawEllipse(rect)

        painter.setBrush(QtCore.Qt.NoBrush)
        ring_width = 4 if self._point_selected and not self._small_label else 3 if not self._small_label else 2
        painter.setPen(QtGui.QPen(ring_color, ring_width))
        painter.drawEllipse(rect)

        core_color = QtGui.QColor(255, 0, 0)
        if self.point_key == "end":
            core_size = 6
        elif self.point_key == "start":
            core_size = 9 if not self._small_label else 8
        else:
            core_size = 9 if not self._small_label else 7
        core_offset = core_size // 2
        center_x = int(round(self.width() / 2.0)) - core_offset
        center_y = int(round(self.height() / 2.0)) - core_offset
        painter.setBrush(core_color)
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawEllipse(center_x, center_y, core_size, core_size)

        font = QtGui.QFont("Times New Roman", 9 if self._small_label else 10)
        font.setBold(True)
        painter.setFont(font)
        if self._label_text:
            painter.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 235), 1))
            painter.drawText(self.rect(), QtCore.Qt.AlignCenter, self._label_text)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_shape()

    def showEvent(self, event):
        super().showEvent(event)
        self._apply_shape()
        self._sync_window_style()

    def mousePressEvent(self, event):
        if not self._interactive:
            event.ignore()
            return
        if event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit(self.node_id, self.point_key)
            self._drag_pos = event.pos()
            try:
                self.grabMouse()
            except Exception:
                pass
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not self._interactive:
            event.ignore()
            return
        if event.buttons() == QtCore.Qt.LeftButton and self._drag_pos is not None:
            new_pos = _event_global_pos(event) - self._drag_pos
            self.move(int(new_pos.x()), int(new_pos.y()))
            x, y = self.center_pos()
            self.moved.emit(self.node_id, self.point_key, x, y)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        try:
            self.releaseMouse()
        except Exception:
            pass
        event.accept()
        super().mouseReleaseEvent(event)

    def hideEvent(self, event):
        self._drag_pos = None
        try:
            self.releaseMouse()
        except Exception:
            pass
        super().hideEvent(event)


class SandboxOverlayController(QtCore.QObject):
    point_moved = QtCore.Signal(str, str, int, int)
    point_selected = QtCore.Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._line_overlay = SandboxLineOverlay()
        self._handles = {}
        self._visible = False
        self._selected_node_id = ""
        self._selected_node_ids = set()
        self._selected_point_key = ""
        self._execution_mode = False
        self._top_timer = QtCore.QTimer(self)
        self._top_timer.timeout.connect(self._enforce_topmost)
        self._top_timer.start(350)

    def show(self):
        self._visible = True
        self._enforce_topmost()
        self._line_overlay.show()
        for handle in self._handles.values():
            handle.show()

    def hide(self):
        self._visible = False
        self._line_overlay.hide()
        for handle in self._handles.values():
            handle.hide()

    def close(self):
        self._top_timer.stop()
        self._line_overlay.close()
        for handle in list(self._handles.values()):
            handle.close()
        self._handles.clear()

    def set_interactive(self, enabled: bool):
        for handle in self._handles.values():
            handle.set_interactive(enabled)

    def set_selected(self, node_id: str, point_key: str = "", selected_ids=None):
        self._selected_node_id = node_id or ""
        self._selected_node_ids = {node for node in (selected_ids or []) if node}
        if self._selected_node_id and self._selected_node_id not in self._selected_node_ids:
            self._selected_node_ids.add(self._selected_node_id)
        self._selected_point_key = point_key or ""
        for (handle_node_id, handle_point_key), handle in self._handles.items():
            node_selected = handle_node_id in self._selected_node_ids
            point_selected = (
                node_selected
                and handle_node_id == self._selected_node_id
                and self._selected_point_key != ""
                and handle_point_key == self._selected_point_key
            )
            handle.set_selected(node_selected, point_selected)

    def set_execution_mode(self, executing: bool):
        self._execution_mode = bool(executing)

    def _enforce_topmost(self):
        make_noactivate_topmost(self._line_overlay)
        for handle in self._handles.values():
            make_noactivate_topmost(handle)

    def sync(self, sandbox: dict):
        objects = sandbox.get("objects", {})
        needed = {}
        lines = []

        def effectively_enabled(node_id: str):
            original_node_id = node_id
            node = objects.get(node_id)
            while node:
                if not bool(node.get("enabled", True)):
                    return False
                parent_id = node.get("parent_id", "")
                if not parent_id:
                    return True
                parent = objects.get(parent_id)
                if not parent:
                    return True
                if parent.get("folder_kind") == "sequence" and is_keybound(original_node_id):
                    return True
                node = parent
            return True

        bindings_by_target = {}
        for keybind_id, keybind_node in objects.items():
            if keybind_node.get("type") != "keybind":
                continue
            key_text = str(keybind_node.get("keybind", "")).strip()
            target_id = keybind_node.get("target_id", "")
            if key_text and target_id and effectively_enabled(keybind_id):
                bindings_by_target.setdefault(target_id, []).append(key_text)

        def target_label(node_id: str):
            keys = bindings_by_target.get(node_id, [])
            if not keys:
                return ""
            return " / ".join(keys[:2])

        def is_keybound(node_id: str):
            return node_id in bindings_by_target

        sequence_display_order = {}
        sequence_folder = objects.get("folder_sequence")
        if sequence_folder and sequence_folder.get("type") == "folder":
            ordered_nodes = []
            for child_id in sequence_folder.get("children", []):
                child = objects.get(child_id)
                if not child or child.get("type") not in ("marker", "dragger"):
                    continue
                if not effectively_enabled(child_id) or is_keybound(child_id):
                    continue
                ordered_nodes.append(child)
            ordered_nodes.sort(
                key=lambda child: (
                    int(child.get("index", 99999) or 99999),
                    str(child.get("name", "")),
                    str(child.get("id", "")),
                )
            )
            for display_order, child in enumerate(ordered_nodes, start=1):
                sequence_display_order[child.get("id", "")] = str(display_order)

        for node_id, node in objects.items():
            if node.get("type") == "marker" and effectively_enabled(node_id):
                if self._execution_mode:
                    continue
                label = target_label(node_id)
                if not label and not self._execution_mode:
                    label = sequence_display_order.get(node_id, "")
                needed[(node_id, "center")] = (
                    (int(node.get("x", 0)), int(node.get("y", 0))),
                    QtGui.QColor(255, 60, 60),
                    label,
                    (not is_keybound(node_id) and bool(label)),
                )
            elif node.get("type") == "dragger" and effectively_enabled(node_id):
                if self._execution_mode:
                    continue
                start = (int(node.get("start_x", 0)), int(node.get("start_y", 0)))
                end = (int(node.get("end_x", 0)), int(node.get("end_y", 0)))
                label = target_label(node_id)
                if not label and not self._execution_mode:
                    label = sequence_display_order.get(node_id, "")
                needed[(node_id, "start")] = (start, QtGui.QColor(255, 60, 60), label, (not is_keybound(node_id) and bool(label)))
                needed[(node_id, "end")] = (end, QtGui.QColor(255, 140, 60), "", False)
                lines.append({"start_x": start[0], "start_y": start[1], "end_x": end[0], "end_y": end[1]})

        for key in list(self._handles):
            if key not in needed:
                self._handles[key].close()
                del self._handles[key]

        for key, payload in needed.items():
            center, color, label, small_label = payload
            handle = self._handles.get(key)
            if handle is None:
                handle = SandboxHandleWidget(key[0], key[1], color, label)
                handle.moved.connect(self.point_moved)
                handle.clicked.connect(self.point_selected)
                self._handles[key] = handle
            handle.update_visual(color, label, small_label)
            node_selected = key[0] in self._selected_node_ids
            point_selected = (
                node_selected
                and key[0] == self._selected_node_id
                and self._selected_point_key != ""
                and key[1] == self._selected_point_key
            )
            handle.set_selected(node_selected, point_selected)
            handle.move_center(center[0], center[1])
            if self._visible:
                handle.show()
            else:
                handle.hide()

        self._line_overlay.set_lines(lines)
        if self._visible:
            self._line_overlay.show()
        else:
            self._line_overlay.hide()


class SandboxModeUIMixin:
    def build_ui(self):
        self._ensure_sandbox_data()
        style = self.style()
        self._folder_icon = style.standardIcon(QtWidgets.QStyle.SP_DirIcon)
        self._keybind_icon = style.standardIcon(QtWidgets.QStyle.SP_ArrowForward)
        self._marker_icon = style.standardIcon(QtWidgets.QStyle.SP_DialogYesButton)
        self._dragger_icon = style.standardIcon(QtWidgets.QStyle.SP_BrowserReload)

        def divider():
            line = QtWidgets.QFrame()
            line.setFrameShape(QtWidgets.QFrame.HLine)
            line.setStyleSheet("color: rgba(255,255,255,25);")
            line.setFixedHeight(1)
            return line

        self.content.setContentsMargins(6, 5, 6, 6)
        self.content.setSpacing(6)

        self._tree = QtWidgets.QTreeWidget()
        self._tree.setColumnCount(2)
        self._tree.setHeaderLabels(["Hierarchy", "Info"])
        self._tree.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self._tree.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self._tree.header().setStretchLastSection(False)
        self._tree.header().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self._tree.header().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        self._tree.setIndentation(14)
        self._tree.setAnimated(True)
        self._update_tree_header_indicator()
        self._tree.itemSelectionChanged.connect(self._on_tree_selection_changed)

        self._properties_area = QtWidgets.QScrollArea()
        self._properties_area.setWidgetResizable(True)
        self._properties_area.setFrameShape(QtWidgets.QFrame.NoFrame)
        self._properties_area.setStyleSheet("background: transparent;")
        self._properties_host = QtWidgets.QWidget()
        self._properties_layout = QtWidgets.QVBoxLayout(self._properties_host)
        self._properties_layout.setContentsMargins(0, 0, 0, 0)
        self._properties_layout.setSpacing(6)
        self._properties_area.setWidget(self._properties_host)

        left_card = QtWidgets.QFrame()
        right_card = QtWidgets.QFrame()
        for card in (left_card, right_card):
            card.setStyleSheet("QFrame { background: rgba(255,255,255,10); border: none; border-radius: 8px; }")
        left_layout = QtWidgets.QVBoxLayout(left_card)
        left_layout.setContentsMargins(7, 7, 7, 7)
        left_layout.setSpacing(5)
        right_layout = QtWidgets.QVBoxLayout(right_card)
        right_layout.setContentsMargins(7, 7, 7, 7)
        right_layout.setSpacing(5)
        left_title = QtWidgets.QLabel("Explorer")
        right_title = QtWidgets.QLabel("Properties")
        for lbl in (left_title, right_title):
            lbl.setStyleSheet("color: white; font: bold 11pt 'Times New Roman';")
        left_layout.addWidget(left_title)
        left_layout.addWidget(self._tree)
        right_layout.addWidget(right_title)
        right_layout.addWidget(self._properties_area)

        split = InspectorSplitter(QtCore.Qt.Horizontal)
        split.setChildrenCollapsible(False)
        split.setHandleWidth(18)
        split.setStyleSheet("""
            QSplitter::handle {
                background: rgba(255,255,255,18);
                border-left: 1px solid rgba(255,255,255,24);
                border-right: 1px solid rgba(255,255,255,24);
            }
        """)
        split.addWidget(left_card)
        split.addWidget(right_card)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setSizes([60, 40])
        self.content.addWidget(split, 1)

        bottom_card = QtWidgets.QFrame()
        bottom_card.setStyleSheet("QFrame { background: rgba(255,255,255,10); border: none; border-radius: 8px; } QLabel { color: white; }")
        bottom_layout = QtWidgets.QVBoxLayout(bottom_card)
        bottom_layout.setContentsMargins(8, 6, 8, 6)
        bottom_layout.setSpacing(4)
        top_row = QtWidgets.QHBoxLayout()
        self._selection_lbl = QtWidgets.QLabel("Selected: N/A")
        self._selection_lbl.setTextFormat(QtCore.Qt.RichText)
        self._selection_lbl.setStyleSheet("color: white; font: 9pt 'Times New Roman';")
        self._status_lbl = QtWidgets.QLabel("Stopped")
        self._status_lbl.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        top_row.addWidget(self._selection_lbl, 1)
        top_row.addWidget(self._status_lbl, 1)
        bottom_layout.addLayout(top_row)
        bottom_layout.addWidget(divider())
        self._hint_lbl = QtWidgets.QLabel(self._format_hint_text(ConfigManager.load().get("keybinds", {})))
        self._hint_lbl.setAlignment(QtCore.Qt.AlignCenter)
        self._hint_lbl.setStyleSheet("color: rgba(255,255,255,170); font: italic 7.2pt 'Times New Roman';")
        self._hint_lbl.setFixedHeight(18)
        bottom_layout.addWidget(self._hint_lbl)
        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch()
        self._execute_btn = QtWidgets.QPushButton("▶  Execute")
        self._stop_btn = QtWidgets.QPushButton("■  Stop")
        self._info_btn = QtWidgets.QPushButton("i")
        for btn in (self._execute_btn, self._stop_btn):
            btn.setFixedHeight(27)
            btn.setFont(QtGui.QFont("Times New Roman", 11))
        self._execute_btn.setFixedWidth(140)
        self._stop_btn.setFixedWidth(120)
        self._execute_btn.setStyleSheet("QPushButton { background: #6200cc; color: white; border-radius: 6px; padding: 4px 14px; } QPushButton:hover { background: #8a1fff; } QPushButton:disabled { background: rgba(80,0,140,70); color: rgba(255,255,255,55); }")
        self._stop_btn.setStyleSheet("QPushButton { background: rgba(160,25,25,180); color: white; border-radius: 6px; padding: 4px 14px; } QPushButton:hover { background: rgba(210,40,40,210); } QPushButton:disabled { background: rgba(80,10,10,70); color: rgba(255,255,255,55); }")
        self._info_btn.setFixedSize(27, 27)
        self._info_btn.setStyleSheet("QPushButton { background: rgba(255,255,255,22); color: white; border-radius: 6px; border: none; font: bold 11pt 'Times New Roman'; } QPushButton:hover { background: rgba(255,255,255,36); }")
        self._execute_btn.clicked.connect(self._on_execute)
        self._stop_btn.clicked.connect(self._on_stop)
        self._info_btn.clicked.connect(self._toggle_setup_info)
        self._stop_btn.setEnabled(False)
        btn_row.addWidget(self._execute_btn)
        btn_row.addWidget(self._stop_btn)
        btn_row.addWidget(self._info_btn)
        btn_row.addStretch()
        bottom_layout.addLayout(btn_row)
        self.content.addWidget(bottom_card)

    def refresh_keybind_hints(self, keybinds: dict):
        if hasattr(self, "_hint_lbl"):
            self._hint_lbl.setText(self._format_hint_text(keybinds))

    def _line_edit_style(self):
        return "color: white; background: rgba(0,0,0,92); border: none; border-radius: 4px; font: 8pt 'Times New Roman'; padding: 3px 5px;"

    def _spin_style(self):
        return (
            "QSpinBox { color: white; background: rgba(0,0,0,92); border: none; border-radius: 4px; "
            "font: 8pt 'Times New Roman'; padding: 3px 18px 3px 5px; } "
            "QSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right; width: 12px; height: 8px; "
            "border: none; border-left: 1px solid rgba(255,255,255,18); border-bottom: 1px solid rgba(255,255,255,8); "
            "background: rgba(0,0,0,18); border-top-right-radius: 4px; } "
            "QSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right; width: 12px; height: 8px; "
            "border: none; border-left: 1px solid rgba(255,255,255,18); background: rgba(0,0,0,18); border-bottom-right-radius: 4px; } "
            "QSpinBox::up-button:hover, QSpinBox::down-button:hover { background: rgba(255,255,255,10); } "
            "QSpinBox::up-arrow { image: none; width: 0; height: 0; border-left: 3px solid transparent; "
            "border-right: 3px solid transparent; border-bottom: 4px solid rgba(255,255,255,175); } "
            "QSpinBox::down-arrow { image: none; width: 0; height: 0; border-left: 3px solid transparent; "
            "border-right: 3px solid transparent; border-top: 4px solid rgba(255,255,255,175); }"
        )

    def _combo_style(self):
        return "QComboBox { color: white; background: rgba(0,0,0,92); border: none; border-radius: 4px; font: 8pt 'Times New Roman'; padding: 3px 22px 3px 6px; } QComboBox QAbstractItemView { color: white; background: rgba(18,10,40,235); selection-background-color: rgba(122,0,255,150); border: none; }"

    def _button_style(self):
        return "QPushButton { background: rgba(255,255,255,16); color: white; border: none; border-radius: 4px; font: 8pt 'Times New Roman'; padding: 3px 8px; } QPushButton:hover { background: rgba(255,255,255,28); } QPushButton:disabled { color: rgba(255,255,255,70); border-color: transparent; }"

    def _section_label(self, text: str):
        lbl = QtWidgets.QLabel(text)
        lbl.setStyleSheet("color: rgba(255,255,255,205); font: bold 9pt 'Times New Roman';")
        return lbl

    def _note_label(self, text: str):
        lbl = QtWidgets.QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("color: rgba(255,255,255,135); font: 8pt 'Times New Roman';")
        return lbl

    def _add_property_row(self, label_text: str, editor: QtWidgets.QWidget):
        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        label = QtWidgets.QLabel(label_text)
        label.setFixedWidth(112)
        label.setStyleSheet("color: rgba(255,255,255,200); font: 8pt 'Times New Roman';")
        row.addWidget(label)
        row.addWidget(editor, 1)
        self._properties_layout.addLayout(row)
        self._property_widgets.append(editor)

    def _clear_properties(self):
        while self._properties_layout.count():
            child = self._properties_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
            elif child.layout():
                layout = child.layout()
                while layout.count():
                    sub = layout.takeAt(0)
                    if sub.widget():
                        sub.widget().deleteLater()
                layout.deleteLater()
        self._property_widgets = []
        self._property_value_widgets = {}

    def _update_live_position_widgets(self, node_id: str):
        node = self._node(node_id)
        if not node:
            return
        for key in ("x", "y", "start_x", "start_y", "end_x", "end_y"):
            widget = self._property_value_widgets.get((node_id, key))
            if widget is not None:
                try:
                    blocked = widget.blockSignals(True)
                    widget.setValue(int(node.get(key, 0)))
                    widget.blockSignals(blocked)
                except RuntimeError:
                    self._property_value_widgets.pop((node_id, key), None)

    def _update_tree_item_display(self, node_id: str):
        item = self._find_tree_item(node_id)
        node = self._node(node_id)
        if item is None or node is None:
            return
        item.setText(0, node.get("name", "Unnamed"))
        item.setToolTip(0, self._node_info_text(node))
        info_widget = self._make_tree_info_widget(node)
        self._tree.setItemWidget(item, 1, info_widget)

    def _refresh_overlay(self):
        sandbox = copy.deepcopy(self.data["sandbox"])
        objects = sandbox.get("objects", {})
        for node_id, node in objects.items():
            if node.get("type") in ("marker", "dragger"):
                node["enabled"] = self._can_show_overlay_node(node_id)
        self._overlay_controller.sync(sandbox)
        self._overlay_controller.set_selected(
            self.data["sandbox"].get("selected_id", ""),
            self._selected_point_key,
            self._selection_node_ids(),
        )
        self._overlay_controller.set_interactive(not self._executing)

    def _make_tree_info_widget(self, node: dict):
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        info = QtWidgets.QLabel(self._node_info_text(node))
        warning = self._sequence_index_warnings().get(node.get("id", ""))
        info_color = "rgba(255,120,120,235)" if warning else "rgba(255,255,255,170)"
        info.setStyleSheet(f"color: {info_color}; font: 7.8pt 'Times New Roman';")
        layout.addWidget(info)
        if node.get("type") == "folder":
            add_btn = QtWidgets.QPushButton("+")
            add_btn.setFixedSize(18, 18)
            add_btn.setStyleSheet("QPushButton { background: rgba(255,255,255,14); color: white; border: none; border-radius: 4px; font: bold 9pt 'Consolas'; } QPushButton:hover { background: rgba(255,255,255,28); }")
            add_btn.clicked.connect(lambda _=False, node_id=node["id"]: self._open_create_object_dialog(node_id))
            layout.addWidget(add_btn)
        return widget

    def _refresh_hierarchy(self):
        if not hasattr(self, "_tree"):
            return
        selected_id = self.data["sandbox"].get("selected_id", "")
        selected_ids = self._selection_node_ids()
        self._tree.blockSignals(True)
        self._tree.clear()

        def add_item(node_id: str, parent_item=None):
            node = self._node(node_id)
            if not node:
                return
            item = QtWidgets.QTreeWidgetItem([node.get("name", "Unnamed"), ""])
            item.setData(0, QtCore.Qt.UserRole, node_id)
            item.setIcon(0, self._node_icon(node))
            item.setToolTip(0, self._node_info_text(node))
            warning = self._sequence_index_warnings().get(node_id)
            if warning:
                item.setForeground(0, QtGui.QBrush(QtGui.QColor(255, 120, 120)))
            if not bool(node.get("enabled", True)):
                item.setForeground(0, QtGui.QBrush(QtGui.QColor(180, 180, 180)))
            if parent_item is None:
                self._tree.addTopLevelItem(item)
            else:
                parent_item.addChild(item)
            self._tree.setItemWidget(item, 1, self._make_tree_info_widget(node))
            if node.get("type") == "folder":
                for child_id in node.get("children", []):
                    add_item(child_id, item)
                item.setExpanded(True)

        for root_id in self.data["sandbox"].get("root_ids", []):
            add_item(root_id)
        self._tree.expandAll()
        matches = self._tree.findItems("*", QtCore.Qt.MatchWildcard | QtCore.Qt.MatchRecursive, 0)
        current_item = None
        for item in matches:
            node_id = item.data(0, QtCore.Qt.UserRole)
            if node_id in selected_ids:
                item.setSelected(True)
            if node_id == selected_id:
                current_item = item
        if current_item is not None:
            self._tree.setCurrentItem(current_item)
        self._tree.blockSignals(False)
        self._overlay_controller.set_selected(selected_id, self._selected_point_key, selected_ids)

    def _build_multi_properties(self, nodes):
        node_ids = [node["id"] for node in nodes]
        names = ", ".join(node.get("name", "Unnamed") for node in nodes)
        self._properties_layout.addWidget(self._section_label(names))
        self._properties_layout.addWidget(self._note_label(f"{len(nodes)} objects selected"))

        node_types = {node.get("type") for node in nodes}
        if len(node_types) != 1:
            self._properties_layout.addWidget(self._note_label("Multi-edit currently works best when all selected objects are the same type."))
            self._properties_layout.addStretch()
            return

        node_type = next(iter(node_types))
        self._add_multi_checkbox_row("Enabled", node_ids, nodes, "enabled")

        if node_type == "keybind":
            self._add_multi_combo_row(
                "Target Marker",
                node_ids,
                nodes,
                "target_id",
                [(text, target_id) for target_id, text in self._sandbox_target_options("")]
            )
            self._add_multi_text_row("Description", node_ids, nodes, "description")
            self._add_multi_checkbox_row("Teleport Back", node_ids, nodes, "teleport_back")
            return

        if node_type == "marker":
            self._add_multi_numeric_row("Index", node_ids, nodes, "index")
            self._add_multi_numeric_row("Position X", node_ids, nodes, "x")
            self._add_multi_numeric_row("Position Y", node_ids, nodes, "y")
            self._add_multi_numeric_row("Delay", node_ids, nodes, "click_delay_ms")
            self._add_multi_numeric_row("Hold", node_ids, nodes, "mouse_hold_ms")
            self._add_multi_checkbox_row("Click Randomness", node_ids, nodes, CLICK_RANDOMNESS_KEY)
            self._add_multi_combo_row("Mouse Button", node_ids, nodes, "mouse_button", [("Left", "left"), ("Right", "right"), ("Middle", "middle")])
            self._add_multi_combo_row("Mouse Behavoir", node_ids, nodes, MOUSE_BEHAVIOR_KEY, MOUSE_BEHAVIOR_OPTIONS)
            return

        if node_type == "dragger":
            self._add_multi_numeric_row("Index", node_ids, nodes, "index")
            self._add_multi_numeric_row("Start X", node_ids, nodes, "start_x")
            self._add_multi_numeric_row("Start Y", node_ids, nodes, "start_y")
            self._add_multi_numeric_row("End X", node_ids, nodes, "end_x")
            self._add_multi_numeric_row("End Y", node_ids, nodes, "end_y")
            self._add_multi_numeric_row("Delay", node_ids, nodes, "click_delay_ms")
            self._add_multi_numeric_row("Hold", node_ids, nodes, "mouse_hold_ms")
            self._add_multi_combo_row("Mouse Button", node_ids, nodes, "mouse_button", [("Left", "left"), ("Right", "right"), ("Middle", "middle")])
            self._add_multi_combo_row("Mouse Behavoir", node_ids, nodes, MOUSE_BEHAVIOR_KEY, MOUSE_BEHAVIOR_OPTIONS)
            return

        if node_type == "folder":
            self._properties_layout.addWidget(self._note_label("Folder multi-edit is limited for now."))

    def _refresh_properties(self):
        if not hasattr(self, "_properties_layout"):
            return
        self._clear_properties()
        nodes = self._selection_nodes()
        if not nodes:
            self._properties_layout.addWidget(self._note_label("Select an item from the hierarchy to inspect it."))
            self._properties_layout.addStretch()
            return
        if len(nodes) > 1:
            self._build_multi_properties(nodes)
            self._properties_layout.addStretch()
            for widget in self._property_widgets:
                widget.setEnabled(not self._executing)
            return

        node = nodes[0]

        self._properties_layout.addWidget(self._section_label(f"{node.get('name', 'Unnamed')}  [{node.get('type', 'object').title()}]"))
        self._properties_layout.addWidget(self._note_label(self._node_info_text(node)))
        self._build_common_properties(node)
        node_type = node.get("type")
        if node_type == "folder":
            self._build_folder_properties(node)
        elif node_type == "keybind":
            self._build_keybind_properties(node)
        elif node_type == "marker":
            self._build_marker_properties(node)
        elif node_type == "dragger":
            self._build_dragger_properties(node)
        self._build_action_buttons(node)
        self._properties_layout.addStretch()
        for widget in self._property_widgets:
            widget.setEnabled(not self._executing)

    def _build_common_properties(self, node: dict):
        if node.get("type") != "folder":
            name_edit = QtWidgets.QLineEdit(node.get("name", ""))
            name_edit.setStyleSheet(self._line_edit_style())
            name_edit.editingFinished.connect(lambda node_id=node["id"], box=name_edit: self._commit_line_edit_value(node_id, "name", box))
            self._add_property_row("Object Name", name_edit)
        enabled = QtWidgets.QCheckBox()
        enabled.setChecked(bool(node.get("enabled", True)))
        enabled.setStyleSheet("QCheckBox { color: white; }")
        enabled.stateChanged.connect(lambda _=0, box=enabled, node_id=node["id"]: self._set_node_value(node_id, "enabled", box.isChecked()))
        self._add_property_row("Enabled", enabled)

    def _build_folder_properties(self, node: dict):
        name_edit = QtWidgets.QLineEdit(node.get("name", ""))
        name_edit.setStyleSheet(self._line_edit_style())
        name_edit.editingFinished.connect(lambda node_id=node["id"], box=name_edit: self._commit_line_edit_value(node_id, "name", box))
        self._add_property_row("Folder Name", name_edit)
        child_count = QtWidgets.QLabel(str(len(node.get("children", []))))
        child_count.setAlignment(QtCore.Qt.AlignCenter)
        child_count.setStyleSheet("color: white; background: rgba(0,0,0,92); border: none; border-radius: 4px; font: 8pt 'Times New Roman'; padding: 4px 0;")
        self._add_property_row("Child Count", child_count)
        if node.get("folder_kind") == "sequence":
            mode_combo = QtWidgets.QComboBox()
            mode_combo.setStyleSheet(self._combo_style())
            mode_combo.addItem("Repeat Until Stop", "until_stop")
            mode_combo.addItem("Repeat Times", "repeat_times")
            mode_combo.addItem("Repeat Timer", "repeat_timer")
            mode_combo.setCurrentIndex(max(0, mode_combo.findData(node.get("repeat_mode", "until_stop"))))
            mode_combo.currentIndexChanged.connect(lambda _=0, combo=mode_combo, node_id=node["id"]: self._set_node_value(node_id, "repeat_mode", combo.currentData() or "until_stop"))
            self._add_property_row("Run Mode", mode_combo)

            times_btn = QtWidgets.QPushButton(f"Count: {int(node.get('repeat_times_target', 5))}")
            times_btn.setStyleSheet(self._button_style())
            times_btn.clicked.connect(self._edit_sequence_repeat_times)
            self._add_property_row("Repeat Times", times_btn)

            timer_btn = QtWidgets.QPushButton(f"Timer: {self._format_repeat_time(int(node.get('repeat_timer_seconds', 60)))}")
            timer_btn.setStyleSheet(self._button_style())
            timer_btn.clicked.connect(self._edit_sequence_repeat_timer)
            self._add_property_row("Repeat Timer", timer_btn)
        self._properties_layout.addWidget(self._note_label("If a folder is disabled, every child inside it is ignored during execution."))

    def _build_keybind_properties(self, node: dict):
        binding_label = QtWidgets.QLabel(node.get("keybind", "Not Set"))
        binding_label.setAlignment(QtCore.Qt.AlignCenter)
        binding_label.setStyleSheet("color: white; background: rgba(0,0,0,92); border: none; border-radius: 4px; font: 8pt 'Consolas'; padding: 4px 6px;")
        binding_btn = QtWidgets.QPushButton("Edit")
        binding_btn.setFixedWidth(52)
        binding_btn.setStyleSheet(self._button_style())
        binding_btn.clicked.connect(lambda _=False, node_id=node["id"]: self._capture_sandbox_keybind(node_id))
        host = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(binding_label, 1)
        layout.addWidget(binding_btn)
        self._add_property_row("Assigned Key", host)

        target_combo = QtWidgets.QComboBox()
        target_combo.setStyleSheet(self._combo_style())
        for target_id, text in self._sandbox_target_options(node["id"]):
            target_combo.addItem(text, target_id)
        idx = target_combo.findData(node.get("target_id", ""))
        target_combo.setCurrentIndex(0 if idx < 0 else idx)
        target_combo.currentIndexChanged.connect(lambda _=0, combo=target_combo, node_id=node["id"]: self._set_node_value(node_id, "target_id", combo.currentData() or ""))
        self._add_property_row("Target Marker", target_combo)

        desc_edit = QtWidgets.QLineEdit(node.get("description", ""))
        desc_edit.setStyleSheet(self._line_edit_style())
        desc_edit.editingFinished.connect(lambda node_id=node["id"], box=desc_edit: self._commit_line_edit_value(node_id, "description", box))
        self._add_property_row("Description", desc_edit)
        teleport_back = QtWidgets.QCheckBox()
        teleport_back.setChecked(bool(node.get("teleport_back", False)))
        teleport_back.setStyleSheet("QCheckBox { color: white; }")
        teleport_back.stateChanged.connect(lambda _=0, box=teleport_back, node_id=node["id"]: self._set_node_value(node_id, "teleport_back", box.isChecked()))
        self._add_property_row("Teleport Back", teleport_back)
        self._properties_layout.addWidget(self._note_label("When execution is active, this key instantly triggers its assigned marker or dragger."))
        self._properties_layout.addWidget(self._note_label("Teleport Back restores immediately after the current trigger finishes. While you keep spamming the key, SnapCursorX keeps the same saved return position and does not replace it from points near the marker, so it avoids teleport-back drift."))

    def _build_marker_properties(self, node: dict):
        if self._is_keybind_bound(node["id"]):
            index_widget = QtWidgets.QLabel("0")
            index_widget.setAlignment(QtCore.Qt.AlignCenter)
            index_widget.setStyleSheet("color: white; background: rgba(0,0,0,92); border: none; border-radius: 4px; font: 8pt 'Times New Roman'; padding: 4px 0;")
            self._add_property_row("Index", index_widget)
            self._properties_layout.addWidget(self._note_label("Index 0 is reserved automatically because this marker is bound to a keybind."))
        else:
            index_spin = HorizontalStepSpinBox()
            index_spin.setRange(1, 99999)
            index_spin.setSingleStep(10)
            index_spin.setKeyboardTracking(False)
            index_spin.setValue(int(node.get("index", 10)))
            index_spin.setStyleSheet(self._spin_style())
            index_spin.valueChanged.connect(lambda value, node_id=node["id"]: self._set_node_value(node_id, "index", int(value)))
            self._add_property_row("Index", index_spin)
        for key, label_text in (("x", "Position X"), ("y", "Position Y"), ("click_delay_ms", "Delay"), ("mouse_hold_ms", "Hold")):
            spin = HorizontalStepSpinBox()
            spin.setRange(0, 99999)
            spin.setKeyboardTracking(False)
            spin.setValue(int(node.get(key, 0)))
            spin.setStyleSheet(self._spin_style())
            spin.valueChanged.connect(lambda value, node_id=node["id"], data_key=key: self._set_node_value(node_id, data_key, int(value)))
            self._property_value_widgets[(node["id"], key)] = spin
            self._add_property_row(label_text, spin)
        anti = QtWidgets.QCheckBox()
        anti.setChecked(read_click_randomness(node, True))
        anti.setStyleSheet("QCheckBox { color: white; }")
        anti.stateChanged.connect(lambda _=0, box=anti, node_id=node["id"]: self._set_node_value(node_id, CLICK_RANDOMNESS_KEY, box.isChecked()))
        self._add_property_row("Click Randomness", anti)
        combo = QtWidgets.QComboBox()
        for label, value in (("Left", "left"), ("Right", "right"), ("Middle", "middle")):
            combo.addItem(label, value)
        combo.setStyleSheet(self._combo_style())
        combo.setCurrentIndex(max(0, combo.findData(node.get("mouse_button", "left"))))
        combo.currentIndexChanged.connect(lambda _=0, box=combo, node_id=node["id"]: self._set_node_value(node_id, "mouse_button", box.currentData() or "left"))
        self._add_property_row("Mouse Button", combo)
        behavior_combo = QtWidgets.QComboBox()
        for label, value in MOUSE_BEHAVIOR_OPTIONS:
            behavior_combo.addItem(label, value)
        behavior_combo.setStyleSheet(self._combo_style())
        behavior_combo.setCurrentIndex(max(0, behavior_combo.findData(read_mouse_behavior(node, "default"))))
        behavior_combo.currentIndexChanged.connect(lambda _=0, box=behavior_combo, node_id=node["id"]: self._set_node_value(node_id, MOUSE_BEHAVIOR_KEY, box.currentData() or "default"))
        self._add_property_row("Mouse Behavior", behavior_combo)
        self._properties_layout.addWidget(self._note_label("Default: uses tween movement with C click. \nTeleport: jumps instantly with C click. \nBackground: sends background input without moving the real mouse and may fail in some apps."))

    def _build_dragger_properties(self, node: dict):
        if self._is_keybind_bound(node["id"]):
            index_widget = QtWidgets.QLabel("0")
            index_widget.setAlignment(QtCore.Qt.AlignCenter)
            index_widget.setStyleSheet("color: white; background: rgba(0,0,0,92); border: none; border-radius: 4px; font: 8pt 'Times New Roman'; padding: 4px 0;")
            self._add_property_row("Index", index_widget)
            self._properties_layout.addWidget(self._note_label("Index 0 is reserved automatically because this dragger is bound to a keybind."))
        else:
            index_spin = HorizontalStepSpinBox()
            index_spin.setRange(1, 99999)
            index_spin.setSingleStep(10)
            index_spin.setKeyboardTracking(False)
            index_spin.setValue(int(node.get("index", 10)))
            index_spin.setStyleSheet(self._spin_style())
            index_spin.valueChanged.connect(lambda value, node_id=node["id"]: self._set_node_value(node_id, "index", int(value)))
            self._add_property_row("Index", index_spin)
        for key, label_text in (
            ("start_x", "Start X"), ("start_y", "Start Y"), ("end_x", "End X"), ("end_y", "End Y"),
            ("click_delay_ms", "Delay"), ("mouse_hold_ms", "Hold")
        ):
            spin = HorizontalStepSpinBox()
            spin.setRange(0, 99999)
            spin.setKeyboardTracking(False)
            spin.setValue(int(node.get(key, 0)))
            spin.setStyleSheet(self._spin_style())
            spin.valueChanged.connect(lambda value, node_id=node["id"], data_key=key: self._set_node_value(node_id, data_key, int(value)))
            self._property_value_widgets[(node["id"], key)] = spin
            self._add_property_row(label_text, spin)
        combo = QtWidgets.QComboBox()
        for label, value in (("Left", "left"), ("Right", "right"), ("Middle", "middle")):
            combo.addItem(label, value)
        combo.setStyleSheet(self._combo_style())
        combo.setCurrentIndex(max(0, combo.findData(node.get("mouse_button", "left"))))
        combo.currentIndexChanged.connect(lambda _=0, box=combo, node_id=node["id"]: self._set_node_value(node_id, "mouse_button", box.currentData() or "left"))
        self._add_property_row("Mouse Button", combo)
        behavior_combo = QtWidgets.QComboBox()
        for label, value in MOUSE_BEHAVIOR_OPTIONS:
            behavior_combo.addItem(label, value)
        behavior_combo.setStyleSheet(self._combo_style())
        behavior_combo.setCurrentIndex(max(0, behavior_combo.findData(read_mouse_behavior(node, "default"))))
        behavior_combo.currentIndexChanged.connect(lambda _=0, box=behavior_combo, node_id=node["id"]: self._set_node_value(node_id, MOUSE_BEHAVIOR_KEY, box.currentData() or "default"))
        self._add_property_row("Mouse Behavoir", behavior_combo)
        self._properties_layout.addWidget(self._note_label("Default uses tween movement with C click. Teleport jumps instantly with C click. Background sends background input without moving the real mouse and may fail in some apps."))
        self._properties_layout.addWidget(self._note_label("Draggers use two draggable overlay points connected by a fading line."))

    def _build_action_buttons(self, node: dict):
        row = QtWidgets.QHBoxLayout()
        row.setSpacing(6)
        clone_btn = QtWidgets.QPushButton("Clone")
        delete_btn = QtWidgets.QPushButton("Delete")
        for btn in (clone_btn, delete_btn):
            btn.setStyleSheet(self._button_style())
        clone_btn.clicked.connect(lambda _=False, node_id=node["id"]: self._clone_node(node_id))
        delete_btn.clicked.connect(lambda _=False, node_id=node["id"]: self._delete_node(node_id))
        if node.get("type") == "folder" and not node.get("parent_id"):
            clone_btn.setEnabled(False)
            delete_btn.setEnabled(False)
        row.addWidget(clone_btn)
        row.addWidget(delete_btn)
        self._properties_layout.addLayout(row)

    def _refresh_bottom_bar(self):
        if hasattr(self, "_selection_lbl"):
            self._selection_lbl.setText(f"Selected: {self._selected_node_name()}")
        if hasattr(self, "_status_lbl"):
            color = "#50fa7b" if self._executing else "rgba(255,255,255,150)"
            self._status_lbl.setStyleSheet(f"color: {color}; font: 8pt 'Times New Roman';")
            self._status_lbl.setText(self._status_text)

    def _set_status(self, text: str):
        self._status_text = text
        self._refresh_bottom_bar()

    def _open_create_object_dialog(self, folder_id: str):
        folder = self._node(folder_id)
        if not folder or folder.get("type") != "folder":
            return
        target_options = [(text, target_id) for target_id, text in self._sandbox_target_options("")]
        dialog = SandboxCreateObjectDialog(self._folder_allowed_types(folder), target_options=target_options, parent=self)
        if dialog.exec() != QtWidgets.QDialog.Accepted:
            return
        node_type, name, extra = dialog.values()
        if not name:
            name = node_type.title()
        self._create_node(folder_id, node_type, name, extra)

    def _show_index_warning_dialog(self, warnings: dict):
        if not warnings:
            return
        self._play_system_sound("SystemExclamation", 720)
        unique_messages = []
        seen = set()
        for node_id, warning in warnings.items():
            node = self._node(node_id)
            label = node.get("name", node_id) if node else node_id
            message = f"{label}: {warning}"
            if message not in seen:
                seen.add(message)
                unique_messages.append(message)
        QtWidgets.QMessageBox.warning(
            self,
            "Sequence Index Conflict",
            "Fix the sequence index conflicts before Execute.\n\n" + "\n".join(unique_messages),
            QtWidgets.QMessageBox.Ok,
        )

    def _prompt_edit_dialog(self, title: str, body: str, editor: QtWidgets.QWidget, getter):
        self._play_system_sound("SystemQuestion", 760)
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setModal(True)
        dialog.setWindowFlags(QtCore.Qt.Dialog | QtCore.Qt.FramelessWindowHint | QtCore.Qt.WindowStaysOnTopHint)
        dialog.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        dialog.resize(260, 120)
        layout = QtWidgets.QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)
        frame = QtWidgets.QFrame(dialog)
        frame.setStyleSheet("QFrame { background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0f0c29, stop:0.45 #400071, stop:1 #24243e); border: none; border-radius: 8px; } QLabel { color: white; }")
        layout.addWidget(frame)
        frame_layout = QtWidgets.QVBoxLayout(frame)
        frame_layout.setContentsMargins(14, 12, 14, 12)
        frame_layout.setSpacing(8)
        frame_layout.addWidget(QtWidgets.QLabel(title, alignment=QtCore.Qt.AlignCenter))
        body_lbl = QtWidgets.QLabel(body)
        body_lbl.setAlignment(QtCore.Qt.AlignCenter)
        body_lbl.setStyleSheet("font: 8pt 'Times New Roman'; color: rgba(255,255,255,150);")
        frame_layout.addWidget(body_lbl)
        frame_layout.addWidget(editor)
        row = QtWidgets.QHBoxLayout()
        row.addStretch()
        ok_btn = QtWidgets.QPushButton("OK")
        cancel_btn = QtWidgets.QPushButton("Cancel")
        for btn in (ok_btn, cancel_btn):
            btn.setFixedSize(64, 24)
            btn.setStyleSheet("QPushButton { background: rgba(255,255,255,16); color: white; border: none; border-radius: 4px; } QPushButton:hover { background: rgba(255,255,255,28); }")
        ok_btn.clicked.connect(dialog.accept)
        cancel_btn.clicked.connect(dialog.reject)
        row.addWidget(ok_btn)
        row.addWidget(cancel_btn)
        frame_layout.addLayout(row)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            return getter()
        return None

    def _setup_info_text(self):
        return (
            "<b>Sandbox Runtime</b>\n"
            "Execute arms enabled keybind listeners and can also run the selected sequence object.\n\n"
            "<b>Folders</b>\n"
            "If a folder is disabled, every child inside it is ignored during execution.\n\n"
            "<b>Keybind Objects</b>\n"
            "Keybind nodes work like runtime listeners. While execution is active, pressing their assigned key instantly triggers the linked marker or dragger.\n\n"
            "<b>Sequence Objects</b>\n"
            "Normal markers and draggers are sequence objects. Markers perform a click at their stored position, and draggers press at the start point, drag to the end point, then release.\n\n"
            "<b>Overlay Sync</b>\n"
            "Overlay handles stay synced with the hierarchy and properties panel in real time."
        )

    def _create_setup_info_dialog(self):
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("Sandbox Info")
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

        title = QtWidgets.QLabel("Sandbox Info")
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

        info_text = self._setup_info_text().replace("\n", "<br>")
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
