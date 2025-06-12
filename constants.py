# constants.py
import os
import sys

# --- Application Version ---
APP_VERSION = "0.4.1" # Updated version for these fixes

# --- File/Path Constants ---
SETTINGS_FILE = "settings.json"

if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    PROJECT_ROOT = sys._MEIPASS
else:
    # This assumes constants.py is in the project's root directory
    PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

# --- Media Extensions ---
VIDEO_EXTENSIONS = (
    ".mp4", ".mkv", ".webm", ".avi", ".mov", ".flv", ".wmv", ".gif",
)
AUDIO_EXTENSIONS = (
    ".mp3", ".m4a", ".aac", ".ogg", ".opus", ".wav", ".flac",
)

# --- Message Prefixes/IDs for Queue ---
MSG_PROGRESS_PREFIX = "Download Progress:"
MSG_LOG_PREFIX = "Download Log:"
MSG_DONE_ID = "DONE"
MSG_DOWNLOAD_ERROR_DETAILS = "DOWNLOAD_ERROR_DETAILS"
MSG_DOWNLOAD_CANCELLED_SIGNAL = "DOWNLOAD_CANCELLED_SIGNAL"

MSG_DOWNLOAD_ITEM_UPDATE = "DOWNLOAD_ITEM_UPDATE"
MSG_DOWNLOAD_ITEM_STATUS = "DOWNLOAD_ITEM_STATUS"
MSG_DOWNLOAD_ITEM_ADDED = "DOWNLOAD_ITEM_ADDED"
MSG_THUMB_LOADED_FOR_HISTORY = "THUMB_LOADED_FOR_HISTORY"

# --- UI Appearance ---
THUMBNAIL_SIZE = (128, 72)

# --- External Tools ---
FFMPEG_TIMEOUT = 30 

# --- Font Options ---
DEFAULT_FONT_FAMILY = "Segoe UI"
FONT_FAMILIES = ["Segoe UI", "Calibri", "Arial", "Verdana", "Helvetica", "Roboto", "System"]
FONT_SIZES = {"Small": 11, "Medium": 13, "Large": 15, "X-Large": 17}
DEFAULT_FONT_SIZE_NAME = "Medium"
# Correctly join path using PROJECT_ROOT defined above
FONT_ROBOTO_REGULAR = os.path.join(PROJECT_ROOT, "assets", "fonts", "Roboto-Regular.ttf")


# --- History/Active Item Sizes ---
HISTORY_ITEM_SIZES = { "Compact": 2, "Normal": 5, "Spacious": 10 }
DEFAULT_HISTORY_ITEM_SIZE_NAME = "Normal"

# --- Player Settings ---
DEFAULT_PLAYER_COMMAND = ""

# --- Environment Setup ---
os.environ['PYTHONUTF8'] = '1'