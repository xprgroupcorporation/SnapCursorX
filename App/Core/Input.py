import ctypes
import importlib
import os
from pathlib import Path

from PySide6 import QtCore
import win32api
from Core.Utils import CORE_DIR


CALLBACK = ctypes.CFUNCTYPE(None)
NATIVE_FALSE = ctypes.c_bool(False)


class ClickEngineBridge:
    def __init__(self):
        self._dll = None
        self._dll_path = None
        self._load_error = None
        self._callback_ref = None
        self._release_callback_ref = None
        self._has_native_click_count = False
        self._has_native_smooth_move = False
        self._dll_directories = []
        self._load()

    @property
    def available(self) -> bool:
        return self._dll is not None

    @property
    def dll_path(self):
        return self._dll_path

    @property
    def load_error(self):
        return self._load_error

    @property
    def has_native_click_count(self) -> bool:
        return self._has_native_click_count

    @property
    def has_native_smooth_move(self) -> bool:
        return self._has_native_smooth_move

    def _candidate_paths(self):
        return [
            CORE_DIR / "ClickEngine_tuned.dll",
            CORE_DIR / "ClickEngine.dll",
            CORE_DIR / "ClickEngine_linear.dll",
            CORE_DIR / "ClickEngine_recovery.dll",
            CORE_DIR / "ClickEngine_smoketest.dll",
            CORE_DIR.parent / "ClickEngine.dll",
            CORE_DIR.parent.parent / "ClickEngine.dll",
        ]

    def _load(self):
        errors = []

        try:
            importlib.import_module("pybind11")
        except Exception:
            pass

        for candidate in self._candidate_paths():
            if not candidate.exists():
                errors.append(f"missing: {candidate}")
                continue

            try:
                if hasattr(os, "add_dll_directory"):
                    self._dll_directories.append(os.add_dll_directory(str(candidate.parent)))
                dll = ctypes.WinDLL(str(candidate))
                dll.start_clicking.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_bool, ctypes.c_bool]
                dll.start_clicking.restype = None
                dll.start_clicking_ex.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_bool, ctypes.c_bool, ctypes.c_int]
                dll.start_clicking_ex.restype = None
                dll.stop_clicking.argtypes = []
                dll.stop_clicking.restype = None
                dll.set_callback.argtypes = [CALLBACK]
                dll.set_callback.restype = None
                dll.set_release_callback.argtypes = [CALLBACK]
                dll.set_release_callback.restype = None
                dll.smooth_move_cursor.argtypes = [
                    ctypes.c_int,
                    ctypes.c_int,
                    ctypes.c_int,
                    ctypes.c_int,
                    ctypes.c_int,
                ]
                dll.smooth_move_cursor.restype = ctypes.c_bool
                dll.mouse_button_down.argtypes = [ctypes.c_int]
                dll.mouse_button_down.restype = ctypes.c_bool
                dll.mouse_button_up.argtypes = [ctypes.c_int]
                dll.mouse_button_up.restype = ctypes.c_bool
                dll.release_all_mouse_buttons.argtypes = []
                dll.release_all_mouse_buttons.restype = None
            except Exception as exc:
                errors.append(f"{candidate} -> {exc}")
                continue

            has_native_click_count = False
            has_native_smooth_move = False
            try:
                dll.get_click_count.argtypes = []
                dll.get_click_count.restype = ctypes.c_uint64
                has_native_click_count = True
            except Exception:
                has_native_click_count = False
            try:
                has_native_smooth_move = bool(dll.smooth_move_cursor)
            except Exception:
                has_native_smooth_move = False

            self._dll = dll
            self._dll_path = candidate
            self._load_error = None
            self._has_native_click_count = has_native_click_count
            self._has_native_smooth_move = has_native_smooth_move
            print(f"[ClickEngine] DLL loaded: {candidate}")
            return

        self._dll = None
        self._dll_path = None
        self._load_error = " | ".join(errors) if errors else "No DLL candidates were checked."
        self._has_native_click_count = False
        self._has_native_smooth_move = False
        print(f"[ClickEngine] DLL load failed: {self._load_error}")

    def start_clicking(self, delay_us: int, x: int, y: int, follow_mouse: bool, click_randomness: bool):
        if not self.available:
            raise RuntimeError(f"ClickEngine DLL unavailable: {self._load_error}")

        normalized_delay = max(1, int(delay_us))
        target_x = int(x)
        target_y = int(y)
        follow = bool(follow_mouse)
        randomness = bool(click_randomness)
        print(f"[ClickEngine] Calling start_clicking(delay_us={normalized_delay}, x={target_x}, y={target_y}, follow_mouse={follow}, click_randomness={randomness})")
        self._dll.start_clicking(normalized_delay, target_x, target_y, follow, randomness)

    def start_clicking_ex(self, delay_us: int, hold_us: int, x: int, y: int, follow_mouse: bool, click_randomness: bool, button: int):
        if not self.available:
            raise RuntimeError(f"ClickEngine DLL unavailable: {self._load_error}")
        normalized_delay = max(1, int(delay_us))
        normalized_hold = max(0, int(hold_us))
        target_x = int(x)
        target_y = int(y)
        follow = bool(follow_mouse)
        randomness = bool(click_randomness)
        native_button = int(button)
        print(
            f"[ClickEngine] Calling start_clicking_ex(delay_us={normalized_delay}, hold_us={normalized_hold}, "
            f"x={target_x}, y={target_y}, follow_mouse={follow}, click_randomness={randomness}, button={native_button})"
        )
        self._dll.start_clicking_ex(normalized_delay, normalized_hold, target_x, target_y, follow, randomness, native_button)

    def stop_clicking(self):
        if not self.available:
            raise RuntimeError(f"ClickEngine DLL unavailable: {self._load_error}")

        print("[ClickEngine] Calling stop_clicking()")
        self._dll.stop_clicking()

    def set_callback(self, callback):
        if not self.available:
            raise RuntimeError(f"ClickEngine DLL unavailable: {self._load_error}")

        if callback is None:
            self._callback_ref = None
            self._dll.set_callback(ctypes.cast(0, CALLBACK))
            return

        self._callback_ref = CALLBACK(callback)
        self._dll.set_callback(self._callback_ref)

    def set_release_callback(self, callback):
        if not self.available:
            raise RuntimeError(f"ClickEngine DLL unavailable: {self._load_error}")

        if callback is None:
            self._release_callback_ref = None
            self._dll.set_release_callback(ctypes.cast(0, CALLBACK))
            return

        self._release_callback_ref = CALLBACK(callback)
        self._dll.set_release_callback(self._release_callback_ref)

    def get_click_count(self) -> int:
        if not self.available:
            raise RuntimeError(f"ClickEngine DLL unavailable: {self._load_error}")
        if not self._has_native_click_count:
            raise RuntimeError("ClickEngine DLL does not expose get_click_count()")
        return int(self._dll.get_click_count())

    def smooth_move_cursor(self, start_x: int, start_y: int, end_x: int, end_y: int, duration_ms: int) -> bool:
        if not self.available:
            raise RuntimeError(f"ClickEngine DLL unavailable: {self._load_error}")
        if not self._has_native_smooth_move:
            raise RuntimeError("ClickEngine DLL does not expose smooth_move_cursor()")
        return bool(
            self._dll.smooth_move_cursor(
                int(start_x),
                int(start_y),
                int(end_x),
                int(end_y),
                max(0, int(duration_ms)),
            )
        )

    def mouse_button_down(self, button: int) -> bool:
        if not self.available:
            raise RuntimeError(f"ClickEngine DLL unavailable: {self._load_error}")
        return bool(self._dll.mouse_button_down(int(button)))

    def mouse_button_up(self, button: int) -> bool:
        if not self.available:
            raise RuntimeError(f"ClickEngine DLL unavailable: {self._load_error}")
        return bool(self._dll.mouse_button_up(int(button)))

    def release_all_mouse_buttons(self):
        if not self.available:
            raise RuntimeError(f"ClickEngine DLL unavailable: {self._load_error}")
        self._dll.release_all_mouse_buttons()


