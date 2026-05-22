import json
import re
import time
from pathlib import Path

from Config.Manager import ConfigManager
from Core.Utils import ACTIVE_DIR, SETUPS_DIR


def atomic_json_write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f"{path.name}.tmp"
    payload = json.dumps(data, indent=4)
    with tmp.open("w", encoding="utf-8") as f:
        f.write(payload)

    for _ in range(8):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            time.sleep(0.05)

    try:
        with path.open("w", encoding="utf-8") as f:
            f.write(payload)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


class SetupManager:
    BASE_PATH = SETUPS_DIR

    @classmethod
    def ensure_folder(cls):
        cls.BASE_PATH.mkdir(parents=True, exist_ok=True)

    @classmethod
    def _safe_name(cls, name):
        cleaned = re.sub(r'[<>:"/\\|?*]+', "", str(name or "")).strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned

    @classmethod
    def _path_for_name(cls, name):
        safe_name = cls._safe_name(name).replace(" ", "_")
        return cls.BASE_PATH / f"{safe_name}.json"

    @classmethod
    def is_loadable_data(cls, data):
        return isinstance(data, dict) and data.get("mode") in ("single", "sandbox") and bool(str(data.get("name", "")).strip())

    @classmethod
    def is_loadable(cls, path):
        try:
            return cls.is_loadable_data(cls.load(path))
        except Exception:
            return False

    @classmethod
    def existing_names(cls):
        names = []
        for path in cls.list_setups():
            try:
                data = cls.load(path)
            except Exception:
                continue
            name = str(data.get("name", "")).strip()
            if name:
                names.append(name)
        return names

    @classmethod
    def unique_name(cls, name):
        base_name = cls._safe_name(name)
        if not base_name:
            base_name = "New Setup"
        existing = {existing.lower() for existing in cls.existing_names()}
        if base_name.lower() not in existing:
            return base_name
        index = 1
        while True:
            candidate = f"{base_name} - ({index})"
            if candidate.lower() not in existing:
                return candidate
            index += 1

    @classmethod
    def create(cls, name, mode):
        cls.ensure_folder()
        final_name = cls.unique_name(name)
        path = cls._path_for_name(final_name)

        data_block = {}
        if mode == "single":
            cfg = ConfigManager.load()
            default_px = max(0, int(cfg.get("general", {}).get("Default_Screen_Failsafe_PX", 50)))
            data_block = {
                "enabled": True,
                "top_px": default_px,
                "bottom_px": default_px,
                "left_px": default_px,
                "right_px": default_px,
            }

        data = {
            "name": final_name,
            "mode": mode,
            "data": {},
        }
        if mode == "single":
            data["failsafe"] = data_block

        atomic_json_write(path, data)
        return str(path)

    @classmethod
    def load(cls, path):
        with Path(path).open("r", encoding="utf-8") as f:
            return json.load(f)

    @classmethod
    def list_setups(cls):
        cls.ensure_folder()
        files = []

        for path in cls.BASE_PATH.iterdir():
            if path.suffix == ".json":
                files.append(str(path))

        return files

    @classmethod
    def delete(cls, path):
        path = Path(path)
        if path.exists():
            path.unlink()

    @classmethod
    def can_use_name(cls, name, exclude_path=None):
        desired = cls._safe_name(name)
        if not desired:
            return False
        excluded = str(Path(exclude_path).resolve()).lower() if exclude_path else None
        for path in cls.list_setups():
            norm = str(Path(path).resolve()).lower()
            if excluded and norm == excluded:
                continue
            try:
                existing_name = cls._safe_name(cls.load(path).get("name", ""))
            except Exception:
                continue
            if existing_name.lower() == desired.lower():
                return False
        return True

    @classmethod
    def rename(cls, path, new_name):
        cls.ensure_folder()
        cleaned_name = cls._safe_name(new_name)
        if not cleaned_name:
            raise ValueError("Name required")
        if not cls.can_use_name(cleaned_name, exclude_path=path):
            raise FileExistsError("Duplicate setup name")
        current_path = Path(path)
        data = cls.load(current_path)
        data["name"] = cleaned_name
        target_path = cls._path_for_name(cleaned_name)
        current_norm = str(current_path.resolve()).lower()
        target_norm = str(target_path.resolve()).lower()
        if current_norm == target_norm:
            atomic_json_write(current_path, data)
            return str(current_path)
        atomic_json_write(target_path, data)
        if current_path.exists():
            current_path.unlink()
        return str(target_path)


class ActiveSetupManager:
    ACTIVE_PATH = ACTIVE_DIR

    @classmethod
    def ensure_folder(cls):
        cls.ACTIVE_PATH.mkdir(parents=True, exist_ok=True)

    @classmethod
    def write(cls, name, data):
        """Atomic write: temp file -> rename. Prevents corruption on crash."""
        cls.ensure_folder()
        safe = name.replace(" ", "_")
        path = cls.ACTIVE_PATH / f"{safe}_active.json"
        atomic_json_write(path, data)
        return str(path)

    @classmethod
    def clear(cls, name):
        cls.ensure_folder()
        safe = name.replace(" ", "_")
        path = cls.ACTIVE_PATH / f"{safe}_active.json"
        if path.exists():
            path.unlink()

    @classmethod
    def read(cls, name):
        cls.ensure_folder()
        safe = name.replace(" ", "_")
        path = cls.ACTIVE_PATH / f"{safe}_active.json"
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
