# app_logic.py
import subprocess
import sys
import re
import pyperclip
import threading
import time
import os
import datetime
import shlex

from constants import (
    MSG_LOG_PREFIX, MSG_PROGRESS_PREFIX, FFMPEG_TIMEOUT, MSG_DONE_ID,
    MSG_DOWNLOAD_ERROR_DETAILS, MSG_DOWNLOAD_CANCELLED_SIGNAL # NEW: Import cancellation signal
)

# Import download_logic functions that don't depend on self directly
from download_logic import (
    detect_platform, generate_thumbnail_from_video_logic,
    run_download_process, get_media_duration_logic
)
from global_hotkey_manager import GlobalHotkeyManager

MSG_DURATION_DONE = "DURATION_DONE" # Keeping this here as it's specific to app_logic's internal messaging


class AppLogic:
    def __init__(self, app_instance):
        self.app = app_instance # Reference to the main application instance
        self.global_hotkey_manager = None
        self._last_focus_paste_time = 0 # For debouncing paste on focus

        # These thread lists belong to AppLogic, as it manages these background tasks
        self.thumbnail_gen_threads = []
        self.duration_gen_threads = []


    def generate_thumbnail_from_video(self, video_path, output_thumb_path, queue_for_log=None):
        """Wrapper for download_logic's generate_thumbnail_from_video_logic."""
        def log_adapter(msg):
            log_message_content = f"(ffmpeg) {msg}"
            if queue_for_log:
                queue_for_log.put(f"{MSG_LOG_PREFIX} {log_message_content}")
            else:
                self.app.log_message(log_message_content)
        return generate_thumbnail_from_video_logic(video_path, output_thumb_path, log_adapter)

    def _process_thumbnail_generation_tasks(self, video_jobs):
        """Thread target for generating thumbnails for a list of video jobs."""
        num_jobs = len(video_jobs)
        self.app.thumbnail_gen_queue.put(
            f"{MSG_LOG_PREFIX} INFO: Starting background thumbnail generation for {num_jobs} video(s)..."
        )
        for i, job in enumerate(video_jobs):
            video_path, thumb_output_path = job["video_path"], job["thumb_output_path"]
            success = self.generate_thumbnail_from_video(
                video_path, thumb_output_path, queue_for_log=self.app.thumbnail_gen_queue
            )
            if success:
                self.app.thumbnail_gen_queue.put(("THUMB_DONE", video_path, thumb_output_path))
            else:
                self.app.thumbnail_gen_queue.put(
                    f"{MSG_LOG_PREFIX} WARN: Failed to generate thumbnail for {os.path.basename(video_path)}"
                )
        self.app.thumbnail_gen_queue.put(
            f"{MSG_LOG_PREFIX} INFO: Background thumbnail generation for {num_jobs} video(s) finished."
        )

    def _process_duration_tasks(self, files_for_duration_jobs):
        """Thread target for calculating media duration for a list of file paths."""
        num_jobs = len(files_for_duration_jobs)
        self.app.duration_queue.put(
            f"{MSG_LOG_PREFIX} INFO: Starting background media duration calculation for {num_jobs} file(s)..."
        )
        for i, job in enumerate(files_for_duration_jobs):
            file_path, original_item_index_in_original_list = job["file_path"], job["original_index"]
            def log_to_queue(msg): self.app.duration_queue.put(f"{MSG_LOG_PREFIX} (ffprobe duration) {msg}")
            duration_seconds = get_media_duration_logic(file_path, log_to_queue)

            self.app.duration_queue.put((MSG_DURATION_DONE, file_path, duration_seconds, original_item_index_in_original_list))

        self.app.duration_queue.put(
            f"{MSG_LOG_PREFIX} INFO: Background media duration calculation finished."
        )

    def _format_duration(self, seconds):
        """Formats duration in seconds to H:MM:SS or MM:SS."""
        if seconds is None or seconds < 0:
            return "Duration: N/A"
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds = int(seconds % 60)
        if hours > 0:
            return f"Duration: {hours}:{minutes:02d}:{seconds:02d}"
        return f"Duration: {minutes:02d}:{seconds:02d}"

    def open_file_with_player(self, file_path):
        """Opens a media file using the configured player or OS default."""
        player_command_template = self.app.settings.get("player_command", "")
        normalized_file_path = os.path.normpath(file_path)

        if not os.path.exists(normalized_file_path):
            self.app.log_message(f"File not found: {normalized_file_path}")
            self.app.after(0, lambda: self.app.messagebox.showerror(
                "File Not Found", f"The media file could not be found:\n{normalized_file_path}", parent=self.app
            ))
            return

        try:
            final_command_parts = []
            if player_command_template and player_command_template.strip():
                if "{file}" in player_command_template:
                    parts = player_command_template.split("{file}", 1)
                    command_prefix_str, command_suffix_str = parts[0], parts[1]
                    try:
                        if command_prefix_str.strip():
                            final_command_parts.extend(shlex.split(command_prefix_str.strip()))
                        final_command_parts.append(normalized_file_path)
                        if command_suffix_str.strip():
                            final_command_parts.extend(shlex.split(command_suffix_str.strip()))
                    except ValueError as e:
                        self.app.log_message(
                            f"Error parsing player command prefix/suffix: {player_command_template} - {e}"
                        )
                        self.app.after(0, lambda: self.app.messagebox.showerror(
                            "Player Command Error",
                            f"Error parsing player command prefix/suffix:\n'{player_command_template}'\n{e}",
                            parent=self.app
                        ))
                        return
                else:
                    # If {file} is not present, append the file path to the command
                    try:
                        final_command_parts = shlex.split(player_command_template)
                        final_command_parts.append(normalized_file_path)
                    except ValueError as e:
                        self.app.log_message(
                            f"Error parsing player command: {player_command_template} - {e}"
                        )
                        self.app.after(0, lambda: self.app.messagebox.showerror(
                            "Player Command Error",
                            f"Error parsing player command (no {{file}} placeholder):\n'{player_command_template}'\n{e}",
                            parent=self.app
                        ))
                        return

                if not final_command_parts or not any(p.strip() for p in final_command_parts):
                    self.app.log_message(
                        f"Player command resulted in empty or invalid list: {player_command_template}"
                    )
                    self.app.after(0, lambda: self.app.messagebox.showerror(
                        "Player Command Error", "Player command is invalid or empty after parsing.", parent=self.app
                    ))
                    return

                self.app.log_message(
                    f"Attempting to open '{normalized_file_path}' with custom player: {shlex.join(final_command_parts)}"
                )
                subprocess.Popen(final_command_parts)
            else:
                self.app.log_message(f"Attempting to open '{normalized_file_path}' with OS default player...")
                if sys.platform.startswith("win"):
                    os.startfile(normalized_file_path)
                elif sys.platform.startswith("darwin"):
                    subprocess.Popen(["open", normalized_file_path])
                else:
                    subprocess.Popen(["xdg-open", normalized_file_path])
        except FileNotFoundError:
            player_exe = final_command_parts[0] if final_command_parts else "Specified player"
            self.app.log_message(
                f"Error: {player_exe} not found or OS default handler missing for '{normalized_file_path}'."
            )
            self.app.after(0, lambda: self.app.messagebox.showerror(
                "Player Not Found",
                f"{player_exe} not found or no default application for this file type.",
                parent=self.app
            ))
        except Exception as e:
            self.app.log_message(f"Failed to open '{normalized_file_path}': {type(e).__name__} - {e}")
            self.app.after(0, lambda: self.app.messagebox.showerror(
                "Open Error", f"Failed to open media: {e}", parent=self.app
            ))

    def get_and_validate_clipboard_url(self):
        """Retrieves and validates a URL from the clipboard."""
        try:
            clipboard_content = pyperclip.paste()
            url_regex = r"https?://\S+"
            match = re.search(url_regex, clipboard_content)
            if match:
                url = match.group(0)
                platform = detect_platform(url)
                if platform in ["youtube", "instagram", "tiktok", "other"]:
                    if self.app.url_var.get() != url:
                        self.app.url_var.set(url)
                        self.app.platform_label_var.set(f"Platform: {platform.capitalize()}")
                        self.app.log_message(f"URL pasted from clipboard: {url}")
                    return url
                else:
                    if self.app.url_var.get() != "Clipboard URL not from a recognized or supported platform.":
                        self.app.url_var.set("Clipboard URL not from a recognized or supported platform.")
                        self.app.platform_label_var.set("Platform: Unknown")
                        self.app.log_message("No supported URL found in clipboard.")
                    return None
            else:
                if self.app.url_var.get() != "No valid URL found in clipboard.":
                    self.app.url_var.set("No valid URL found in clipboard.")
                    self.app.platform_label_var.set("Platform: N/A")
                    self.app.log_message("No URL found in clipboard.")
                return None
        except pyperclip.PyperclipException:
            if time.time() - self._last_focus_paste_time > 5:
                self.app.after(0, lambda: self.app.messagebox.showerror("Clipboard Error", "Could not access clipboard. Please check permissions or install a clipboard utility if on Linux (e.g., xclip, xsel).", parent=self.app))
                self.app.log_message("Error: Could not access clipboard. Pyperclip might not be configured.")
            return None
        except Exception as e:
            if time.time() - self._last_focus_paste_time > 5:
                self.app.after(0, lambda: self.app.messagebox.showerror("Error", f"Clipboard error: {e}", parent=self.app))
                self.app.log_message(f"Clipboard error: {e}")
            return None

    def on_main_window_focus(self, event):
        """
        Handles the main application window gaining focus.
        Attempts to paste URL from clipboard if setting is enabled and no modal windows are open.
        """
        if self.app.settings.get("auto_paste_on_focus", False):
            if time.time() - self._last_focus_paste_time < 1.0:
                return

            if self.app.grab_current() is not None:
                return

            if event.widget == self.app.winfo_toplevel():
                self._last_focus_paste_time = time.time()
                self.get_and_validate_clipboard_url()

    def on_global_hotkey_trigger(self):
        """
        Callback function executed when the global hotkey is pressed.
        Triggers the download button's functionality on the main thread.
        """
        self.app.after(0, self.app.on_download_button_click)


    def update_global_hotkey_listener(self):
        """
        Initializes or updates the global hotkey listener based on current settings.
        """
        enabled = self.app.settings.get("global_hotkey_enabled", False)
        hotkey_combo = self.app.settings.get("global_hotkey_combination", "")

        if self.global_hotkey_manager is None:
            self.global_hotkey_manager = GlobalHotkeyManager(
                hotkey_combo, self.on_global_hotkey_trigger, self.app.log_message
            )

        if enabled and hotkey_combo:
            if self.global_hotkey_manager.hotkey_combination_str != hotkey_combo:
                self.global_hotkey_manager.update_hotkey(hotkey_combo)
            elif not (self.global_hotkey_manager.listener_thread and self.global_hotkey_manager.listener_thread.is_alive()):
                self.global_hotkey_manager.start_listener()
            else:
                self.app.log_message(f"Global hotkey listener already active for '{hotkey_combo}'.")
        else:
            if self.global_hotkey_manager:
                self.global_hotkey_manager.stop_listener()
            self.app.log_message("Global hotkey disabled or no combination set. Listener stopped.")

    # NEW: Added cancel_event parameter
    def run_download_process_threaded(self, url, cancel_event: threading.Event):
        """
        Starts the download process in a new thread.
        `cancel_event` is a threading.Event used to signal cancellation to the download process.
        """
        platform = detect_platform(url)
        download_type = self.app.download_type_var.get()
        selected_format = self.app.settings.get("selected_format_code", "best")
        download_subs = self.app.settings.get("download_subtitles", False)
        subs_langs = self.app.settings.get("subtitle_languages", "en")
        embed_subs = self.app.settings.get("embed_subtitles", True)

        download_thread = threading.Thread(
            target=run_download_process,
            args=(
                url, platform, download_type, self.app.download_dir,
                self.app.download_queue, self.generate_thumbnail_from_video,
                selected_format, download_subs, subs_langs, embed_subs,
                cancel_event # NEW: Pass the cancellation event
            ),
            daemon=True
        )
        download_thread.start()
        self.app.download_threads.append(download_thread)