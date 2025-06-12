# ui_elements/subprocess_output_processor.py
import subprocess
import sys
import os
import re
import datetime
import threading
import time
import json
import queue
import uuid
import glob

from constants import (
    MSG_LOG_PREFIX,
    MSG_DOWNLOAD_ITEM_UPDATE,
    MSG_DOWNLOAD_ITEM_STATUS,
)

# Helper function to get startupinfo (Windows-specific)
def get_subprocess_startupinfo():
    """Returns platform-specific startupinfo to prevent console window."""
    if sys.platform.startswith("win"):
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        return si
    return None


# Error patterns for yt-dlp output
YT_DLP_ERROR_PATTERNS = [
    (
        re.compile(
            r"ERROR:.*(?:video is unavailable|This video is not available|unavailable in your country)",
            re.IGNORECASE,
        ),
        "Video Unavailable: This video cannot be accessed (e.g., deleted, private, region-blocked).",
    ),
    (
        re.compile(r"ERROR:.*(?:age-restricted)", re.IGNORECASE),
        "Age-Restricted Video: Please ensure you are logged in if required, or access via a browser.",
    ),
    (
        re.compile(r"ERROR:.*(?:private video|requires login)", re.IGNORECASE),
        "Login/Private Video: This video is private or requires login credentials (e.g., channel membership).",
    ),
    (
        re.compile(
            r"ERROR:.*(?:The uploader has not made this video available in your country|geo-restricted)",
            re.IGNORECASE,
        ),
        "Geo-Restricted: Video is not available in your region.",
    ),
    (
        re.compile(
            r"ERROR:.*(?:no video formats found|no audio formats found)",
            re.IGNORECASE,
        ),
        "No Formats Found: yt-dlp could not find any suitable video or audio formats.",
    ),
    (
        re.compile(r"ERROR:.*(?:Too Many Requests|429)", re.IGNORECASE),
        "Rate Limit Exceeded: You are making too many requests. Try again later, or use a VPN.",
    ),
    (
        re.compile(r"ERROR:.*(?:The playlist is empty)", re.IGNORECASE),
        "Empty Playlist: The specified playlist contains no videos.",
    ),
    (
        re.compile(
            r"ERROR:.*(?:VPN detected|Sorry for the interruption|Try again later)",
            re.IGNORECASE,
        ),
        "VPN/Bot Detection: The platform may be detecting VPN or automated access. Try a different connection or method.",
    ),
    (
        re.compile(
            r"ERROR:.*(?:Could not download WebPage|HTTP Error 404|403|400)",
            re.IGNORECASE,
        ),
        "Network/URL Error: Failed to retrieve video information from the URL (e.g., page not found, access denied).",
    ),
    (
        re.compile(r"ERROR:.*(?:Unsupported URL)", re.IGNORECASE),
        "Unsupported URL: The provided URL is not supported by yt-dlp or the specific extractor.",
    ),
    (
        re.compile(r"ERROR:.*(?:Unknown host)", re.IGNORECASE),
        "Network Error: Could not resolve the host name. Check your internet connection.",
    ),
    (
        re.compile(r"ERROR:(.*)", re.IGNORECASE),  # Catch-all for any "ERROR:" line
        "yt-dlp Error: Check log for details.",
    ),
]


def _parse_yt_dlp_error_internal(output_lines):
    """Parses yt-dlp output to identify specific error messages."""
    relevant_lines = output_lines[-500:]
    full_output_string = "\n".join(
        [
            line
            for line in relevant_lines
            if "error" in line.lower()
            or "warning" in line.lower()
            or "fail" in line.lower()
        ]
    )
    if not full_output_string:
        full_output_string = "\n".join(relevant_lines)

    for pattern, message in YT_DLP_ERROR_PATTERNS:
        match = pattern.search(full_output_string)
        if match:
            if (
                pattern == YT_DLP_ERROR_PATTERNS[-1][0]
            ):  # If it's the catch-all error
                captured_error_text = match.group(1).strip()
                if captured_error_text:
                    return f"yt-dlp Error: {captured_error_text[:150]}{'...' if len(captured_error_text) > 150 else ''}"
                else:
                    return message
            else:
                return message
    return None


# Constants for internal use
CREATE_NO_WINDOW = 0x08000000
QUEUE_PUT_TIMEOUT = 0.05
MAX_OUTPUT_LINES_FOR_ERROR_PARSE = 1000


