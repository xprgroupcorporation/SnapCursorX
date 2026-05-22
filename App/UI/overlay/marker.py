from PySide6 import QtWidgets, QtCore, QtGui
import win32gui
import win32con
from Config.Manager import ConfigManager


def _event_global_pos(event):
    if hasattr(event, "globalPosition"):
        return event.globalPosition().toPoint()
    return event.globalPos()


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
    except Exception:
        pass


class Marker(QtWidgets.QWidget):
    def __init__(self, x, y, radius=20, color=QtGui.QColor(255, 0, 0)):
        super().__init__()
        self.base_radius = max(1, int(radius))
        self.radius = self.base_radius
        self.color = color
        self.dragging = False
        self.drag_pos = None
        self._interactive = True
        self._executing_visual = False
        self.apply_size_multiplier(ConfigManager.marker_size_percent(), center_x=x, center_y=y)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_NoSystemBackground)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.setMask(QtGui.QRegion(self.rect(), QtGui.QRegion.Ellipse))

    def apply_size_multiplier(self, percent: int, center_x: int = None, center_y: int = None):
        if center_x is None or center_y is None:
            center_x = self.x() + self.radius
            center_y = self.y() + self.radius

        self.radius = ConfigManager.scale_marker_size(self.base_radius, percent=percent)
        diameter = self.radius * 2
        self.setGeometry(
            int(center_x - self.radius),
            int(center_y - self.radius),
            int(diameter),
            int(diameter),
        )
        self.setMask(QtGui.QRegion(self.rect(), QtGui.QRegion.Ellipse))
        self.update()

    def set_interactive(self, enabled: bool):
        self._interactive = enabled
        self.drag_pos = None
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents, not enabled)

    def set_execution_visual(self, enabled: bool):
        self._executing_visual = enabled
        self.update()

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)

        margin = 1
        diameter = self.radius * 2 - margin * 2

        hitbox_color = QtGui.QColor(self.color)
        hitbox_color.setAlpha(32 if self._executing_visual else 48)
        painter.setBrush(hitbox_color)
        painter.setPen(QtCore.Qt.NoPen)
        painter.drawEllipse(margin, margin, diameter, diameter)

        painter.setBrush(QtCore.Qt.NoBrush)
        painter.setPen(QtGui.QPen(self.color, 2))
        painter.drawEllipse(margin, margin, diameter, diameter)

        painter.setBrush(self.color)
        painter.setPen(QtCore.Qt.NoPen)
        core_size = 6 if self._executing_visual else 8
        offset = core_size // 2
        painter.drawEllipse(self.radius - offset, self.radius - offset, core_size, core_size)

    def mousePressEvent(self, event):
        if not self._interactive:
            event.ignore()
            return
        if event.button() == QtCore.Qt.LeftButton:
            widget = self.childAt(event.pos())
            if isinstance(widget, QtWidgets.QPushButton):
                self.drag_pos = None
            else:
                self.drag_pos = _event_global_pos(event)

        # 🔥 Prevent focus steal on click
        parent = self.parentWidget()
        if parent:
            hwnd = int(parent.winId())
            _strip_native_window_frame(hwnd)
            win32gui.SetWindowPos(
                hwnd,
                win32con.HWND_TOPMOST,
                0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE
            )

    def mouseMoveEvent(self, event):
        if not self._interactive:
            event.ignore()
            return
        if event.buttons() == QtCore.Qt.LeftButton and self.drag_pos:
            self.move(
                self.pos() + _event_global_pos(event) - self.drag_pos
            )
            self.drag_pos = _event_global_pos(event)

            # 🔥 Sync with Overlay data
            parent = self.parentWidget()
            if parent and hasattr(parent, "update_marker_position"):
                parent.update_marker_position(self)

    def mouseReleaseEvent(self, event):
        if not self._interactive:
            event.ignore()
            return
        self.drag_pos = None
