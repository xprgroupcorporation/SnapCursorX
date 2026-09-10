import os
import subprocess
import sys
from pathlib import Path

from Core.Utils import APP_DIR


STARTUP_REGISTRY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_VALUE_NAME = "SnapCursorX"


def _startup_command() -> str:
    """Build a command that works in both source and frozen builds."""
    if getattr(sys, "frozen", False):
        return subprocess.list2cmdline([sys.executable])

    entry_point = Path(APP_DIR) / "Main.py"
    return subprocess.list2cmdline([sys.executable, str(entry_point)])


def set_run_on_start(enabled: bool) -> tuple[bool, str]:
    """Enable or disable per-user Windows startup for SnapCursorX."""
    if os.name != "nt":
        return False, "Windows startup is only available on Windows."

    try:
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, STARTUP_REGISTRY_PATH) as key:
            if enabled:
                winreg.SetValueEx(
                    key,
                    STARTUP_VALUE_NAME,
                    0,
                    winreg.REG_SZ,
                    _startup_command(),
                )
            else:
                try:
                    winreg.DeleteValue(key, STARTUP_VALUE_NAME)
                except FileNotFoundError:
                    pass
        return True, ""
    except Exception as exc:
        return False, str(exc).strip() or exc.__class__.__name__
