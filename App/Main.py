import ctypes
import os
import sys
import traceback
import win32gui
import win32con
import win32api
import win32event
import winerror
from pathlib import Path

if os.name == "nt":
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "0")
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "0")
    os.environ.setdefault("QT_SCALE_FACTOR", "1")

from PySide6 import QtCore, QtGui, QtWidgets

# Add parent directory to Python path so imports work
sys.path.insert(0, str(Path(__file__).parent))

from Core.Utils import ASSETS_DIR


def _configure_windows_dpi():
    if os.name != "nt":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

def handle_exception(exc_type, exc_value, exc_traceback):
    print("\n=== UNCAUGHT EXCEPTION ===")
    traceback.print_exception(exc_type, exc_value, exc_traceback)

sys.excepthook = handle_exception

def main():
    _configure_windows_dpi()
    from Loading import LoadingWindow
    from UI.components.animations import WindowAnimator

    app = QtWidgets.QApplication(sys.argv)
    single_instance_mutex = win32event.CreateMutex(
        None,
        True,
        "Local\\SnapCursorX_MainControlPanel_SingleInstance"
    )

    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        QtWidgets.QMessageBox.warning(
            None,
            "SnapCursorX",
            "SnapCursorX is already running."
        )
        return 0

    app._single_instance_mutex = single_instance_mutex

    icon = QtGui.QIcon(str(ASSETS_DIR / "app_icon.ico"))
    app.setWindowIcon(icon)

    state = {"loading": None, "control": None, "control_class": None, "opening_control": False}

    def preload_control_panel_class():
        if state["control_class"] is not None:
            return
        from UI.main_window import ControlPanel
        state["control_class"] = ControlPanel

    def open_control_panel():
        if state["control"] is not None or state["opening_control"]:
            return
        state["opening_control"] = True

        try:
            preload_control_panel_class()
            control = state["control_class"]()
            control.setWindowIcon(icon)

            end_pos = control.pos()
            start_pos = end_pos + QtCore.QPoint(0, 24)
            control.move(start_pos)
            control.show()
            control.raise_()
            control.activateWindow()
            app.processEvents()

            if state["loading"] is not None:
                state["loading"].close()
                state["loading"].deleteLater()
                state["loading"] = None

            WindowAnimator.fade_in(control, duration=200)
            WindowAnimator.slide(control, start_pos, end_pos, duration=200)
            state["control"] = control
        finally:
            state["opening_control"] = False

    loading = LoadingWindow(startup_delay_ms=550)
    loading.setWindowIcon(icon)
    loading.startup_ready.connect(lambda: QtCore.QTimer.singleShot(250, open_control_panel))
    loading.show()
    state["loading"] = loading
    QtCore.QTimer.singleShot(0, preload_control_panel_class)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
