from PySide6 import QtWidgets, QtCore, QtGui
import copy
import ctypes
from ctypes import wintypes
import importlib
import pyautogui
import queue
import random
import threading
import time
import winsound
import win32api
import win32con
import win32gui

from Config.Manager import ConfigManager
from Core.Setup import ActiveSetupManager
from Core.timing import apply_cycle_timing, interval_ms_from_timing, normalize_timing_config
from Modes._SharedUtils.Worker_helper import SharedWorkerHelper
from UI.components.animations import WindowAnimator


def _main_window_module():
    return importlib.import_module("UI.main_window")


def _overlay_type():
    return _main_window_module()._overlay_type()


def _overlay_window_hwnds():
    return _main_window_module()._overlay_window_hwnds()


def atomic_json_write(path, data):
    return _main_window_module().atomic_json_write(path, data)


def get_click_engine_bridge():
    return importlib.import_module("Core.Input").get_click_engine_bridge()


def read_click_randomness(source, default=True):
    return _main_window_module().read_click_randomness(source, default)


def write_click_randomness(target, value):
    return _main_window_module().write_click_randomness(target, value)


def _keybind_listener_type():
    return _main_window_module().KeybindListener


def _keybind_capture_dialog_type():
    return _main_window_module().KeybindCaptureDialog


MOUSE_BEHAVIOR_KEY = "mouse_behavior"
MOUSE_BEHAVIOR_DEFAULT = "default"
MOUSE_BEHAVIOR_TELEPORT = "teleport"
MOUSE_BEHAVIOR_PYTHON = "python"
MOUSE_BEHAVIOR_VALUES = {
    MOUSE_BEHAVIOR_DEFAULT,
    MOUSE_BEHAVIOR_TELEPORT,
    MOUSE_BEHAVIOR_PYTHON,
}


def read_mouse_behavior(source, default=MOUSE_BEHAVIOR_DEFAULT):
    if not isinstance(source, dict):
        return default
    value = str(source.get(MOUSE_BEHAVIOR_KEY, "") or "").strip().lower()
    if value == "background":
        value = MOUSE_BEHAVIOR_PYTHON
    if value in MOUSE_BEHAVIOR_VALUES:
        return value
    if "teleport_mouse" in source:
        return MOUSE_BEHAVIOR_TELEPORT if bool(source.get("teleport_mouse", False)) else MOUSE_BEHAVIOR_PYTHON
    return default


def write_mouse_behavior(target, value):
    if not isinstance(target, dict):
        return
    normalized = str(value or MOUSE_BEHAVIOR_DEFAULT).strip().lower()
    if normalized not in MOUSE_BEHAVIOR_VALUES:
        normalized = MOUSE_BEHAVIOR_DEFAULT
    target[MOUSE_BEHAVIOR_KEY] = normalized
    target.pop("teleport_mouse", None)


class SandboxDataModel:
    VERSION = 3

    @staticmethod
    def _general_defaults():
        cfg = ConfigManager.load()
        merged = {}
        merged.update(cfg.get("general", {}))
        merged.update(cfg.get("visual", {}))
        merged.update(cfg.get("starter_values", {}))
        return merged

    @classmethod
    def default_sandbox(cls):
        gen = cls._general_defaults()
        mouse_hold = max(0, int(gen.get("Default_Mouse_Hold_MS", 100)))
        drag_duration = max(0, int(gen.get("Default_Drag_Duration_MS", mouse_hold)))
        seq_delay = max(1, int(gen.get("Default_Delay_Before_Next_Target_MS", 200)))
        sandbox = {
            "version": cls.VERSION,
            "selected_id": "keybind_1",
            "root_ids": ["folder_keybind", "folder_sequence"],
            "objects": {
                "folder_keybind": {
                    "id": "folder_keybind",
                    "type": "folder",
                    "name": "Keybind",
                    "enabled": True,
                    "children": ["keybind_1"],
                    "parent_id": "",
                    "folder_kind": "keybind",
                },
                "folder_sequence": {
                    "id": "folder_sequence",
                    "type": "folder",
                    "name": "Sequence",
                    "enabled": True,
                    "children": ["marker_1", "dragger_1"],
                    "parent_id": "",
                    "folder_kind": "sequence",
                    "repeat_mode": "until_stop",
                    "repeat_times_target": 5,
                    "repeat_timer_seconds": 60,
                },
                "keybind_1": {
                    "id": "keybind_1",
                    "type": "keybind",
                    "name": "Quick Marker",
                    "enabled": True,
                    "parent_id": "folder_keybind",
                    "keybind": "Q",
                    "target_id": "marker_1",
                    "description": "Instantly click Marker A",
                    "teleport_back": True,
                },
                "marker_1": {
                    "id": "marker_1",
                    "type": "marker",
                    "name": "Marker A",
                    "enabled": True,
                    "parent_id": "folder_sequence",
                    "x": 500,
                    "y": 300,
                    "mouse_hold_ms": mouse_hold,
                    "click_randomness": True,
                    "mouse_button": "left",
                    MOUSE_BEHAVIOR_KEY: MOUSE_BEHAVIOR_DEFAULT,
                    "index": 0,
                },
                "dragger_1": {
                    "id": "dragger_1",
                    "type": "dragger",
                    "name": "Dragger A",
                    "enabled": True,
                    "parent_id": "folder_sequence",
                    "start_x": 620,
                    "start_y": 340,
                    "end_x": 760,
                    "end_y": 340,
                    "mouse_hold_ms": drag_duration,
                    "mouse_button": "left",
                    MOUSE_BEHAVIOR_KEY: MOUSE_BEHAVIOR_DEFAULT,
                    "index": 10,
                },
            },
        }
        apply_cycle_timing(sandbox["objects"]["marker_1"], seq_delay, "ms")
        apply_cycle_timing(sandbox["objects"]["dragger_1"], seq_delay, "ms")
        return sandbox

    @classmethod
    def _default_node(cls, node_type: str, node_id: str, name: str, parent_id: str):
        gen = cls._general_defaults()
        mouse_hold = max(0, int(gen.get("Default_Mouse_Hold_MS", 100)))
        drag_duration = max(0, int(gen.get("Default_Drag_Duration_MS", mouse_hold)))
        seq_delay = max(1, int(gen.get("Default_Delay_Before_Next_Target_MS", 200)))
        if node_type == "keybind":
            return {
                "id": node_id,
                "type": "keybind",
                "name": name,
                "enabled": True,
                "parent_id": parent_id,
                "keybind": "",
                "target_id": "",
                "description": "",
                "teleport_back": True,
            }
        if node_type == "dragger":
            node = {
                "id": node_id,
                "type": "dragger",
                "name": name,
                "enabled": True,
                "parent_id": parent_id,
                "start_x": 600,
                "start_y": 340,
                "end_x": 760,
                "end_y": 340,
                "mouse_hold_ms": drag_duration,
                "mouse_button": "left",
                MOUSE_BEHAVIOR_KEY: MOUSE_BEHAVIOR_DEFAULT,
                "index": 10,
            }
            apply_cycle_timing(node, seq_delay, "ms")
            return node
        node = {
            "id": node_id,
            "type": "marker",
            "name": name,
            "enabled": True,
            "parent_id": parent_id,
            "x": 520,
            "y": 320,
            "mouse_hold_ms": mouse_hold,
                    "click_randomness": True,
            "mouse_button": "left",
            MOUSE_BEHAVIOR_KEY: MOUSE_BEHAVIOR_DEFAULT,
            "index": 10,
        }
        apply_cycle_timing(node, seq_delay, "ms")
        return node

    @classmethod
    def ensure_structure(cls, data: dict):
        data["mode"] = "sandbox"
        sandbox = data.setdefault("sandbox", {})
        defaults = cls.default_sandbox()
        if not sandbox.get("objects"):
            data["sandbox"] = copy.deepcopy(defaults)
            return

        sandbox.setdefault("version", cls.VERSION)
        sandbox.setdefault("root_ids", list(defaults["root_ids"]))
        sandbox.setdefault("selected_id", defaults["selected_id"])
        sandbox.setdefault("objects", {})
        objects = sandbox["objects"]

        for node_id, node in list(objects.items()):
            if not isinstance(node, dict):
                objects[node_id] = {"id": node_id, "type": "marker", "name": node_id}
                node = objects[node_id]
            node.setdefault("id", node_id)
            node.setdefault("name", node_id)
            node.setdefault("enabled", True)
            node_type = node.setdefault("type", "marker")
            if node_type == "folder":
                node.setdefault("children", [])
                node.setdefault("folder_kind", "keybind" if "keybind" in node_id.lower() else "sequence")
                if node.get("folder_kind") == "sequence":
                    node.setdefault("repeat_mode", "until_stop")
                    node.setdefault("repeat_times_target", 5)
                    node.setdefault("repeat_timer_seconds", 60)
            elif node_type == "keybind":
                node.setdefault("keybind", "")
                node.setdefault("target_id", "")
                node.setdefault("description", "")
                node.setdefault("teleport_back", True)
            elif node_type == "marker":
                node.setdefault("x", 0)
                node.setdefault("y", 0)
                normalize_timing_config(node, default_interval_ms=interval_ms_from_timing(defaults["objects"]["marker_1"]))
                node.setdefault("mouse_hold_ms", defaults["objects"]["marker_1"]["mouse_hold_ms"])
                write_click_randomness(node, read_click_randomness(node, True))
                node.setdefault("mouse_button", "left")
                write_mouse_behavior(node, read_mouse_behavior(node, defaults["objects"]["marker_1"][MOUSE_BEHAVIOR_KEY]))
                node.setdefault("index", 10)
            elif node_type == "dragger":
                node.setdefault("start_x", 0)
                node.setdefault("start_y", 0)
                node.setdefault("end_x", 0)
                node.setdefault("end_y", 0)
                normalize_timing_config(node, default_interval_ms=interval_ms_from_timing(defaults["objects"]["dragger_1"]))
                node.setdefault("mouse_hold_ms", defaults["objects"]["dragger_1"]["mouse_hold_ms"])
                node.setdefault("mouse_button", "left")
                write_mouse_behavior(node, read_mouse_behavior(node, defaults["objects"]["dragger_1"][MOUSE_BEHAVIOR_KEY]))
                node.setdefault("index", 10)
            node.setdefault("parent_id", "")

        cls._rebuild_parent_links(sandbox)
        cls._sanitize_references(sandbox)
        cls._apply_index_rules(sandbox)

    @classmethod
    def _rebuild_parent_links(cls, sandbox: dict):
        objects = sandbox.get("objects", {})
        for node in objects.values():
            node["parent_id"] = node.get("parent_id", "")
        for root_id in sandbox.get("root_ids", []):
            if root_id in objects:
                objects[root_id]["parent_id"] = ""
        for node_id, node in objects.items():
            if node.get("type") != "folder":
                continue
            clean_children = []
            for child_id in list(node.get("children", [])):
                if child_id in objects and child_id != node_id:
                    objects[child_id]["parent_id"] = node_id
                    clean_children.append(child_id)
            node["children"] = clean_children

    @classmethod
    def _sanitize_references(cls, sandbox: dict):
        objects = sandbox.get("objects", {})
        valid_targets = {node_id for node_id, node in objects.items() if node.get("type") in ("marker", "dragger")}
        for node in objects.values():
            if node.get("type") == "keybind" and node.get("target_id") not in valid_targets:
                node["target_id"] = ""
        sandbox["root_ids"] = [root_id for root_id in sandbox.get("root_ids", []) if root_id in objects] or list(cls.default_sandbox()["root_ids"])
        if sandbox.get("selected_id") not in objects:
            sandbox["selected_id"] = sandbox["root_ids"][0] if sandbox["root_ids"] else ""

    @classmethod
    def _apply_index_rules(cls, sandbox: dict):
        objects = sandbox.get("objects", {})
        keybound_targets = {
            node.get("target_id", "")
            for node in objects.values()
            if node.get("type") == "keybind" and node.get("target_id")
        }
        for node_id, node in objects.items():
            if node.get("type") not in ("marker", "dragger"):
                continue
            if node_id in keybound_targets:
                node["index"] = 0
            else:
                node["index"] = max(1, int(node.get("index", 10) or 10))

    @classmethod
    def sanitize_snapshot(cls, sandbox: dict):
        clean = copy.deepcopy(sandbox)
        wrapper = {"mode": "sandbox", "sandbox": clean}
        cls.ensure_structure(wrapper)
        return wrapper["sandbox"]

    @classmethod
    def next_id(cls, objects: dict, prefix: str):
        index = 1
        while f"{prefix}_{index}" in objects:
            index += 1
        return f"{prefix}_{index}"

    @classmethod
    def clone_node(cls, node: dict, node_id: str, parent_id: str):
        cloned = copy.deepcopy(node)
        cloned["id"] = node_id
        cloned["name"] = f"Copy - {node.get('name', 'Unnamed')}"
        cloned["parent_id"] = parent_id
        if cloned.get("type") == "keybind":
            cloned["keybind"] = ""
        return cloned


