import time

import win32con
import win32gui


class SharedWorkerHelper:
    def _button_messages(self, mouse_button: str):
        button = (mouse_button or "left").lower()
        if button == "right":
            return win32con.WM_RBUTTONDOWN, win32con.WM_RBUTTONUP, win32con.MK_RBUTTON
        if button == "middle":
            return win32con.WM_MBUTTONDOWN, win32con.WM_MBUTTONUP, win32con.MK_MBUTTON
        return win32con.WM_LBUTTONDOWN, win32con.WM_LBUTTONUP, win32con.MK_LBUTTON

    def _resolve_target_hwnd(self, click_x: int, click_y: int, ignored_hwnds=None, descend_to_child: bool = False):
        ignored_hwnds = frozenset(ignored_hwnds or ())
        hwnd = win32gui.WindowFromPoint((click_x, click_y))
        while hwnd:
            try:
                if hwnd in ignored_hwnds:
                    hwnd = win32gui.GetWindow(hwnd, win32con.GW_HWNDNEXT)
                    continue
                if win32gui.IsWindowVisible(hwnd):
                    target_hwnd = hwnd
                    if descend_to_child:
                        while True:
                            try:
                                client_pt = win32gui.ScreenToClient(target_hwnd, (click_x, click_y))
                                child_hwnd = win32gui.ChildWindowFromPointEx(
                                    target_hwnd,
                                    client_pt,
                                    win32con.CWP_SKIPDISABLED | win32con.CWP_SKIPINVISIBLE,
                                )
                            except Exception:
                                break
                            if not child_hwnd or child_hwnd == target_hwnd or child_hwnd in ignored_hwnds:
                                break
                            target_hwnd = child_hwnd
                    return target_hwnd
                hwnd = win32gui.GetWindow(hwnd, win32con.GW_HWNDNEXT)
            except Exception:
                return None
        return None

    def _sleep_until(
        self,
        target_time: float,
        coarse_threshold: float = 0.003,
        coarse_ratio=None,
        coarse_cap=None,
        fine_sleep: float = 0.0,
    ):
        while getattr(self, "_running", False):
            remaining = target_time - time.perf_counter()
            if remaining <= 0:
                return
            if remaining > coarse_threshold:
                if coarse_ratio is None:
                    sleep_for = max(0.0, remaining - 0.001)
                else:
                    sleep_for = max(0.0, remaining * float(coarse_ratio))
                    if coarse_cap is not None:
                        sleep_for = min(sleep_for, float(coarse_cap))
                time.sleep(sleep_for)
            else:
                time.sleep(max(0.0, fine_sleep))