class SubprocessOutputProcessor(threading.Thread):
    """
    Manages a yt-dlp subprocess, reads its stdout/stderr from pipes,
    parses progress, and sends updates to the main application's queue.
    """

    def __init__(
        self,
        command,
        download_id,
        download_dir,
        output_queue,
        generate_thumbnail_func,
        is_playlist_item,
        initial_title,
        download_type,
        subprocess_env_path,
        subtitle_options,
        cancel_event,
    ):
        super().__init__(daemon=True)
        self.command = command
        self.download_id = download_id
        self.download_dir = download_dir
        self.output_queue = output_queue
        self.generate_thumbnail_func = generate_thumbnail_func
        self.is_playlist_item = is_playlist_item
        self.initial_title = initial_title
        self.download_type = download_type
        self.subprocess_env_path = subprocess_env_path
        self.subtitle_options = subtitle_options
        self.cancel_event = cancel_event

        self.process = None
        self.yt_dlp_full_output_for_error_parse = []
        self.final_filename_with_path = None
        self.download_title = self.initial_title

        # Thread-safe locks for shared resources
        self._output_lock = threading.Lock()
        self._filename_lock = threading.Lock()

    def _read_stream(self, stream, stream_name):
        """Reads lines from a stream (stdout/stderr) and processes them."""
        for line in iter(stream.readline, ""):
            if not line:
                break
            line_strip = line.strip()
            if not line_strip:
                continue

            with self._output_lock:
                self.yt_dlp_full_output_for_error_parse.append(
                    f"[{stream_name}] {line_strip}"
                )
                if (
                    len(self.yt_dlp_full_output_for_error_parse)
                    > MAX_OUTPUT_LINES_FOR_ERROR_PARSE
                ):
                    self.yt_dlp_full_output_for_error_parse.pop(0)

            # --- Metadata and Progress Parsing (only for stdout) ---
            if stream_name == "stdout":
                # Try to parse initial JSON metadata
                if line_strip.startswith("{") and line_strip.endswith("}"):
                    try:
                        metadata = json.loads(line_strip)
                        self.download_title = metadata.get(
                            "title", self.initial_title
                        )
                        filepath = metadata.get("filepath") or metadata.get(
                            "_filename"
                        )
                        if filepath:
                            with self._filename_lock:
                                self.final_filename_with_path = (
                                    os.path.normpath(filepath)
                                )
                        try:
                            self.output_queue.put(
                                (
                                    MSG_DOWNLOAD_ITEM_UPDATE,
                                    self.download_id,
                                    {
                                        "title": self.download_title,
                                        "url": self.initial_title,
                                    },
                                ),
                                timeout=QUEUE_PUT_TIMEOUT,
                            )
                        except queue.Full:
                            pass
                        continue  # Skip logging the raw JSON
                    except json.JSONDecodeError:
                        pass  # Not a JSON line, process as normal log

                # Check for progress updates
                if "[download]" in line_strip:
                    progress_match = re.search(
                        r"\[download\]\s+([\d\.]+)%\s+of\s+.*?(?:at\s+([\d\.]+\s*(?:KiB/s|MiB/s|GiB/s|B/s))?)?\s*(?:ETA\s+(.*))?",
                        line_strip,
                    )
                    if progress_match:
                        percent = float(progress_match.group(1))
                        speed = (
                            progress_match.group(2).strip()
                            if progress_match.group(2)
                            else "N/A"
                        )
                        eta = (
                            progress_match.group(3).strip()
                            if progress_match.group(3)
                            else "N/A"
                        )
                        try:
                            self.output_queue.put(
                                (
                                    MSG_DOWNLOAD_ITEM_UPDATE,
                                    self.download_id,
                                    {
                                        "progress_percent": percent,
                                        "speed": speed,
                                        "eta": eta,
                                        "status": "downloading",
                                    },
                                ),
                                timeout=QUEUE_PUT_TIMEOUT,
                            )
                        except queue.Full:
                            pass
                        continue

                # Capture final filename from merge/extract messages
                if "Merging formats into" in line_strip:
                    match = re.search(r'Merging formats into "(.+?)"', line_strip)
                    if match:
                        with self._filename_lock:
                            self.final_filename_with_path = os.path.normpath(
                                match.group(1).strip()
                            )
                elif "Extracting audio to" in line_strip:
                    match = re.search(r"Extracting audio to (.+)", line_strip)
                    if match:
                        with self._filename_lock:
                            self.final_filename_with_path = os.path.normpath(
                                match.group(1).strip()
                            )

            # Log the line to the main app's log view
            try:
                self.output_queue.put(
                    f"{MSG_LOG_PREFIX} [{stream_name}] {line_strip}",
                    timeout=QUEUE_PUT_TIMEOUT,
                )
            except queue.Full:
                pass
        stream.close()

    def run(self):
        try:
            self.process = subprocess.Popen(
                self.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=CREATE_NO_WINDOW
                if sys.platform.startswith("win")
                else 0,
                startupinfo=get_subprocess_startupinfo()
                if sys.platform.startswith("win")
                else None,
                env=self.subprocess_env_path,
            )
            print(
                f"DEBUG: SubprocessOutputProcessor launched yt-dlp process {self.process.pid}."
            )

            stdout_thread = threading.Thread(
                target=self._read_stream,
                args=(self.process.stdout, "stdout"),
                daemon=True,
            )
            stderr_thread = threading.Thread(
                target=self._read_stream,
                args=(self.process.stderr, "stderr"),
                daemon=True,
            )
            stdout_thread.start()
            stderr_thread.start()

            # Monitor for cancellation while the process runs
            while self.process.poll() is None:
                if self.cancel_event.is_set():
                    self.process.terminate()
                    print(
                        f"DEBUG: Cancellation detected. Terminating process {self.process.pid}."
                    )
                    break
                time.sleep(0.1)

            # Wait for the process and reader threads to finish
            self.process.wait(timeout=10)
            stdout_thread.join(timeout=5)
            stderr_thread.join(timeout=5)

        except FileNotFoundError:
            self._send_final_status(
                "failed",
                "yt-dlp command not found. Ensure it is installed and in your system PATH.",
            )
            return
        except Exception as e:
            self._send_final_status(
                "failed",
                f"An unexpected error occurred in processor: {type(e).__name__} - {e}.",
            )
            return
        finally:
            if self.process and self.process.poll() is None:
                self.process.kill()  # Force kill if it's still running

        # --- Finalization ---
        final_return_code = self.process.returncode

        if self.cancel_event.is_set():
            self._send_final_status("cancelled", "Download cancelled by user.")
        elif final_return_code == 0:
            self._finalize_successful_download()
        else:
            specific_error = _parse_yt_dlp_error_internal(
                self.yt_dlp_full_output_for_error_parse
            )
            final_message = (
                specific_error
                if specific_error
                else f"yt-dlp exited with code {final_return_code}. Check log for details."
            )
            self._send_final_status("failed", final_message)

    def _finalize_successful_download(self):
        """Handles thumbnail and subtitle checks for a successful download."""
        with self._filename_lock:
            final_path = self.final_filename_with_path

        if not final_path or not os.path.exists(final_path):
            self._send_final_status(
                "failed",
                "Download process finished, but the final file could not be found.",
            )
            return

        # Handle thumbnail generation
        thumbnail_path = None
        base, _ = os.path.splitext(final_path)
        expected_thumb_path = base + ".jpg"
        if os.path.exists(expected_thumb_path):
            thumbnail_path = expected_thumb_path
        elif callable(self.generate_thumbnail_func):

            def log_adapter(msg):
                try:
                    self.output_queue.put(
                        f"{MSG_LOG_PREFIX} (thumbnail-gen) {msg}",
                        timeout=QUEUE_PUT_TIMEOUT,
                    )
                except queue.Full:
                    pass

            if self.generate_thumbnail_func(
                final_path, expected_thumb_path, log_adapter
            ):
                thumbnail_path = expected_thumb_path

        # Check for subtitles
        sub_indicator = ""
        if self.subtitle_options[0]:  # If download_subtitles was true
            media_base_no_ext, _ = os.path.splitext(os.path.basename(final_path))
            found_sub_file = False
            subtitle_globs = [
                f"{media_base_no_ext}.*{ext}"
                for ext in [".srt", ".vtt", ".ass", ".ssa", ".sub", ".lrc"]
            ]
            for g in subtitle_globs:
                if glob.glob(os.path.join(self.download_dir, g)):
                    found_sub_file = True
                    break
            if found_sub_file or self.subtitle_options[2]:
                sub_indicator = "+Subs"

        self._send_final_status(
            "completed",
            "Download completed successfully.",
            file_path=final_path,
            thumbnail_path=thumbnail_path,
            sub_indicator=sub_indicator,
        )

    def _send_final_status(
        self,
        status,
        message,
        file_path=None,
        thumbnail_path=None,
        sub_indicator="",
    ):
        """Helper to construct and send the final status message to the queue."""
        status_payload = {
            "status": status,
            "message": message,
            "file_path": file_path,
            "download_success": status == "completed",
            "download_date_str": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "item_type_for_history": self.download_type.lower(),
            "is_playlist_item": self.is_playlist_item,
            "title": self.download_title,
            "thumbnail_path": thumbnail_path,
            "sub_indicator": sub_indicator,
        }
        try:
            self.output_queue.put(
                (MSG_DOWNLOAD_ITEM_STATUS, self.download_id, status_payload),
                timeout=QUEUE_PUT_TIMEOUT,
            )
        except queue.Full:
            print(
                f"ERROR: Main queue full. Could not send final status for {self.download_id}"
            )