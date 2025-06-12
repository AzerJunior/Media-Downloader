# ui_elements/main_app_window.py
import customtkinter as ctk
from tkinter import messagebox, END, Menu
import threading
import queue
import os
from collections import deque

# Import constants
from constants import (
    MSG_LOG_PREFIX,
    THUMBNAIL_SIZE,
    SETTINGS_FILE,
    MSG_DOWNLOAD_ITEM_UPDATE,
    MSG_DOWNLOAD_ITEM_STATUS,
    MSG_DOWNLOAD_ITEM_ADDED,
    HISTORY_ITEM_SIZES,
    DEFAULT_HISTORY_ITEM_SIZE_NAME,
    MSG_THUMB_LOADED_FOR_HISTORY,
)
# Import utility functions
from utils import get_ctk_color_from_theme_path
# Import settings manager functions
from settings_manager import (
    load_settings as sm_load_settings,
    save_settings as sm_save_settings,
)

# Import UI elements/windows
from ui_elements.settings_window import SettingsWindow
from ui_elements.format_selection_window import FormatSelectionWindow
from ui_elements.tooltip import Tooltip

# Import the new modularized components
from ui_elements.app_logic import AppLogic, MSG_DURATION_DONE
from ui_elements.history_manager import HistoryManager
from ui_elements.ui_manager import UIManager
from ui_elements.format_fetcher import FormatFetcher


class RateLimitedLogger:
    def __init__(self, ctk_textbox, interval_ms=100, max_lines=1000):
        self.textbox = ctk_textbox
        self.log_buffer = deque()
        self.interval_ms = interval_ms
        self.max_lines = max_lines
        self._after_id = None
        self._flush_lock = threading.Lock()

    def log(self, message):
        self.log_buffer.append(message)
        self._schedule_flush()

    def _schedule_flush(self):
        if self._after_id is None and self.textbox.winfo_exists():
            self._after_id = self.textbox.after(
                self.interval_ms, self._flush_log
            )

    def _flush_log(self):
        with self._flush_lock:
            self._after_id = None
            if not self.log_buffer or not self.textbox.winfo_exists():
                self.log_buffer.clear()
                return

            try:
                y_coords = self.textbox.yview()
                is_at_bottom = y_coords[1] > 0.95
            except Exception:
                is_at_bottom = True

            lines_to_flush = []
            while self.log_buffer:
                lines_to_flush.append(self.log_buffer.popleft())

            if lines_to_flush:
                try:
                    self.textbox.configure(state="normal")
                    self.textbox.insert(END, "\n".join(lines_to_flush) + "\n")

                    current_lines = int(
                        self.textbox.index("end-1c").split(".")[0]
                    )
                    if current_lines > self.max_lines:
                        delete_to_line = current_lines - self.max_lines + 1
                        self.textbox.delete("1.0", f"{delete_to_line}.0")

                    if is_at_bottom:
                        self.textbox.see(END)
                    self.textbox.configure(state="disabled")
                except Exception as e:
                    print(f"ERROR: Failed to update CTkTextbox: {e}")
                    self.log_buffer.clear()

    def cancel_flush(self):
        if self._after_id:
            with self._flush_lock:
                try:
                    if self.textbox.winfo_exists():
                        self.textbox.after_cancel(self._after_id)
                except Exception:
                    pass
                self._after_id = None


class VideoDownloaderApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self._is_closing = False

        self.settings = sm_load_settings()
        ctk.set_appearance_mode(self.settings.get("appearance_mode", "System"))
        ctk.set_default_color_theme(self.settings.get("color_theme", "blue"))

        self.title("Universal Media Downloader")
        self.geometry("750x850")
        self.resizable(True, True)

        self.download_dir = self.settings.get(
            "download_directory", os.path.expanduser("~/Downloads")
        )
        if not os.path.exists(self.download_dir):
            try:
                os.makedirs(self.download_dir, exist_ok=True)
            except OSError as e:
                self.download_dir = os.getcwd()
                print(
                    f"ERROR: Creating download directory failed: {e}. Using {self.download_dir}"
                )

        self.download_queue = queue.Queue()
        self.thumbnail_gen_queue = queue.Queue()
        self.duration_queue = queue.Queue()
        self.format_info_queue = queue.Queue()

        self.download_threads = []
        self.history_items_with_paths = []
        self.thumbnail_cache = {}

        self.pending_downloads = queue.Queue()
        self.active_downloads = {}
        self.current_active_download_id = None
        self.current_download_cancel_event = None

        self.settings_window_instance = None
        self.format_selection_window_instance = None
        self.context_menu_tk_font = None
        self._main_queue_processor_after_id = None
        self._after_ids = []

        self.ui_manager = UIManager(self)
        self.ui_manager._create_font_objects()
        self.ui_manager._create_placeholder_images()

        self._create_widgets()

        self.app_logic = AppLogic(self, self.download_threads)
        self.format_fetcher = FormatFetcher(self)
        self.history_manager = HistoryManager(self)

        self.get_formats_button.configure(
            command=self.format_fetcher.get_available_formats
        )

        self.after(10, self._post_init_setup)

    def _create_widgets(self):
        """Creates and grids all UI widgets."""
        self.header_buttons_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.header_buttons_frame.grid(
            row=0, column=0, padx=10, pady=10, sticky="ew"
        )
        self.header_buttons_frame.columnconfigure(0, weight=1)

        self.theme_toggle_button = ctk.CTkButton(
            self.header_buttons_frame,
            text="Toggle Theme",
            command=self.ui_manager.toggle_theme,
            font=self.ui_font,
        )
        self.theme_toggle_button.pack(side="right", padx=(5, 0), pady=0)
        Tooltip(
            self.theme_toggle_button,
            "Switch between light and dark appearance mode.",
        )
        self.ui_manager.update_theme_toggle_button_text()

        self.settings_button = ctk.CTkButton(
            self.header_buttons_frame,
            text="⚙️ Settings",
            command=self.open_settings_window,
            font=self.ui_font,
        )
        self.settings_button.pack(side="right", padx=(5, 0), pady=0)
        Tooltip(self.settings_button, "Open application settings.")

        self.clear_log_button = ctk.CTkButton(
            self.header_buttons_frame,
            text="🗑️ Clear Log",
            command=self.ui_manager.clear_log,
            font=self.ui_font,
        )
        self.clear_log_button.pack(side="right", padx=(5, 0), pady=0)
        Tooltip(self.clear_log_button, "Clear messages from the download log.")

        self.open_folder_button = ctk.CTkButton(
            self.header_buttons_frame,
            text="📂 Open Folder",
            command=self.ui_manager.open_download_folder,
            font=self.ui_font,
        )
        self.open_folder_button.pack(side="right", padx=(5, 0), pady=0)
        Tooltip(
            self.open_folder_button, "Open the configured download directory."
        )

        self.top_bar_frame = ctk.CTkFrame(self)
        self.top_bar_frame.grid(row=1, column=0, padx=0, pady=0, sticky="nsew")
        self.top_bar_frame.grid_columnconfigure(0, weight=1)

        self.url_controls_frame = ctk.CTkFrame(
            self.top_bar_frame, fg_color="transparent"
        )
        self.url_controls_frame.pack(expand=True, fill="both")
        self.url_controls_frame.grid_columnconfigure(0, weight=1)

        self.url_mode_frame = ctk.CTkFrame(
            self.url_controls_frame, fg_color="transparent"
        )
        self.url_mode_frame.grid(row=0, column=0, padx=10, pady=5, sticky="ew")
        self.url_mode_frame.grid_columnconfigure(0, weight=1)
        self.url_mode_frame.grid_columnconfigure(1, weight=0)

        self.url_text_label = ctk.CTkLabel(
            self.url_mode_frame, text="Media URL:", font=self.ui_font
        )
        self.url_text_label.grid(row=0, column=0, padx=(0, 5), pady=0, sticky="w")

        self.url_input_type_var = ctk.StringVar(value="Single URL")
        self.url_type_toggle = ctk.CTkSegmentedButton(
            self.url_mode_frame,
            values=["Single URL", "Playlist URL"],
            variable=self.url_input_type_var,
            command=self.on_url_type_toggle,
            font=self.ui_font_small,
        )
        self.url_type_toggle.grid(
            row=0, column=1, padx=(5, 0), pady=0, sticky="e"
        )

        self.url_var = ctk.StringVar()
        self.url_entry = ctk.CTkEntry(
            self.url_controls_frame,
            textvariable=self.url_var,
            width=450,
            font=self.ui_font,
        )
        self.url_entry.grid(row=1, column=0, padx=10, pady=5, sticky="ew")

        self.platform_label_var = ctk.StringVar(value="Platform: N/A")
        self.platform_label = ctk.CTkLabel(
            self.url_controls_frame,
            textvariable=self.platform_label_var,
            font=self.ui_font,
        )
        self.platform_label.grid(row=2, column=0, padx=10, pady=2, sticky="w")

        self.format_selection_frame = ctk.CTkFrame(
            self.url_controls_frame, fg_color="transparent"
        )
        self.format_selection_frame.grid(
            row=3, column=0, padx=10, pady=(5, 0), sticky="ew"
        )
        self.format_selection_frame.grid_columnconfigure(1, weight=1)

        self.get_formats_button = ctk.CTkButton(
            self.format_selection_frame,
            text="🎞️ Get Formats",
            command=None,
            font=self.ui_font,
        )
        self.get_formats_button.grid(row=0, column=0, padx=(0, 5), pady=0)
        Tooltip(
            self.get_formats_button,
            "Fetch available video/audio formats for the URL.",
        )

        self.selected_format_label_var = ctk.StringVar(
            value=f"Format: {self.settings.get('selected_format_code', 'best')}"
        )
        self.selected_format_label = ctk.CTkLabel(
            self.format_selection_frame,
            textvariable=self.selected_format_label_var,
            font=self.ui_font,
            anchor="w",
        )
        self.selected_format_label.grid(
            row=0, column=1, padx=5, pady=0, sticky="ew"
        )

        self.download_type_var = ctk.StringVar(
            value=self.settings.get("default_download_type", "Video")
        )
        self.download_type_label = ctk.CTkLabel(
            self.url_controls_frame, text="Download Type:", font=self.ui_font
        )
        self.download_type_label.grid(
            row=4, column=0, padx=10, pady=(10, 0), sticky="w"
        )
        self.download_type_selector = ctk.CTkSegmentedButton(
            self.url_controls_frame,
            values=["Video", "Audio"],
            variable=self.download_type_var,
            font=self.ui_font,
        )
        self.download_type_selector.grid(
            row=5, column=0, padx=10, pady=5, sticky="ew"
        )

        self.action_buttons_frame = ctk.CTkFrame(
            self.url_controls_frame, fg_color="transparent"
        )
        self.action_buttons_frame.grid(
            row=6, column=0, padx=10, pady=10, sticky="ew"
        )
        self.action_buttons_frame.grid_columnconfigure(0, weight=1)
        self.action_buttons_frame.grid_columnconfigure(1, weight=1)

        self.download_button = ctk.CTkButton(
            self.action_buttons_frame,
            text="⬇️ Download from Clipboard",
            command=self.on_download_button_click,
            font=self.ui_font_bold,
        )
        self.download_button.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        Tooltip(
            self.download_button,
            "Paste URL from clipboard and start download with current settings.",
        )

        self.cancel_button = ctk.CTkButton(
            self.action_buttons_frame,
            text="✖️ Cancel Download",
            command=self.on_cancel_download_click,
            font=self.ui_font_bold,
            fg_color="firebrick",
            hover_color="darkred",
            state="disabled",
        )
        self.cancel_button.grid(row=0, column=1, padx=(5, 0), sticky="ew")
        Tooltip(self.cancel_button, "Stop the currently active download.")

        self.progress_bar = ctk.CTkProgressBar(
            self.url_controls_frame, orientation="horizontal"
        )
        self.progress_bar.set(0)
        self.progress_bar.grid(row=7, column=0, padx=10, pady=(0, 10), sticky="ew")

        self.progress_details_label = ctk.CTkLabel(
            self.url_controls_frame,
            text="Current Task: N/A | Overall Progress: N/A",
            font=self.ui_font_small,
            text_color="gray",
            anchor="w",
        )
        self.progress_details_label.grid(
            row=8, column=0, padx=10, pady=(0, 5), sticky="ew"
        )

        self.active_downloads_outer_frame = ctk.CTkFrame(self)
        self.active_downloads_outer_frame.grid(
            row=2, column=0, padx=10, pady=10, sticky="nsew"
        )
        self.active_downloads_outer_frame.grid_columnconfigure(0, weight=1)
        self.active_downloads_outer_frame.grid_rowconfigure(1, weight=1)

        self.active_downloads_label = ctk.CTkLabel(
            self.active_downloads_outer_frame,
            text="Active Downloads:",
            font=self.ui_font_bold,
        )
        self.active_downloads_label.grid(
            row=0, column=0, padx=10, pady=5, sticky="nw"
        )

        self.active_downloads_scrollable_frame = ctk.CTkScrollableFrame(
            self.active_downloads_outer_frame
        )
        self.active_downloads_scrollable_frame.grid(
            row=1, column=0, padx=10, pady=5, sticky="nsew"
        )
        self.active_downloads_scrollable_frame.grid_columnconfigure(0, weight=1)

        self.log_frame = ctk.CTkFrame(self)
        self.log_frame.grid(row=3, column=0, padx=10, pady=10, sticky="nsew")
        self.log_frame.grid_columnconfigure(0, weight=1)
        self.log_frame.grid_rowconfigure(1, weight=1)
        self.log_label = ctk.CTkLabel(
            self.log_frame, text="Download Log:", font=self.ui_font_bold
        )
        self.log_label.grid(row=0, column=0, padx=10, pady=5, sticky="nw")
        self.log_text = ctk.CTkTextbox(
            self.log_frame,
            wrap="word",
            state="disabled",
            height=100,
            font=self.ui_font,
        )
        self.log_text.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")
        self._rate_limited_logger = RateLimitedLogger(self.log_text)

        self.history_outer_frame = ctk.CTkFrame(self)
        self.history_outer_frame.grid(
            row=4, column=0, padx=10, pady=10, sticky="nsew"
        )
        self.history_outer_frame.grid_columnconfigure(0, weight=1)
        self.history_outer_frame.grid_rowconfigure(1, weight=1)

        self.history_label = ctk.CTkLabel(
            self.history_outer_frame,
            text="Download History:",
            font=self.ui_font_bold,
        )
        self.history_label.grid(row=0, column=0, padx=10, pady=5, sticky="nw")

        self.history_scrollable_frame = ctk.CTkScrollableFrame(
            self.history_outer_frame
        )
        self.history_scrollable_frame.grid(
            row=1, column=0, padx=10, pady=5, sticky="nsew"
        )
        self.history_scrollable_frame.grid_columnconfigure(0, weight=1)

        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=0)
        self.grid_rowconfigure(2, weight=1)
        self.grid_rowconfigure(3, weight=1)
        self.grid_rowconfigure(4, weight=2)
        self.grid_columnconfigure(0, weight=1)

    def _post_init_setup(self):
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.bind(
            "<FocusIn>",
            self.app_logic.on_main_window_focus
            if self.app_logic
            else lambda e: None,
        )
        if self.app_logic:
            self.app_logic.update_global_hotkey_listener()
        if self.history_manager:
            self.history_manager.load_existing_downloads_to_history()
        self._schedule_main_queue_processor()

    def _schedule_main_queue_processor(self):
        if (
            self._main_queue_processor_after_id is None
            and self.winfo_exists()
            and not self._is_closing
        ):
            self._main_queue_processor_after_id = self.after(
                100, self.process_all_queues
            )

    def log_message(self, message):
        if hasattr(
            self, "_rate_limited_logger"
        ) and self._rate_limited_logger.textbox.winfo_exists():
            self._rate_limited_logger.log(message)
        else:
            print(f"LOG (no-logger/textbox): {message}")

    def save_app_settings(self):
        sm_save_settings(self.settings)

    def open_settings_window(self):
        if (
            self.settings_window_instance is None
            or not self.settings_window_instance.winfo_exists()
        ):
            self.settings_window_instance = SettingsWindow(self, app_instance=self)
            self.settings_window_instance.focus()
        else:
            self.settings_window_instance.lift()
            self.settings_window_instance.focus()

    def open_format_selection_window(self, formats_data):
        if (
            self.format_selection_window_instance is None
            or not self.format_selection_window_instance.winfo_exists()
        ):
            self.format_selection_window_instance = FormatSelectionWindow(
                self, self, formats_data
            )
            self.format_selection_window_instance.focus()
        else:
            self.format_selection_window_instance.lift()
            self.format_selection_window_instance.focus()

    def on_url_type_toggle(self, value):
        if not self.winfo_exists():
            return
        if value == "Single URL":
            self.get_formats_button.configure(state="normal")
            self.download_button.configure(text="⬇️ Download from Clipboard")
        elif value == "Playlist URL":
            self.get_formats_button.configure(state="disabled")
            self.selected_format_label_var.set("Format: Best (Playlist)")
            self.download_button.configure(text="⬇️ Download Playlist/Batch")
        self.url_var.set("")
        self.platform_label_var.set("Platform: N/A")

    def on_download_button_click(self):
        if not self.winfo_exists() or self._is_closing:
            return

        url = self.app_logic.get_and_validate_clipboard_url()
        if not url:
            if self.winfo_exists():
                messagebox.showwarning(
                    "No Valid URL",
                    "No valid media URL found in clipboard to download.",
                    parent=self,
                )
            return

        if self.current_active_download_id or not self.pending_downloads.empty():
            if self.winfo_exists():
                messagebox.showinfo(
                    "Download Queued",
                    "Downloads are already active or queued. Please wait.",
                    parent=self,
                )
            return

        self._reset_ui_on_download_completion(is_full_reset=True)
        self.download_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.current_download_cancel_event = threading.Event()

        if self.url_input_type_var.get() == "Single URL":
            self.log_message(
                f"\n--- Adding Single {self.download_type_var.get()} download to queue: {url} ---"
            )
            self.pending_downloads.put(
                {
                    "url": url,
                    "download_type": self.download_type_var.get(),
                    "selected_format_code": self.settings.get(
                        "selected_format_code", "best"
                    ),
                    "download_subtitles": self.settings.get(
                        "download_subtitles", False
                    ),
                    "subtitle_languages": self.settings.get(
                        "subtitle_languages", "en"
                    ),
                    "embed_subtitles": self.settings.get(
                        "embed_subtitles", True
                    ),
                    "is_playlist_item": False,
                    "title": self.url_var.get(),
                    "cancel_event": self.current_download_cancel_event,
                }
            )
            self.start_next_download_if_available()
        else:
            self.log_message(
                f"\n--- Initiating Playlist/Batch download from: {url} ---"
            )
            self.app_logic.current_playlist_download_info = {
                "total_items": 0,
                "completed_items": 0,
                "failed_items": 0,
                "skipped_items": 0,
                "cancelled": False,
            }
            if self.progress_details_label.winfo_exists():
                self.progress_details_label.configure(
                    text="Fetching playlist items..."
                )
            self.app_logic.run_playlist_download_threaded(
                url, self.current_download_cancel_event
            )

    def start_next_download_if_available(self):
        if not self.winfo_exists() or self._is_closing:
            return

        if not self.current_active_download_id and not self.pending_downloads.empty():
            download_data = self.pending_downloads.get()
            self.log_message(
                f"Starting next queued download: {download_data.get('url')[:50]}..."
            )
            self.app_logic.run_download_process_threaded_actual(
                **download_data
            )
        elif self.current_active_download_id is None:
            self._reset_ui_on_download_completion(is_full_reset=True)

    def on_cancel_download_click(self):
        if not self.winfo_exists() or self._is_closing:
            return
        if self.current_download_cancel_event:
            self.log_message(
                "Cancellation requested. Signaling all active/queued downloads to stop..."
            )
            self.current_download_cancel_event.set()
            if self.cancel_button.winfo_exists():
                self.cancel_button.configure(state="disabled")

    def _reset_ui_on_download_completion(self, is_full_reset=True):
        if not self.winfo_exists() or self._is_closing:
            return

        if is_full_reset:
            if self.download_button.winfo_exists():
                self.download_button.configure(state="normal")
            if self.cancel_button.winfo_exists():
                self.cancel_button.configure(state="disabled")
            if self.progress_bar.winfo_exists():
                self.progress_bar.set(0)
            if self.progress_details_label.winfo_exists():
                self.progress_details_label.configure(
                    text="Current Task: N/A | Overall Progress: N/A"
                )

            self.current_active_download_id = None
            self.current_download_cancel_event = None
            while not self.pending_downloads.empty():
                try:
                    self.pending_downloads.get_nowait()
                except queue.Empty:
                    pass
            for download_id in list(self.active_downloads.keys()):
                self._remove_active_download_item_ui(download_id)
        else:
            if self.progress_bar.winfo_exists():
                self.progress_bar.set(0)
            self.current_active_download_id = None

    def _create_active_download_item_ui(self, download_id, item_data):
        if (
            not self.winfo_exists()
            or not self.active_downloads_scrollable_frame.winfo_exists()
        ):
            return

        item_frame = ctk.CTkFrame(
            self.active_downloads_scrollable_frame, corner_radius=5
        )
        item_frame.pack(fill="x", pady=2, padx=5)

        title_text = item_data.get("title", item_data.get("url", "Unknown"))
        title_label = ctk.CTkLabel(
            item_frame,
            text=title_text,
            font=self.ui_font,
            anchor="w",
            wraplength=450,
        )
        title_label.pack(fill="x", padx=5, pady=(5, 0))

        progress_bar = ctk.CTkProgressBar(item_frame, orientation="horizontal")
        progress_bar.set(0)
        progress_bar.pack(fill="x", padx=5, pady=(2, 0))

        details_label = ctk.CTkLabel(
            item_frame,
            text="Progress: 0% | Speed: N/A | ETA: N/A",
            font=self.ui_font_small,
            text_color="gray",
            anchor="w",
        )
        details_label.pack(fill="x", padx=5, pady=(0, 5))

        status_label = ctk.CTkLabel(
            item_frame,
            text=f"Status: {item_data.get('status', 'Queued').capitalize()}",
            font=self.ui_font_small,
            text_color="gray",
            anchor="w",
        )
        status_label.pack(fill="x", padx=5, pady=(0, 5))

        self.active_downloads[download_id] = {
            "frame": item_frame,
            "title_label": title_label,
            "progress_bar": progress_bar,
            "details_label": details_label,
            "status_label": status_label,
            "data": item_data,
        }

    def _update_active_download_item_ui(self, download_id, update_data):
        if not self.winfo_exists() or download_id not in self.active_downloads:
            return

        item_ui = self.active_downloads[download_id]
        if not item_ui["frame"].winfo_exists():
            return

        item_data = item_ui["data"]
        item_data.update(update_data)

        if "title" in update_data:
            item_ui["title_label"].configure(text=item_data["title"])
        if "progress_percent" in update_data:
            item_ui["progress_bar"].set(update_data["progress_percent"] / 100.0)
        if any(k in update_data for k in ["progress_percent", "speed", "eta"]):
            item_ui["details_label"].configure(
                text=f"Progress: {item_data.get('progress_percent', 0):.1f}% | Speed: {item_data.get('speed','N/A')} | ETA: {item_data.get('eta','N/A')}"
            )
        if "status" in update_data:
            status = update_data["status"]
            message = update_data.get("message", status)
            color = "gray"
            if status == "completed":
                color = "green"
            elif status == "failed":
                color = "red"
            item_ui["status_label"].configure(
                text=f"Status: {status.capitalize()} - {message}",
                text_color=color,
            )
            if status in ["failed", "cancelled"]:
                item_ui["progress_bar"].set(0)
            elif status == "completed":
                item_ui["progress_bar"].set(1)

    def _remove_active_download_item_ui(self, download_id):
        if self.winfo_exists() and download_id in self.active_downloads:
            item_ui = self.active_downloads.pop(download_id)
            if item_ui["frame"].winfo_exists():
                item_ui["frame"].destroy()

    def process_all_queues(self):
        if not self.winfo_exists() or self._is_closing:
            self._main_queue_processor_after_id = None
            return

        self._main_queue_processor_after_id = None
        self._process_download_queue()
        self._process_thumbnail_queue()
        self._process_duration_queue()
        self._process_format_queue()

        if self.winfo_exists() and not self._is_closing:
            self._schedule_main_queue_processor()

    def _process_download_queue(self):
        try:
            while True:
                if not self.winfo_exists() or self._is_closing:
                    break
                msg_type, *payload = self.download_queue.get_nowait()

                if msg_type == MSG_DOWNLOAD_ITEM_ADDED:
                    download_id, item_data = payload
                    self._create_active_download_item_ui(download_id, item_data)
                    self.current_active_download_id = download_id
                elif msg_type == MSG_DOWNLOAD_ITEM_UPDATE:
                    self._update_active_download_item_ui(*payload)
                elif msg_type == MSG_DOWNLOAD_ITEM_STATUS:
                    self._handle_download_item_final_status(*payload)
                elif msg_type == MSG_LOG_PREFIX:
                    self.log_message(str(payload[0]))
        except queue.Empty:
            pass
        except Exception as e:
            if not self._is_closing:
                self.log_message(f"ERROR in download_queue processing: {e}")

    def _process_thumbnail_queue(self):
        try:
            while True:
                if not self.winfo_exists() or self._is_closing:
                    break
                msg_type, *payload = self.thumbnail_gen_queue.get_nowait()

                if msg_type == MSG_THUMB_LOADED_FOR_HISTORY:
                    thumb_path, ctk_image, index = payload
                    self.thumbnail_cache[thumb_path] = ctk_image
                    if self.history_manager:
                        self.history_manager.update_history_item_ui(
                            index, {"ctk_image": ctk_image}
                        )
                elif msg_type == MSG_LOG_PREFIX:
                    self.log_message(str(payload[0]))
        except queue.Empty:
            pass
        except Exception as e:
            if not self._is_closing:
                self.log_message(f"ERROR in thumbnail_queue processing: {e}")

    def _process_duration_queue(self):
        try:
            while True:
                if not self.winfo_exists() or self._is_closing:
                    break
                msg_type, *payload = self.duration_queue.get_nowait()

                if msg_type == MSG_DURATION_DONE:
                    file_path, duration, index = payload
                    item_to_update = self.history_items_with_paths[index]
                    item_to_update["duration"] = duration
                    formatted_duration = self.app_logic._format_duration(
                        duration
                    )
                    item_to_update["formatted_duration"] = formatted_duration
                    if self.history_manager:
                        self.history_manager.update_history_item_ui(
                            index, {"formatted_duration": formatted_duration}
                        )
                elif msg_type == MSG_LOG_PREFIX:
                    self.log_message(str(payload[0]))
        except queue.Empty:
            pass
        except Exception as e:
            if not self._is_closing:
                self.log_message(f"ERROR in duration_queue processing: {e}")

    def _process_format_queue(self):
        try:
            while True:
                if not self.winfo_exists() or self._is_closing:
                    break
                msg_type, data = self.format_info_queue.get_nowait()

                if self.get_formats_button.winfo_exists():
                    self.get_formats_button.configure(
                        state="normal", text="🎞️ Get Formats"
                    )

                if msg_type == "FORMAT_JSON_DATA":
                    parsed = self.format_fetcher._parse_formats_json(data)
                    if parsed:
                        self.open_format_selection_window(parsed)
                    else:
                        self.messagebox.showinfo(
                            "No Formats",
                            "Could not parse any formats.",
                            parent=self,
                        )
                elif msg_type == "FORMAT_ERROR":
                    self.messagebox.showerror(
                        "Format Fetch Error", str(data), parent=self
                    )
                elif msg_type == MSG_LOG_PREFIX:
                    self.log_message(f"(FormatFetch) {data}")
        except queue.Empty:
            pass
        except Exception as e:
            if not self._is_closing:
                self.log_message(f"ERROR in format_info_queue processing: {e}")

    def _handle_download_item_final_status(self, download_id, status_payload):
        if not self.winfo_exists() or self._is_closing:
            return

        self._update_active_download_item_ui(download_id, status_payload)
        is_playlist_item = status_payload.get("is_playlist_item", False)

        if status_payload["status"] in ["completed", "failed"]:
            if self.history_manager:
                self.history_manager.update_history(
                    display_name_base=status_payload.get("title", "Unknown"),
                    file_path=status_payload.get("file_path"),
                    item_type=status_payload.get("item_type_for_history"),
                    thumbnail_path=status_payload.get("thumbnail_path"),
                    sub_indicator=status_payload.get("sub_indicator", ""),
                    download_date_str=status_payload.get("download_date_str"),
                )

        if is_playlist_item:
            # Playlist logic...
            if status_payload["status"] == "completed":
                self.app_logic.current_playlist_download_info[
                    "completed_items"
                ] += 1
            # ... handle other statuses ...
            self._remove_active_download_item_ui(download_id)
            self.start_next_download_if_available()
        else:
            # Single download logic...
            self._remove_active_download_item_ui(download_id)
            self._reset_ui_on_download_completion(is_full_reset=True)
            if status_payload["status"] == "completed" and self.settings.get(
                "show_download_complete_popup", True
            ):
                messagebox.showinfo(
                    "Download Complete", status_payload["message"], parent=self
                )
            elif status_payload["status"] == "failed":
                messagebox.showerror(
                    "Download Failed", status_payload["message"], parent=self
                )

    def on_closing(self):
        if self._is_closing:
            return
        self._is_closing = True
        print("DEBUG: Initiating application shutdown...")

        if self._main_queue_processor_after_id:
            try:
                self.after_cancel(self._main_queue_processor_after_id)
            except Exception:
                pass
            self._main_queue_processor_after_id = None

        if hasattr(self, "_rate_limited_logger"):
            self._rate_limited_logger.cancel_flush()

        if (
            self.current_download_cancel_event
            and not self.current_download_cancel_event.is_set()
        ):
            self.log_message("Signaling active downloads to stop...")
            self.current_download_cancel_event.set()

        if self.app_logic and self.app_logic.global_hotkey_manager:
            self.app_logic.global_hotkey_manager.stop_listener()

        active_threads = [
            t for t in self.download_threads if t.is_alive()
        ] + [t for t in self.app_logic.thumbnail_gen_threads if t.is_alive()]

        if active_threads:
            if messagebox.askyesno(
                "Exit Application",
                f"{len(active_threads)} background task(s) are still active.\nExiting now might terminate them abruptly. Continue anyway?",
                parent=self,
            ):
                print("DEBUG: User confirmed exit despite active processes.")
                self.destroy()
            else:
                print("DEBUG: User cancelled exit.")
                self._is_closing = False
                self._schedule_main_queue_processor()
        else:
            print("DEBUG: No active processes found. Destroying application.")
            self.destroy()