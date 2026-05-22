import copy
import json

from Core.info_loader import load_info_config
from Core.Utils import APP_DIR, BASE_DIR, CONFIG_DIR, DATA_DIR


APP_ROOT = APP_DIR
PROJECT_ROOT = BASE_DIR
DATA_ROOT = DATA_DIR
CONFIG_ROOT = CONFIG_DIR

_info_config = load_info_config(
    required=[
        "NAME",
        "VERSION",
        "COMPANY",
        "TAGLINE",
        "COPYRIGHT",
        "EMAIL",
        "DISCORD",
        "ABOUTUS",
    ],
    allow_github_alias=True,
)


class AppConfig:
    NAME = _info_config["NAME"]
    VERSION = _info_config["VERSION"]
    APP_FULL = f"{NAME} — {VERSION}"

    COMPANY = _info_config["COMPANY"]
    TAGLINE = _info_config["TAGLINE"]
    COPYRIGHT = _info_config["COPYRIGHT"]

    EMAIL = _info_config["EMAIL"]
    DISCORD = _info_config["DISCORD"]
    GITHUB = _info_config.get("GITHUB", _info_config.get("GitHub"))
    ABOUTUS = _info_config["ABOUTUS"]
    UPDATE_RELEASE_API_URL = _info_config.get(
        "UPDATE_RELEASE_API_URL",
        "https://api.github.com/repos/YOUR-USERNAME/YOUR-REPO/releases/latest",
    )
    UPDATE_RELEASE_PAGE_URL = _info_config.get(
        "UPDATE_RELEASE_PAGE_URL",
        "https://github.com/YOUR-USERNAME/YOUR-REPO/releases/latest",
    )


class ConfigManager:
    PATH = CONFIG_ROOT / "Meta.json"
    STARTER_CLICK_RANDOMNESS_KEY = "Auto_Click_Click_Randomness"
    LEGACY_STARTER_CLICK_RANDOMNESS_KEY = "Auto_Click_Anti-Detection"

    DEFAULT = {
        "keybinds": {
            "See_Setup_Info": "F1",
            "Execute": "F2",
            "Stop": "F3",
            "Register_Click_Position": "F4",
            "New_Marker_Sandbox": "F5",
            "New_Keybind_Sandbox": "F6",
            "Quick_Save": "F7",
            "Recover_Window_Position": "F8",
            "Save_Close_Setup": "F9",
            "Kill_Switch": "F10"
        },
        "general": {
            "Run_On_Start": False,
            "Performance_Mode_Trigger_MS": 99,
        },
        "visual": {
            "Click_Effects": True,
            "Hide_Marker_On_Execute": True,
            "Hide_Keybind_When_Marker_Is_Hidden": False,
            "Marker_Size_Multiplier_Percent": 50,
        },
        "starter_values": {
            "Default_Delay_Before_Next_Target_MS": 200,
            "Default_Drag_Duration_MS": 100,
            "Default_Mouse_Hold_MS": 100,
            "Default_Auto_Click_Delay_MS": 100,
            "Default_Screen_Failsafe_PX": 50,
            "Default_Always_Follow_Mouse": False,
            STARTER_CLICK_RANDOMNESS_KEY: True,
        },
    }

    LEGACY_KEY_GROUPS = {
        "Hide_Marker_On_Execute": "visual",
        "Hide_Keybind_When_Marker_Is_Hidden": "visual",
        "Click_Effects": "visual",
        "Default_Delay_Before_Next_Target_MS": "starter_values",
        "Default_Drag_Duration_MS": "starter_values",
        "Default_Mouse_Hold_MS": "starter_values",
        "Default_Auto_Click_Delay_MS": "starter_values",
        "Default_Screen_Failsafe_PX": "starter_values",
        "Default_Always_Follow_Mouse": "starter_values",
        STARTER_CLICK_RANDOMNESS_KEY: "starter_values",
        LEGACY_STARTER_CLICK_RANDOMNESS_KEY: "starter_values",
        "Run_On_Start": "general",
        "Performance_Mode_Trigger_MS": "general",
    }

    @classmethod
    def load(cls):
        if not cls.PATH.exists():
            cls.save(cls.DEFAULT)
            return cls.DEFAULT

        with cls.PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)

        data = cls._normalize(data)

        def merge(default, current):
            cleaned = {}

            for key, value in default.items():
                if key in current:
                    if isinstance(value, dict) and isinstance(current[key], dict):
                        cleaned[key] = merge(value, current[key])
                    else:
                        cleaned[key] = current[key]
                else:
                    cleaned[key] = value

            return cleaned

        merged = merge(cls.DEFAULT, data)
        cls.save(merged)
        return merged

    @classmethod
    def _normalize(cls, data):
        current = copy.deepcopy(data) if isinstance(data, dict) else {}

        current.setdefault("keybinds", {})
        current.setdefault("general", {})
        current.setdefault("visual", {})
        current.setdefault("starter_values", {})

        legacy_general = current.get("general", {})
        if isinstance(legacy_general, dict):
            for key, section_name in cls.LEGACY_KEY_GROUPS.items():
                if key in legacy_general:
                    current.setdefault(section_name, {})
                    current[section_name].setdefault(key, legacy_general[key])

        visual = current.setdefault("visual", {})
        visual["Marker_Size_Multiplier_Percent"] = cls.clamp_marker_size_percent(
            visual.get(
                "Marker_Size_Multiplier_Percent",
                cls.DEFAULT["visual"]["Marker_Size_Multiplier_Percent"],
            )
        )
        starter_values = current.setdefault("starter_values", {})
        if (
            cls.LEGACY_STARTER_CLICK_RANDOMNESS_KEY in starter_values
            and cls.STARTER_CLICK_RANDOMNESS_KEY not in starter_values
        ):
            starter_values[cls.STARTER_CLICK_RANDOMNESS_KEY] = starter_values[cls.LEGACY_STARTER_CLICK_RANDOMNESS_KEY]
        starter_values.pop(cls.LEGACY_STARTER_CLICK_RANDOMNESS_KEY, None)
        keybinds = current.setdefault("keybinds", {})
        if "Hide_Program_From_Taskbar" in keybinds and "Save_Close_Setup" not in keybinds:
            keybinds["Save_Close_Setup"] = keybinds["Hide_Program_From_Taskbar"]
        keybinds.pop("Hide_Program_From_Taskbar", None)

        return current

    @staticmethod
    def clamp_marker_size_percent(value):
        try:
            value = int(value)
        except (TypeError, ValueError):
            value = 50
        return max(5, min(100, value))

    @classmethod
    def marker_size_percent(cls, data=None):
        source = data if isinstance(data, dict) else cls.load()
        visual = source.get("visual", {}) if isinstance(source, dict) else {}
        return cls.clamp_marker_size_percent(
            visual.get(
                "Marker_Size_Multiplier_Percent",
                cls.DEFAULT["visual"]["Marker_Size_Multiplier_Percent"],
            )
        )

    @classmethod
    def scale_marker_size(cls, base_size, percent=None, data=None):
        clamped_percent = (
            cls.clamp_marker_size_percent(percent)
            if percent is not None
            else cls.marker_size_percent(data)
        )
        return max(2, int(round(float(base_size) * (clamped_percent / 50.0))))

    @classmethod
    def save(cls, data):
        cls.PATH.parent.mkdir(parents=True, exist_ok=True)
        with cls.PATH.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)


