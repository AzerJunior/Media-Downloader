# ui_elements/app_logic.py
import subprocess
import sys
import re
import pyperclip
import threading
import time
import os
import datetime
import shlex
import json

from constants import (
    MSG_LOG_PREFIX, MSG_PROGRESS_PREFIX, FFMPEG_TIMEOUT, MSG_DONE_ID,
    MSG_DOWNLOAD_ERROR_DETAILS, MSG_DOWNLOAD_CANCELLED_SIGNAL,
    MSG_DOWNLOAD_ITEM_UPDATE, MSG_DOWNLOAD_ITEM_STATUS, MSG_DOWNLOAD_ITEM_ADDED
)

import download_logic

from download_logic import (
    detect_platform, generate_thumbnail_from_video_logic,
    run_download_process, get_media_duration_logic
)
from global_hotkey_manager import GlobalHotkeyManager

MSG_DURATION_DONE = "DURATION_DONE"


class AppLogic:
    def __init__(self, app_instance):
        self.app = app_instance
        self.global_hotkey_manager = None
        self._last_focus_paste_time = 0

        self.thumbnail_gen_threads = []
        self.duration_gen_threads = [] # This list will hold the duration worker threads

        self.current_playlist_download_info = {
            "total_items": 0,
            "completed_items": 0,
            "failed_items": 0,
            "skipped_items": 0,
            "cancelled": False
        }


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

    # --- NEW: Public method to start duration calculation thread ---
    def start_duration_calculation_for_files(self, files_for_duration_jobs):
        """
        Starts a thread to calculate duration for given files if one isn't already active.
        Accepts a list of job dictionaries: `[{"file_path": ..., "original_index": ...}, ...]`.
        """
        # Clean up any finished threads
        self.duration_gen_threads = [t for t in self.duration_gen_threads if t.is_alive()]

        # Only start a new thread if no duration calculation is currently active
        if not any(t.is_alive() for t in self.duration_gen_threads):
            duration_thread = threading.Thread(
                target=self._process_duration_tasks,
                args=(files_for_duration_jobs,),
                daemon=True
            )
            duration_thread.start()
            self.duration_gen_threads.append(duration_thread)
        else:
            self.app.log_message("INFO: Media duration calculation for existing files is already in progress.")
    # --- END NEW ---

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

    # NEW: Renamed from run_download_process_threaded to better reflect its role
    # This method is called by start_next_download_if_available.
    def run_download_process_threaded_actual(self, url, download_type, selected_format_code,
                                              download_subtitles, subtitle_languages,
                                              embed_subtitles, cancel_event: threading.Event,
                                              is_playlist_item: bool):
        """
        Starts a single media download process in a new thread.
        This is the actual thread starter for individual downloads.
        """
        platform = detect_platform(url) # Detect platform for this specific URL

        download_thread = threading.Thread(
            target=run_download_process,
            args=(
                url, platform, download_type, self.app.download_dir,
                self.app.download_queue, self.generate_thumbnail_from_video, # From AppLogic itself
                selected_format_code, download_subtitles, subtitle_languages, embed_subtitles,
                cancel_event,
                is_playlist_item
            ),
            daemon=True
        )
        download_thread.start()
        self.app.download_threads.append(download_thread)


    def _fetch_playlist_urls(self, playlist_url, output_queue, cancel_event: threading.Event):
        urls = []
        try:
            command = [sys.executable, "-m", "yt_dlp", "--flat-playlist", "--print-json", playlist_url]
            output_queue.put(f"{MSG_LOG_PREFIX} Fetching playlist items: {' '.join(command)}")

            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace',
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform.startswith('win') else 0,
                startupinfo=download_logic._get_subprocess_startupinfo() if sys.platform.startswith('win') else None
            )

            temp_urls = []
            for line in iter(process.stdout.readline, ''):
                if cancel_event and cancel_event.is_set():
                    output_queue.put(f"{MSG_LOG_PREFIX} Playlist URL fetching cancelled.")
                    if process.poll() is None: process.terminate()
                    return None

                line_strip = line.strip()
                if line_strip:
                    try:
                        entry_data = json.loads(line_strip)
                        if entry_data.get("url"):
                            temp_urls.append(entry_data["url"])
                            self.current_playlist_download_info["total_items"] = len(temp_urls)
                            self.app.after(0, lambda total=len(temp_urls): self.app.progress_details_label.configure(
                                text=f"Fetched {total} items from playlist..."
                            ))
                            output_queue.put(f"{MSG_LOG_PREFIX} Found item: {entry_data.get('title', entry_data['url'])}")
                    except json.JSONDecodeError:
                        output_queue.put(f"{MSG_LOG_PREFIX} (Playlist Fetch) {line_strip}")
                        pass

            urls = temp_urls

            stderr_output = process.stderr.read()
            process.stdout.close()
            process.stderr.close()
            return_code = process.wait()

            if return_code == 0:
                output_queue.put(f"{MSG_LOG_PREFIX} Successfully fetched {len(urls)} items from playlist.")
                return urls
            else:
                error_msg = f"Failed to fetch playlist items (yt-dlp code {return_code}). Stderr: {stderr_output.strip()[:200]}"
                output_queue.put(f"{MSG_LOG_PREFIX} ERROR: {error_msg}")
                output_queue.put((MSG_DOWNLOAD_ERROR_DETAILS, f"Playlist fetch failed: {error_msg}"))
                return None

        except FileNotFoundError:
            output_queue.put(f"{MSG_LOG_PREFIX} ERROR: yt-dlp not found for playlist fetch.")
            output_queue.put((MSG_DOWNLOAD_ERROR_DETAILS, "yt-dlp command not found for playlist processing. Ensure it's installed."))
            return None
        except Exception as e:
            output_queue.put(f"{MSG_LOG_PREFIX} ERROR: Unexpected error fetching playlist: {e}")
            output_queue.put((MSG_DOWNLOAD_ERROR_DETAILS, f"Unexpected error fetching playlist: {type(e).__name__} - {e}"))
            return None

    def run_playlist_download_threaded(self, playlist_url, cancel_event: threading.Event):
        """
        Manages the download of an entire playlist or batch of URLs in a dedicated thread.
        This thread is responsible for fetching URLs and then *queuing* individual download tasks
        to the main download_queue, letting the main process_download_queue handle actual execution.
        """
        self.app.log_message(f"Starting playlist download process in background for: {playlist_url}")
        self.current_playlist_download_info = {
            "total_items": 0, "completed_items": 0, "failed_items": 0, "skipped_items": 0, "cancelled": False
        }

        def playlist_download_worker():
            playlist_urls = self._fetch_playlist_urls(playlist_url, self.app.download_queue, cancel_event)

            if playlist_urls is None:
                self.app.log_message("Playlist URL fetching aborted or failed.")
                if cancel_event.is_set():
                    self.current_playlist_download_info["cancelled"] = True
                    self.app.download_queue.put((MSG_DOWNLOAD_CANCELLED_SIGNAL, "Playlist fetch cancelled."))
                else:
                    self.app.download_queue.put((MSG_DOWNLOAD_ERROR_DETAILS, "Failed to retrieve playlist items."))
                # Send a final MSG_DOWNLOAD_ITEM_STATUS to trigger UI reset as a 'failure' for the overall playlist process
                self.app.download_queue.put((
                    MSG_DOWNLOAD_ITEM_STATUS, "PLAYLIST_OVERALL", {
                        "status": "failed", # Overall status of playlist
                        "message": "Playlist fetch failed or was cancelled.",
                        "is_playlist_item": False, # This is an overall signal, not individual item
                        "download_success": False,
                        "download_date_str": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                    }
                ))
                return

            self.current_playlist_download_info["total_items"] = len(playlist_urls)
            self.app.log_message(f"Found {len(playlist_urls)} videos in playlist. Queuing for download.")
            self.app.after(0, lambda: self.app.progress_details_label.configure(
                text=f"Queued {len(playlist_urls)} items. Downloading 0/{len(playlist_urls)} (0% Complete)"
            ))
            self.app.after(0, lambda: self.app.progress_bar.set(0))

            for i, url in enumerate(playlist_urls):
                if cancel_event.is_set():
                    self.current_playlist_download_info["cancelled"] = True
                    self.app.log_message(f"Playlist queuing cancelled by user after {i} items queued.")
                    self.app.download_queue.put((MSG_DOWNLOAD_CANCELLED_SIGNAL, "Playlist queuing cancelled."))
                    break

                # Queue the download for the main thread to pick up and process
                self.app.download_queue.put((
                    MSG_DOWNLOAD_ITEM_ADDED, # Type to signal main thread to create UI and start download
                    # `download_id` will be generated by `download_logic.run_download_process`
                    # `download_id` needs to be passed here for the main app to track its UI before it's started
                    # Let's generate a temporary ID here, which will be overwritten by download_logic.
                    # Or, better, just pass the item_data and let main app generate its UI key.
                    # This item data will contain everything needed to initiate a download.
                    str(uuid.uuid4()), # Use a temporary ID for the ADDED message itself
                    {
                        "url": url,
                        "playlist_item_index": i + 1,
                        "download_type": self.app.download_type_var.get(),
                        "selected_format_code": self.app.settings.get("selected_format_code", "best"),
                        "download_subtitles": self.app.settings.get("download_subtitles", False),
                        "subtitle_languages": self.app.settings.get("subtitle_languages", "en"),
                        "embed_subtitles": self.app.settings.get("embed_subtitles", True),
                        "is_playlist_item": True,
                        "title": f"Playlist Item {i+1}", # Temporary title
                        "cancel_event": cancel_event # Pass the shared cancel_event for this item
                    }
                ))
                self.app.log_message(f"Queued playlist item {i+1}: {url}")
                time.sleep(0.05) # Small delay to avoid flooding the queue and allow UI to update

            if not self.current_playlist_download_info["cancelled"]:
                self.app.log_message(
                    f"All {self.current_playlist_download_info['total_items']} items queued for playlist download. "
                    f"Waiting for completion..."
                )
                # No final overall MSG_DONE_ID from here anymore.
                # The main thread's process_download_queue will determine overall completion
                # when the last item's MSG_DOWNLOAD_ITEM_STATUS is received.
            else:
                self.app.log_message(f"Playlist queuing ended prematurely due to cancellation.")

        threading.Thread(target=playlist_download_worker, daemon=True).start()