import ctypes
import sys

from PySide6 import QtWidgets, QtCore, QtGui
import win32gui
import win32con

from Config.Manager import ConfigManager
from UI.overlay.marker import Marker


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


def _suppress_native_window_chrome(hwnd):
    _strip_native_window_frame(hwnd)
    try:
        ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        ex_style |= win32con.WS_EX_TOOLWINDOW | win32con.WS_EX_LAYERED | win32con.WS_EX_NOACTIVATE
        win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE, ex_style)
    except Exception:
        pass
    try:
        DWMWA_NCRENDERING_POLICY = 2
        DWMNCRP_DISABLED = 1
        DWMWA_BORDER_COLOR = 34
        DWM_COLOR_NONE = 0xFFFFFFFE
        policy = ctypes.c_int(DWMNCRP_DISABLED)
        none_color = ctypes.c_int(DWM_COLOR_NONE)
        dwmapi = ctypes.windll.dwmapi
        dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_NCRENDERING_POLICY, ctypes.byref(policy), ctypes.sizeof(policy))
        dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_BORDER_COLOR, ctypes.byref(none_color), ctypes.sizeof(none_color))
    except Exception:
        pass


def _runtime_main_attr(name):
    main_mod = (
        sys.modules.get("UI.main_window")
        or sys.modules.get("__main__")
        or sys.modules.get("Main")
    )
    if main_mod is None or not hasattr(main_mod, name):
        raise AttributeError(f"Runtime main module is missing {name}")
    return getattr(main_mod, name)


