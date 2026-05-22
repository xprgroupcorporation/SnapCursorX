import copy
import json

from Core.Utils import CONFIG_DIR, CORE_DIR


INFO_PATH = CONFIG_DIR / "Info.json"


def _load_external_info() -> dict:
    if not INFO_PATH.exists():
        raise FileNotFoundError(f"Missing Info.json: {INFO_PATH}")

    with INFO_PATH.open("r", encoding="utf-8") as f:
        loaded = json.load(f)

    if not isinstance(loaded, dict):
        raise ValueError("Info.json must contain a JSON object.")

    return loaded


def _write_external_info(info: dict) -> None:
    INFO_PATH.parent.mkdir(parents=True, exist_ok=True)
    with INFO_PATH.open("w", encoding="utf-8") as f:
        json.dump(info, f, indent=4, ensure_ascii=False)


def _validate_info(loaded: dict, required: list[str], allow_github_alias: bool) -> dict:
    missing = [key for key in required if key not in loaded]
    if allow_github_alias and "GITHUB" not in loaded and "GitHub" not in loaded:
        missing.append("GITHUB")
    if missing:
        raise KeyError(f"Info.json is missing keys: {', '.join(missing)}")
    return loaded


def load_info_config(required: list[str], allow_github_alias: bool = False) -> dict:
    if (CORE_DIR / "Exe_Builder.py").exists():
        return _validate_info(_load_external_info(), required, allow_github_alias)

    try:
        from Core.build_info import BUILD_INFO
    except ImportError as exc:
        raise RuntimeError(
            "Missing embedded build metadata in production. "
            "Expected Core.build_info.BUILD_INFO to be bundled into the executable."
        ) from exc

    if not isinstance(BUILD_INFO, dict):
        raise ValueError("Core.build_info.BUILD_INFO must contain a dict.")

    loaded = _validate_info(copy.deepcopy(BUILD_INFO), required, allow_github_alias)

    try:
        _write_external_info(loaded)
    except OSError:
        pass

    return loaded
