# main.py
import sys
import os
import time
import multiprocessing  # 1. IMPORT THE MULTIPROCESSING MODULE
from datetime import datetime

from settings_manager import load_settings as sm_load_settings
from constants import APP_VERSION, PROJECT_ROOT
from ui_elements.main_app_window import VideoDownloaderApp
from dependency_checker import run_dependency_check

RECHECK_INTERVAL_DAYS = 30

if __name__ == "__main__":
    # 2. ADD THIS LINE AS THE VERY FIRST THING IN THE MAIN BLOCK
    # This is essential for PyInstaller to prevent re-launching the app
    # when a subprocess is created from the frozen executable.
    multiprocessing.freeze_support()

    skip_dependency_check_cli = "--skip-deps-check" in sys.argv

    current_settings = sm_load_settings()
    last_check_timestamp = current_settings.get("last_deps_check_timestamp", 0.0)
    app_version_at_last_check = current_settings.get(
        "app_version_at_last_deps_check", "0.0.0"
    )

    force_recheck = False

    if app_version_at_last_check != APP_VERSION:
        print(
            f"App version changed from {app_version_at_last_check} to {APP_VERSION}. Forcing dependency re-check."
        )
        force_recheck = True
    elif time.time() - last_check_timestamp > RECHECK_INTERVAL_DAYS * 24 * 3600:
        print(
            f"Last dependency check was over {RECHECK_INTERVAL_DAYS} days ago. Forcing re-check."
        )
        force_recheck = True

    run_checker = True
    if skip_dependency_check_cli:
        print(
            "Skipping dependency check as '--skip-deps-check' argument was provided."
        )
        run_checker = False
    elif last_check_timestamp > 0 and not force_recheck:
        print(
            f"Skipping dependency check. Last successful check on: {datetime.fromtimestamp(last_check_timestamp).strftime('%Y-%m-%d %H:%M')}"
        )
        run_checker = False

    if run_checker:
        if run_dependency_check(PROJECT_ROOT):
            app = VideoDownloaderApp()
            app.mainloop()
        else:
            print(
                "Dependency check failed or user chose to exit. Application will not start."
            )
            sys.exit(1)
    else:
        app = VideoDownloaderApp()
        app.mainloop()