_BRIDGE = None


def get_click_engine_bridge() -> ClickEngineBridge:
    global _BRIDGE
    if _BRIDGE is None:
        _BRIDGE = ClickEngineBridge()
    return _BRIDGE


class NativeClickController(QtCore.QObject):
    clicked = QtCore.Signal(int, int)
    click_started = QtCore.Signal(int, int)
    click_progress = QtCore.Signal(int, int)
    click_finished = QtCore.Signal(int, int)
    _queued_click = QtCore.Signal(int, int)
    _queued_release = QtCore.Signal(int, int)
    stopped = QtCore.Signal()

    def __init__(self, delay_us: int, x: int, y: int, follow_mouse: bool, click_randomness: bool, hold_ms: int = 0, mouse_button: str = "left", enable_click_feedback: bool = True, parent=None):
        super().__init__(parent)
        self._delay_us = max(1, int(delay_us))
        self._x = int(x)
        self._y = int(y)
        self._follow_mouse = bool(follow_mouse)
        self._click_randomness = bool(click_randomness)
        self._hold_ms = max(0, int(hold_ms))
        self._mouse_button = (mouse_button or "left").lower()
        self._enable_click_feedback = bool(enable_click_feedback)
        self._bridge = get_click_engine_bridge()
        self._active = False
        self._button_down_active = False
        self._release_point = None
        self._tracking_timer = QtCore.QTimer(self)
        self._tracking_timer.setInterval(8)
        self._tracking_timer.timeout.connect(self._poll_hold_cursor)
        self._use_callback_feedback = self._enable_click_feedback or (not self._bridge.has_native_click_count)
        if self._use_callback_feedback:
            self._queued_click.connect(self._schedule_click_effect, QtCore.Qt.QueuedConnection)
            self._queued_release.connect(self._schedule_release_effect, QtCore.Qt.QueuedConnection)
            self._bridge.set_callback(self._handle_native_click)
            self._bridge.set_release_callback(self._handle_native_release)
        else:
            self._bridge.set_callback(None)
            self._bridge.set_release_callback(None)

    def _native_button_code(self) -> int:
        if self._mouse_button == "right":
            return 1
        if self._mouse_button == "middle":
            return 2
        return 0

    def start(self):
        if self._active:
            return

        try:
            self._bridge.stop_clicking()
        except Exception:
            pass

        self._bridge.start_clicking_ex(
            self._delay_us,
            self._hold_ms * 1000,
            self._x,
            self._y,
            self._follow_mouse,
            self._click_randomness,
            self._native_button_code(),
        )
        self._active = True

    def stop(self):
        if not self._active:
            QtCore.QTimer.singleShot(0, lambda: self.stopped.emit())
            return

        try:
            self._bridge.stop_clicking()
        finally:
            self._tracking_timer.stop()
            if self._button_down_active:
                self._button_down_active = False
                try:
                    x, y = win32api.GetCursorPos()
                except Exception:
                    x, y = self._release_point or (self._x, self._y)
                self.click_finished.emit(int(x), int(y))
            self._active = False
            QtCore.QTimer.singleShot(0, lambda: self.stopped.emit())

    def wait(self, _timeout_ms=0):
        return True

    def update_target(self, x, y):
        self._x = int(x)
        self._y = int(y)

    def click_count(self) -> int:
        if not self._bridge.has_native_click_count:
            raise RuntimeError("Native click count unavailable")
        return self._bridge.get_click_count()

    @QtCore.Slot(int, int)
    def _schedule_click_effect(self, x, y):
        self._button_down_active = True
        self.click_started.emit(int(x), int(y))
        self.clicked.emit(int(x), int(y))
        if self._follow_mouse and self._hold_ms > 0:
            self._tracking_timer.start()

    @QtCore.Slot(int, int)
    def _schedule_release_effect(self, x, y):
        self._release_point = (int(x), int(y))
        self._tracking_timer.stop()
        if self._button_down_active:
            self._button_down_active = False
            self.click_finished.emit(int(x), int(y))

    def _poll_hold_cursor(self):
        if not self._button_down_active or not self._follow_mouse:
            self._tracking_timer.stop()
            return
        try:
            x, y = win32api.GetCursorPos()
        except Exception:
            return
        self.click_progress.emit(int(x), int(y))

    def _handle_native_click(self):
        if self._follow_mouse:
            try:
                x, y = win32api.GetCursorPos()
                self._queued_click.emit(int(x), int(y))
                return
            except Exception:
                pass

        self._queued_click.emit(self._x, self._y)

    def _handle_native_release(self):
        if self._follow_mouse:
            try:
                x, y = win32api.GetCursorPos()
                self._queued_release.emit(int(x), int(y))
                return
            except Exception:
                pass
        self._queued_release.emit(self._x, self._y)
