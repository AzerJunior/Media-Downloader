# main_app_window.py
import customtkinter as ctk
from tkinter import messagebox, END, Menu, font as tkfont
import subprocess
import sys
import re
import pyperclip
import threading
import queue
import os
from PIL import Image, ImageTk, ImageDraw, ImageColor, ImageFont
import json
import shlex
import datetime
import time

# Import constants
from constants import (
    VIDEO_EXTENSIONS, AUDIO_EXTENSIONS, MSG_PROGRESS_PREFIX, MSG_LOG_PREFIX,
    MSG_DONE_ID, THUMBNAIL_SIZE, FFMPEG_TIMEOUT, SETTINGS_FILE,
    DEFAULT_FONT_FAMILY, FONT_FAMILIES, FONT_SIZES, DEFAULT_FONT_SIZE_NAME,
    DEFAULT_PLAYER_COMMAND, MSG_DOWNLOAD_ERROR_DETAILS,
    MSG_DOWNLOAD_CANCELLED_SIGNAL
)
# Import utility functions
from utils import get_ctk_color_from_theme_path
# Import settings manager functions
from settings_manager import load_settings as sm_load_settings, \
                             save_settings as sm_save_settings

# Import UI elements/windows
from ui_elements.settings_window import SettingsWindow
from ui_elements.format_selection_window import FormatSelectionWindow
from ui_elements.tooltip import Tooltip

# Import the new modularized components
from ui_elements.app_logic import AppLogic
from ui_elements.history_manager import HistoryManager, MSG_DURATION_DONE
from ui_elements.ui_manager import UIManager
from ui_elements.format_fetcher import FormatFetcher


