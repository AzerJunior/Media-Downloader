# ui_elements/app_logic.py
import subprocess
import sys
import os
import re
import pyperclip
import threading
import time
import json
import uuid
import queue
import shlex
import customtkinter as ctk
from PIL import Image

from constants import (
    MSG_LOG_PREFIX,
    MSG_DOWNLOAD_ITEM_ADDED,
    MSG_THUMB_LOADED_FOR_HISTORY,
    THUMBNAIL_SIZE,
)

# 3. CORRECTED IMPORT PATH
from download_process_core import (
    detect_platform,
    generate_thumbnail_from_video_logic,
    extract_album_art_logic,
    get_media_duration_logic,
    get_subprocess_startupinfo,
    run_download_process,
)
from global_hotkey_manager import GlobalHotkeyManager
from ui_elements.subprocess_output_processor import SubprocessOutputProcessor


MSG_DURATION_DONE = "DURATION_DONE"
QUEUE_PUT_TIMEOUT = 0.05

# ... (The rest of the AppLogic class remains exactly the same as before) ...
class AppLogic:
    def __init__(self, app_instance, download_threads_list):
        self.app = app_instance
        self.global_hotkey_manager = None
        self._last_focus_paste_time = 0

        self.thumbnail_gen_threads = []
        self.duration_gen_threads = []
        self.app_threads_list = download_threads_list

        self.current_playlist_download_info = {
            "total_items": 0,
            "completed_items": 0,
            "failed_items": 0,
            "skipped_items": 0,
            "cancelled": False,
        }

    def _process_thumbnail_loading_tasks(self, loading_jobs):
        """Processes thumbnail loading jobs for the history display."""
        for job in loading_jobs:
            thumb_path, original_item_index = (
                job["thumb_path"],
                job["original_index"],
            )
            try:
                pil_img = Image.open(thumb_path)
                pil_img.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
                ctk_image = ctk.CTkImage(
                    light_image=pil_img,
                    dark_image=pil_img,
                    size=THUMBNAIL_SIZE,
                )
                self.app.thumbnail_gen_queue.put(
                    (
                        MSG_THUMB_LOADED_FOR_HISTORY,
                        thumb_path,
                        ctk_image,
                        original_item_index,
                    ),
                    timeout=QUEUE_PUT_TIMEOUT,
                )
            except Exception as e:
                self.app.thumbnail_gen_queue.put(
                    f"{MSG_LOG_PREFIX} WARN: Failed to load history thumbnail {os.path.basename(thumb_path)}: {e}",
                    timeout=QUEUE_PUT_TIMEOUT,
                )

    def start_thumbnail_loading_for_history(self, loading_jobs):
        """Starts a thread to load thumbnails for existing history items."""
        self.thumbnail_gen_threads = [
            t for t in self.thumbnail_gen_threads if t.is_alive()
        ]
        if not any(
            t.is_alive() and t.name == "history_thumbnail_loader"
            for t in self.thumbnail_gen_threads
        ):
            thread = threading.Thread(
                target=self._process_thumbnail_loading_tasks,
                args=(loading_jobs,),
                daemon=True,
                name="history_thumbnail_loader",
            )
            thread.start()
            self.thumbnail_gen_threads.append(thread)

    def _process_duration_tasks(self, files_for_duration_jobs):
        """Processes media duration calculation jobs."""

        def log_adapter(msg):
            try:
                self.app.duration_queue.put(
                    f"{MSG_LOG_PREFIX} (ffprobe) {msg}",
                    timeout=QUEUE_PUT_TIMEOUT,
                )
            except queue.Full:
                pass

        for job in files_for_duration_jobs:
            file_path, original_index = job["file_path"], job["original_index"]
            duration_seconds = get_media_duration_logic(file_path, log_adapter)
            self.app.duration_queue.put(
                (MSG_DURATION_DONE, file_path, duration_seconds, original_index),
                timeout=QUEUE_PUT_TIMEOUT,
            )

    def start_duration_calculation_for_files(self, files_for_duration_jobs):
        """Starts a thread to calculate media durations."""
        self.duration_gen_threads = [
            t for t in self.duration_gen_threads if t.is_alive()
        ]
        if not any(t.is_alive() for t in self.duration_gen_threads):
            thread = threading.Thread(
                target=self._process_duration_tasks,
                args=(files_for_duration_jobs,),
                daemon=True,
            )
            thread.start()
            self.duration_gen_threads.append(thread)

    def _format_duration(self, seconds):
        if seconds is None or seconds < 0:
            return "Duration: N/A"
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds = int(seconds % 60)
        if hours > 0:
            return f"Duration: {hours}:{minutes:02d}:{seconds:02d}"
        return f"Duration: {minutes:02d}:{seconds:02d}"

    def open_file_with_player(self, file_path):
        player_command = self.app.settings.get("player_command", "")
        normalized_path = os.path.normpath(file_path)
        if not os.path.exists(normalized_path):
            self.app.messagebox.showerror(
                "File Not Found",
                f"The media file could not be found:\n{normalized_path}",
                parent=self.app,
            )
            return

        try:
            if player_command and player_command.strip():
                command_parts = shlex.split(
                    player_command.replace("{file}", shlex.quote(normalized_path))
                )
                subprocess.Popen(command_parts, env=os.environ.copy())
            else:
                if sys.platform.startswith("win"):
                    os.startfile(normalized_path)
                elif sys.platform.startswith("darwin"):
                    subprocess.Popen(["open", normalized_path])
                else:
                    subprocess.Popen(["xdg-open", normalized_path])
        except Exception as e:
            self.app.messagebox.showerror(
                "Open Error", f"Failed to open media: {e}", parent=self.app
            )

    def get_and_validate_clipboard_url(self):
        """Retrieves and validates a URL from the clipboard."""
        try:
            content = pyperclip.paste()
            match = re.search(r"https?://\S+", content)
            if match:
                url = match.group(0)
                self.app.url_var.set(url)
                platform = detect_platform(url)
                self.app.platform_label_var.set(f"Platform: {platform.capitalize()}")
                return url
        except Exception:
            return None
        return None

    def on_main_window_focus(self, event):
        if self.app.settings.get(
            "auto_paste_on_focus", True
        ) and self.app.grab_current() is None:
            if time.time() - self._last_focus_paste_time > 1.0:
                self._last_focus_paste_time = time.time()
                self.get_and_validate_clipboard_url()

    def on_global_hotkey_trigger(self):
        self.app.after(0, self.app.on_download_button_click)

    def update_global_hotkey_listener(self):
        enabled = self.app.settings.get("global_hotkey_enabled", False)
        combo = self.app.settings.get("global_hotkey_combination", "")
        if self.global_hotkey_manager is None:
            self.global_hotkey_manager = GlobalHotkeyManager(
                combo, self.on_global_hotkey_trigger, self.app.log_message
            )
        if enabled and combo:
            self.global_hotkey_manager.update_hotkey(combo)
            self.global_hotkey_manager.start_listener()
        else:
            self.global_hotkey_manager.stop_listener()

    def run_download_process_threaded_actual(self, **kwargs):
        """Starts a single media download process in a new thread."""
        platform = detect_platform(kwargs["url"])
        thumb_gen_func = (
            extract_album_art_logic
            if kwargs["download_type"] == "Audio"
            else generate_thumbnail_from_video_logic
        )
        thread = threading.Thread(
            target=run_download_process,
            args=(
                kwargs["url"],
                platform,
                kwargs["download_type"],
                self.app.download_dir,
                self.app.download_queue,
                thumb_gen_func,
            ),
            kwargs={
                "selected_format_code": kwargs["selected_format_code"],
                "download_subtitles": kwargs["download_subtitles"],
                "subtitle_languages": kwargs["subtitle_languages"],
                "embed_subtitles": kwargs["embed_subtitles"],
                "cancel_event": kwargs["cancel_event"],
                "is_playlist_item": kwargs["is_playlist_item"],
            },
            daemon=True,
        )
        self.app_threads_list.append(thread)
        thread.start()

    def _fetch_playlist_urls(
        self, playlist_url, output_queue, cancel_event: threading.Event
    ):
        """
        Fetches all video URLs from a playlist URL using yt-dlp.
        """
        urls = []
        try:
            yt_dlp_exe_path = None
            python_dir = os.path.dirname(sys.executable)
            scripts_dir = os.path.join(python_dir, "Scripts")
            if os.path.exists(os.path.join(scripts_dir, "yt-dlp.exe")):
                yt_dlp_exe_path = os.path.join(scripts_dir, "yt-dlp.exe")
            elif os.path.exists(os.path.join(scripts_dir, "yt-dlp")):
                yt_dlp_exe_path = os.path.join(scripts_dir, "yt-dlp")

            command_base = (
                [yt_dlp_exe_path]
                if yt_dlp_exe_path
                else [sys.executable, "-m", "yt_dlp"]
            )
            command = command_base + [
                "--flat-playlist",
                "--print-json",
                playlist_url,
            ]

            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=get_subprocess_startupinfo().dwFlags
                if sys.platform.startswith("win")
                else 0,
                startupinfo=get_subprocess_startupinfo()
                if sys.platform.startswith("win")
                else None,
                env=os.environ.copy(),
            )

            for line in iter(process.stdout.readline, ""):
                if cancel_event.is_set():
                    process.terminate()
                    return None
                try:
                    entry_data = json.loads(line)
                    if entry_data.get("url"):
                        urls.append(entry_data["url"])
                        self.app.after(
                            0,
                            lambda total=len(urls): self.app.progress_details_label.configure(
                                text=f"Fetched {total} items from playlist..."
                            ),
                        )
                except json.JSONDecodeError:
                    output_queue.put(
                        f"{MSG_LOG_PREFIX} (Playlist Fetch) {line.strip()}"
                    )

            process.stdout.close()
            return_code = process.wait()

            if return_code != 0:
                stderr_output = process.stderr.read()
                output_queue.put(
                    f"{MSG_LOG_PREFIX} ERROR: Playlist fetch failed. Stderr: {stderr_output}"
                )
                return None

            return urls

        except Exception as e:
            output_queue.put(
                f"{MSG_LOG_PREFIX} ERROR: Unexpected error fetching playlist: {e}"
            )
            return None

    def run_playlist_download_threaded(
        self, playlist_url, cancel_event: threading.Event
    ):
        """Starts the entire playlist download process in a background thread."""

        def playlist_worker():
            playlist_urls = self._fetch_playlist_urls(
                playlist_url, self.app.download_queue, cancel_event
            )

            if playlist_urls is None:
                self.app.log_message("Playlist URL fetching aborted or failed.")
                return

            self.current_playlist_download_info["total_items"] = len(
                playlist_urls
            )
            self.app.log_message(
                f"Found {len(playlist_urls)} videos. Queuing for download."
            )

            for i, url in enumerate(playlist_urls):
                if cancel_event.is_set():
                    self.app.log_message("Playlist queuing cancelled by user.")
                    break

                self.app.pending_downloads.put(
                    {
                        "url": url,
                        "download_type": self.app.download_type_var.get(),
                        "selected_format_code": "best",
                        "download_subtitles": self.app.settings.get(
                            "download_subtitles", False
                        ),
                        "subtitle_languages": self.app.settings.get(
                            "subtitle_languages", "en"
                        ),
                        "embed_subtitles": self.app.settings.get(
                            "embed_subtitles", True
                        ),
                        "is_playlist_item": True,
                        "title": f"Item {i+1}",
                        "cancel_event": cancel_event,
                    }
                )
            self.app.after(0, self.app.start_next_download_if_available)

        threading.Thread(target=playlist_worker, daemon=True).start()