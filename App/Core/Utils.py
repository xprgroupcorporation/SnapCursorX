import os
import shutil
import sys
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent.parent
IS_FROZEN = bool(getattr(sys, "frozen", False))

BASE_DIR = Path(sys.executable).resolve().parent if IS_FROZEN else APP_DIR.parent
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR)) if IS_FROZEN else APP_DIR.parent
RUNTIME_APP_DIR = BUNDLE_DIR / "App" if IS_FROZEN else APP_DIR
CORE_DIR = RUNTIME_APP_DIR / "Core"

ASSETS_DIR = BUNDLE_DIR / "Assets" if IS_FROZEN else BASE_DIR / "Assets"
INSTALL_DATA_DIR = BASE_DIR / "Data"


def _is_data_root_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_test.tmp"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def _seed_user_data(source: Path, target: Path) -> None:
    if not source.exists():
        target.mkdir(parents=True, exist_ok=True)
        return

    for item in source.iterdir():
        destination = target / item.name
        if destination.exists():
            continue
        if item.is_dir():
            shutil.copytree(item, destination)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, destination)


def _resolve_data_dir() -> Path:
    if not IS_FROZEN:
        return INSTALL_DATA_DIR

    if _is_data_root_writable(INSTALL_DATA_DIR):
        return INSTALL_DATA_DIR

    local_appdata = Path(os.environ.get("LOCALAPPDATA", str(BASE_DIR)))
    user_data_dir = local_appdata / "SnapCursorX" / "Data"
    user_data_dir.mkdir(parents=True, exist_ok=True)
    _seed_user_data(INSTALL_DATA_DIR, user_data_dir)
    return user_data_dir


DATA_DIR = _resolve_data_dir()
CONFIG_DIR = DATA_DIR / "Config"
SETUPS_DIR = DATA_DIR / "Setups"
ACTIVE_DIR = DATA_DIR / "Active"