class VideoDownloaderApp(ctk.CTk):
    """
    Main application window for the Universal Media Downloader.
    Orchestrates UI, settings, download processes, and history display
    by delegating to specialized manager classes.
    """
    def __init__(self):
        super().__init__()

        # --- 1. Core Application Setup (Initialization Order Critical) ---

        # 1.1 Load application settings (needed by almost everything else)
        self.settings = sm_load_settings()
        ctk.set_appearance_mode(self.settings.get("appearance_mode", "System"))
        ctk.set_default_color_theme(self.settings.get("color_theme", "blue"))

        self.title("Universal Media Downloader")
        self.geometry("750x850")
        self.resizable(True, True)

        # Initialize download directory (depends on settings)
        self.download_dir = self.settings.get(
            "download_directory", os.path.expanduser("~/Downloads")
        )
        if not os.path.exists(self.download_dir):
            try:
                os.makedirs(self.download_dir, exist_ok=True)
            except OSError as e:
                self.download_dir = os.getcwd()
                self.settings["download_directory"] = self.download_dir
                # Use a temporary print/log message here, as self.log_text isn't ready yet
                print(f"ERROR: Creating download directory {self.settings.get('download_directory')}: {e}. Using {self.download_dir}")


        # 1.2 Initialize inter-thread communication queues
        self.download_queue = queue.Queue()
        self.thumbnail_gen_queue = queue.Queue()
        self.duration_queue = queue.Queue()
        self.format_info_queue = queue.Queue()

        # 1.3 Initialize core data structures
        self.download_threads = [] # List to keep track of active download threads (for on_closing)
        self.history_items_with_paths = [] # List of dictionaries holding history data
        self.thumbnail_cache = {} # Dictionary for in-memory thumbnail caching

        # NEW: Cancellation event for stopping downloads
        self.current_download_cancel_event = None # A threading.Event for the active download

        # 1.4 Initialize references to child/Toplevel window instances (managed by main app)
        self.settings_window_instance = None
        self.format_selection_window_instance = None


        # --- 2. Instantiate Manager Classes (Dependency-aware order) ---

        # UIManager initializes fonts and placeholder images which are used by many UI elements.
        self.ui_manager = UIManager(self)
        # Note: self.ui_font, self.ui_font_bold, etc., and placeholder images
        # are set as attributes of `self` (VideoDownloaderApp) by UIManager's init.


        # AppLogic contains core application logic and hotkey management.
        self.app_logic = AppLogic(self)

        # FormatFetcher handles fetching formats, which depends on app_logic and main app queues.
        self.format_fetcher = FormatFetcher(self)


        # --- 3. Build Main Window Layout (UI Elements) ---

        # Configure main window grid layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0) # Top bar section
        self.grid_rowconfigure(1, weight=1) # Log frame section
        self.grid_rowconfigure(2, weight=1) # History frame section


        # Log Frame: Where download progress and other messages are displayed
        self.log_frame = ctk.CTkFrame(self)
        self.log_frame.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")
        self.log_frame.grid_columnconfigure(0, weight=1)
        self.log_frame.grid_rowconfigure(1, weight=1)
        self.log_label = ctk.CTkLabel(
            self.log_frame, text="Download Log:", font=self.ui_font_bold
        )
        self.log_label.grid(row=0, column=0, padx=10, pady=5, sticky="nw")
        self.log_text = ctk.CTkTextbox( # Crucial: This must be created before self.log_message is fully functional
            self.log_frame, wrap="word", state="disabled", height=100, font=self.ui_font
        )
        self.log_text.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")
        # Now that log_text exists, log initial messages (if any were buffered or error occurred before)
        self.log_message(f"Download directory: {self.download_dir}") # Re-log info after log_text is ready
        self.log_message(
            "INFO: For optimal thumbnail generation and duration detection, ensure ffmpeg and ffprobe are installed and in your system PATH."
        )


        # Top Bar Frame: Contains URL input, format selection, download button, and right-side controls
        self.top_bar_frame = ctk.CTkFrame(self)
        self.top_bar_frame.grid(row=0, column=0, padx=0, pady=0, sticky="nsew")
        self.top_bar_frame.grid_columnconfigure(0, weight=1) # URL controls area
        self.top_bar_frame.grid_columnconfigure(1, weight=0) # Right buttons area

        # URL and Download Controls Frame (left side of top bar)
        self.url_controls_frame = ctk.CTkFrame(self.top_bar_frame, fg_color="transparent")
        self.url_controls_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.url_controls_frame.grid_columnconfigure(0, weight=1)

        self.url_text_label = ctk.CTkLabel(
            self.url_controls_frame, text="Media URL:", font=self.ui_font
        )
        self.url_text_label.grid(row=0, column=0, padx=10, pady=5, sticky="w")
        self.url_var = ctk.StringVar()
        self.url_entry = ctk.CTkEntry(
            self.url_controls_frame, textvariable=self.url_var, width=450, font=self.ui_font
        )
        self.url_entry.grid(row=1, column=0, padx=10, pady=5, sticky="ew")

        self.platform_label_var = ctk.StringVar(value="Platform: N/A")
        self.platform_label = ctk.CTkLabel(
            self.url_controls_frame, textvariable=self.platform_label_var, font=self.ui_font
        )
        self.platform_label.grid(row=2, column=0, padx=10, pady=2, sticky="w")

        self.format_selection_frame = ctk.CTkFrame(
            self.url_controls_frame, fg_color="transparent"
        )
        self.format_selection_frame.grid(row=3, column=0, padx=10, pady=(5, 0), sticky="ew")
        self.format_selection_frame.grid_columnconfigure(1, weight=1)

        self.get_formats_button = ctk.CTkButton(
            self.format_selection_frame, text="🎞️ Get Formats",
            command=self.format_fetcher.get_available_formats, # Call via format_fetcher
            font=self.ui_font
        )
        self.get_formats_button.grid(row=0, column=0, padx=(0, 5), pady=0)
        Tooltip(self.get_formats_button, "Fetch available video/audio formats for the URL.")

        self.selected_format_label_var = ctk.StringVar(
            value=f"Format: {self.settings.get('selected_format_code', 'best')}"
        )
        self.selected_format_label = ctk.CTkLabel(
            self.format_selection_frame, textvariable=self.selected_format_label_var,
            font=self.ui_font, anchor="w"
        )
        self.selected_format_label.grid(row=0, column=1, padx=5, pady=0, sticky="ew")

        self.download_type_var = ctk.StringVar(
            value=self.settings.get("default_download_type", "Video")
        )
        self.download_type_label = ctk.CTkLabel(
            self.url_controls_frame, text="Download Type:", font=self.ui_font
        )
        self.download_type_label.grid(row=4, column=0, padx=10, pady=(10, 0), sticky="w")
        self.download_type_selector = ctk.CTkSegmentedButton(
            self.url_controls_frame, values=["Video", "Audio"],
            variable=self.download_type_var, font=self.ui_font
        )
        self.download_type_selector.grid(row=5, column=0, padx=10, pady=5, sticky="ew")

        # Buttons in a sub-frame to manage layout easily
        self.action_buttons_frame = ctk.CTkFrame(self.url_controls_frame, fg_color="transparent")
        self.action_buttons_frame.grid(row=6, column=0, padx=10, pady=10, sticky="ew")
        self.action_buttons_frame.grid_columnconfigure(0, weight=1)
        self.action_buttons_frame.grid_columnconfigure(1, weight=1)

        self.download_button = ctk.CTkButton(
            self.action_buttons_frame, text="⬇️ Download from Clipboard",
            command=self.on_download_button_click, font=self.ui_font_bold
        )
        self.download_button.grid(row=0, column=0, padx=(0,5), sticky="ew")
        Tooltip(self.download_button, "Paste URL from clipboard and start download with current settings.")

        # Cancel Button
        self.cancel_button = ctk.CTkButton(
            self.action_buttons_frame, text="✖️ Cancel Download",
            command=self.on_cancel_download_click, font=self.ui_font_bold,
            fg_color="firebrick", hover_color="darkred", state="disabled" # Initially disabled
        )
        self.cancel_button.grid(row=0, column=1, padx=(5,0), sticky="ew")
        Tooltip(self.cancel_button, "Stop the currently active download.")

        self.progress_bar = ctk.CTkProgressBar(self.url_controls_frame, orientation="horizontal")
        self.progress_bar.set(0)
        self.progress_bar.grid(row=7, column=0, padx=10, pady=(0, 10), sticky="ew")

        # NEW: Label for detailed progress (speed, ETA)
        self.progress_details_label = ctk.CTkLabel(
            self.url_controls_frame, text="Speed: N/A | ETA: N/A",
            font=self.ui_font_small, text_color="gray", anchor="w"
        )
        self.progress_details_label.grid(row=8, column=0, padx=10, pady=(0, 5), sticky="ew")
        # End NEW

        # Right-side buttons (right side of top bar)
        self.right_buttons_frame = ctk.CTkFrame(self.top_bar_frame, fg_color="transparent")
        self.right_buttons_frame.grid(row=0, column=1, padx=10, pady=10, sticky="ne")

        self.open_folder_button = ctk.CTkButton(
            self.right_buttons_frame, text="📂 Open Folder",
            command=self.ui_manager.open_download_folder, width=120, font=self.ui_font
        )
        self.open_folder_button.pack(pady=(5, 5))
        Tooltip(self.open_folder_button, "Open the configured download directory.")

        self.clear_log_button = ctk.CTkButton(
            self.right_buttons_frame, text="🗑️ Clear Log",
            command=self.ui_manager.clear_log, width=120, font=self.ui_font
        )
        self.clear_log_button.pack(pady=5)
        Tooltip(self.clear_log_button, "Clear messages from the download log.")

        self.settings_button = ctk.CTkButton(
            self.right_buttons_frame, text="⚙️ Settings",
            command=self.open_settings_window, width=120, font=self.ui_font
        )
    # ... (rest of the class remains the same) ...
        self.settings_button.pack(pady=5)
        Tooltip(self.settings_button, "Open application settings.")

        self.theme_toggle_button = ctk.CTkButton(
            self.right_buttons_frame, text="Toggle Theme",
            command=self.ui_manager.toggle_theme, width=120, font=self.ui_font
        )
        self.theme_toggle_button.pack(pady=(5, 5))
        Tooltip(self.theme_toggle_button, "Switch between light and dark appearance mode.")
        self.ui_manager.update_theme_toggle_button_text()


        # Download History Frame (Bottom section of main window)
        self.history_outer_frame = ctk.CTkFrame(self)
        self.history_outer_frame.grid(row=2, column=0, padx=10, pady=10, sticky="nsew")
        self.history_outer_frame.grid_columnconfigure(0, weight=1)
        self.history_outer_frame.grid_rowconfigure(1, weight=1)

        self.history_label = ctk.CTkLabel(
            self.history_outer_frame, text="Download History:", font=self.ui_font_bold
        )
        self.history_label.grid(row=0, column=0, padx=10, pady=5, sticky="nw")

        self.history_scrollable_frame = ctk.CTkScrollableFrame(self.history_outer_frame)
        self.history_scrollable_frame.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")

        # HistoryManager depends on `history_scrollable_frame`
        self.history_manager = HistoryManager(self)
        # self.history_context_menu will be set as an attribute by HistoryManager init.


        # --- 4. Final Initialization and Event Binding ---

        # Populate history list from disk (must be called after HistoryManager is ready)
        self.history_manager.load_existing_downloads_to_history()

        # Start the main message queue processing loop
        self.process_download_queue()

        # Bind window close protocol
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Bind main window focus event for auto-paste
        self.bind("<FocusIn>", self.app_logic.on_main_window_focus)

        # Initialize global hotkey listener
        self.app_logic.update_global_hotkey_listener()


    # --- Methods remaining in VideoDownloaderApp (top-level callbacks or glue logic) ---

    def log_message(self, message):
        """
        Inserts a message into the application's log textbox.
        This method is kept directly on `self` because it's a fundamental logging
        mechanism used early in `__init__` before UIManager is fully set up,
        and by various other components.
        """
        # Ensure log_text widget exists before attempting to use it
        if hasattr(self, 'log_text') and self.log_text.winfo_exists():
            self.log_text.configure(state="normal")
            self.log_text.insert(END, message + "\n")
            self.log_text.see(END) # Scroll to the end
            self.log_text.configure(state="disabled")
        else:
            # Fallback for very early messages before log_text is initialized
            print(f"LOG (early): {message}")

    def save_app_settings(self):
        """
        Saves the current application settings to file.
        This remains a direct method on `VideoDownloaderApp` as it's a core
        application function used by various sub-components (e.g., settings window,
        download directory change) to persist state.
        """
        sm_save_settings(self.settings)

    def open_settings_window(self):
        """
        Opens or brings to front the settings window.
        This method remains here as it's the direct command for opening a Toplevel window
        that is associated with the main application.
        """
        # Ensure only one settings window instance is open at a time
        if self.settings_window_instance is None or not self.settings_window_instance.winfo_exists():
            self.settings_window_instance = SettingsWindow(self, app_instance=self)
            self.settings_window_instance.focus() # Give focus to the new window
        else:
            self.settings_window_instance.lift() # Bring existing window to top
            self.settings_window_instance.focus()

    def open_format_selection_window(self, formats_data):
        """
        Opens or brings to front the format selection window.
        This method is called by the `FormatFetcher` when it successfully retrieves
        format data, so it needs to be a public method of `VideoDownloaderApp`.
        """
        # Ensure only one format selection window instance is open at a time
        if self.format_selection_window_instance is None or not self.format_selection_window_instance.winfo_exists():
            self.format_selection_window_instance = FormatSelectionWindow(
                self, self, formats_data # `master` and `app_instance` both reference `self`
            )
            self.format_selection_window_instance.focus()
        else:
            self.format_selection_window_instance.lift()
            self.format_selection_window_instance.focus()

    def on_download_button_click(self):
        """
        Handles the main download button click event.
        This method initiates a download, but delegates the actual download logic
        to `app_logic`. It stays here as it's the direct UI event handler.
        """
        url_from_clipboard = self.app_logic.get_and_validate_clipboard_url()
        if url_from_clipboard:
            # Prevent multiple simultaneous downloads
            if any(t.is_alive() for t in self.download_threads):
                messagebox.showinfo("Download in Progress", "A download is already active. Please wait.", parent=self)
                return

            self.log_message(
                f"\n--- Starting {self.download_type_var.get()} download for {self.platform_label_var.get().replace('Platform: ', '')}: {url_from_clipboard} ---"
            )
            self.log_message(
                f"Format: {self.settings.get('selected_format_code', 'best')}, "
                f"Subtitles: {'Yes' if self.settings.get('download_subtitles', False) else 'No'} "
                f"(Langs: {self.settings.get('subtitle_languages', 'en')}, Embed: {self.settings.get('embed_subtitles', True)})"
            )

            # Update UI to reflect downloading state
            self.download_button.configure(state="disabled") # Disable download button
            self.cancel_button.configure(state="normal")     # Enable cancel button
            self.progress_bar.set(0)
            self.progress_bar.configure(mode="determinate")
            self.progress_details_label.configure(text="Speed: N/A | ETA: N/A") # Clear details on new download

            # Create a new cancel event for this specific download
            self.current_download_cancel_event = threading.Event()

            # Delegate to AppLogic to start the download in a separate thread, passing the cancel event
            self.app_logic.run_download_process_threaded(url_from_clipboard, self.current_download_cancel_event)
        else:
            messagebox.showwarning("No Valid URL", "No valid media URL found in clipboard to download.", parent=self)

    def on_cancel_download_click(self):
        """
        Callback for the 'Cancel Download' button.
        Sets the cancel event to signal the active download thread to stop.
        """
        if self.current_download_cancel_event:
            self.log_message("Cancellation requested. Waiting for download to stop...")
            self.current_download_cancel_event.set() # Signal the event
            # UI will be reset when download_logic sends MSG_DOWNLOAD_CANCELLED_SIGNAL
            self.cancel_button.configure(state="disabled") # Disable cancel button immediately

    def _reset_ui_on_download_completion(self):
        """Helper to reset UI elements after a download attempt (success, failure, or cancellation)."""
        self.download_button.configure(state="normal", text="⬇️ Download from Clipboard")
        self.cancel_button.configure(state="disabled") # Ensure cancel button is disabled
        self.progress_bar.set(0) # Reset progress bar
        self.progress_details_label.configure(text="Speed: N/A | ETA: N/A") # Reset detailed progress label
        self.current_download_cancel_event = None # Clear the event reference

    def process_download_queue(self):
        """
        Continuously processes messages from various queues (download, thumbnail, duration, format fetch).
        This acts as the main event loop for updating the UI based on background task results.
        It must remain on the main `VideoDownloaderApp` instance to directly interact with UI widgets.
        """
        # Process download queue
        try:
            while True:
                message = self.download_queue.get_nowait()
                if isinstance(message, tuple) and message[0] == MSG_DONE_ID:
                    # Expected format: (MSG_DONE_ID, success, hist_basename, hist_path, item_type, thumb_path, sub_indicator, download_date_str)
                    if len(message) >= 7:
                        _, success, hist_basename, hist_path, item_type, thumb_path, sub_indicator = message[:7]
                        download_date_str = message[7] if len(message) > 7 else datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

                        if len(message) == 7:
                            self.log_message("WARN: Received older MSG_DONE_ID format. Using current time as download date.")
                    else:
                        self.log_message(f"ERROR: Received MSG_DONE_ID with unexpected tuple length: {len(message)}. Message: {message}")
                        continue

                    # Update UI elements for completion
                    self._reset_ui_on_download_completion() # Reset button/progress bar
                    self.progress_bar.set(1.0 if success else 0) # Set to 100% or 0%

                    # Update history via HistoryManager
                    self.history_manager.update_history(
                        hist_basename, hist_path, item_type, thumb_path, sub_indicator, download_date_str
                    )

                    # Compose log message summary
                    log_name_for_summary = hist_basename
                    if self.history_items_with_paths:
                        matching_items = [item for item in self.history_items_with_paths if item.get("file_path") == hist_path]
                        if matching_items:
                            log_name_for_summary = matching_items[0].get("display_name_base", hist_basename)

                    log_msg = f"--- {log_name_for_summary} Download "
                    log_msg += "Complete!" if success else "Failed or file not found."
                    if success and thumb_path and os.path.exists(thumb_path):
                        log_msg += f" (Thumbnail/Art: {os.path.basename(thumb_path)})"
                    elif success and not thumb_path:
                        log_msg += " (No thumbnail/art)"
                    self.log_message(log_msg + " ---")

                    # Clean up finished download threads
                    self.download_threads = [t for t in self.download_threads if t.is_alive()]

                elif isinstance(message, tuple) and message[0] == MSG_DOWNLOAD_ERROR_DETAILS: # Handle specific errors
                    error_details = message[1]
                    self.log_message(f"Download Failed: {error_details}") # Log it
                    self._reset_ui_on_download_completion() # Reset UI
                    self.progress_bar.set(0) # Ensure progress bar is reset to 0 for error
                    messagebox.showerror("Download Failed", error_details, parent=self) # Show pop-up to user
                    self.download_threads = [t for t in self.download_threads if t.is_alive()] # Clean up finished download threads

                elif isinstance(message, tuple) and message[0] == MSG_DOWNLOAD_CANCELLED_SIGNAL: # Handle cancellation signal
                    self.log_message("Download was cancelled by the user.")
                    self._reset_ui_on_download_completion() # Reset UI
                    self.progress_bar.set(0) # Reset progress bar
                    messagebox.showinfo("Download Cancelled", "The download operation has been cancelled.", parent=self)
                    self.download_threads = [t for t in self.download_threads if t.is_alive()] # Clean up finished download threads

                elif isinstance(message, str) and message.startswith(MSG_PROGRESS_PREFIX):
                    # Update progress bar and log progress messages
                    full_progress_line = message.replace(MSG_PROGRESS_PREFIX, "").strip()
                    # RegEx to capture percentage, size, speed, and ETA
                    progress_match = re.search(r"([\d\.]+)%\s+of\s+.*?((?:[\d\.]+\s*(?:MiB|KiB|GiB|B|TiB|Bytes))?)\s*(?:at\s+([\d\.]+\s*(?:MiB/s|KiB/s|GiB/s|B/s|Bytes/s))?)?\s*(?:ETA\s+(.*))?", full_progress_line)
                    if progress_match:
                        percentage_str = progress_match.group(1)
                        file_size_str = progress_match.group(2).strip() if progress_match.group(2) else ""
                        speed_str = progress_match.group(3).strip() if progress_match.group(3) else "N/A"
                        eta_str = progress_match.group(4).strip() if progress_match.group(4) else "N/A"

                        try:
                            self.progress_bar.set(float(percentage_str) / 100.0)
                        except ValueError:
                            pass
                        
                        # Update detailed progress label
                        details_text = f"Speed: {speed_str} | ETA: {eta_str}"
                        self.progress_details_label.configure(text=details_text)

                    self.log_message(f"Progress: {full_progress_line}") # Log the full progress line

                elif isinstance(message, str) and message.startswith(MSG_LOG_PREFIX):
                    # Log general messages
                    self.log_message(message.replace(MSG_LOG_PREFIX, "").strip())
                else:
                    self.log_message(f"Unhandled message from download queue: {message}")
        except queue.Empty:
            pass

        # Process thumbnail generation queue
        try:
            while True:
                thumb_message = self.thumbnail_gen_queue.get_nowait()
                if isinstance(thumb_message, tuple) and thumb_message[0] == "THUMB_DONE":
                    _, video_path, new_thumb_path = thumb_message
                    updated = False
                    for item in self.history_items_with_paths:
                        if item.get("file_path") == video_path:
                            item["thumbnail_path"] = new_thumb_path
                            if new_thumb_path in self.thumbnail_cache:
                                del self.thumbnail_cache[new_thumb_path]
                            updated = True
                            break
                    if updated:
                        self.log_message(f"INFO: Updated thumbnail for {os.path.basename(video_path)} in history.")
                        self.history_manager.redraw_history_listbox()
                    else:
                        self.log_message(
                            f"WARN: Received THUMB_DONE for {video_path}, but item not found in history (may have been cleared)."
                        )
                elif isinstance(thumb_message, str) and thumb_message.startswith(MSG_LOG_PREFIX):
                    self.log_message(thumb_message.replace(MSG_LOG_PREFIX, "").strip())
        except queue.Empty:
            pass

        # Process duration calculation queue
        try:
            while True:
                duration_message = self.duration_queue.get_nowait()
                if isinstance(duration_message, tuple) and duration_message[0] == MSG_DURATION_DONE:
                    _, file_path_for_duration, duration_seconds, _ = duration_message
                    updated = False

                    item_to_update = None
                    current_idx = -1
                    for i, hist_item in enumerate(self.history_items_with_paths):
                        if hist_item.get("file_path") == file_path_for_duration:
                            item_to_update = hist_item
                            current_idx = i
                            break

                    if item_to_update:
                        item_to_update["duration"] = duration_seconds
                        item_to_update["formatted_duration"] = self.app_logic._format_duration(duration_seconds)
                        updated = True
                        self.log_message(f"INFO: Updated duration for {os.path.basename(file_path_for_duration)}: {item_to_update['formatted_duration']}.")

                        if 0 <= current_idx < len(self.history_manager.history_item_frames):
                            item_frame_widget = self.history_manager.history_item_frames[current_idx]
                            for child in item_frame_widget.winfo_children():
                                if isinstance(child, ctk.CTkLabel) and child.cget("text").startswith("Duration:"):
                                    child.configure(text=item_to_update["formatted_duration"])
                                    break
                            else:
                                self.history_manager.redraw_history_listbox()
                        else:
                            self.history_manager.redraw_history_listbox()
                    else:
                        self.log_message(
                            f"WARN: Received DURATION_DONE for {file_path_for_duration}, but item not found or mismatched in history."
                        )
                elif isinstance(duration_message, str) and duration_message.startswith(MSG_LOG_PREFIX):
                    self.log_message(duration_message.replace(MSG_LOG_PREFIX, "").strip())
        except queue.Empty:
            pass

        # Process format information queue
        try:
            while True:
                format_message = self.format_info_queue.get_nowait()
                self.get_formats_button.configure(state="normal", text="🎞️ Get Formats")

                if isinstance(format_message, tuple):
                    msg_type, data = format_message
                    if msg_type == "FORMAT_JSON_DATA":
                        self.log_message("Successfully fetched format JSON. Parsing...")
                        parsed_formats = self.format_fetcher._parse_formats_json(data)
                        if parsed_formats:
                            self.log_message(f"Parsed {len(parsed_formats)} formats. Opening selection window.")
                            self.open_format_selection_window(parsed_formats)
                        else:
                            self.log_message("No formats could be parsed from the JSON output.")
                            messagebox.showinfo(
                                "No Formats", "Could not parse any formats from the output. Check logs.", parent=self
                            )
                    elif msg_type == MSG_LOG_PREFIX:
                        self.log_message(data.replace(MSG_LOG_PREFIX, "(FormatFetch) ").strip())
                    elif msg_type == "FORMAT_ERROR":
                        self.log_message(f"Error fetching formats: {data}")
                        messagebox.showerror("Format Fetch Error", str(data), parent=self)
        except queue.Empty:
            pass

        # Schedule the next call to this method
        self.after(100, self.process_download_queue)

    def on_closing(self):
        """
        Handles the application closing event, prompting the user if background
        processes are still active. It also gracefully stops the hotkey listener.
        """
        # Check if any download or background tasks are still running
        active_downloads = any(t.is_alive() for t in self.download_threads)
        active_thumb_gens = any(t.is_alive() for t in self.app_logic.thumbnail_gen_threads)
        active_duration_gens = any(t.is_alive() for t in self.app_logic.duration_gen_threads)
        active_format_fetch = self.format_fetcher.format_fetch_thread and self.format_fetcher.format_fetch_thread.is_alive()

        # Signal active download to stop before closing if there is one
        if self.current_download_cancel_event and not self.current_download_cancel_event.is_set():
            self.current_download_cancel_event.set() # Set the event to signal termination
            self.log_message("Signaling active download to stop before closing.")
            # Give a small moment for the thread to recognize the signal and exit
            time.sleep(0.1) # Brief pause

        # Stop global hotkey listener gracefully
        if self.app_logic.global_hotkey_manager:
            self.app_logic.global_hotkey_manager.stop_listener()
            self.log_message("Global hotkey listener stopped.")

        # Re-check active threads after attempting to signal cancellation
        active_downloads = any(t.is_alive() for t in self.download_threads)
        active_thumb_gens = any(t.is_alive() for t in self.app_logic.thumbnail_gen_threads)
        active_duration_gens = any(t.is_alive() for t in self.app_logic.duration_gen_threads)
        active_format_fetch = self.format_fetcher.format_fetch_thread and self.format_fetcher.format_fetch_thread.is_alive()

        if active_downloads or active_thumb_gens or active_duration_gens or active_format_fetch:
            # Construct message for active processes
            msg = "Warning: The following background processes are still running and might not stop immediately:\n"
            if active_downloads:
                msg += "- Downloads in progress.\n"
            if active_thumb_gens:
                msg += "- Thumbnail generation in progress.\n"
            if active_duration_gens:
                msg += "- Media duration calculation in progress.\n"
            if active_format_fetch:
                msg += "- Format fetching in progress.\n"
            msg += "\nExiting now might terminate them abruptly. Continue anyway?"

            if messagebox.askyesno("Exit Application", msg, parent=self):
                # If user confirms, destroy the window, which will terminate daemon threads
                self.destroy()
            # If user cancels, do nothing, application remains open
        else:
            # No active processes, simply destroy the window
            self.destroy()