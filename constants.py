# constants.py
import os
import sys # Import sys for PyInstaller bundle detection

# --- Application Version ---
APP_VERSION = "0.3.1" # Define your application's current version

# --- File/Path Constants ---
SETTINGS_FILE = "settings.json"

# Determine PROJECT_ROOT robustly for both development and PyInstaller bundle
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    # Running in a PyInstaller bundle (single-file or one-directory)
    # _MEIPASS is the path to the temporary directory where the bundle is extracted
    PROJECT_ROOT = sys._MEIPASS
else:
    # Running as a normal Python script (e.g., during development)
    # PROJECT_ROOT is the directory where the current script (constants.py) resides.
    # Assuming constants.py is in the top-level project directory with main.py.
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
MSG_DOWNLOAD_CANCELLED_SIGNAL = "DOWNLOAD_CANCELLED_SIGNAL" # For download cancellation

# --- UI Appearance ---
THUMBNAIL_SIZE = (128, 72)

# --- External Tools ---
FFMPEG_TIMEOUT = 30 # Seconds for ffmpeg/ffprobe subprocess timeout

# --- Font Options ---
DEFAULT_FONT_FAMILY = "Segoe UI"
FONT_FAMILIES = ["Segoe UI", "Calibri", "Arial", "Verdana", "Helvetica", "Roboto", "System"]
FONT_SIZES = {"Small": 11, "Medium": 13, "Large": 15, "X-Large": 17}
DEFAULT_FONT_SIZE_NAME = "Medium"
# Path to the bundled font file, relative to the determined PROJECT_ROOT
FONT_ROBOTO_REGULAR = os.path.join(PROJECT_ROOT, "assets", "fonts", "Roboto-Regular.ttf")


# --- Player Settings ---
DEFAULT_PLAYER_COMMAND = "" # Default empty, implies OS default action

# --- Environment Setup ---
# Ensures Python subprocesses use UTF-8 encoding, crucial for handling diverse filenames/titles.
os.environ['PYTHONUTF8'] = '1'