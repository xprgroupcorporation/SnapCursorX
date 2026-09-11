import ctypes
import logging
import os
import sys
import tempfile
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
from Config.Manager import ConfigManager
from Core.Startup import set_run_on_start


def _configure_logging():
    """Keep startup/background failures available after a silent crash."""
    try:
        log_dir = Path(tempfile.gettempdir()) / "SnapCursorX"
        log_dir.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            filename=str(log_dir / "snapcursorx.log"),
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
            encoding="utf-8",
        )
    except Exception:
        # Logging must never prevent the application from starting.
        pass
<<<<<<< HEAD


def _configure_logging():
    """Keep startup/background failures available after a silent crash."""
    try:
        log_dir = Path(tempfile.gettempdir()) / "SnapCursorX"
        log_dir.mkdir(parents=True, exist_ok=True)
        logging.basicConfig(
            filename=str(log_dir / "snapcursorx.log"),
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
            encoding="utf-8",
        )
    except Exception:
        # Logging must never prevent the application from starting.
        pass
=======
>>>>>>> main


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
    """Global exception handler - prevents crashes from propagating."""
    print("\n=== UNCAUGHT EXCEPTION ===")
    traceback.print_exception(exc_type, exc_value, exc_traceback)
    # Don't re-raise - let app continue running

sys.excepthook = handle_exception


def _install_qt_error_handler():
    """Install handler for Qt signal/slot exceptions."""
    original_excepthook = sys.excepthook
    
    def qt_excepthook(exc_type, exc_value, exc_traceback):
        print(f"\n[Qt Exception] {exc_type.__name__}: {exc_value}")
        traceback.print_exception(exc_type, exc_value, exc_traceback)
    
    sys.excepthook = qt_excepthook


def _show_already_running_warning():
    flags = 0x00000030 | 0x00040000 | 0x00001000  # warning icon, topmost, system modal
    try:
        ctypes.windll.user32.MessageBoxW(
            None,
            "SnapCursorX is already running.",
            "SnapCursorX",
            flags,
        )
    except Exception:
        QtWidgets.QMessageBox.warning(
            None,
            "SnapCursorX",
            "SnapCursorX is already running.",
        )

def main():
    _configure_logging()
    _configure_windows_dpi()
    _install_qt_error_handler()

    try:
        startup_config = ConfigManager.load()
        startup_enabled = bool(
            startup_config.get("general", {}).get("Run_On_Start", False)
        )
        startup_ok, startup_error = set_run_on_start(startup_enabled)
        if not startup_ok:
            logging.getLogger(__name__).warning(
                "Unable to apply Run On Start setting: %s",
                startup_error,
            )
    except Exception:
        logging.getLogger(__name__).exception(
            "Failed to apply Run On Start setting during startup"
        )
    
    from Loading import LoadingWindow
    from UI.components.animations import WindowAnimator

    app = QtWidgets.QApplication(sys.argv)
    
    # Install exception handler for this thread's QApplication
    old_hook = sys.excepthook
    
    def safe_exec():
        try:
            return app.exec()
        except Exception as e:
            print(f"[CRASH PROTECTION] App exception caught and suppressed: {e}")
            traceback.print_exc()
            return 1
    
    single_instance_mutex = win32event.CreateMutex(
        None,
        True,
        "Local\\SnapCursorX_MainControlPanel_SingleInstance"
    )

    if win32api.GetLastError() in (winerror.ERROR_ALREADY_EXISTS, winerror.ERROR_ACCESS_DENIED):
        _show_already_running_warning()
        return 0

    app._single_instance_mutex = single_instance_mutex

    icon = QtGui.QIcon(str(ASSETS_DIR / "app_icon.ico"))
    app.setWindowIcon(icon)

    state = {"loading": None, "control": None, "control_class": None, "opening_control": False}

    def preload_control_panel_class():
        if state["control_class"] is not None:
            return
        try:
            from UI.main_window import ControlPanel
            state["control_class"] = ControlPanel
        except Exception as e:
            print(f"[ERROR] Failed to preload ControlPanel: {e}")
            traceback.print_exc()

    def open_control_panel():
        if state["control"] is not None or state["opening_control"]:
            return
        state["opening_control"] = True

        try:
            preload_control_panel_class()
            if state["control_class"] is None:
                print("[ERROR] ControlPanel class failed to load")
                return
            
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
        except Exception as e:
            print(f"[ERROR] Failed to open control panel: {e}")
            traceback.print_exc()
        finally:
            state["opening_control"] = False

    try:
        loading = LoadingWindow(startup_delay_ms=550)
        loading.setWindowIcon(icon)
        loading.startup_ready.connect(lambda: QtCore.QTimer.singleShot(250, open_control_panel))
        loading.show()
        state["loading"] = loading
        QtCore.QTimer.singleShot(0, preload_control_panel_class)
    except Exception as e:
        print(f"[ERROR] Failed to create loading window: {e}")
        traceback.print_exc()
        return 1

    return safe_exec()


if __name__ == "__main__":
    sys.exit(main())
