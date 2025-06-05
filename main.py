# main.py
import sys
import os
import time # NEW: Import time module for timestamp comparison
from datetime import datetime, timedelta # NEW: For setting a re-check interval

# Import settings and constants to read stored state
from settings_manager import load_settings as sm_load_settings
from constants import APP_VERSION, PROJECT_ROOT # PROJECT_ROOT already defined implicitly in constants

# Define the project root directory *once* at the very beginning (redundant if using constants.PROJECT_ROOT)
# PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__)) # Can remove if you import from constants.PROJECT_ROOT

from ui_elements.main_app_window import VideoDownloaderApp
from dependency_checker import run_dependency_check

# Define how often to force a re-check (e.g., every 30 days)
RECHECK_INTERVAL_DAYS = 30

if __name__ == "__main__":
    # Check for a command-line argument to explicitly skip the dependency check (overrides automatic check)
    skip_dependency_check_cli = "--skip-deps-check" in sys.argv

    # Load current settings to check dependency state
    current_settings = sm_load_settings()
    last_check_timestamp = current_settings.get("last_deps_check_timestamp", 0.0)
    app_version_at_last_check = current_settings.get("app_version_at_last_deps_check", "0.0.0")

    force_recheck = False

    # Force recheck if the app version has changed (indicating a potential update with new/changed dependencies)
    if app_version_at_last_check != APP_VERSION:
        print(f"App version changed from {app_version_at_last_check} to {APP_VERSION}. Forcing dependency re-check.")
        force_recheck = True
    # Force recheck if a long time has passed since the last critical check
    elif time.time() - last_check_timestamp > RECHECK_INTERVAL_DAYS * 24 * 3600: # Convert days to seconds
        print(f"Last dependency check was over {RECHECK_INTERVAL_DAYS} days ago. Forcing re-check.")
        force_recheck = True

    # Decide whether to run the dependency checker
    run_checker = True
    if skip_dependency_check_cli:
        print("Skipping dependency check as '--skip-deps-check' argument was provided.")
        run_checker = False
    elif last_check_timestamp > 0 and not force_recheck:
        # If timestamp is positive (meaning a successful check occurred) AND no force recheck
        print(f"Skipping dependency check. Last successful check on: {datetime.fromtimestamp(last_check_timestamp).strftime('%Y-%m-%d %H:%M')}")
        run_checker = False

    if run_checker:
        # Pass constants.PROJECT_ROOT as it is the most reliable way to get the base path
        if run_dependency_check(PROJECT_ROOT): # Pass PROJECT_ROOT to the function
            app = VideoDownloaderApp()
            app.mainloop()
        else:
            print("Dependency check failed or user chose to exit. Application will not start.")
            sys.exit(1)
    else:
        # If checker was skipped, launch the main application directly
        app = VideoDownloaderApp()
        app.mainloop()