class SandboxExecutionWorker(SharedWorkerHelper, QtCore.QThread):
    stopped = QtCore.Signal()
    status_changed = QtCore.Signal(str)
    click_started = QtCore.Signal(int, int)
    click_finished = QtCore.Signal(int, int)
    drag_progress = QtCore.Signal(int, int)
    target_completed = QtCore.Signal(str)

    def __init__(self, sandbox_data: dict):
        super().__init__()
        self.sandbox_data = copy.deepcopy(sandbox_data)
        self._queue = queue.Queue()
        self._running = False
        self._click_engine_bridge = None
        self._keybind_burst_lock = threading.Lock()
        self._keybind_bursts = {}
        self._keybind_last_user_positions = {}
        self._keybind_spam_window_seconds = 0.18
        self._sequence_lock_depth = 0

    def _all_keybind_targets(self):
        targets = {}
        for node_id, node in self.sandbox_data.get("objects", {}).items():
            if node.get("type") == "keybind":
                target_id = node.get("target_id", "")
                if target_id:
                    targets.setdefault(target_id, []).append(node_id)
        return targets

    def _active_keybind_targets(self):
        targets = {}
        keybind_folder = self._node("folder_keybind")
        if keybind_folder and not bool(keybind_folder.get("enabled", True)):
            return targets
        for node_id, node in self.sandbox_data.get("objects", {}).items():
            if node.get("type") != "keybind":
                continue
            if not self._is_enabled(node_id):
                continue
            target_id = node.get("target_id", "")
            if target_id:
                targets.setdefault(target_id, []).append(node_id)
        return targets

    def stop(self):
        self._running = False
        with self._keybind_burst_lock:
            self._keybind_bursts.clear()
            self._keybind_last_user_positions.clear()
        self._clear_cursor_lock()
        try:
            bridge = self._native_bridge()
            if bridge and bridge.available:
                bridge.stop_clicking()
                bridge.release_all_mouse_buttons()
        except Exception:
            pass
        try:
            pyautogui.mouseUp(button="left")
            pyautogui.mouseUp(button="right")
            pyautogui.mouseUp(button="middle")
        except Exception:
            pass

    def enqueue_target(self, node_id: str):
        if node_id:
            self._queue.put(node_id)

    def trigger_keybind_target(self, node_id: str):
        if not self._running or not node_id:
            return
        thread = threading.Thread(
            target=self._execute_keybind_target_async,
            args=(node_id,),
            daemon=True,
        )
        thread.start()

    def _node(self, node_id: str):
        return self.sandbox_data.get("objects", {}).get(node_id)

    def _is_keybind_path_enabled(self, node_id: str):
        node = self._node(node_id)
        while node:
            if not bool(node.get("enabled", True)):
                return False
            parent_id = node.get("parent_id", "")
            if not parent_id:
                return True
            parent = self._node(parent_id)
            if not parent:
                return True
            if parent.get("folder_kind") == "sequence":
                return True
            node = parent

    def _is_enabled(self, node_id: str):
        node = self._node(node_id)
        while node:
            if not bool(node.get("enabled", True)):
                return False
            parent_id = node.get("parent_id", "")
            node = self._node(parent_id) if parent_id else None
        return True

    def _button_messages(self, mouse_button: str):
        return super()._button_messages(mouse_button)

    def _resolve_target_hwnd(self, click_x: int, click_y: int):
        return super()._resolve_target_hwnd(click_x, click_y, ignored_hwnds=_overlay_window_hwnds())

    def _sleep_until(self, target_time: float):
        return super()._sleep_until(target_time, coarse_threshold=0.003, coarse_ratio=None, coarse_cap=None, fine_sleep=0.0)

    def _native_bridge(self):
        if not hasattr(self, "_click_engine_bridge"):
            self._click_engine_bridge = None
        if self._click_engine_bridge is None:
            try:
                self._click_engine_bridge = get_click_engine_bridge()
            except Exception:
                self._click_engine_bridge = False
        return None if self._click_engine_bridge is False else self._click_engine_bridge

    def _native_button_code(self, mouse_button: str):
        button = (mouse_button or "left").lower()
        if button == "right":
            return 1
        if button == "middle":
            return 2
        return 0

    def _use_native_motion(self, node: dict):
        if read_mouse_behavior(node, MOUSE_BEHAVIOR_DEFAULT) != MOUSE_BEHAVIOR_DEFAULT:
            return False
        bridge = self._native_bridge()
        return bool(bridge and bridge.available and bridge.has_native_smooth_move)

    def _native_move_cursor(self, target_x: int, target_y: int, duration_ms: int):
        bridge = self._native_bridge()
        if not bridge or not bridge.available or not bridge.has_native_smooth_move:
            raise RuntimeError("Native smooth movement is unavailable")
        try:
            start_x, start_y = win32api.GetCursorPos()
        except Exception:
            start_x, start_y = int(target_x), int(target_y)
        return bool(bridge.smooth_move_cursor(start_x, start_y, int(target_x), int(target_y), max(0, int(duration_ms))))

    def _native_mouse_down(self, mouse_button: str):
        bridge = self._native_bridge()
        if not bridge or not bridge.available:
            raise RuntimeError("Native input bridge is unavailable")
        return bool(bridge.mouse_button_down(self._native_button_code(mouse_button)))

    def _native_mouse_up(self, mouse_button: str):
        bridge = self._native_bridge()
        if not bridge or not bridge.available:
            raise RuntimeError("Native input bridge is unavailable")
        return bool(bridge.mouse_button_up(self._native_button_code(mouse_button)))

    def _smooth_restore_cursor(self, restore_x: int, restore_y: int, duration_ms: int = 140):
        bridge = self._native_bridge()
        if bridge and bridge.available and bridge.has_native_smooth_move:
            try:
                moved = self._native_move_cursor(int(restore_x), int(restore_y), max(0, int(duration_ms)))
                if moved:
                    return True
            except Exception:
                pass
        return self._teleport_cursor(restore_x, restore_y)

    def _native_restore_duration_for_target(self, target_id: str):
        target = self._node(target_id)
        if not target:
            return 140
        target_type = target.get("type")
        if target_type == "marker":
            return max(0, int(round(interval_ms_from_timing(target, 140))))
        if target_type == "dragger":
            return max(0, int(round(interval_ms_from_timing(target, 140))))
        if target_type == "folder" and target.get("folder_kind") == "sequence":
            children = self._sequence_candidates(target)
            if children:
                first_child = children[0]
                if first_child.get("type") in ("marker", "dragger"):
                    return max(0, int(round(interval_ms_from_timing(first_child, 140))))
        return 140

    def _target_anchor_position(self, target_id: str):
        target = self._node(target_id)
        if not target:
            return None
        target_type = target.get("type")
        if target_type == "marker":
            return (int(target.get("x", 0)), int(target.get("y", 0)))
        if target_type == "dragger":
            return (int(target.get("end_x", 0)), int(target.get("end_y", 0)))
        if target_type == "folder" and target.get("folder_kind") == "sequence":
            children = self._sequence_candidates(target)
            if children:
                first_child = children[0]
                child_type = first_child.get("type")
                if child_type == "marker":
                    return (int(first_child.get("x", 0)), int(first_child.get("y", 0)))
                if child_type == "dragger":
                    return (int(first_child.get("start_x", 0)), int(first_child.get("start_y", 0)))
        return None

    def _point_near(self, a, b, threshold: int = 24):
        if a is None or b is None:
            return False
        try:
            return abs(int(a[0]) - int(b[0])) <= threshold and abs(int(a[1]) - int(b[1])) <= threshold
        except Exception:
            return False

    def _sequence_cursor_lock_enabled(self):
        if not hasattr(self, "_sequence_lock_depth"):
            self._sequence_lock_depth = 0
        return self._sequence_lock_depth > 0

    def _clear_cursor_lock(self):
        try:
            ctypes.windll.user32.ClipCursor(None)
            return True
        except Exception:
            return False

    def _lock_cursor_at(self, x: int, y: int, radius: int = 0):
        if not self._sequence_cursor_lock_enabled():
            return False
        try:
            left = int(x) - int(radius)
            top = int(y) - int(radius)
            right = int(x) + int(radius) + 1
            bottom = int(y) + int(radius) + 1
            rect = wintypes.RECT(left, top, right, bottom)
            return bool(ctypes.windll.user32.ClipCursor(ctypes.byref(rect)))
        except Exception:
            return False

    def _wait_for_cursor_position(self, x: int, y: int, tolerance: int = 2, timeout_ms: int = 80):
        deadline = time.perf_counter() + (max(1, int(timeout_ms)) / 1000.0)
        while self._running and time.perf_counter() < deadline:
            try:
                cursor_x, cursor_y = win32api.GetCursorPos()
                if abs(int(cursor_x) - int(x)) <= tolerance and abs(int(cursor_y) - int(y)) <= tolerance:
                    return True
            except Exception:
                return False
            self._sleep_until(min(deadline, time.perf_counter() + 0.0015))
        return False

    def _settle_cursor_before_press(self, x: int, y: int, timeout_ms: int = 80, settle_ms: int = 12):
        self._wait_for_cursor_position(x, y, timeout_ms=timeout_ms)
        self._sleep_until(time.perf_counter() + (max(0, int(settle_ms)) / 1000.0))

    def _begin_keybind_burst(self, keybind_id: str, target_id: str, teleport_back: bool):
        if not teleport_back:
            return None
        if not hasattr(self, "_keybind_burst_lock"):
            self._keybind_burst_lock = threading.Lock()
        if not hasattr(self, "_keybind_bursts"):
            self._keybind_bursts = {}
        if not hasattr(self, "_keybind_last_user_positions"):
            self._keybind_last_user_positions = {}
        if not hasattr(self, "_keybind_spam_window_seconds"):
            self._keybind_spam_window_seconds = 0.18
        try:
            current_pos = win32api.GetCursorPos()
        except Exception:
            current_pos = None
        anchor_pos = self._target_anchor_position(target_id)
        now = time.perf_counter()
        with self._keybind_burst_lock:
            if current_pos is not None and not self._point_near(current_pos, anchor_pos):
                self._keybind_last_user_positions[keybind_id] = current_pos
            fallback_restore_pos = self._keybind_last_user_positions.get(keybind_id, current_pos)
            state = self._keybind_bursts.get(keybind_id)
            if (
                state is None
                or (now - float(state.get("last_trigger", 0.0))) > self._keybind_spam_window_seconds
            ):
                state = {
                    "restore_pos": fallback_restore_pos,
                    "last_trigger": now,
                    "token": 0,
                    "active": 0,
                    "target_id": target_id,
                }
            elif state.get("restore_pos") is None and fallback_restore_pos is not None:
                state["restore_pos"] = fallback_restore_pos
            state["last_trigger"] = now
            state["target_id"] = target_id
            state["token"] = int(state.get("token", 0)) + 1
            state["active"] = int(state.get("active", 0)) + 1
            self._keybind_bursts[keybind_id] = state
            return {
                "keybind_id": keybind_id,
                "token": state["token"],
            }

    def _finish_keybind_burst(self, burst_info):
        if not burst_info:
            return
        keybind_id = burst_info.get("keybind_id", "")
        if not keybind_id:
            return
        with self._keybind_burst_lock:
            state = self._keybind_bursts.get(keybind_id)
            if not state:
                return
            state["active"] = max(0, int(state.get("active", 0)) - 1)

    def _watch_keybind_burst_restore(self, burst_info):
        if not burst_info:
            return
        keybind_id = burst_info.get("keybind_id", "")
        token = int(burst_info.get("token", 0))
        if not keybind_id or token <= 0:
            return

        while self._running:
            restore_pos = None
            target_id = ""
            with self._keybind_burst_lock:
                state = self._keybind_bursts.get(keybind_id)
                if not state:
                    return
                if token != int(state.get("token", 0)):
                    return
                if int(state.get("active", 0)) > 0:
                    state = None
                else:
                    restore_pos = state.get("restore_pos")
                    target_id = state.get("target_id", "")
                    self._keybind_bursts.pop(keybind_id, None)

            if state is None:
                self._sleep_until(time.perf_counter() + 0.001)
                continue

            if restore_pos is not None and self._running:
                self._smooth_restore_cursor(
                    restore_pos[0],
                    restore_pos[1],
                    self._native_restore_duration_for_target(target_id),
                )
            return

    def _post_click(self, click_x: int, click_y: int, hold_time: float, mouse_button: str):
        hwnd = self._resolve_target_hwnd(click_x, click_y)
        if not hwnd:
            return False
        client_x, client_y = win32gui.ScreenToClient(hwnd, (click_x, click_y))
        lparam = ((client_y & 0xFFFF) << 16) | (client_x & 0xFFFF)
        down_msg, up_msg, modifier = self._button_messages(mouse_button)
        try:
            self.click_started.emit(click_x, click_y)
            if bool(getattr(self, "_background_move_toggle", False)):
                wiggle_dx = -1
            else:
                wiggle_dx = 1
            self._background_move_toggle = not bool(getattr(self, "_background_move_toggle", False))
            hover_x = click_x + wiggle_dx
            hover_y = click_y
            hover_client_x, hover_client_y = win32gui.ScreenToClient(hwnd, (hover_x, hover_y))
            hover_lparam = ((hover_client_y & 0xFFFF) << 16) | (hover_client_x & 0xFFFF)
            win32gui.PostMessage(hwnd, win32con.WM_MOUSEMOVE, 0, hover_lparam)
            win32gui.PostMessage(hwnd, win32con.WM_MOUSEMOVE, 0, lparam)
            win32gui.PostMessage(hwnd, down_msg, modifier, lparam)
            self._sleep_until(time.perf_counter() + hold_time)
            win32gui.PostMessage(hwnd, up_msg, 0, lparam)
            self.click_finished.emit(click_x, click_y)
            return True
        except Exception:
            return False

    def _post_drag(self, start_x: int, start_y: int, end_x: int, end_y: int, hold_time: float, mouse_button: str):
        hwnd = self._resolve_target_hwnd(start_x, start_y)
        if not hwnd:
            return False
        down_msg, up_msg, modifier = self._button_messages(mouse_button)
        try:
            self.click_started.emit(start_x, start_y)
            start_client_x, start_client_y = win32gui.ScreenToClient(hwnd, (start_x, start_y))
            start_lparam = ((start_client_y & 0xFFFF) << 16) | (start_client_x & 0xFFFF)
            win32gui.PostMessage(hwnd, win32con.WM_MOUSEMOVE, 0, start_lparam)
            win32gui.PostMessage(hwnd, down_msg, modifier, start_lparam)

            grip_pause = min(0.06, max(0.02, hold_time * 0.25 if hold_time > 0 else 0.03))
            if grip_pause > 0:
                self._sleep_until(time.perf_counter() + grip_pause)

            drag_duration = max(0.05, hold_time - grip_pause) if hold_time > 0 else 0.14
            steps = max(18, int(drag_duration / 0.008) if drag_duration > 0 else 18)
            step_duration = drag_duration / float(steps) if steps else 0.0
            for index in range(1, steps + 1):
                if not self._running:
                    break
                t = index / float(steps)
                x = int(start_x + (end_x - start_x) * t)
                y = int(start_y + (end_y - start_y) * t)
                client_x, client_y = win32gui.ScreenToClient(hwnd, (x, y))
                lparam = ((client_y & 0xFFFF) << 16) | (client_x & 0xFFFF)
                win32gui.PostMessage(hwnd, win32con.WM_MOUSEMOVE, modifier, lparam)
                self.drag_progress.emit(x, y)
                if step_duration > 0:
                    self._sleep_until(time.perf_counter() + step_duration)

            end_client_x, end_client_y = win32gui.ScreenToClient(hwnd, (end_x, end_y))
            end_lparam = ((end_client_y & 0xFFFF) << 16) | (end_client_x & 0xFFFF)
            win32gui.PostMessage(hwnd, win32con.WM_MOUSEMOVE, modifier, end_lparam)
            win32gui.PostMessage(hwnd, up_msg, 0, end_lparam)
            self.click_finished.emit(end_x, end_y)
            return True
        except Exception:
            return False

    def _teleport_cursor(self, x: int, y: int):
        try:
            win32api.SetCursorPos((int(x), int(y)))
            return True
        except Exception:
            return False

    def _python_move_cursor(self, x: int, y: int, duration_ms: int = 0):
        try:
            pyautogui.moveTo(int(x), int(y), duration=max(0.0, float(duration_ms) / 1000.0))
            return True
        except Exception:
            return False

    def _execute_marker(self, node: dict):
        click_x = int(node.get("x", 0))
        click_y = int(node.get("y", 0))
        if read_click_randomness(node, True):
            click_x += random.randint(-4, 4)
            click_y += random.randint(-4, 4)
        hold_time = max(0, int(node.get("mouse_hold_ms", 100))) / 1000.0
        move_duration_ms = max(0, int(round(interval_ms_from_timing(node, 100))))
        mouse_button = node.get("mouse_button", "left")
        mouse_behavior = read_mouse_behavior(node, MOUSE_BEHAVIOR_DEFAULT)
        if self._use_native_motion(node):
            try:
                self._clear_cursor_lock()
                self.click_started.emit(click_x, click_y)
                moved = self._native_move_cursor(click_x, click_y, move_duration_ms)
                if not moved or not self._running:
                    self.status_changed.emit(f"Stopped {node.get('name', 'Marker')}")
                    return
                self._lock_cursor_at(click_x, click_y)
                self._settle_cursor_before_press(click_x, click_y)
                down_ok = self._native_mouse_down(mouse_button)
                if not down_ok:
                    raise RuntimeError("native mouse down failed")
                if hold_time > 0:
                    self._sleep_until(time.perf_counter() + hold_time)
                up_ok = self._native_mouse_up(mouse_button)
                if not up_ok:
                    raise RuntimeError("native mouse up failed")
                self.click_finished.emit(click_x, click_y)
                self.status_changed.emit(f"Executed {node.get('name', 'Marker')}")
                self._sleep_until(time.perf_counter() + (max(1, move_duration_ms) / 1000.0))
                return
            except Exception:
                try:
                    self._native_mouse_up(mouse_button)
                except Exception:
                    pass
                self.status_changed.emit(f"Failed {node.get('name', 'Marker')}")
                return
        bridge = self._native_bridge()
        use_native_button = bool(mouse_behavior in (MOUSE_BEHAVIOR_DEFAULT, MOUSE_BEHAVIOR_TELEPORT) and bridge and bridge.available)
        if mouse_behavior == MOUSE_BEHAVIOR_TELEPORT:
            try:
                self.click_started.emit(click_x, click_y)
                self._clear_cursor_lock()
                self._teleport_cursor(click_x, click_y)
                self._lock_cursor_at(click_x, click_y)
                self._settle_cursor_before_press(click_x, click_y)
                if use_native_button:
                    if not self._native_mouse_down(mouse_button):
                        raise RuntimeError("native mouse down failed")
                else:
                    pyautogui.mouseDown(button=mouse_button)
                if hold_time > 0:
                    self._sleep_until(time.perf_counter() + hold_time)
                if use_native_button:
                    if not self._native_mouse_up(mouse_button):
                        raise RuntimeError("native mouse up failed")
                else:
                    pyautogui.mouseUp(button=mouse_button)
                self.click_finished.emit(click_x, click_y)
                ok = self._running
            except Exception:
                try:
                    if use_native_button:
                        self._native_mouse_up(mouse_button)
                    else:
                        pyautogui.mouseUp(button=mouse_button)
                except Exception:
                    pass
                ok = False
        elif mouse_behavior == MOUSE_BEHAVIOR_PYTHON:
            ok = self._post_click(click_x, click_y, hold_time, mouse_button)
        else:
            try:
                self.click_started.emit(click_x, click_y)
                moved = False
                if bridge and bridge.available and bridge.has_native_smooth_move:
                    self._clear_cursor_lock()
                    moved = self._native_move_cursor(click_x, click_y, move_duration_ms)
                else:
                    moved = self._python_move_cursor(click_x, click_y, move_duration_ms)
                if not moved or not self._running:
                    raise RuntimeError("default move failed")
                self._lock_cursor_at(click_x, click_y)
                self._settle_cursor_before_press(click_x, click_y)
                if use_native_button:
                    if not self._native_mouse_down(mouse_button):
                        raise RuntimeError("native mouse down failed")
                else:
                    pyautogui.mouseDown(button=mouse_button)
                if hold_time > 0:
                    self._sleep_until(time.perf_counter() + hold_time)
                if use_native_button:
                    if not self._native_mouse_up(mouse_button):
                        raise RuntimeError("native mouse up failed")
                else:
                    pyautogui.mouseUp(button=mouse_button)
                self.click_finished.emit(click_x, click_y)
                ok = self._running
            except Exception:
                try:
                    if use_native_button:
                        self._native_mouse_up(mouse_button)
                    else:
                        pyautogui.mouseUp(button=mouse_button)
                except Exception:
                    pass
                ok = False
        self.status_changed.emit(f"Executed {node.get('name', 'Marker')}" if ok else f"Failed {node.get('name', 'Marker')}")
        self._sleep_until(time.perf_counter() + (max(1, int(round(interval_ms_from_timing(node, 100)))) / 1000.0))

    def _execute_dragger(self, node: dict):
        start_x = int(node.get("start_x", 0))
        start_y = int(node.get("start_y", 0))
        end_x = int(node.get("end_x", 0))
        end_y = int(node.get("end_y", 0))
        button = (node.get("mouse_button", "left") or "left").lower()
        hold_time = max(0, int(node.get("mouse_hold_ms", 100))) / 1000.0
        timing_interval_ms = max(1, int(round(interval_ms_from_timing(node, 100))))
        delay_time = timing_interval_ms / 1000.0
        move_duration_ms = max(0, timing_interval_ms)
        mouse_behavior = read_mouse_behavior(node, MOUSE_BEHAVIOR_DEFAULT)
        bridge = self._native_bridge()
        use_native_motion = bool(
            mouse_behavior == MOUSE_BEHAVIOR_DEFAULT
            and bridge
            and bridge.available
            and bridge.has_native_smooth_move
        )
        use_native_button = bool(
            mouse_behavior in (MOUSE_BEHAVIOR_DEFAULT, MOUSE_BEHAVIOR_TELEPORT)
            and bridge
            and bridge.available
        )
        if mouse_behavior == MOUSE_BEHAVIOR_PYTHON:
            ok = self._post_drag(start_x, start_y, end_x, end_y, hold_time, button)
            self._clear_cursor_lock()
            self.status_changed.emit(
                f"Dragged {node.get('name', 'Dragger')}" if ok and self._running else f"Failed {node.get('name', 'Dragger')}"
            )
            self._sleep_until(time.perf_counter() + delay_time)
            return
        try:
            self.click_started.emit(start_x, start_y)
            self.drag_progress.emit(start_x, start_y)
            if use_native_motion:
                self._clear_cursor_lock()
                moved_to_start = self._native_move_cursor(start_x, start_y, move_duration_ms)
                if not moved_to_start or not self._running:
                    self.status_changed.emit(f"Stopped {node.get('name', 'Dragger')}")
                    return
            else:
                self._teleport_cursor(start_x, start_y)
            self._lock_cursor_at(start_x, start_y)
            self._settle_cursor_before_press(start_x, start_y)
            if use_native_button:
                if not self._native_mouse_down(button):
                    raise RuntimeError("native mouse down failed")
            else:
                pyautogui.mouseDown(button=button)
            grip_pause = min(0.06, max(0.02, hold_time * 0.25 if hold_time > 0 else 0.03))
            if grip_pause > 0:
                self._sleep_until(time.perf_counter() + grip_pause)

            drag_duration = max(0.05, hold_time - grip_pause) if hold_time > 0 else 0.14
            if use_native_motion:
                self._clear_cursor_lock()
                moved_to_end = self._native_move_cursor(end_x, end_y, int(drag_duration * 1000.0))
                if not moved_to_end and self._running:
                    raise RuntimeError("native drag motion failed")
                self.drag_progress.emit(end_x, end_y)
            else:
                steps = max(18, int(drag_duration / 0.008) if drag_duration > 0 else 18)
                step_duration = drag_duration / float(steps) if steps else 0.0
                for index in range(1, steps + 1):
                    if not self._running:
                        break
                    self._clear_cursor_lock()
                    t = index / float(steps)
                    x = int(start_x + (end_x - start_x) * t)
                    y = int(start_y + (end_y - start_y) * t)
                    self._teleport_cursor(x, y)
                    self._lock_cursor_at(x, y)
                    self.drag_progress.emit(x, y)
                    if step_duration > 0:
                        self._sleep_until(time.perf_counter() + step_duration)
            if mouse_behavior == MOUSE_BEHAVIOR_TELEPORT:
                self._teleport_cursor(end_x, end_y)
            self._lock_cursor_at(end_x, end_y)
            self._settle_cursor_before_press(end_x, end_y, timeout_ms=40, settle_ms=10)
            if use_native_button:
                if not self._native_mouse_up(button):
                    raise RuntimeError("native mouse up failed")
            else:
                pyautogui.mouseUp(button=button)
            self._clear_cursor_lock()
            self.click_finished.emit(end_x, end_y)
            self.status_changed.emit(
                f"Dragged {node.get('name', 'Dragger')}" if self._running else f"Stopped {node.get('name', 'Dragger')}"
            )
        except Exception:
            try:
                if use_native_button:
                    self._native_mouse_up(button)
                else:
                    pyautogui.mouseUp(button=button)
            except Exception:
                pass
            self._clear_cursor_lock()
            self.status_changed.emit(f"Failed {node.get('name', 'Dragger')}")
        self._sleep_until(time.perf_counter() + delay_time)

    def _sequence_candidates(self, folder_node: dict):
        keybound_targets = set(self._all_keybind_targets())
        children = []
        for child_id in folder_node.get("children", []):
            child = self._node(child_id)
            if not child or child.get("type") not in ("marker", "dragger"):
                continue
            if not self._is_enabled(child_id):
                continue
            if child_id in keybound_targets:
                continue
            children.append(child)
        children.sort(key=lambda child: (int(child.get("index", 99999)), child.get("name", "")))
        return children

    def _can_execute_node(self, node_id: str, trigger_mode: str):
        node = self._node(node_id)
        if not node or not bool(node.get("enabled", True)):
            return False
        if node.get("type") in ("marker", "dragger"):
            if trigger_mode == "keybind":
                return node_id in self._active_keybind_targets() and self._is_keybind_path_enabled(node_id)
            sequence_folder = self._node("folder_sequence")
            return bool(sequence_folder and sequence_folder.get("enabled", True) and node.get("parent_id") == "folder_sequence" and node_id not in self._all_keybind_targets())
        return self._is_enabled(node_id)

    def _execute_keybind_target_async(self, node_id: str):
        if not self._running:
            return
        self._execute_target(node_id, "keybind")

    def _execute_target(self, node_id: str, trigger_mode: str = "sequence"):
        if not self._running or not node_id or not self._can_execute_node(node_id, trigger_mode):
            return
        node = self._node(node_id)
        if not node:
            return
        node_type = node.get("type")
        if node_type == "folder":
            if node.get("folder_kind") == "sequence":
                self._sequence_lock_depth = int(getattr(self, "_sequence_lock_depth", 0)) + 1
                try:
                    for child in self._sequence_candidates(node):
                        self._execute_target(child["id"], "sequence")
                finally:
                    self._sequence_lock_depth = max(0, int(getattr(self, "_sequence_lock_depth", 0)) - 1)
                    if not self._sequence_cursor_lock_enabled():
                        self._clear_cursor_lock()
            return
        if node_type == "keybind":
            target_id = node.get("target_id", "")
            burst_info = self._begin_keybind_burst(
                node.get("id", ""),
                target_id,
                bool(node.get("teleport_back", False)),
            )
            if burst_info:
                restore_thread = threading.Thread(
                    target=self._watch_keybind_burst_restore,
                    args=(burst_info,),
                    daemon=True,
                )
                restore_thread.start()
            self._execute_target(target_id, "keybind")
            self._finish_keybind_burst(burst_info)
            return
        if node_type == "marker":
            self._execute_marker(node)
        elif node_type == "dragger":
            self._execute_dragger(node)

    def run(self):
        self._running = True
        self.status_changed.emit("Sandbox armed")
        try:
            while self._running:
                try:
                    node_id = self._queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                self._execute_target(node_id)
                self.target_completed.emit(node_id)
        finally:
            self._clear_cursor_lock()
            self.stopped.emit()


