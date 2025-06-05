# format_fetcher.py
import customtkinter as ctk
from tkinter import messagebox
import subprocess
import sys
import json
import threading
import shlex

from constants import FFMPEG_TIMEOUT, MSG_LOG_PREFIX
from ui_elements.format_selection_window import FormatSelectionWindow # Import the specific window


class FormatFetcher:
    def __init__(self, app_instance):
        self.app = app_instance
        self.format_fetch_thread = None

    def get_available_formats(self):
        """Initiates fetching of available formats for the entered URL."""
        url = self.app.url_var.get().strip()
        if not url:
            self.app.messagebox.showwarning("No URL", "Please enter a media URL first.", parent=self.app)
            return
        if self.format_fetch_thread and self.format_fetch_thread.is_alive():
            self.app.log_message("Format fetching already in progress.")
            return
        self.app.log_message(f"Fetching available formats for: {url}...")
        self.app.get_formats_button.configure(state="disabled", text="🎞️ Fetching...")
        self.format_fetch_thread = threading.Thread(
            target=self._fetch_formats_thread_target, args=(url,), daemon=True
        )
        self.format_fetch_thread.start()

    def _fetch_formats_thread_target(self, url):
        """Thread target for running yt-dlp to list formats."""
        try:
            command = [sys.executable, "-m", "yt_dlp", "--list-formats", "--dump-json", url]
            self.app.format_info_queue.put(
                (MSG_LOG_PREFIX, f"Executing for formats: {shlex.join(command)}")
            )
            process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, encoding='utf-8', errors='replace'
            )
            stdout, stderr = process.communicate(timeout=FFMPEG_TIMEOUT)

            if process.returncode == 0 and stdout:
                # yt-dlp might output multiple JSON objects for playlists or related.
                # We typically want the main video's info, often the first one.
                json_lines = [
                    line for line in stdout.strip().splitlines()
                    if line.strip().startswith("{") and line.strip().endswith("}")
                ]
                if json_lines:
                    # Pass only the first valid JSON object as a string
                    self.app.format_info_queue.put(("FORMAT_JSON_DATA", json_lines[0]))
                else:
                    self.app.format_info_queue.put(
                        ("FORMAT_ERROR", f"No valid JSON object found in yt-dlp output. Output: {stdout.strip()[:200]}...")
                    )
            else:
                error_msg = f"yt-dlp exited with {process.returncode}. "
                if stdout:
                    error_msg += f"Output: {stdout.strip()[:200]}... "
                if stderr:
                    error_msg += f"Stderr: {stderr.strip()[:200]}..."
                if not stdout and not stderr:
                    error_msg = f"Failed to fetch formats (yt-dlp code {process.returncode}, no stdout/stderr)."
                self.app.format_info_queue.put(("FORMAT_ERROR", error_msg))
        except subprocess.TimeoutExpired:
            self.app.format_info_queue.put(("FORMAT_ERROR", "Timeout fetching formats."))
        except FileNotFoundError:
            self.app.format_info_queue.put(("FORMAT_ERROR", "yt-dlp (or python) not found for format fetching. Ensure yt-dlp is installed and in PATH, or install with 'pip install yt-dlp'."))
        except Exception as e:
            self.app.format_info_queue.put(("FORMAT_ERROR", f"Error fetching formats: {type(e).__name__} - {e}"))

    def _parse_formats_json(self, json_string):
        """Parses the JSON output from yt-dlp to extract format information."""
        parsed_formats_list = []
        try:
            data = json.loads(json_string)
            raw_formats = data.get("formats")
            if not raw_formats:
                self.app.log_message(f"No 'formats' array found in JSON. Data: {str(data)[:200]}...")
                return []
            if not isinstance(raw_formats, list):
                self.app.log_message(f"'formats' is not a list. Type: {type(raw_formats)}. Data: {str(raw_formats)[:200]}...")
                return []

            for fmt_json in raw_formats:
                if not isinstance(fmt_json, dict):
                    continue

                def get_val(key, default="-"):
                    return fmt_json.get(key, default) if fmt_json.get(key) is not None else default

                fmt_entry = {
                    "id": get_val("format_id"), "ext": get_val("ext"),
                    "resolution": get_val("resolution", f"{get_val('width', '')}x{get_val('height', '')}" if get_val('width') else "audio only"),
                    "fps": get_val("fps"),
                    "vcodec": get_val("vcodec", "none").split('.')[0], # Remove any '.' from codec name
                    "acodec": get_val("acodec", "none").split('.')[0],
                    "tbr": f"{get_val('tbr', '?')}k" if get_val('tbr', '?') != '?' and get_val('tbr') is not None else get_val('tbr', '-'),
                    "filesize": self.app.history_manager._format_filesize(fmt_json.get("filesize") or fmt_json.get("filesize_approx")), # Reuse filesize formatter
                    "note": get_val("format_note", ""),
                    "protocol": get_val("protocol"),
                    "channels": get_val("audio_channels", "-")
                }
                if fmt_json.get("dynamic_range"):
                    fmt_entry["note"] = f"{fmt_entry['note']} ({fmt_json['dynamic_range']})".strip()
                # Refine resolution/note for audio-only or video-only formats
                if fmt_entry["vcodec"] == "none" and fmt_entry["acodec"] != "none":
                    fmt_entry["resolution"] = "audio only"
                elif fmt_json.get("acodec") == "none" and fmt_json.get("vcodec") != "none":
                    if not fmt_entry["note"] and fmt_entry["resolution"] != "audio only":
                        fmt_entry["note"] = "video only"
                parsed_formats_list.append(fmt_entry)

            # Sort formats by bitrate (tbr) and then by height (resolution)
            def sort_key(fmt):
                try:
                    tbr_val = float(str(fmt.get("tbr", "0")).replace('k', '')) if fmt.get("tbr") and fmt.get("tbr") != '-' else 0
                except ValueError:
                    tbr_val = 0
                try:
                    res_str = str(fmt.get("resolution", "0x0"))
                    height_val = 0
                    if 'x' in res_str:
                        try: height_val = int(res_str.split('x')[-1])
                        except ValueError: pass
                    elif res_str == "audio only":
                        height_val = 0
                    else: # Other resolution strings or "video only"
                        height_val = -1 # A small negative value to sort below real resolutions but above 0 for audio only
                except ValueError:
                    height_val = 0
                return (-tbr_val, -height_val, fmt.get("id")) # Descending bitrate, descending height, then ID

            parsed_formats_list.sort(key=sort_key)
        except json.JSONDecodeError as e:
            self.app.log_message(f"JSONDecodeError: {e}. Data: {json_string[:200]}...");
            return []
        except Exception as e:
            self.app.log_message(f"Error processing formats JSON: {type(e).__name__} - {e}");
            return []
        return parsed_formats_list

    def open_format_selection_window(self, formats_data):
        """Opens or brings to front the format selection window."""
        if self.app.format_selection_window_instance is None or not self.app.format_selection_window_instance.winfo_exists():
            self.app.format_selection_window_instance = FormatSelectionWindow(
                self.app, self.app, formats_data # master is self.app, app_instance is self.app
            )
            self.app.format_selection_window_instance.focus()
        else:
            self.app.format_selection_window_instance.lift()
            self.app.format_selection_window_instance.focus()