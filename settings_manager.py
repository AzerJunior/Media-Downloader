import json
import os
from constants import (
    SETTINGS_FILE, DEFAULT_FONT_FAMILY, DEFAULT_FONT_SIZE_NAME,
    DEFAULT_PLAYER_COMMAND, DEFAULT_HISTORY_ITEM_SIZE_NAME, APP_VERSION # Added APP_VERSION
)
import time

def get_default_settings():
    """Returns a dictionary of default application settings."""
    return {
        "download_directory": os.path.expanduser("~/Downloads"),
        "appearance_mode": "System",
        "color_theme": "blue",
        "default_download_type": "Video",
        "font_family": DEFAULT_FONT_FAMILY,
        "font_size_name": DEFAULT_FONT_SIZE_NAME,
        "player_command": DEFAULT_PLAYER_COMMAND,
        "selected_format_code": "best",
        "download_subtitles": False,
        "subtitle_languages": "en",
        "embed_subtitles": True,
        "auto_paste_on_focus": True,
        "global_hotkey_enabled": False,
        "global_hotkey_combination": "<ctrl>+<shift>+D",
        "last_deps_check_timestamp": 0.0,
        "app_version_at_last_deps_check": "0.0.0",
        "history_item_size_name": DEFAULT_HISTORY_ITEM_SIZE_NAME,
        "show_download_complete_popup": True
    }

def load_settings():
    """Loads settings from the settings file, using defaults if not found or invalid."""
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r') as f:
                loaded_settings = json.load(f)
                defaults = get_default_settings()
                
                # Update loaded settings with any new default keys
                for key, default_value in defaults.items():
                    if key not in loaded_settings:
                        loaded_settings[key] = default_value
                
                # Ensure data types for critical settings
                if not isinstance(loaded_settings.get("last_deps_check_timestamp"), (int, float)):
                    loaded_settings["last_deps_check_timestamp"] = 0.0
                if not isinstance(loaded_settings.get("app_version_at_last_deps_check"), str):
                    loaded_settings["app_version_at_last_deps_check"] = "0.0.0"
                if not isinstance(loaded_settings.get("history_item_size_name"), str):
                    loaded_settings["history_item_size_name"] = DEFAULT_HISTORY_ITEM_SIZE_NAME
                if not isinstance(loaded_settings.get("show_download_complete_popup"), bool):
                    loaded_settings["show_download_complete_popup"] = True # Default to True if not boolean

                return loaded_settings
        return get_default_settings()
    except (json.JSONDecodeError, IOError) as e:
        print(f"Error loading settings from {SETTINGS_FILE}: {e}. Using defaults.")
        return get_default_settings()

def save_settings(settings_data):
    """Saves the provided settings data to the settings file."""
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings_data, f, indent=4)
    except IOError as e:
        print(f"Error saving settings to {SETTINGS_FILE}: {e}")