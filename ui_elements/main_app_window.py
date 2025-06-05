# ui_elements/main_app_window.py
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
    MSG_DOWNLOAD_CANCELLED_SIGNAL,
    MSG_DOWNLOAD_ITEM_UPDATE, MSG_DOWNLOAD_ITEM_STATUS, MSG_DOWNLOAD_ITEM_ADDED,
    HISTORY_ITEM_SIZES, DEFAULT_HISTORY_ITEM_SIZE_NAME
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
                print(f"ERROR: Creating download directory {self.settings.get('download_directory')}: {e}. Using {self.download_dir}")


        # 1.2 Initialize inter-thread communication queues
        self.download_queue = queue.Queue() # Main queue for all download-related messages
        self.thumbnail_gen_queue = queue.Queue()
        self.duration_queue = queue.Queue()
        self.format_info_queue = queue.Queue()

        # 1.3 Initialize core data structures
        self.download_threads = [] # List to keep track of actual running threads (for on_closing)
        self.history_items_with_paths = [] # List of dictionaries holding history data
        self.thumbnail_cache = {} # Dictionary for in-memory thumbnail caching

        # NEW: Central Download Queue/State for UI
        self.pending_downloads = queue.Queue() # Stores items to be downloaded sequentially
        self.active_downloads = {} # Dict: {download_id: {"frame": CTkFrame, "title_label": ..., "progress_bar": ..., "data": {...}}}
        self.current_active_download_id = None # ID of the item currently being downloaded
        # End NEW

        # Cancellation event for stopping downloads (used for single and playlist)
        self.current_download_cancel_event = None # A threading.Event for the active download

        # 1.4 Initialize references to child/Toplevel window instances (managed by main app)
        self.settings_window_instance = None
        self.format_selection_window_instance = None


        # --- 2. Instantiate Manager Classes (Dependency-aware order) ---

        # UIManager initializes fonts and placeholder images which are used by many UI elements.
        self.ui_manager = UIManager(self)


        # AppLogic contains core application logic and hotkey management.
        self.app_logic = AppLogic(self)

        # FormatFetcher handles fetching formats, which depends on app_logic and main app queues.
        self.format_fetcher = FormatFetcher(self)


        # --- 3. Build Main Window Layout (UI Elements) ---

        # Configure main window grid layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0) # Header buttons row (fixed height)
        self.grid_rowconfigure(1, weight=0) # Top bar section (URL controls, fixed height)
        self.grid_rowconfigure(2, weight=2) # Active Downloads Frame (e.g., twice the height of log frame by default)
        self.grid_rowconfigure(3, weight=1) # Log frame section (smaller, or dynamically sized)
        self.grid_rowconfigure(4, weight=3) # History frame section (larger, should take most of remaining space)


        # Header Buttons Frame (Open Folder, Clear Log, Settings, Theme Toggle)
        self.header_buttons_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_buttons_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

        # Buttons packed in reverse order for visual left-to-right alignment when side="right"
        self.theme_toggle_button = ctk.CTkButton(
            self.header_buttons_frame, text="Toggle Theme",
            command=self.ui_manager.toggle_theme, font=self.ui_font
        )
        self.theme_toggle_button.pack(side="right", padx=(5, 0), pady=0)
        Tooltip(self.theme_toggle_button, "Switch between light and dark appearance mode.")
        self.ui_manager.update_theme_toggle_button_text()

        self.settings_button = ctk.CTkButton(
            self.header_buttons_frame, text="⚙️ Settings",
            command=self.open_settings_window, font=self.ui_font
        )
        self.settings_button.pack(side="right", padx=(5, 0), pady=0)
        Tooltip(self.settings_button, "Open application settings.")

        self.clear_log_button = ctk.CTkButton(
            self.header_buttons_frame, text="🗑️ Clear Log",
            command=self.ui_manager.clear_log, font=self.ui_font
        )
        self.clear_log_button.pack(side="right", padx=(5, 0), pady=0)
        Tooltip(self.clear_log_button, "Clear messages from the download log.")

        self.open_folder_button = ctk.CTkButton(
            self.header_buttons_frame, text="📂 Open Folder",
            command=self.ui_manager.open_download_folder, font=self.ui_font
        )
        self.open_folder_button.pack(side="right", padx=(5, 0), pady=0)
        Tooltip(self.open_folder_button, "Open the configured download directory.")


        # Log Frame: Where download progress and other messages are displayed
        self.log_frame = ctk.CTkFrame(self)
        self.log_frame.grid(row=3, column=0, padx=10, pady=10, sticky="nsew") # Adjusted row to 3
        self.log_frame.grid_columnconfigure(0, weight=1)
        self.log_frame.grid_rowconfigure(1, weight=1)
        self.log_label = ctk.CTkLabel(
            self.log_frame, text="Download Log:", font=self.ui_font_bold
        )
        self.log_label.grid(row=0, column=0, padx=10, pady=5, sticky="nw")
        self.log_text = ctk.CTkTextbox(
            self.log_frame, wrap="word", state="disabled", height=100, font=self.ui_font
        )
        self.log_text.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")


        # Top Bar Frame: Contains URL input, format selection, download button, and right-side controls
        self.top_bar_frame = ctk.CTkFrame(self)
        self.top_bar_frame.grid(row=1, column=0, padx=0, pady=0, sticky="nsew") # Row 1
        self.top_bar_frame.grid_columnconfigure(0, weight=1)

        # URL and Download Controls Frame (now fills top_bar_frame)
        self.url_controls_frame = ctk.CTkFrame(self.top_bar_frame, fg_color="transparent")
        self.url_controls_frame.pack(expand=True, fill="both")
        self.url_controls_frame.grid_columnconfigure(0, weight=1)

        # Single/Playlist Toggle
        self.url_mode_frame = ctk.CTkFrame(self.url_controls_frame, fg_color="transparent")
        self.url_mode_frame.grid(row=0, column=0, padx=10, pady=5, sticky="ew")
        self.url_mode_frame.grid_columnconfigure(0, weight=1)
        self.url_mode_frame.grid_columnconfigure(1, weight=0)

        self.url_text_label = ctk.CTkLabel(
            self.url_mode_frame, text="Media URL:", font=self.ui_font
        )
        self.url_text_label.grid(row=0, column=0, padx=(0,5), pady=0, sticky="w")

        self.url_input_type_var = ctk.StringVar(value="Single URL")
        self.url_type_toggle = ctk.CTkSegmentedButton(
            self.url_mode_frame, values=["Single URL", "Playlist URL"],
            variable=self.url_input_type_var, command=self.on_url_type_toggle,
            font=self.ui_font_small
        )
        self.url_type_toggle.grid(row=0, column=1, padx=(5,0), pady=0, sticky="e")

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
            command=self.format_fetcher.get_available_formats,
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

        self.cancel_button = ctk.CTkButton(
            self.action_buttons_frame, text="✖️ Cancel Download",
            command=self.on_cancel_download_click, font=self.ui_font_bold,
            fg_color="firebrick", hover_color="darkred", state="disabled"
        )
        self.cancel_button.grid(row=0, column=1, padx=(5,0), sticky="ew")
        Tooltip(self.cancel_button, "Stop the currently active download.")


        # Overall Progress Bar (at the bottom of URL controls frame)
        self.progress_bar = ctk.CTkProgressBar(self.url_controls_frame, orientation="horizontal")
        self.progress_bar.set(0)
        self.progress_bar.grid(row=7, column=0, padx=10, pady=(0, 10), sticky="ew")

        # Overall Progress Details Label (at the bottom of URL controls frame)
        self.progress_details_label = ctk.CTkLabel(
            self.url_controls_frame, text="Current Task: N/A | Overall Progress: N/A",
            font=self.ui_font_small, text_color="gray", anchor="w"
        )
        self.progress_details_label.grid(row=8, column=0, padx=10, pady=(0, 5), sticky="ew")


        # Active Downloads Section
        self.active_downloads_outer_frame = ctk.CTkFrame(self)
        self.active_downloads_outer_frame.grid(row=2, column=0, padx=10, pady=10, sticky="nsew") # Row 2
        self.active_downloads_outer_frame.grid_columnconfigure(0, weight=1)
        self.active_downloads_outer_frame.grid_rowconfigure(1, weight=1) # Scrollable frame for items

        self.active_downloads_label = ctk.CTkLabel(
            self.active_downloads_outer_frame, text="Active Downloads:", font=self.ui_font_bold
        )
        self.active_downloads_label.grid(row=0, column=0, padx=10, pady=5, sticky="nw")

        self.active_downloads_scrollable_frame = ctk.CTkScrollableFrame(self.active_downloads_outer_frame)
        self.active_downloads_scrollable_frame.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")


        # Download History Frame (Bottom section of main window)
        self.history_outer_frame = ctk.CTkFrame(self)
        self.history_outer_frame.grid(row=4, column=0, padx=10, pady=10, sticky="nsew") # Row 4
        self.history_outer_frame.grid_columnconfigure(0, weight=1)
        self.history_outer_frame.grid_rowconfigure(1, weight=1)

        self.history_label = ctk.CTkLabel(
            self.history_outer_frame, text="Download History:", font=self.ui_font_bold
        )
        self.history_label.grid(row=0, column=0, padx=10, pady=5, sticky="nw")

        self.history_scrollable_frame = ctk.CTkScrollableFrame(self.history_outer_frame)
        self.history_scrollable_frame.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")

        self.history_manager = HistoryManager(self)


        # --- 4. Final Initialization and Event Binding ---

        self.history_manager.load_existing_downloads_to_history()
        self.process_download_queue()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.bind("<FocusIn>", self.app_logic.on_main_window_focus)
        self.app_logic.update_global_hotkey_listener()


    # --- Methods remaining in VideoDownloaderApp (top-level callbacks or glue logic) ---

    def log_message(self, message):
        if hasattr(self, 'log_text') and self.log_text.winfo_exists():
            self.log_text.configure(state="normal")
            self.log_text.insert(END, message + "\n")
            self.log_text.see(END)
            self.log_text.configure(state="disabled")
        else:
            print(f"LOG (early): {message}")

    def save_app_settings(self):
        sm_save_settings(self.settings)

    def open_settings_window(self):
        if self.settings_window_instance is None or not self.settings_window_instance.winfo_exists():
            self.settings_window_instance = SettingsWindow(self, app_instance=self)
            self.settings_window_instance.focus()
        else:
            self.settings_window_instance.lift()
            self.settings_window_instance.focus()

    def open_format_selection_window(self, formats_data):
        if self.format_selection_window_instance is None or not self.format_selection_window_instance.winfo_exists():
            self.format_selection_window_instance = FormatSelectionWindow(
                self, self, formats_data
            )
            self.format_selection_window_instance.focus()
        else:
            self.format_selection_window_instance.lift()
            self.format_selection_window_instance.focus()

    # Callback for the URL Type Toggle
    def on_url_type_toggle(self, value):
        if value == "Single URL":
            self.get_formats_button.configure(state="normal")
            self.download_button.configure(text="⬇️ Download from Clipboard")
            self.log_message("Switched to Single URL mode.")
        elif value == "Playlist URL":
            self.get_formats_button.configure(state="disabled")
            self.selected_format_label_var.set("Format: Best (Playlist)")
            self.download_button.configure(text="⬇️ Download Playlist/Batch")
            self.log_message("Switched to Playlist URL mode.")
        self.url_var.set("")
        self.platform_label_var.set("Platform: N/A")

    def on_download_button_click(self):
        url_from_clipboard = self.app_logic.get_and_validate_clipboard_url()
        if not url_from_clipboard:
            messagebox.showwarning("No Valid URL", "No valid media URL found in clipboard to download.", parent=self)
            return

        if self.current_active_download_id or not self.pending_downloads.empty():
            messagebox.showinfo("Download Queued", "Downloads are already queued or active. Please wait for current tasks to complete.", parent=self)
            return


        download_mode = self.url_input_type_var.get()
        if download_mode == "Single URL":
            self.log_message(f"\n--- Adding Single {self.download_type_var.get()} download to queue: {url_from_clipboard} ---")

            # Reset UI for a new single download (full reset first)
            self._reset_ui_on_download_completion(is_full_reset=True)
            self.download_button.configure(state="disabled") # Re-disable download button
            self.cancel_button.configure(state="normal") # Enable cancel button

            # Add to pending_downloads queue
            self.pending_downloads.put({
                "url": url_from_clipboard,
                "download_type": self.download_type_var.get(),
                "selected_format_code": self.settings.get("selected_format_code", "best"),
                "download_subtitles": self.settings.get("download_subtitles", False),
                "subtitle_languages": self.settings.get("subtitle_languages", "en"),
                "embed_subtitles": self.settings.get("embed_subtitles", True),
                "is_playlist_item": False,
                "title": self.url_var.get(), # Use raw URL as temporary title
                "cancel_event": threading.Event() # Create a NEW cancel event for this single download
            })
            self.current_download_cancel_event = self.pending_downloads.queue[0]["cancel_event"] # Ref to this item's event
            self.start_next_download_if_available() # Attempt to start immediately

        elif download_mode == "Playlist URL":
            self.log_message(f"\n--- Initiating Playlist/Batch download from: {url_from_clipboard} ---")

            # Reset UI for a new playlist download (full reset first)
            self._reset_ui_on_download_completion(is_full_reset=True)
            self.download_button.configure(state="disabled")
            self.cancel_button.configure(state="normal")

            self.app_logic.current_playlist_download_info = {
                "total_items": 0, "completed_items": 0, "failed_items": 0, "skipped_items": 0, "cancelled": False
            }
            self.progress_details_label.configure(text="Fetching playlist items...")

            # The current_download_cancel_event controls the entire playlist queuing/downloading
            self.current_download_cancel_event = threading.Event()

            # Delegate fetching and queuing to app_logic
            self.app_logic.run_playlist_download_threaded(url_from_clipboard, self.current_download_cancel_event)

    def start_next_download_if_available(self):
        """Checks if a download slot is free and starts the next pending download."""
        if not self.current_active_download_id and not self.pending_downloads.empty():
            download_data = self.pending_downloads.get()
            self.log_message(f"Starting next queued download: {download_data.get('url')[:50]}...")

            # Get the cancel_event that came with this download_data (either a fresh one or playlist's shared one)
            item_cancel_event = download_data["cancel_event"]

            # This initiates the actual download process (download_logic.run_download_process)
            # which will generate its own download_id and send MSG_DOWNLOAD_ITEM_ADDED immediately.
            self.app_logic.run_download_process_threaded_actual(
                download_data["url"],
                download_data["download_type"],
                download_data["selected_format_code"],
                download_data["download_subtitles"],
                download_data["subtitle_languages"],
                download_data["embed_subtitles"],
                item_cancel_event, # Pass this item's specific cancel_event
                is_playlist_item=download_data.get("is_playlist_item", False)
            )
            # current_active_download_id will be set by process_download_queue when it receives MSG_DOWNLOAD_ITEM_ADDED
            # from `run_download_process_threaded_actual`. This creates a tight loop.

        else: # No active download, and no pending items
            # If playlist is active and not yet cancelled, its current_download_cancel_event is still in use by app_logic
            # If a playlist finished (or was cancelled), _reset_ui_on_download_completion(True) already called.
            # So, if we reach here, it implies no playlist activity and no single downloads queued.
            # Ensure full UI reset if everything is truly done.
            if self.current_active_download_id is None and self.pending_downloads.empty() and \
               self.app_logic.current_playlist_download_info["total_items"] == 0: # Check if overall playlist finished
                self._reset_ui_on_download_completion(is_full_reset=True)


    def on_cancel_download_click(self):
        if self.current_download_cancel_event:
            self.log_message("Cancellation requested. Signaling all active/queued downloads to stop...")
            self.current_download_cancel_event.set()
            self.cancel_button.configure(state="disabled")
            # The UI will be reset when the MSG_DOWNLOAD_ITEM_STATUS (cancelled) for the active item comes through
            # and when the playlist worker detects its cancellation.

    def _reset_ui_on_download_completion(self, is_full_reset=True):
        if is_full_reset:
            if self.url_input_type_var.get() == "Single URL":
                 self.download_button.configure(text="⬇️ Download from Clipboard")
            else:
                 self.download_button.configure(text="⬇️ Download Playlist/Batch")

            self.cancel_button.configure(state="disabled")
            self.progress_bar.set(0)
            self.progress_details_label.configure(text="Current Task: N/A | Overall Progress: N/A")
            self.current_active_download_id = None
            self.current_download_cancel_event = None # Clear event reference

            # Clear the pending queue on full reset (e.g., if cancelled mid-playlist)
            while not self.pending_downloads.empty():
                try: self.pending_downloads.get_nowait()
                except queue.Empty: pass
            
            # Reset all active download item UIs
            for download_id in list(self.active_downloads.keys()): # Iterate a copy of keys as dict changes during loop
                self._remove_active_download_item_ui(download_id)

            # Reset app_logic's playlist info
            self.app_logic.current_playlist_download_info = {
                "total_items": 0, "completed_items": 0, "failed_items": 0, "skipped_items": 0, "cancelled": False
            }
        else: # Partial reset, for individual playlist items completing
            self.progress_bar.set(0) # Reset main bar for next item's individual progress
            # The progress_details_label remains showing overall playlist progress by design
            self.current_active_download_id = None


    def _create_active_download_item_ui(self, download_id, item_data):
        current_item_ipady = HISTORY_ITEM_SIZES.get(
            self.settings.get("history_item_size_name", DEFAULT_HISTORY_ITEM_SIZE_NAME),
            HISTORY_ITEM_SIZES[DEFAULT_HISTORY_ITEM_SIZE_NAME]
        )

        item_frame = ctk.CTkFrame(self.active_downloads_scrollable_frame, corner_radius=5)
        item_frame.pack(fill="x", pady=2, padx=5, ipady=current_item_ipady)

        title_text = item_data.get("title", item_data.get("url", "Unknown Title"))
        if item_data.get("is_playlist_item") and item_data.get("playlist_item_index"):
            title_text = f"#{item_data['playlist_item_index']}: {title_text}"

        title_label = ctk.CTkLabel(item_frame, text=title_text, font=self.ui_font, anchor="w", wraplength=450)
        title_label.pack(fill="x", padx=5, pady=(5,0))

        progress_bar = ctk.CTkProgressBar(item_frame, orientation="horizontal")
        progress_bar.set(0)
        progress_bar.pack(fill="x", padx=5, pady=(2,0))

        details_label = ctk.CTkLabel(item_frame, text="Progress: 0% | Speed: N/A | ETA: N/A", font=self.ui_font_small, text_color="gray", anchor="w")
        details_label.pack(fill="x", padx=5, pady=(0,5))

        status_text = item_data.get("status", "Queued")
        status_label = ctk.CTkLabel(item_frame, text=f"Status: {status_text.capitalize()}", font=self.ui_font_small, text_color="gray", anchor="w")
        status_label.pack(fill="x", padx=5, pady=(0,5))

        self.active_downloads[download_id] = {
            "frame": item_frame,
            "title_label": title_label,
            "progress_bar": progress_bar,
            "details_label": details_label,
            "status_label": status_label,
            "data": item_data # Store original data
        }
        return item_frame

    def _update_active_download_item_ui(self, download_id, update_data):
        if download_id not in self.active_downloads:
            self.log_message(f"WARN: Attempted to update non-existent download item UI for ID: {download_id[:8]}")
            return

        item_ui = self.active_downloads[download_id]
        item_data = item_ui["data"]
        item_data.update(update_data)

        if "title" in update_data:
            item_ui["title_label"].configure(text=item_data["title"])
        if "progress_percent" in update_data:
            item_ui["progress_bar"].set(update_data["progress_percent"] / 100.0)
            item_ui["details_label"].configure(
                text=f"Progress: {item_data['progress_percent']:.1f}% | Speed: {item_data.get('speed','N/A')} | ETA: {item_data.get('eta','N/A')}"
            )
        if "speed" in update_data or "eta" in update_data:
             # This will be updated by progress_percent if it comes with it.
             # If separately sent speed/eta, it will update only that part.
             item_ui["details_label"].configure(
                 text=f"Progress: {item_data.get('progress_percent', 0):.1f}% | Speed: {item_data.get('speed','N/A')} | ETA: {item_data.get('eta','N/A')}"
             )
        if "status" in update_data:
            status = update_data["status"]
            message = update_data.get("message", status)
            color = "gray"
            if status == "completed": color = "green"
            elif status == "failed": color = "red"
            elif status == "cancelled": color = "orange"
            elif status == "downloading" or status == "starting": color = "blue"
            elif status == "queued": color = "gray"

            item_ui["status_label"].configure(text=f"Status: {status.capitalize()} - {message}", text_color=color)
            item_ui["progress_bar"].set(0 if status in ["failed", "cancelled"] else (1 if status == "completed" else item_ui["progress_bar"].get()))


    def _remove_active_download_item_ui(self, download_id):
        if download_id in self.active_downloads:
            item_ui = self.active_downloads.pop(download_id)
            item_ui["frame"].destroy()


    def process_download_queue(self):
        try:
            while True:
                message = self.download_queue.get_nowait()
                msg_type = message[0]
                payload = message[1:]

                if msg_type == MSG_DOWNLOAD_ITEM_ADDED:
                    # Payload: (download_id, {item_data})
                    download_id, item_data = payload
                    # Create UI for this item (it's either newly started or just queued from playlist worker)
                    self._create_active_download_item_ui(download_id, item_data)
                    self.current_active_download_id = download_id # Mark this as the currently executing item
                    self.active_downloads[download_id]["status_label"].configure(text="Status: Downloading...", text_color="blue")
                    self.log_message(f"Download item '{item_data.get('title', item_data.get('url'))[:50]}' (ID: {download_id[:8]}) added to active downloads and started.")


                elif msg_type == MSG_DOWNLOAD_ITEM_UPDATE:
                    download_id, update_data = payload
                    self._update_active_download_item_ui(download_id, update_data)

                    # Update overall progress bar & details ONLY IF this is the current active download
                    if download_id == self.current_active_download_id:
                        percent = update_data.get("progress_percent", self.active_downloads[download_id]["progress_bar"].get() * 100)

                        if self.app_logic.current_playlist_download_info["total_items"] > 0:
                            # Playlist overall progress
                            total = self.app_logic.current_playlist_download_info["total_items"]
                            completed = self.app_logic.current_playlist_download_info["completed_items"]
                            # Current item's contribution to overall progress
                            current_item_portion = percent / 100.0 / total if total > 0 else 0
                            overall_percentage = (completed / total if total > 0 else 0) + current_item_portion
                            self.progress_bar.set(overall_percentage) # Overall progress

                            speed_str = update_data.get("speed", "N/A")
                            eta_str = update_data.get("eta", "N/A")
                            self.progress_details_label.configure(
                                text=f"Item {completed+1}/{total} | Speed: {speed_str} | ETA: {eta_str}"
                            )
                        else: # Single download progress for main bar and details
                            self.progress_bar.set(percent / 100.0) # Main bar shows current item progress
                            speed_str = update_data.get("speed", "N/A")
                            eta_str = update_data.get("eta", "N/A")
                            self.progress_details_label.configure(
                                text=f"Speed: {speed_str} | ETA: {eta_str}"
                            )

                elif msg_type == MSG_DOWNLOAD_ITEM_STATUS:
                    download_id, status_payload = payload
                    self._update_active_download_item_ui(download_id, status_payload) # Update final status in UI

                    is_playlist_item = status_payload.get("is_playlist_item", False)
                    if is_playlist_item:
                        if status_payload["status"] == "completed":
                            self.app_logic.current_playlist_download_info["completed_items"] += 1
                        elif status_payload["status"] == "failed":
                            self.app_logic.current_playlist_download_info["failed_items"] += 1
                        elif status_payload["status"] == "cancelled":
                            self.app_logic.current_playlist_download_info["cancelled"] = True

                        # Add item to history if it completed or failed
                        if status_payload["status"] in ["completed", "failed"]:
                            actual_display_name_base = status_payload.get("title", status_payload.get("file_path", status_payload.get("url", "Unknown Item")).split(os.sep)[-1])
                            if status_payload["status"] == "failed":
                                 actual_display_name_base = f"[Failed] {actual_display_name_base}"

                            self.history_manager.update_history(
                                actual_display_name_base,
                                status_payload["file_path"],
                                status_payload["item_type_for_history"],
                                status_payload["thumbnail_path"],
                                status_payload["sub_indicator"],
                                status_payload["download_date_str"]
                            )

                        # Check if overall playlist is complete/cancelled
                        total_items = self.app_logic.current_playlist_download_info["total_items"]
                        processed_items = self.app_logic.current_playlist_download_info["completed_items"] + \
                                          self.app_logic.current_playlist_download_info["failed_items"] + \
                                          self.app_logic.current_playlist_download_info["skipped_items"]

                        if total_items > 0 and (processed_items == total_items or self.app_logic.current_playlist_download_info["cancelled"]):
                            # Playlist finished or cancelled
                            self.log_message(f"Playlist sequence finished. Total: {total_items}, Completed: {self.app_logic.current_playlist_download_info['completed_items']}, Failed: {self.app_logic.current_playlist_download_info['failed_items']}, Cancelled: {self.app_logic.current_playlist_download_info['cancelled']}.")

                            # Final overall progress bar update
                            self.progress_bar.set(1.0 if not self.app_logic.current_playlist_download_info["cancelled"] else 0)

                            if self.app_logic.current_playlist_download_info["cancelled"]:
                                messagebox.showinfo("Playlist Download Cancelled", "The playlist download has been cancelled.", parent=self)
                            else:
                                messagebox.showinfo(
                                    "Playlist Download Complete",
                                    f"Playlist download finished! {self.app_logic.current_playlist_download_info['completed_items']}/{total_items} items completed, {self.app_logic.current_playlist_download_info['failed_items']} failed.",
                                    parent=self
                                )
                            self._reset_ui_on_download_completion(is_full_reset=True) # Full UI reset
                            # All active item UIs are removed by _reset_ui_on_download_completion(True)

                        else: # Playlist item completed, but playlist still active (not all items processed yet)
                            # Remove this item's UI, then start next queued item
                            self._remove_active_download_item_ui(download_id)
                            self.current_active_download_id = None # Clear active ID for next item
                            self.start_next_download_if_available() # Attempt to start next queued item


                    else: # This is a standalone single download (not part of a playlist)
                        self._reset_ui_on_download_completion(is_full_reset=True) # Full reset for single download
                        self._remove_active_download_item_ui(download_id) # Remove this item's UI
                        # Display message box based on status
                        if status_payload["status"] == "completed":
                            messagebox.showinfo("Download Complete", status_payload["message"], parent=self)
                            self.progress_bar.set(1.0)
                        elif status_payload["status"] == "failed":
                            messagebox.showerror("Download Failed", status_payload["message"], parent=self)
                            self.progress_bar.set(0)
                        elif status_payload["status"] == "cancelled":
                            messagebox.showinfo("Download Cancelled", status_payload["message"], parent=self)
                            self.progress_bar.set(0)

                        # Add to history if status is completed or failed
                        if status_payload["status"] in ["completed", "failed"]:
                            actual_display_name_base = status_payload.get("title", status_payload.get("file_path", status_payload.get("url", "Unknown Item")).split(os.sep)[-1])
                            if status_payload["status"] == "failed":
                                 actual_display_name_base = f"[Failed] {actual_display_name_base}"
                            self.history_manager.update_history(
                                actual_display_name_base,
                                status_payload["file_path"],
                                status_payload["item_type_for_history"],
                                status_payload["thumbnail_path"],
                                status_payload["sub_indicator"],
                                status_payload["download_date_str"]
                            )
                        self.download_threads = [t for t in self.download_threads if t.is_alive()]

                elif isinstance(message, str) and message.startswith(MSG_LOG_PREFIX):
                    self.log_message(message.replace(MSG_LOG_PREFIX, "").strip())
                else:
                    self.log_message(f"Unhandled message from download queue: {message}")
        except queue.Empty:
            pass

        # Process thumbnail generation queue (unchanged)
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
                            f"WARN: Received THUMB_DONE for {video_path}, but item not found in history (may be old)."
                        )
                elif isinstance(thumb_message, str) and thumb_message.startswith(MSG_LOG_PREFIX):
                    self.log_message(thumb_message.replace(MSG_LOG_PREFIX, "").strip())
        except queue.Empty:
            pass

        # Process duration calculation queue (unchanged)
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
                        #self.log_message(f"INFO: Updated duration for {os.path.basename(file_path_for_duration)}: {item_to_update['formatted_duration']}.")

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

        # Process format information queue (unchanged)
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
        active_downloads_from_thread_list = any(t.is_alive() for t in self.download_threads)
        active_thumb_gens = any(t.is_alive() for t in self.app_logic.thumbnail_gen_threads)
        active_duration_gens = any(t.is_alive() for t in self.app_logic.duration_gen_threads)
        active_format_fetch = self.format_fetcher.format_fetch_thread and self.format_fetcher.format_fetch_thread.is_alive()

        active_downloads_from_queue = not self.pending_downloads.empty() or self.current_active_download_id is not None

        if self.current_download_cancel_event and not self.current_download_cancel_event.is_set():
            self.current_download_cancel_event.set()
            self.log_message("Signaling active download to stop before closing.")
            time.sleep(0.1)

        if self.app_logic.global_hotkey_manager:
            self.app_logic.global_hotkey_manager.stop_listener()
            self.log_message("Global hotkey listener stopped.")

        active_downloads_from_thread_list = any(t.is_alive() for t in self.download_threads)
        active_downloads_from_queue = not self.pending_downloads.empty() or self.current_active_download_id is not None

        if active_downloads_from_thread_list or active_thumb_gens or active_duration_gens or active_format_fetch or active_downloads_from_queue:
            msg = "Warning: The following background processes or queued downloads are still active:\n"
            if active_downloads_from_thread_list or active_downloads_from_queue:
                msg += "- Downloads in progress or queued.\n"
            if active_thumb_gens:
                msg += "- Thumbnail generation in progress.\n"
            if active_duration_gens:
                msg += "- Media duration calculation in progress.\n"
            if active_format_fetch:
                msg += "- Format fetching in progress.\n"
            msg += "\nExiting now might terminate them abruptly. Continue anyway?"

            if messagebox.askyesno("Exit Application", msg, parent=self):
                self.destroy()
        else:
            self.destroy()