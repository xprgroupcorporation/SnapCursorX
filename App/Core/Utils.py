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
# External Data folder (next to exe or in dev folder)
INSTALL_DATA_DIR = BASE_DIR / "Data"
# Bundled Data folder (inside _internal when frozen)
BUNDLED_DATA_DIR = BUNDLE_DIR / "Data" if IS_FROZEN else None


def _ensure_dir_structure(path: Path) -> None:
    """Ensure directory exists with writable parent structure."""
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass


def _is_dir_writable(path: Path) -> bool:
    """Check if a directory is writable."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_test.tmp"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def _seed_user_data(source: Path, target: Path) -> None:
    """Copy data from source to target, skipping existing files."""
    if not source.exists():
        _ensure_dir_structure(target)
        return

    for item in source.iterdir():
        destination = target / item.name
        if destination.exists():
            continue
        try:
            if item.is_dir():
                shutil.copytree(item, destination)
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item, destination)
        except OSError:
            pass


def _resolve_data_dir() -> Path:
    """Resolve the data directory, preferring external Data folder next to exe."""
    if not IS_FROZEN:
        # Development mode: use Data folder next to App directory
        return INSTALL_DATA_DIR

    # Production mode: Data should be next to exe
    # First, try to use the external data directory (should be at exe location)
    if INSTALL_DATA_DIR.exists():
        # Data folder exists next to exe - use it and ensure it's writable
        _ensure_dir_structure(INSTALL_DATA_DIR)
        if _is_dir_writable(INSTALL_DATA_DIR):
            return INSTALL_DATA_DIR
    
    # If external Data folder doesn't exist or isn't writable,
    # fall back to user's local appdata with seed from bundled data
    local_appdata = Path(os.environ.get("LOCALAPPDATA", str(BASE_DIR)))
    user_data_dir = local_appdata / "SnapCursorX" / "Data"
    
    # Seed from bundled Data folder if available, otherwise external
    seed_source = BUNDLED_DATA_DIR if BUNDLED_DATA_DIR and BUNDLED_DATA_DIR.exists() else INSTALL_DATA_DIR
    try:
        _seed_user_data(seed_source, user_data_dir)
    except OSError:
        pass
    
    _ensure_dir_structure(user_data_dir)
    return user_data_dir


DATA_DIR = _resolve_data_dir()
CONFIG_DIR = DATA_DIR / "Config"
SETUPS_DIR = DATA_DIR / "Setups"
ACTIVE_DIR = DATA_DIR / "Active"