class Overlay(QtWidgets.QWidget):
    def __init__(self):
      super().__init__()
      self.setWindowFlags(
          QtCore.Qt.Window |
          QtCore.Qt.FramelessWindowHint |
          QtCore.Qt.BypassWindowManagerHint |
          QtCore.Qt.NoDropShadowWindowHint |
          QtCore.Qt.WindowStaysOnTopHint |
          QtCore.Qt.Tool
      )
      self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
      self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
      self.setWindowFlag(QtCore.Qt.WindowDoesNotAcceptFocus)

      screen = QtWidgets.QApplication.primaryScreen().geometry()
      self.setGeometry(screen)

      self.markers = []
      self._effects = []
      self._execution_indicator = None
      self._execution_endpoint_indicator = None
      self.on_marker_moved = None  # optional callback(x, y) — set by SingleModeUI
      self._mask_update_timer = QtCore.QTimer(self)
      self._mask_update_timer.setSingleShot(True)
      self._mask_update_timer.timeout.connect(self.update_hit_region)

      # Remove old win32 block and replace with this:
      hwnd = int(self.winId())
      _suppress_native_window_chrome(hwnd)
      ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
      win32gui.SetWindowLong(
          hwnd, win32con.GWL_EXSTYLE,
          ex_style | win32con.WS_EX_LAYERED | win32con.WS_EX_NOACTIVATE
      )

      # Force and KEEP topmost via win32 (stronger than Qt flag)
      self._force_topmost()

      # Re-assert every 500ms so other windows can't steal top
      self._top_timer = QtCore.QTimer(self)
      self._top_timer.timeout.connect(self._force_topmost)
      self._top_timer.start(500)

    def _force_topmost(self):
        hwnd = int(self.winId())
        _suppress_native_window_chrome(hwnd)
        # Re-apply NOACTIVATE every tick so it can't be stripped
        ex_style = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
        win32gui.SetWindowLong(
            hwnd, win32con.GWL_EXSTYLE,
            ex_style | win32con.WS_EX_NOACTIVATE | win32con.WS_EX_LAYERED
        )
        win32gui.SetWindowPos(
            hwnd,
            win32con.HWND_TOPMOST,
            0, 0, 0, 0,
            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE | win32con.SWP_FRAMECHANGED
        )

    def new(self, x, y):
        marker = Marker(x, y)
        marker.setParent(self)
        marker.show()
        self.markers.append({'marker': marker, 'x': x, 'y': y})
        self._schedule_hit_region_update()

    def refresh_marker_sizes(self):
        marker_percent = ConfigManager.marker_size_percent()
        for marker_info in self.markers:
            marker = marker_info["marker"]
            marker.apply_size_multiplier(
                marker_percent,
                center_x=marker_info["x"],
                center_y=marker_info["y"],
            )

        if self._execution_indicator and self.markers:
            marker = self.markers[0]["marker"]
            self._execution_indicator.set_base_size(marker.radius * 2)
        self._schedule_hit_region_update()

    def update_marker_position(self, marker):
        for m in self.markers:
            if m['marker'] == marker:
                m['x'] = marker.x() + marker.radius
                m['y'] = marker.y() + marker.radius
                # Notify any listener (e.g. SingleModeUI) so data stays in sync
                if callable(self.on_marker_moved):
                    self.on_marker_moved(m['x'], m['y'])
        self._schedule_hit_region_update()

    def _schedule_hit_region_update(self):
        if self._mask_update_timer.isActive():
            return
        self._mask_update_timer.start(16)

    def update_hit_region(self):
        region = QtGui.QRegion()
        for m in self.markers:
            if m['marker'].isVisible() and getattr(m['marker'], "_interactive", True):
                region = region.united(QtGui.QRegion(m['marker'].geometry()))
        self.setMask(region)  # only visible marker areas receive clicks, rest passes through

    def set_marker_execution_mode(self, executing: bool, keep_visible: bool, x: int = None, y: int = None, label_text: str = "", text_only: bool = False, secondary_dot=None):
        ExecutionMarkerIndicator = _runtime_main_attr("ExecutionMarkerIndicator")
        for m in self.markers:
            marker = m["marker"]
            marker.set_interactive(not executing)
            marker.set_execution_visual(False)
            if executing:
                marker.hide()
            elif marker.isVisible():
                marker.show()

        if executing and keep_visible and self.markers:
            marker = self.markers[0]["marker"]
            if self._execution_indicator is None:
                self._execution_indicator = ExecutionMarkerIndicator(marker.radius * 2)
            else:
                self._execution_indicator.set_base_size(marker.radius * 2)
            self._execution_indicator.set_display_mode("text_only" if text_only else "ring")
            self._execution_indicator.set_label_text(label_text)
            center_x = x if x is not None else (marker.x() + marker.radius)
            center_y = y if y is not None else (marker.y() + marker.radius)
            self._execution_indicator.move_center(
                center_x,
                center_y,
            )
        elif self._execution_indicator:
            self._execution_indicator.set_display_mode("ring")
            self._execution_indicator.set_label_text("")
            self._execution_indicator.hide()
        if executing and keep_visible and secondary_dot and self.markers:
            marker = self.markers[0]["marker"]
            if self._execution_endpoint_indicator is None:
                self._execution_endpoint_indicator = ExecutionMarkerIndicator(marker.radius * 2)
            else:
                self._execution_endpoint_indicator.set_base_size(marker.radius * 2)
            self._execution_endpoint_indicator.set_display_mode("dot_only")
            self._execution_endpoint_indicator.set_label_text("")
            self._execution_endpoint_indicator.move_center(int(secondary_dot[0]), int(secondary_dot[1]))
        elif self._execution_endpoint_indicator:
            self._execution_endpoint_indicator.set_display_mode("ring")
            self._execution_endpoint_indicator.set_label_text("")
            self._execution_endpoint_indicator.hide()
        self.update_hit_region()

    def show_position_indicator(self, x: int, y: int, label_text: str = ""):
        ExecutionMarkerIndicator = _runtime_main_attr("ExecutionMarkerIndicator")
        if not self.markers:
            return
        marker = self.markers[0]["marker"]
        if self._execution_indicator is None:
            self._execution_indicator = ExecutionMarkerIndicator(marker.radius * 2)
        else:
            self._execution_indicator.set_base_size(marker.radius * 2)
        self._execution_indicator.set_display_mode("ring")
        self._execution_indicator.set_label_text(label_text)
        self._execution_indicator.move_center(x, y)

    def hide_position_indicator(self):
        if self._execution_indicator:
            self._execution_indicator.set_label_text("")
            self._execution_indicator.hide()

    def show_click_effect(self, x, y):
        ClickEffect = _runtime_main_attr("ClickEffect")
        if not self.markers:
            return
        marker = self.markers[0]["marker"]
        effect = ClickEffect(x, y, marker.radius * 4)
        self._effects.append(effect)

        def cleanup():
            if effect in self._effects:
                self._effects.remove(effect)

        effect.destroyed.connect(lambda *_: cleanup())
        effect.show()

    def move_active_click_effect(self, x, y):
        if not self._effects:
            return
        self._effects[-1].move_center(x, y)

    def release_click_effect(self, x, y):
        if not self._effects:
            return
        for effect in reversed(self._effects):
            center_x = effect.x() + effect.width() / 2
            center_y = effect.y() + effect.height() / 2
            if abs(center_x - x) <= 1 and abs(center_y - y) <= 1:
                effect.finish_release()
                return
        self._effects[-1].finish_release()