class SandboxModeLogicMixin:
    def __init__(self, file_path, pos=None, parent=None):
        self._executing = False
        self._worker = None
        self._runtime_keybind_listener = None
        self._setup_keybind_listener = None
        self._status_text = "Stopped"
        self._property_widgets = []
        self._info_dialog = None
        self._current_indicator_node_id = ""
        self._pre_execute_selected_id = ""
        self._active_execute_target_id = ""
        self._property_value_widgets = {}
        self._progress_timer = None
        self._sequence_iteration_count = 0
        self._sequence_started_at = None
        self._sequence_duration_seconds = 0
        self._selected_point_key = ""
        self._selected_node_ids = []
        self._ctrl_hint_active = False
        self._overlay_refresh_timer = QtCore.QTimer()
        self._overlay_refresh_timer.setSingleShot(True)
        self._overlay_refresh_timer.timeout.connect(self._refresh_overlay)
        from Modes.sandbox.ui import SandboxOverlayController

        self._overlay_controller = SandboxOverlayController()
        super().__init__(file_path, pos, title="Sandbox Mode", parent=parent)

        center = self.geometry().center()
        self.resize(720, 430)
        rect = self.geometry()
        rect.moveCenter(center)
        self.move(rect.topLeft())

        kb = ConfigManager.load().get("keybinds", {})
        self._setup_keybind_listener = _keybind_listener_type()(
            {
                "Execute": kb.get("Execute", "F2"),
                "Stop": kb.get("Stop", "F3"),
                "Register_Click_Position": kb.get("Register_Click_Position", "F4"),
                "See_Setup_Info": kb.get("See_Setup_Info", "F1"),
                "New_Marker_Sandbox": kb.get("New_Marker_Sandbox", "F5"),
                "New_Keybind_Sandbox": kb.get("New_Keybind_Sandbox", "F6"),
            },
            parent=self,
        )
        self._setup_keybind_listener.triggered.connect(self._on_setup_keybind)
        self._overlay_controller.point_moved.connect(self._on_overlay_point_moved)
        self._overlay_controller.point_selected.connect(self._on_overlay_node_selected)
        self._overlay_controller.show()
        QtWidgets.QApplication.instance().installEventFilter(self)
        self._saved_state = copy.deepcopy(self.data)
        self._refresh_all()

    def _schedule_overlay_refresh(self, delay_ms: int = 16):
        if self._overlay_refresh_timer.isActive():
            return
        self._overlay_refresh_timer.start(max(0, int(delay_ms)))

    def save(self):
        SandboxDataModel.ensure_structure(self.data)
        self.data["sandbox"] = SandboxDataModel.sanitize_snapshot(self.data["sandbox"])
        super().save()

    def _persist_active_snapshot(self):
        snapshot = self._build_active_snapshot()
        ActiveSetupManager.write(self.data.get("name", "setup"), snapshot)
        return ActiveSetupManager.read(self.data.get("name", "setup")) or snapshot

    def _ensure_sandbox_data(self):
        SandboxDataModel.ensure_structure(self.data)

    def _play_system_sound(self, alias: str, fallback_freq: int):
        try:
            winsound.PlaySound(alias, winsound.SND_ALIAS | winsound.SND_ASYNC)
        except Exception:
            try:
                winsound.Beep(fallback_freq, 150)
            except Exception:
                pass

    def _node_map(self):
        return self.data["sandbox"]["objects"]

    def _node(self, node_id: str):
        return self._node_map().get(node_id)

    def _parent_node(self, node: dict):
        if not node:
            return None
        return self._node(node.get("parent_id", ""))

    def _is_keybind_path_enabled(self, node_id: str):
        node = self._node(node_id)
        while node:
            if not bool(node.get("enabled", True)):
                return False
            parent_id = node.get("parent_id", "")
            if not parent_id:
                return True
            parent = self._node(parent_id)
            if not parent:
                return True
            if parent.get("folder_kind") == "sequence":
                return True
            node = parent

    def _keybind_references(self, active_only=False):
        refs = {}
        keybind_folder = self._node("folder_keybind")
        for node_id, node in self._node_map().items():
            if node.get("type") != "keybind":
                continue
            if active_only:
                if keybind_folder and not bool(keybind_folder.get("enabled", True)):
                    continue
                if not self._is_keybind_path_enabled(node_id):
                    continue
            target_id = node.get("target_id", "")
            if target_id:
                refs.setdefault(target_id, []).append(node_id)
        return refs

    def _is_keybind_bound(self, node_id: str):
        return node_id in self._keybind_references(active_only=False)

    def _sequence_index_warnings(self):
        warnings = {}
        sequence_folder = self._node("folder_sequence")
        if not sequence_folder:
            return warnings
        seen = {}
        for child_id in sequence_folder.get("children", []):
            child = self._node(child_id)
            if not child or child.get("type") not in ("marker", "dragger"):
                continue
            if not bool(child.get("enabled", True)):
                continue
            if self._is_keybind_bound(child_id):
                continue
            index = int(child.get("index", 0) or 0)
            if index <= 0:
                warnings[child_id] = "Index must be 1+"
                continue
            seen.setdefault(index, []).append(child_id)
        for index, node_ids in seen.items():
            if len(node_ids) > 1:
                for node_id in node_ids:
                    warnings[node_id] = f"Index {index} duplicated"
        return warnings

    def _can_show_overlay_node(self, node_id: str):
        node = self._node(node_id)
        if not node or not bool(node.get("enabled", True)):
            return False
        if self._is_keybind_bound(node_id):
            return node_id in self._keybind_references(active_only=True)
        sequence_folder = self._node("folder_sequence")
        return bool(sequence_folder and sequence_folder.get("enabled", True) and node.get("parent_id") == "folder_sequence" and self._is_effectively_enabled(node_id))

    def _sequence_execute_nodes(self):
        sequence_folder = self._node("folder_sequence")
        if not sequence_folder or not bool(sequence_folder.get("enabled", True)):
            return []
        warnings = self._sequence_index_warnings()
        if warnings:
            return []
        nodes = []
        for child_id in sequence_folder.get("children", []):
            child = self._node(child_id)
            if not child or child.get("type") not in ("marker", "dragger"):
                continue
            if not self._can_show_overlay_node(child_id):
                continue
            nodes.append(child)
        nodes.sort(key=lambda child: (int(child.get("index", 99999)), child.get("name", "")))
        return nodes

    def _edit_sequence_repeat_times(self):
        sequence = self._sequence_settings()
        spin = QtWidgets.QSpinBox()
        spin.setRange(1, 999999999)
        spin.setValue(max(1, int(sequence.get("repeat_times_target", 5))))
        spin.setStyleSheet("color: white; background: rgba(0,0,0,100); border: none; border-radius: 3px; font: 9pt 'Times New Roman'; padding: 2px 4px;")
        value = self._prompt_edit_dialog("Repeat Times", "Set the target number of sequence loops.", spin, spin.value)
        if value is None:
            return
        sequence["repeat_times_target"] = int(value)
        sequence["repeat_mode"] = "repeat_times"
        self._refresh_properties()

    def _edit_sequence_repeat_timer(self):
        sequence = self._sequence_settings()
        time_edit = QtWidgets.QTimeEdit()
        time_edit.setDisplayFormat("HH:mm:ss")
        time_edit.setTime(QtCore.QTime(0, 0, 0).addSecs(max(1, int(sequence.get("repeat_timer_seconds", 60)))))
        time_edit.setStyleSheet("color: white; background: rgba(0,0,0,100); border: none; border-radius: 3px; font: 9pt 'Times New Roman'; padding: 2px 4px;")
        value = self._prompt_edit_dialog("Repeat Timer", "Set total sequence runtime in HH:MM:SS.", time_edit, lambda: QtCore.QTime(0, 0, 0).secsTo(time_edit.time()))
        if value is None:
            return
        sequence["repeat_timer_seconds"] = max(1, int(value))
        sequence["repeat_mode"] = "repeat_timer"
        self._refresh_properties()

    def _refresh_all(self):
        SandboxDataModel._apply_index_rules(self.data["sandbox"])
        self._refresh_hierarchy()
        self._refresh_properties()
        self._refresh_bottom_bar()
        self._refresh_overlay()
        self._refresh_runtime_keybind_listener()

    def _ensure_progress_timer(self):
        if self._progress_timer is None:
            self._progress_timer = QtCore.QTimer(self)
            self._progress_timer.setInterval(200)
            self._progress_timer.timeout.connect(self._update_execution_progress)

    def _sequence_settings(self):
        sequence = self._node("folder_sequence")
        if not sequence:
            return {"repeat_mode": "until_stop", "repeat_times_target": 5, "repeat_timer_seconds": 60}
        sequence.setdefault("repeat_mode", "until_stop")
        sequence.setdefault("repeat_times_target", 5)
        sequence.setdefault("repeat_timer_seconds", 60)
        return sequence

    def _format_repeat_time(self, seconds: int):
        seconds = max(0, int(seconds))
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def _update_execution_progress(self):
        if not self._executing:
            return
        settings = self._sequence_settings()
        mode = settings.get("repeat_mode", "until_stop")
        if mode == "repeat_times":
            target = max(1, int(settings.get("repeat_times_target", 1)))
            self._set_status(f"Sequence {self._sequence_iteration_count} / {target}")
        elif mode == "repeat_timer":
            elapsed = int(max(0, time.perf_counter() - (self._sequence_started_at or time.perf_counter())))
            total = max(1, int(self._sequence_duration_seconds))
            self._set_status(f"Sequence {self._format_repeat_time(min(elapsed, total))} / {self._format_repeat_time(total)}")
        elif self._default_execute_target():
            self._set_status("Sequence running")

    def _find_tree_item(self, node_id: str):
        if not hasattr(self, "_tree") or not node_id:
            return None
        matches = self._tree.findItems("*", QtCore.Qt.MatchWildcard | QtCore.Qt.MatchRecursive, 0)
        for item in matches:
            if item.data(0, QtCore.Qt.UserRole) == node_id:
                return item
        return None

    def _default_point_key_for_node(self, node_id: str):
        node = self._node(node_id)
        if not node:
            return ""
        if node.get("type") == "marker":
            return "center"
        if node.get("type") == "dragger":
            return "start"
        return ""

    def _register_selected_position(self):
        selected_ids = self._selection_node_ids()
        if len(selected_ids) != 1:
            self._set_status("F4 register works only for one selected marker/dragger")
            return
        node_id = selected_ids[0]
        node = self._node(node_id)
        if not node or node.get("type") not in ("marker", "dragger"):
            self._set_status("Select one marker or dragger to register position")
            return
        point_key = self._selected_point_key or self._default_point_key_for_node(node_id)
        if point_key not in ("center", "start", "end"):
            point_key = self._default_point_key_for_node(node_id)
        x, y = win32api.GetCursorPos()
        self._set_point_value(node_id, point_key, x, y, live_only=False)
        point_label = "Position"
        if point_key == "start":
            point_label = "Start"
        elif point_key == "end":
            point_label = "End"
        self._set_status(f"Registered {node.get('name', 'Object')} {point_label} ({x}, {y})")

    def _set_selected_node(self, node_id: str, *, refresh_properties=True, sync_tree=True, point_key=None):
        self._set_selected_nodes(
            [node_id] if node_id else [],
            primary_id=node_id,
            refresh_properties=refresh_properties,
            sync_tree=sync_tree,
            point_key=point_key,
        )

    def _selection_node_ids(self):
        ids = []
        for node_id in self._selected_node_ids:
            if node_id in self._node_map() and node_id not in ids:
                ids.append(node_id)
        primary_id = self.data["sandbox"].get("selected_id", "")
        if primary_id in self._node_map() and primary_id not in ids:
            ids.insert(0, primary_id)
        return ids

    def _selection_nodes(self):
        return [self._node(node_id) for node_id in self._selection_node_ids() if self._node(node_id)]

    def _multi_select_active(self):
        return len(self._selection_node_ids()) > 1

    def _update_tree_header_indicator(self):
        if not hasattr(self, "_tree"):
            return
        active = self._multi_select_active() or self._ctrl_hint_active
        bg = "rgba(70,170,90,150)" if active else "rgba(255,255,255,9)"
        border = "rgba(130,255,160,120)" if active else "rgba(255,255,255,0)"
        self._tree.setStyleSheet(f"""
            QTreeWidget {{
                background: rgba(0,0,0,68);
                color: white;
                border: none;
                border-radius: 6px;
                font: 8.5pt 'Times New Roman';
                padding: 4px;
            }}
            QHeaderView::section {{
                background: {bg};
                color: rgba(255,255,255,180);
                border: 1px solid {border};
                padding: 2px 6px;
                font: 7pt 'Times New Roman';
                min-height: 12px;
            }}
            QTreeWidget::item {{ padding: 4px 4px; }}
            QTreeWidget::item:selected {{
                background: rgba(122,0,255,120);
                color: white;
                border-radius: 4px;
            }}
            QScrollBar:vertical {{
                background: rgba(0,0,0,45);
                width: 10px;
                margin: 2px;
                border-radius: 5px;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(0,0,0,110);
                min-height: 26px;
                border-radius: 5px;
                border: none;
            }}
            QScrollBar::handle:vertical:hover {{
                background: rgba(0,0,0,145);
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: transparent;
                height: 0px;
            }}
        """)

    def eventFilter(self, obj, event):
        if event.type() in (QtCore.QEvent.KeyPress, QtCore.QEvent.KeyRelease):
            key = getattr(event, "key", lambda: None)()
            if key in (
                QtCore.Qt.Key_Control,
                QtCore.Qt.Key_Meta,
            ):
                active = event.type() == QtCore.QEvent.KeyPress
                if self._ctrl_hint_active != active:
                    self._ctrl_hint_active = active
                    self._update_tree_header_indicator()
        return super().eventFilter(obj, event)

    def _set_selected_nodes(self, node_ids, *, primary_id=None, refresh_properties=True, sync_tree=True, point_key=None):
        filtered_ids = []
        for node_id in node_ids or []:
            if node_id in self._node_map() and node_id not in filtered_ids:
                filtered_ids.append(node_id)

        if primary_id not in filtered_ids:
            primary_id = filtered_ids[0] if filtered_ids else ""

        if point_key is None:
            if primary_id and self.data["sandbox"].get("selected_id", "") == primary_id and self._selected_point_key:
                point_key = self._selected_point_key
            else:
                point_key = self._default_point_key_for_node(primary_id)
        elif point_key and point_key not in ("center", "start", "end"):
            point_key = self._default_point_key_for_node(primary_id)

        self._selected_node_ids = filtered_ids
        self.data["sandbox"]["selected_id"] = primary_id or ""
        self._selected_point_key = point_key or ""
        if hasattr(self, "_overlay_controller"):
            self._overlay_controller.set_selected(primary_id or "", self._selected_point_key, self._selected_node_ids)
        if sync_tree and hasattr(self, "_tree"):
            self._tree.blockSignals(True)
            self._tree.clearSelection()
            current_item = None
            for node_id in filtered_ids:
                item = self._find_tree_item(node_id)
                if item:
                    item.setSelected(True)
                    if node_id == primary_id:
                        current_item = item
            self._tree.setCurrentItem(current_item)
            self._tree.blockSignals(False)
        self._update_tree_header_indicator()
        if refresh_properties:
            self._refresh_properties()
        self._refresh_bottom_bar()

    def _mark_changed(self):
        self._refresh_bottom_bar()

    def _node_icon(self, node: dict):
        node_type = node.get("type")
        if node_type == "folder":
            return self._folder_icon
        if node_type == "keybind":
            return self._keybind_icon
        if node_type == "marker":
            return self._marker_icon
        if node_type == "dragger":
            return self._dragger_icon
        return QtGui.QIcon()

    def _is_effectively_enabled(self, node_id: str):
        node = self._node(node_id)
        original_node_id = node_id
        while node:
            if not bool(node.get("enabled", True)):
                return False
            parent_id = node.get("parent_id", "")
            if not parent_id:
                return True
            parent = self._node(parent_id)
            if not parent:
                return True
            if parent.get("folder_kind") == "sequence" and self._is_keybind_bound(original_node_id):
                return True
            node = parent
        return True

    def _node_info_text(self, node: dict):
        warnings = self._sequence_index_warnings()
        node_id = node.get("id", "")
        if node_id in warnings:
            return warnings[node_id]
        prefix = "" if self._can_show_overlay_node(node_id) or node.get("type") == "folder" or node.get("type") == "keybind" else "Hidden • "
        if not self._is_effectively_enabled(node_id):
            prefix = "Disabled • "
        node_type = node.get("type")
        if node_type == "folder":
            return f"{prefix}{len(node.get('children', []))} item(s)"
        if node_type == "keybind":
            key_name = node.get("keybind", "").strip() or "No key"
            target = self._node(node.get("target_id", ""))
            target_text = target.get("name", "No target") if target else "No target"
            return f"{prefix}{key_name} → {target_text}"
        if node_type == "marker":
            return f"{prefix}({node.get('x', 0)}, {node.get('y', 0)})"
        if node_type == "dragger":
            return f"{prefix}({node.get('start_x', 0)}, {node.get('start_y', 0)}) → ({node.get('end_x', 0)}, {node.get('end_y', 0)})"
        return prefix

    def _format_hint_text(self, keybinds: dict):
        return (
            f"Execute ({keybinds.get('Execute', 'F2')}) • Stop ({keybinds.get('Stop', 'F3')}) • "
            f"Set Pos. ({keybinds.get('Register_Click_Position', 'F4')}) • "
            f"Info ({keybinds.get('See_Setup_Info', 'F1')}) • +Marker ({keybinds.get('New_Marker_Sandbox', 'F5')}) • "
            f"+Keybind ({keybinds.get('New_Keybind_Sandbox', 'F6')}) • Save ({keybinds.get('Quick_Save', 'F7')}) • "
            f"Toggle Minimize ({keybinds.get('Recover_Window_Position', 'F8')}) • S&Close ({keybinds.get('Save_Close_Setup', 'F9')}) • "
            f"Kill ({keybinds.get('Kill_Switch', 'F10')})"
        )

    def _set_node_value(self, node_id: str, key: str, value):
        node = self._node(node_id)
        if not node:
            return
        if key == MOUSE_BEHAVIOR_KEY:
            if read_mouse_behavior(node, MOUSE_BEHAVIOR_DEFAULT) == value:
                return
            write_mouse_behavior(node, value)
        else:
            if node.get(key) == value:
                return
            node[key] = value
        self._mark_changed()
        SandboxDataModel._apply_index_rules(self.data["sandbox"])

        if key in ("enabled", "target_id", "keybind", "index"):
            self._refresh_hierarchy()
            self._refresh_properties()
        else:
            self._update_tree_item_display(node_id)
        self._refresh_bottom_bar()
        self._refresh_overlay()
        self._refresh_runtime_keybind_listener()

    def _commit_line_edit_value(self, node_id: str, key: str, edit: QtWidgets.QLineEdit):
        node = self._node(node_id)
        if not node:
            return
        value = edit.text()
        if str(node.get(key, "")) == value:
            return
        self._set_node_value(node_id, key, value)

    def _set_point_value(self, node_id: str, point_key: str, x: int, y: int, live_only: bool = False):
        node = self._node(node_id)
        if not node:
            return
        if point_key == "center":
            node["x"] = int(x)
            node["y"] = int(y)
        elif point_key == "start":
            node["start_x"] = int(x)
            node["start_y"] = int(y)
        elif point_key == "end":
            node["end_x"] = int(x)
            node["end_y"] = int(y)
        if live_only:
            self._update_live_position_widgets(node_id)
            self._update_tree_item_display(node_id)
            self._schedule_overlay_refresh()
            self._refresh_bottom_bar()
        else:
            self._mark_changed()
            self._refresh_all()

    def _translate_node_points(self, node_id: str, dx: int, dy: int):
        node = self._node(node_id)
        if not node:
            return False
        node_type = node.get("type")
        if node_type == "marker":
            node["x"] = int(node.get("x", 0)) + int(dx)
            node["y"] = int(node.get("y", 0)) + int(dy)
            return True
        if node_type == "dragger":
            node["start_x"] = int(node.get("start_x", 0)) + int(dx)
            node["start_y"] = int(node.get("start_y", 0)) + int(dy)
            node["end_x"] = int(node.get("end_x", 0)) + int(dx)
            node["end_y"] = int(node.get("end_y", 0)) + int(dy)
            return True
        return False

    def _move_selected_nodes_by_delta(self, primary_node_id: str, point_key: str, dx: int, dy: int):
        moved_ids = []
        for node_id in self._selection_node_ids():
            if node_id == primary_node_id:
                continue
            if self._translate_node_points(node_id, dx, dy):
                moved_ids.append(node_id)
        for node_id in moved_ids:
            self._update_live_position_widgets(node_id)
            self._update_tree_item_display(node_id)
        return moved_ids

    def _on_overlay_point_moved(self, node_id: str, point_key: str, x: int, y: int):
        current_selection = self._selection_node_ids()
        multi_keep = len(current_selection) > 1 and node_id in current_selection
        if multi_keep:
            self._set_selected_nodes(
                current_selection,
                primary_id=node_id,
                refresh_properties=(self.data["sandbox"].get("selected_id", "") != node_id),
                point_key=point_key,
            )
        else:
            self._set_selected_node(
                node_id,
                refresh_properties=(self.data["sandbox"].get("selected_id", "") != node_id),
                point_key=point_key,
            )

        node = self._node(node_id)
        if not node:
            return
        if point_key == "center":
            old_x = int(node.get("x", 0))
            old_y = int(node.get("y", 0))
        elif point_key == "start":
            old_x = int(node.get("start_x", 0))
            old_y = int(node.get("start_y", 0))
        else:
            old_x = int(node.get("end_x", 0))
            old_y = int(node.get("end_y", 0))

        dx = int(x) - old_x
        dy = int(y) - old_y
        self._set_point_value(node_id, point_key, x, y, live_only=True)
        if multi_keep and (dx or dy):
            self._move_selected_nodes_by_delta(node_id, point_key, dx, dy)
            self._refresh_overlay()
            self._refresh_bottom_bar()

    def _on_overlay_node_selected(self, node_id: str, point_key: str):
        mods = QtWidgets.QApplication.keyboardModifiers()
        ctrl_active = bool(mods & QtCore.Qt.ControlModifier)
        if ctrl_active:
            current_selection = self._selection_node_ids()
            if node_id in current_selection:
                remaining = [selected_id for selected_id in current_selection if selected_id != node_id]
                primary = remaining[-1] if remaining else ""
                self._set_selected_nodes(remaining, primary_id=primary, point_key=point_key if primary == node_id else None)
            else:
                self._set_selected_nodes(current_selection + [node_id], primary_id=node_id, point_key=point_key)
            return
        current_selection = self._selection_node_ids()
        if len(current_selection) > 1 and node_id in current_selection:
            self._set_selected_nodes(current_selection, primary_id=node_id, point_key=point_key)
            return
        self._set_selected_node(node_id, point_key=point_key)

    def _folder_allowed_types(self, folder_node: dict):
        kind = folder_node.get("folder_kind", "sequence")
        return ["keybind"] if kind == "keybind" else ["marker", "dragger"]

    def _on_tree_selection_changed(self):
        selected_ids = []
        for item in self._tree.selectedItems():
            node_id = item.data(0, QtCore.Qt.UserRole)
            if node_id and node_id not in selected_ids:
                selected_ids.append(node_id)
        item = self._tree.currentItem()
        primary_id = item.data(0, QtCore.Qt.UserRole) if item is not None else ""
        if primary_id and primary_id not in selected_ids:
            selected_ids.insert(0, primary_id)
        self._set_selected_nodes(selected_ids, primary_id=primary_id, sync_tree=False)

    def _sandbox_target_options(self, current_id: str):
        options = [("", "None")]
        for node_id, node in self._node_map().items():
            if node_id == current_id:
                continue
            if node.get("type") in ("marker", "dragger"):
                options.append((node_id, f"{node.get('name', node_id)} [{node.get('type').title()}]"))
        return options

    def _shared_value(self, nodes, key: str):
        if not nodes:
            return "", True
        first = nodes[0].get(key)
        for node in nodes[1:]:
            if node.get(key) != first:
                return None, False
        return first, True

    def _apply_multi_value(self, node_ids, key: str, value):
        changed_ids = []
        for node_id in node_ids:
            node = self._node(node_id)
            if not node:
                continue
            if key == MOUSE_BEHAVIOR_KEY:
                if read_mouse_behavior(node, MOUSE_BEHAVIOR_DEFAULT) == value:
                    continue
                write_mouse_behavior(node, value)
                changed_ids.append(node_id)
                continue
            if node.get(key) == value:
                continue
            node[key] = value
            changed_ids.append(node_id)

        if not changed_ids:
            return

        self._mark_changed()
        SandboxDataModel._apply_index_rules(self.data["sandbox"])
        if key in ("enabled", "target_id", "keybind", "index", "repeat_mode", "repeat_times_target", "repeat_timer_seconds"):
            self._refresh_hierarchy()
            self._refresh_properties()
            self._refresh_overlay()
            self._refresh_bottom_bar()
        else:
            for node_id in changed_ids:
                self._update_tree_item_display(node_id)
                self._update_live_position_widgets(node_id)
            self._refresh_overlay()
            self._refresh_bottom_bar()
        self._refresh_runtime_keybind_listener()

    def _add_multi_numeric_row(self, label_text: str, node_ids, nodes, key: str):
        value, same = self._shared_value(nodes, key)
        edit = QtWidgets.QLineEdit("" if value is None else str(int(value)))
        if not same:
            edit.setPlaceholderText("—")
        edit.setValidator(QtGui.QIntValidator(0, 99999, edit))
        edit.setStyleSheet(self._line_edit_style())

        def commit():
            text = edit.text().strip()
            if not text:
                shared, shared_same = self._shared_value([self._node(node_id) for node_id in node_ids if self._node(node_id)], key)
                blocked = edit.blockSignals(True)
                edit.setText("" if shared is None else str(int(shared)))
                edit.setPlaceholderText("" if shared_same else "—")
                edit.blockSignals(blocked)
                return
            self._apply_multi_value(node_ids, key, int(text))

        edit.editingFinished.connect(commit)
        self._add_property_row(label_text, edit)

    def _add_multi_text_row(self, label_text: str, node_ids, nodes, key: str):
        value, same = self._shared_value(nodes, key)
        edit = QtWidgets.QLineEdit("" if value is None else str(value))
        if not same:
            edit.setPlaceholderText("—")
        edit.setStyleSheet(self._line_edit_style())

        def commit():
            text = edit.text()
            if not text and edit.placeholderText() == "—":
                return
            self._apply_multi_value(node_ids, key, text)

        edit.editingFinished.connect(commit)
        self._add_property_row(label_text, edit)

    def _add_multi_checkbox_row(self, label_text: str, node_ids, nodes, key: str):
        value, same = self._shared_value(nodes, key)
        box = QtWidgets.QCheckBox()
        box.setTristate(True)
        box.setStyleSheet("""
            QCheckBox { color: white; }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                border-radius: 3px;
                border: none;
                background: rgba(0,0,0,100);
            }
            QCheckBox::indicator:checked {
                background: #7a00ff;
                border: 1px solid #a64dff;
            }
            QCheckBox::indicator:indeterminate {
                background: rgba(190,190,190,165);
                border: none;
            }
        """)
        state = QtCore.Qt.PartiallyChecked if not same else (QtCore.Qt.Checked if bool(value) else QtCore.Qt.Unchecked)
        box.setCheckState(state)

        def commit(state_value):
            if state_value == QtCore.Qt.PartiallyChecked:
                return
            self._apply_multi_value(node_ids, key, state_value == QtCore.Qt.Checked)

        box.stateChanged.connect(commit)
        self._add_property_row(label_text, box)

    def _add_multi_combo_row(self, label_text: str, node_ids, nodes, key: str, options):
        value, same = self._shared_value(nodes, key)
        combo = QtWidgets.QComboBox()
        combo.setStyleSheet(self._combo_style())
        if not same:
            combo.addItem("—", None)
        for option_label, option_value in options:
            combo.addItem(option_label, option_value)
        target_value = value if same else None
        combo.setCurrentIndex(max(0, combo.findData(target_value)))

        def commit(_=0):
            chosen = combo.currentData()
            if chosen is None:
                return
            self._apply_multi_value(node_ids, key, chosen)

        combo.currentIndexChanged.connect(commit)
        self._add_property_row(label_text, combo)

    def _capture_sandbox_keybind(self, node_id: str):
        node = self._node(node_id)
        if not node:
            return
        dialog = _keybind_capture_dialog_type()(node.get("keybind", ""), self)
        while True:
            if dialog.exec() != QtWidgets.QDialog.Accepted:
                return
            binding = dialog.binding_text().strip()
            if not binding:
                return
            duplicate = None
            for other_id, other in self._node_map().items():
                if other_id == node_id or other.get("type") != "keybind":
                    continue
                if other.get("keybind", "").strip().upper() == binding.upper():
                    duplicate = other
                    break
            if duplicate:
                self._play_system_sound("SystemExclamation", 720)
                dialog.flash_warning()
                dialog._retry()
                continue
            self._set_node_value(node_id, "keybind", binding)
            return

    def _selected_node_name(self):
        node = self._node(self.data["sandbox"].get("selected_id", ""))
        return node.get("name", "N/A") if node else "N/A"

    def _quick_create_sandbox_object(self, folder_id: str, node_type: str):
        folder = self._node(folder_id)
        if not folder or folder.get("type") != "folder":
            return
        if node_type not in self._folder_allowed_types(folder):
            return
        target_options = [(text, target_id) for target_id, text in self._sandbox_target_options("")]
        dialog = SandboxCreateObjectDialog([node_type], target_options=target_options, parent=self)
        if dialog.exec() != QtWidgets.QDialog.Accepted:
            return
        _, name, extra = dialog.values()
        self._create_node(folder_id, node_type, name or node_type.title(), extra)

    def _create_node(self, parent_id: str, node_type: str, name: str, extra=None):
        objects = self._node_map()
        prefix = "marker" if node_type == "marker" else "dragger" if node_type == "dragger" else "keybind"
        node_id = SandboxDataModel.next_id(objects, prefix)
        node = SandboxDataModel._default_node(node_type, node_id, name, parent_id)
        for key, value in (extra or {}).items():
            if key in node:
                node[key] = value
        if node_type in ("marker", "dragger"):
            siblings = [
                self._node(child_id) for child_id in self._node(parent_id).get("children", [])
                if self._node(child_id) and self._node(child_id).get("type") in ("marker", "dragger") and not self._is_keybind_bound(child_id)
            ]
            next_index = ((max([int(s.get("index", 0)) for s in siblings], default=0) // 10) + 1) * 10
            node["index"] = max(10, next_index)
        if node_type in ("marker", "dragger") and not extra:
            x, y = win32api.GetCursorPos()
            if node_type == "marker":
                node["x"], node["y"] = int(x), int(y)
            else:
                node["start_x"], node["start_y"] = int(x), int(y)
                node["end_x"], node["end_y"] = int(x + 120), int(y)
        objects[node_id] = node
        parent = self._node(parent_id)
        parent.setdefault("children", []).append(node_id)
        self._selected_node_ids = [node_id]
        self.data["sandbox"]["selected_id"] = node_id
        self._selected_point_key = self._default_point_key_for_node(node_id)
        self._mark_changed()
        self._refresh_all()

    def _clone_node(self, node_id: str):
        node = self._node(node_id)
        if not node:
            return
        parent_id = node.get("parent_id", "")
        if not parent_id:
            return
        clone_id = SandboxDataModel.next_id(self._node_map(), node.get("type", "object"))
        cloned = SandboxDataModel.clone_node(node, clone_id, parent_id)
        if cloned.get("type") in ("marker", "dragger") and not self._is_keybind_bound(node_id):
            siblings = [
                self._node(child_id) for child_id in self._node(parent_id).get("children", [])
                if self._node(child_id) and self._node(child_id).get("type") in ("marker", "dragger") and not self._is_keybind_bound(child_id)
            ]
            next_index = ((max([int(s.get("index", 0)) for s in siblings], default=0) // 10) + 1) * 10
            cloned["index"] = max(10, next_index)
        self._node_map()[clone_id] = cloned
        self._node(parent_id).setdefault("children", []).append(clone_id)
        self.data["sandbox"]["selected_id"] = clone_id
        self._mark_changed()
        self._refresh_all()

    def _delete_node(self, node_id: str):
        node = self._node(node_id)
        if not node:
            return
        if node.get("type") == "folder" and not node.get("parent_id"):
            return
        ids_to_delete = []

        def collect(target_id):
            target = self._node(target_id)
            if not target:
                return
            ids_to_delete.append(target_id)
            if target.get("type") == "folder":
                for child_id in target.get("children", []):
                    collect(child_id)

        collect(node_id)
        parent = self._parent_node(node)
        if parent:
            parent["children"] = [child_id for child_id in parent.get("children", []) if child_id != node_id]
        for target_id in ids_to_delete:
            self._node_map().pop(target_id, None)
        for other in self._node_map().values():
            if other.get("type") == "keybind" and other.get("target_id") in ids_to_delete:
                other["target_id"] = ""
        fallback = self.data["sandbox"]["root_ids"][0] if self.data["sandbox"]["root_ids"] else ""
        self.data["sandbox"]["selected_id"] = fallback
        self._mark_changed()
        self._refresh_all()

    def _sandbox_runtime_keybinds(self):
        keybinds = {}
        for node_id, node in self._node_map().items():
            if node.get("type") != "keybind":
                continue
            if not self._is_effectively_enabled(node_id):
                continue
            binding = node.get("keybind", "").strip()
            target_id = node.get("target_id", "")
            if binding and target_id and self._node(target_id):
                keybinds[node_id] = binding
        return keybinds

    def _refresh_runtime_keybind_listener(self):
        if not self._executing:
            return
        bindings = self._sandbox_runtime_keybinds()
        if self._runtime_keybind_listener is None:
            self._runtime_keybind_listener = _keybind_listener_type()(bindings, parent=self)
            self._runtime_keybind_listener.triggered.connect(self._on_runtime_keybind)
        else:
            self._runtime_keybind_listener.update_keybinds(bindings)

    def _set_execution_ui_locked(self, locked: bool):
        self._tree.setEnabled(not locked)
        self._properties_area.setEnabled(not locked)
        self._execute_btn.setEnabled(not locked)
        self._stop_btn.setEnabled(locked)
        self._info_btn.setEnabled(True)
        self._overlay_controller.set_execution_mode(locked)
        self._overlay_controller.set_interactive(not locked)
        self._overlay_controller.show()
        if not locked:
            self._set_shared_execution_indicator("")

    def _default_execute_target(self):
        if self._sequence_execute_nodes():
            return "folder_sequence"
        return ""

    def _build_active_snapshot(self):
        sandbox = SandboxDataModel.sanitize_snapshot(self.data["sandbox"])
        return {"name": self.data.get("name", "setup"), "mode": "sandbox", "sandbox": sandbox}

    def _find_shared_overlay(self):
        Overlay = _overlay_type()
        for widget in QtWidgets.QApplication.instance().topLevelWidgets():
            if isinstance(widget, Overlay):
                return widget
        return None

    def _execution_indicator_enabled(self):
        return True

    def _execution_indicator_text_enabled(self):
        return not ConfigManager.load().get("visual", {}).get("Hide_Keybind_When_Marker_Is_Hidden", False)

    def _hide_marker_on_execute_enabled(self):
        return bool(ConfigManager.load().get("visual", {}).get("Hide_Marker_On_Execute", True))

    def _execution_index_label_for_node(self, node_id: str):
        node = self._node(node_id)
        if not node or node.get("type") not in ("marker", "dragger"):
            return ""
        if self._is_keybind_bound(node_id):
            return "0"
        for display_order, child in enumerate(self._sequence_execute_nodes(), start=1):
            if child.get("id", "") == node_id:
                return str(display_order)
        return ""

    def _indicator_label_for_node(self, node_id: str):
        node = self._node(node_id)
        if not node:
            return ""
        if self._execution_indicator_text_enabled():
            if node.get("type") == "keybind":
                return str(node.get("keybind", "")).strip()
            refs = self._keybind_references(active_only=True).get(node_id, [])
            labels = []
            for ref_id in refs[:2]:
                ref = self._node(ref_id)
                if not ref:
                    continue
                key_text = str(ref.get("keybind", "")).strip()
                if key_text:
                    labels.append(key_text)
            if labels:
                return " / ".join(labels)
        return self._execution_index_label_for_node(node_id)

    def _indicator_overlay_options(self, node_id: str):
        node = self._node(node_id)
        if node and node.get("type") == "keybind":
            node = self._node(node.get("target_id", ""))
        text_only = self._hide_marker_on_execute_enabled()
        secondary_dot = None
        if text_only and node and node.get("type") == "dragger":
            secondary_dot = (
                int(node.get("end_x", 0)),
                int(node.get("end_y", 0)),
            )
        return {
            "text_only": text_only,
            "secondary_dot": secondary_dot,
        }

    def _indicator_position_for_node(self, node_id: str):
        node = self._node(node_id)
        if not node:
            return None
        if node.get("type") == "keybind":
            return self._indicator_position_for_node(node.get("target_id", ""))
        if node.get("type") == "marker":
            return (int(node.get("x", 0)), int(node.get("y", 0)))
        if node.get("type") == "dragger":
            return (int(node.get("start_x", 0)), int(node.get("start_y", 0)))
        if node.get("type") == "folder":
            for child in self._sequence_execute_nodes():
                return self._indicator_position_for_node(child.get("id", ""))
        return None

    def _set_shared_execution_indicator(self, node_id: str = ""):
        overlay = self._find_shared_overlay()
        self._current_indicator_node_id = node_id or ""
        if not overlay:
            return
        if not self._executing or not self._execution_indicator_enabled():
            overlay.set_marker_execution_mode(False, keep_visible=False)
            return
        node = self._node(node_id)
        resolved_node_id = node_id
        if node and node.get("type") == "folder":
            for child in self._sequence_execute_nodes():
                resolved_node_id = child.get("id", "")
                break
            node = self._node(resolved_node_id)
        pos = self._indicator_position_for_node(resolved_node_id)
        label = self._indicator_label_for_node(resolved_node_id)
        options = self._indicator_overlay_options(resolved_node_id)
        if pos is None:
            overlay.set_marker_execution_mode(False, keep_visible=False)
            return
        overlay.set_marker_execution_mode(
            True,
            keep_visible=True,
            x=pos[0],
            y=pos[1],
            label_text=label,
            text_only=options["text_only"],
            secondary_dot=options["secondary_dot"],
        )

    def _show_click_effect(self, x: int, y: int):
        if not ConfigManager.load().get("visual", {}).get("Click_Effects", True):
            return
        overlay = self._find_shared_overlay()
        if overlay:
            overlay.show_click_effect(x, y)
            if self._execution_indicator_enabled() and self._current_indicator_node_id:
                options = self._indicator_overlay_options(self._current_indicator_node_id)
                overlay.set_marker_execution_mode(
                    True,
                    keep_visible=True,
                    x=int(x),
                    y=int(y),
                    label_text=self._indicator_label_for_node(self._current_indicator_node_id),
                    text_only=options["text_only"],
                    secondary_dot=options["secondary_dot"],
                )

    def _on_worker_drag_progress(self, x: int, y: int):
        if not self._executing:
            return
        overlay = self._find_shared_overlay()
        if overlay:
            overlay.move_active_click_effect(x, y)
            if self._execution_indicator_enabled():
                pos = (x, y)
                options = self._indicator_overlay_options(self._current_indicator_node_id)
                if options["text_only"] and options["secondary_dot"]:
                    pos = self._indicator_position_for_node(self._current_indicator_node_id) or pos
                overlay.set_marker_execution_mode(
                    True,
                    keep_visible=True,
                    x=pos[0],
                    y=pos[1],
                    label_text=self._indicator_label_for_node(self._current_indicator_node_id),
                    text_only=options["text_only"],
                    secondary_dot=options["secondary_dot"],
                )

    def _finish_click_effect(self, x: int, y: int):
        if not ConfigManager.load().get("visual", {}).get("Click_Effects", True):
            return
        overlay = self._find_shared_overlay()
        if overlay:
            overlay.release_click_effect(x, y)
            overlay.set_marker_execution_mode(False, keep_visible=False)

    def _on_execute(self):
        if self._executing:
            return
        warnings = self._sequence_index_warnings()
        if warnings:
            self._set_status("Fix red Index warnings before Execute")
            self._refresh_hierarchy()
            self._show_index_warning_dialog(warnings)
            return
        active = self._persist_active_snapshot()

        self._worker = SandboxExecutionWorker(active.get("sandbox", {}))
        self._worker.status_changed.connect(self._set_status)
        self._worker.click_started.connect(self._show_click_effect)
        self._worker.click_finished.connect(self._finish_click_effect)
        self._worker.drag_progress.connect(self._on_worker_drag_progress)
        self._worker.stopped.connect(self._on_worker_stopped)
        self._worker.target_completed.connect(self._on_worker_target_completed)

        self._pre_execute_selected_id = self.data["sandbox"].get("selected_id", "")
        self._active_execute_target_id = self._default_execute_target()
        self._set_selected_node("", refresh_properties=True)
        self._executing = True
        self._sequence_iteration_count = 0
        self._sequence_started_at = time.perf_counter()
        self._sequence_duration_seconds = int(self._sequence_settings().get("repeat_timer_seconds", 60))
        self._ensure_progress_timer()
        self._progress_timer.start()
        self._set_execution_ui_locked(True)
        self._refresh_runtime_keybind_listener()
        self._worker.start()

        target_id = self._active_execute_target_id
        self._current_indicator_node_id = target_id or ""
        if target_id:
            self._worker.enqueue_target(target_id)
        self._play_system_sound("SystemAsterisk", 980)
        self._set_status("Sandbox armed")

    def _on_stop(self):
        if not self._executing:
            return
        self._play_system_sound("SystemExclamation", 720)
        self._set_status("Stopping...")
        if self._runtime_keybind_listener:
            self._runtime_keybind_listener.stop()
            self._runtime_keybind_listener.deleteLater()
            self._runtime_keybind_listener = None
        if self._worker:
            self._worker.stop()
        else:
            self._on_worker_stopped()

    def _on_worker_stopped(self):
        self._executing = False
        if self._runtime_keybind_listener:
            self._runtime_keybind_listener.stop()
            self._runtime_keybind_listener.deleteLater()
            self._runtime_keybind_listener = None
        self._worker = None
        if self._progress_timer:
            self._progress_timer.stop()
        self._set_execution_ui_locked(False)
        self._active_execute_target_id = ""
        ActiveSetupManager.clear(self.data.get("name", "setup"))
        overlay = self._find_shared_overlay()
        if overlay:
            overlay.set_marker_execution_mode(False, keep_visible=False)
        self._set_selected_node(self._pre_execute_selected_id, refresh_properties=True)
        self._set_status("Stopped")
        self._refresh_all()

    def _on_runtime_keybind(self, node_id: str):
        if self._worker and node_id in self._node_map():
            self._set_status(f"Triggered {self._node(node_id).get('name', node_id)}")
            self._current_indicator_node_id = node_id or ""
            self._worker.trigger_keybind_target(node_id)

    def _on_worker_target_completed(self, node_id: str):
        if not self._executing or node_id != "folder_sequence":
            return
        self._sequence_iteration_count += 1
        settings = self._sequence_settings()
        mode = settings.get("repeat_mode", "until_stop")
        if mode == "repeat_times":
            target = max(1, int(settings.get("repeat_times_target", 1)))
            if self._sequence_iteration_count >= target:
                QtCore.QTimer.singleShot(0, self._on_stop)
                return
        elif mode == "repeat_timer":
            total = max(1, int(settings.get("repeat_timer_seconds", 1)))
            if (time.perf_counter() - (self._sequence_started_at or time.perf_counter())) >= total:
                QtCore.QTimer.singleShot(0, self._on_stop)
                return
        if self._worker and self._active_execute_target_id == "folder_sequence":
            self._worker.enqueue_target("folder_sequence")
        self._update_execution_progress()

    def _on_setup_keybind(self, action: str):
        if action == "Execute":
            self._on_execute()
        elif action == "Stop":
            self._on_stop()
        elif action == "Register_Click_Position":
            self._register_selected_position()
        elif action == "See_Setup_Info":
            self._toggle_setup_info()
        elif action == "New_Marker_Sandbox":
            self._play_system_sound("SystemQuestion", 760)
            self._open_create_object_dialog("folder_sequence")
        elif action == "New_Keybind_Sandbox":
            self._play_system_sound("SystemQuestion", 760)
            self._quick_create_sandbox_object("folder_keybind", "keybind")

    def _teardown_sandbox_overlay(self):
        if hasattr(self, "_overlay_refresh_timer") and self._overlay_refresh_timer:
            self._overlay_refresh_timer.stop()
        if self._overlay_controller:
            self._overlay_controller.hide()
            self._overlay_controller.close()
        overlay = self._find_shared_overlay()
        if overlay:
            overlay.set_marker_execution_mode(False, keep_visible=False)

    def closeEvent(self, event):
        if not getattr(self, "_closing", False):
            if not self.prompt_save_before_close():
                event.ignore()
                return
            if self._runtime_keybind_listener:
                self._runtime_keybind_listener.stop()
                self._runtime_keybind_listener.deleteLater()
                self._runtime_keybind_listener = None
            if self._setup_keybind_listener:
                self._setup_keybind_listener.stop()
            if self._worker:
                self._worker.stop()
                self._worker.wait(500)
            if self._info_dialog:
                self._info_dialog.close()
            self._teardown_sandbox_overlay()
            ActiveSetupManager.clear(self.data.get("name", "setup"))
            super().closeEvent(event)
            return

        app = QtWidgets.QApplication.instance()
        if app:
            app.removeEventFilter(self)
        self._teardown_sandbox_overlay()
        super().closeEvent(event)


class SandboxMode:
    def __init__(self, main_window):
        self.main_window = main_window

    def start(self):
        path = getattr(self.main_window, "_mode_launch_path", "")
        if not path:
            return None

        from UI.main_window import SandboxModeUI

        base_pos = self.main_window.pos()
        offset = base_pos + QtCore.QPoint(int(round(self.main_window.width() * 0.5)) + 10, 0)
        self.main_window.mode_window = SandboxModeUI(path, offset, parent=None)

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

        from UI.main_window import SandboxModeUI

        if isinstance(mode_window, SandboxModeUI):
            mode_window.close()

