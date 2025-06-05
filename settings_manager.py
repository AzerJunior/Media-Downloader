# settings_manager.py
import json
import os
from constants import (
    SETTINGS_FILE, DEFAULT_FONT_FAMILY, DEFAULT_FONT_SIZE_NAME,
    DEFAULT_PLAYER_COMMAND, DEFAULT_HISTORY_ITEM_SIZE_NAME # NEW: Import new default
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
        # NEW: History/Active Item Size
        "history_item_size_name": DEFAULT_HISTORY_ITEM_SIZE_NAME # Add new setting
    }

def load_settings():
    """Loads settings from the settings file, using defaults if not found or invalid."""
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r') as f:
                loaded_settings = json.load(f)
                defaults = get_default_settings()
                for key, default_value in defaults.items():
                    if key not in loaded_settings:
                        loaded_settings[key] = default_value
                    if key == "last_deps_check_timestamp" and not isinstance(loaded_settings[key], (int, float)):
                         loaded_settings[key] = 0.0
                    if key == "app_version_at_last_deps_check" and not isinstance(loaded_settings[key], str):
                         loaded_settings[key] = "0.0.0"
                    # NEW: Ensure history_item_size_name is a string
                    if key == "history_item_size_name" and not isinstance(loaded_settings[key], str):
                         loaded_settings[key] = DEFAULT_HISTORY_ITEM_SIZE_NAME
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