class SettingDisplay:
    TABLE = {
        "Execute": {
            "title": "Execute",
            "description": "Start the active setup or sandbox execution.",
        },
        "Stop": {
            "title": "Stop",
            "description": "Stop the current execution immediately.",
        },
        "Register_Click_Position": {
            "title": "Set Position",
            "description": "Single mode shortcut to capture a new click position.",
        },
        "New_Marker_Sandbox": {
            "title": "New Marker",
            "description": "Sandbox shortcut to create a new marker node.",
        },
        "New_Keybind_Sandbox": {
            "title": "New Keybind",
            "description": "Sandbox shortcut to create a new keybind node.",
        },
        "Quick_Save": {
            "title": "Quick Save",
            "description": "Save the current setup without leaving the page.",
        },
        "Recover_Window_Position": {
            "title": "Toggle Minimize",
            "description": "Toggle minimize or restore for the app windows while working on a setup.",
        },
        "Save_Close_Setup": {
            "title": "Save & Close Setup",
            "description": "Save the current setup and close it immediately.",
        },
        "Kill_Switch": {
            "title": "Kill Switch",
            "description": "Force close the app without saving changes.",
        },
        "See_Setup_Info": {
            "title": "Setup Info",
            "description": "Open or hide the setup tips and help window.",
        },
        "Run_On_Start": {
            "title": "Run On Start",
            "description": "Launch this app automatically when Windows starts.",
        },
        "Default_Screen_Failsafe_PX": {
            "title": "Screen Failsafe PX",
            "description": "Default per-edge pixel distance for new single mode screen failsafe boundaries.",
        },
        "Performance_Mode_Trigger_MS": {
            "title": "Performance Mode Trigger",
            "description": "Automatically stop emitting click effects when click delay is at or below this many milliseconds. Default: 99 ms.",
        },
        "Click_Effects": {
            "title": "Click Effects",
            "description": "Show visual click feedback on the overlay. \n(Disable will improve performance and more accurate CPS)",
        },
        "Hide_Marker_On_Execute": {
            "title": "Hide Markers",
            "description": "Hide position indicators while execution is running. \n(Disable may improve performance.)",
        },
        "Hide_Keybind_When_Marker_Is_Hidden": {
            "title": "Hide Keybind Text",
            "description": "Hide marker keybind labels when markers are hidden.",
        },
        "Marker_Size_Multiplier_Percent": {
            "title": "Marker Size Multiplier",
            "description": "Adjust all overlay marker size. (Default: 40%)",
        },
        "Default_Always_Follow_Mouse": {
            "title": "Follow Mouse",
            "description": "Default always-follow-mouse value for any new markers.",
        },
        "Default_Mouse_Hold_MS": {
            "title": "Mouse Hold",
            "description": "Default mouse hold duration for any new markers.",
        },
        "Default_Drag_Duration_MS": {
            "title": "Drag Duration",
            "description": "Default drag hold duration for any newly created draggers in sandbox mode.",
        },
        "Default_Delay_Before_Next_Target_MS": {
            "title": "Next Target Delay",
            "description": "Default delay before the next target for any newly created markers or draggers in sandbox mode.",
        },
        "Default_Auto_Click_Delay_MS": {
            "title": "Auto Click Delay",
            "description": "Default 'single mode' auto click delay.",
        },
        ConfigManager.STARTER_CLICK_RANDOMNESS_KEY: {
            "title": "Click Randomness",
            "description": "Default click randomness behavior for auto click.",
        },
    }

    @classmethod
    def get(cls, key):
        return cls.TABLE.get(key, {}).get("title", key.replace("_", " "))

    @classmethod
    def description(cls, key):
        return cls.TABLE.get(key, {}).get("description", "")
