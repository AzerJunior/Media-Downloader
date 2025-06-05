# constants.py
import os
import sys

# --- Application Version ---
APP_VERSION = "0.3.1"

# --- File/Path Constants ---
SETTINGS_FILE = "settings.json"

# Determine PROJECT_ROOT robustly for both development and PyInstaller bundle
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    PROJECT_ROOT = sys._MEIPASS
else:
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

# --- UI Appearance ---
THUMBNAIL_SIZE = (128, 72)

# --- External Tools ---
FFMPEG_TIMEOUT = 30 # Seconds for ffmpeg/ffprobe subprocess timeout

# --- Font Options ---
DEFAULT_FONT_FAMILY = "Segoe UI"
FONT_FAMILIES = ["Segoe UI", "Calibri", "Arial", "Verdana", "Helvetica", "Roboto", "System"]
FONT_SIZES = {"Small": 11, "Medium": 13, "Large": 15, "X-Large": 17}
DEFAULT_FONT_SIZE_NAME = "Medium"
FONT_ROBOTO_REGULAR = os.path.join(PROJECT_ROOT, "assets", "fonts", "Roboto-Regular.ttf")

# --- NEW: History/Active Item Sizes ---
# Defines the vertical padding for history/active download items
HISTORY_ITEM_SIZES = {
    "Compact": 2, # Smaller padding
    "Normal": 5,  # Default padding
    "Spacious": 10 # More padding
}
DEFAULT_HISTORY_ITEM_SIZE_NAME = "Normal" # Default size name

# --- Player Settings ---
DEFAULT_PLAYER_COMMAND = ""

# --- Environment Setup ---
os.environ['PYTHONUTF8'] = '1'