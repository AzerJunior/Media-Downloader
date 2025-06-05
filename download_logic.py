# download_logic.py
import subprocess
import sys
import os
import re
import datetime
import glob
import threading # NEW: Import threading for Event
import time

from constants import MSG_LOG_PREFIX, MSG_PROGRESS_PREFIX, FFMPEG_TIMEOUT, MSG_DONE_ID, MSG_DOWNLOAD_ERROR_DETAILS, MSG_DOWNLOAD_CANCELLED_SIGNAL # Import new constant
CREATE_NO_WINDOW = 0x08000000 # Windows-specific flag to prevent new console window

def detect_platform(url):
    """Detects the video platform from the URL."""
    if re.search(r"youtube\.com|youtu\.be", url, re.IGNORECASE):
        return "youtube"
    elif re.search(r"instagram\.com", url, re.IGNORECASE):
        return "instagram"
    elif re.search(r"tiktok\.com", url, re.IaGNORECASE):
        return "tiktok"
    else:
        return "other"

def _get_subprocess_startupinfo():
    """Returns platform-specific startupinfo to prevent console window."""
    if sys.platform.startswith('win'):
        # On Windows, use STARTUPINFO and CREATE_NO_WINDOW
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW # Ensures wShowWindow is used
        si.wShowWindow = subprocess.SW_HIDE # Hides the window
        return si
    return None # Not needed for other OS, or handled differently

def generate_thumbnail_from_video_logic(video_path, output_thumb_path, log_func):
    """
    Generates a thumbnail from the middle frame of the video using ffmpeg.
    Uses a provided log_func for logging messages.
    """
    if not os.path.exists(video_path):
        log_func(f"Video file not found for thumbnail generation: {video_path}")
        return False
    try:
        ffprobe_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                       "-of", "default=noprint_wrappers=1:nokey=1", video_path]
        process = subprocess.run(
            ffprobe_cmd,
            capture_output=True,
            check=False,
            timeout=FFMPEG_TIMEOUT,
            # --- NEW ADDITION ---
            creationflags=CREATE_NO_WINDOW if sys.platform.startswith('win') else 0,
            startupinfo=_get_subprocess_startupinfo() if sys.platform.startswith('win') else None
            # --- END NEW ---
        )
        stdout_str = process.stdout.decode('utf-8', errors='replace').strip()
        stderr_str = process.stderr.decode('utf-8', errors='replace').strip()

        if process.returncode != 0 or not stdout_str:
            log_func(f"ffprobe failed for {os.path.basename(video_path)}. Error: {stderr_str if stderr_str else 'No output/Unknown error'}")
            return False

        duration_str = stdout_str
        duration = float(duration_str)
        mid_point = duration / 2

        ffmpeg_cmd = ["ffmpeg", "-ss", str(mid_point), "-i", video_path,
                      "-vframes", "1", "-q:v", "2", "-y", output_thumb_path]
        process_ffmpeg = subprocess.run(
            ffmpeg_cmd,
            capture_output=True,
            check=False,
            timeout=FFMPEG_TIMEOUT,
            # --- NEW ADDITION ---
            creationflags=CREATE_NO_WINDOW if sys.platform.startswith('win') else 0,
            startupinfo=_get_subprocess_startupinfo() if sys.platform.startswith('win') else None
            # --- END NEW ---
        )
        ffmpeg_stderr_str = process_ffmpeg.stderr.decode('utf-8', errors='replace').strip()

        if process_ffmpeg.returncode != 0:
            log_func(f"ffmpeg failed for {os.path.basename(video_path)}. Error: {ffmpeg_stderr_str}")
            return False
        if os.path.exists(output_thumb_path):
            log_func(f"Successfully generated thumbnail: {os.path.basename(output_thumb_path)}")
            return True
        else:
            log_func(f"ffmpeg ran for {os.path.basename(video_path)} but thumbnail not found: {os.path.basename(output_thumb_path)}. Stderr: {ffmpeg_stderr_str}")
            return False
    except FileNotFoundError:
        log_func("ffmpeg or ffprobe not found. Please ensure they are installed and in your system PATH.")
        return False
    except subprocess.TimeoutExpired:
        log_func(f"ffmpeg/ffprobe command timed out for {os.path.basename(video_path)}.")
        return False
    except ValueError:
        log_func(f"Could not parse duration from ffprobe output for {os.path.basename(video_path)}: '{duration_str if 'duration_str' in locals() else 'N/A'}'")
        return False
    except Exception as e:
        log_func(f"Error generating thumbnail for {os.path.basename(video_path)}: {type(e).__name__} - {e}")
        return False

def get_media_duration_logic(file_path, log_func):
    """
    Fetches the duration of a media file using ffprobe.
    Returns duration in seconds as float, or None if failed.
    """
    if not os.path.exists(file_path):
        log_func(f"File not found for duration probe: {file_path}")
        return None
    try:
        ffprobe_cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path
        ]
        process = subprocess.run(
            ffprobe_cmd,
            capture_output=True,
            check=False,
            timeout=FFMPEG_TIMEOUT,
            # --- NEW ADDITION ---
            creationflags=CREATE_NO_WINDOW if sys.platform.startswith('win') else 0,
            startupinfo=_get_subprocess_startupinfo() if sys.platform.startswith('win') else None
            # --- END NEW ---
        )
        stdout_str = process.stdout.decode('utf-8', errors='replace').strip()
        stderr_str = process.stderr.decode('utf-8', errors='replace').strip()

        if process.returncode == 0 and stdout_str:
            try:
                duration_seconds = float(stdout_str)
                return duration_seconds
            except ValueError:
                log_func(f"Could not parse duration from ffprobe output for {os.path.basename(file_path)}: '{stdout_str}'")
                return None
        else:
            log_func(f"ffprobe failed to get duration for {os.path.basename(file_path)}. Error: {stderr_str if stderr_str else 'No output/Unknown error'}")
            return None
    except FileNotFoundError:
        log_func("ffprobe not found. Please ensure it is installed and in your system PATH for duration detection.")
        return None
    except subprocess.TimeoutExpired:
        log_func(f"ffprobe command timed out getting duration for {os.path.basename(file_path)}.")
        return None
    except Exception as e:
        log_func(f"Error getting duration for {os.path.basename(file_path)}: {type(e).__name__} - {e}")
        return None


# --- Define common yt-dlp error patterns ---
YT_DLP_ERROR_PATTERNS = [
    (re.compile(r"ERROR:.*(?:video is unavailable|This video is not available|unavailable in your country)", re.IGNORECASE),
     "Video Unavailable: This video cannot be accessed (e.g., deleted, private, region-blocked)."),

    (re.compile(r"ERROR:.*(?:age-restricted)", re.IGNORECASE),
     "Age-Restricted Video: Please ensure you are logged in if required, or access via a browser."),

    (re.compile(r"ERROR:.*(?:private video|requires login)", re.IGNORECASE),
     "Login/Private Video: This video is private or requires login credentials (e.g., channel membership)."),

    (re.compile(r"ERROR:.*(?:The uploader has not made this video available in your country|geo-restricted)", re.IGNORECASE),
     "Geo-Restricted: Video is not available in your region."),

    (re.compile(r"ERROR:.*(?:no video formats found|no audio formats found)", re.IGNORECASE),
     "No Formats Found: yt-dlp could not find any suitable video or audio formats."),

    (re.compile(r"ERROR:.*(?:Too Many Requests|429)", re.IGNORECASE),
     "Rate Limit Exceeded: You are making too many requests. Try again later, or use a VPN."),

    (re.compile(r"ERROR:.*(?:The playlist is empty)", re.IGNORECASE),
     "Empty Playlist: The specified playlist contains no videos."),

    (re.compile(r"ERROR:.*(?:VPN detected|Sorry for the interruption|Try again later)", re.IGNORECASE),
     "VPN/Bot Detection: The platform may be detecting VPN or automated access. Try a different connection or method."),

    (re.compile(r"ERROR:.*(?:Could not download WebPage|HTTP Error 404|403|400)", re.IGNORECASE),
     "Network/URL Error: Failed to retrieve video information from the URL (e.g., page not found, access denied)."),

    (re.compile(r"ERROR:.*(?:Unsupported URL)", re.IGNORECASE),
     "Unsupported URL: The provided URL is not supported by yt-dlp or the specific extractor."),

    (re.compile(r"ERROR:.*(?:Unknown host)", re.IGNORECASE),
     "Network Error: Could not resolve the host name. Check your internet connection."),

    (re.compile(r"ERROR:(.*)", re.IGNORECASE), # Catch-all for any "ERROR:" line
     "yt-dlp Error: Check log for details."),
]

def parse_yt_dlp_error(output_lines):
    """
    Parses yt-dlp output lines to find a specific, user-friendly error message.
    Returns a string if a specific error is found, otherwise None.
    """
    full_output_string = "\n".join([line for line in output_lines if "error" in line.lower() or "warning" in line.lower() or "fail" in line.lower()])
    if not full_output_string:
        full_output_string = "\n".join(output_lines[-10:])

    for pattern, message in YT_DLP_ERROR_PATTERNS:
        match = pattern.search(full_output_string)
        if match:
            if pattern == YT_DLP_ERROR_PATTERNS[-1][0]:
                captured_error_text = match.group(1).strip()
                if captured_error_text:
                    return f"yt-dlp Error: {captured_error_text[:150]}{'...' if len(captured_error_text) > 150 else ''}"
                else:
                    return message
            else:
                return message
    return None

# NEW: Added cancel_event parameter to the function signature
def run_download_process(url, platform, download_type, download_dir,
                         output_queue, generate_thumbnail_func,
                         selected_format_code="best",
                         download_subtitles=False,
                         subtitle_languages="en",
                         embed_subtitles=True,
                         cancel_event: threading.Event = None):
    download_success = False
    final_filename_with_path = None
    thumbnail_file_path = None
    item_type_for_history = "video" if download_type == "Video" else "audio"
    yt_dlp_output_lines = []
    was_cancelled = False

    base_command = [sys.executable, "-m", "yt_dlp"]
    format_options = []
    output_template_base = "%(title)s.%(ext)s"
    if platform in ["instagram", "tiktok"]:
        output_template_base = "%(uploader)s - %(title)s.%(ext)s"

    additional_args = ["--no-warnings", "--write-thumbnail", "--convert-thumbnails", "jpg"]

    if selected_format_code and selected_format_code.lower() != "best":
        format_options = ["-f", selected_format_code]
        if download_type == "Video":
             additional_args.extend(["--merge-output-format", "mp4"])
    else:
        if download_type == "Audio":
            format_options = ["-f", "bestaudio[ext=m4a]/bestaudio", "--extract-audio", "--audio-format", "m4a"]
        else:
            if platform == "youtube":
                format_options = ["-f", "bestvideo[ext=mp4][vcodec^=avc]+bestaudio[ext=m4a]/best[ext=mp4]/best", "--merge-output-format", "mp4"]
            else:
                format_options = ["-f", "bestvideo+bestaudio/best", "--merge-output-format", "mp4"]

    if download_subtitles:
        additional_args.append("--write-subs")
        if subtitle_languages and subtitle_languages.lower() == "all":
            additional_args.append("--all-subs")
        elif subtitle_languages:
            additional_args.extend(["--sub-lang", subtitle_languages])

        if embed_subtitles:
            additional_args.append("--embed-subs")

    command = (base_command + format_options +
         ["-P", download_dir, "-o", output_template_base] +
         additional_args + [url]
    )
    output_queue.put(f"{MSG_LOG_PREFIX} Executing: {' '.join(command)}")

    process = None
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            errors='replace',
            # --- NEW ADDITION ---
            creationflags=CREATE_NO_WINDOW if sys.platform.startswith('win') else 0,
            startupinfo=_get_subprocess_startupinfo() if sys.platform.startswith('win') else None
            # --- END NEW ---
        )
        while True:
            if cancel_event and cancel_event.is_set():
                output_queue.put(f"{MSG_LOG_PREFIX} Cancellation signal received. Terminating yt-dlp process...")
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        output_queue.put(f"{MSG_LOG_PREFIX} yt-dlp process killed due to timeout during termination.")
                was_cancelled = True
                break

            line = process.stdout.readline()
            if not line:
                if process.poll() is not None: break
                else:
                    time.sleep(0.05)
                    continue

            line_strip = line.strip()
            if not line_strip:
                continue

            yt_dlp_output_lines.append(line_strip)
            output_queue.put(f"{MSG_LOG_PREFIX} {line_strip}")

            if "Merging formats into" in line_strip:
                merged_file_match = re.search(r'Merging formats into "(.+?)"', line_strip)
                if merged_file_match:
                    final_filename_with_path = merged_file_match.group(1).strip()
            elif "Extracting audio to" in line_strip:
                audio_file_match = re.search(r'Extracting audio to (.+)', line_strip)
                if audio_file_match:
                    final_filename_with_path = audio_file_match.group(1).strip()
            elif "Destination:" in line_strip and not final_filename_with_path:
                dest_file_match = re.search(r'Destination: (.+)', line_strip)
                if dest_file_match:
                    potential_fn = dest_file_match.group(1).strip()
                    if not potential_fn.lower().endswith((".part", ".ytdl")):
                        final_filename_with_path = potential_fn


            progress_match = re.search(r"\[download\]\s+([\d\.]+%)", line_strip)
            if progress_match: output_queue.put(f"{MSG_PROGRESS_PREFIX} {progress_match.group(1)}")

        process.stdout.close()
        return_code = process.poll()

        if was_cancelled:
            output_queue.put((MSG_DOWNLOAD_CANCELLED_SIGNAL, "User cancelled download."))
            return

        download_timestamp_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

        if return_code == 0:
            download_success = True
            output_queue.put(f"{MSG_LOG_PREFIX} yt-dlp process completed successfully.")
            if final_filename_with_path:
                if not os.path.isabs(final_filename_with_path):
                    final_filename_with_path = os.path.join(download_dir, os.path.basename(final_filename_with_path))

                if not os.path.exists(final_filename_with_path):
                    output_queue.put(f"{MSG_LOG_PREFIX} ERROR: yt-dlp reported success, but output file not found: {final_filename_with_path}")
                    download_success = False
                else:
                    base, _ = os.path.splitext(final_filename_with_path)
                    expected_thumb_path = base + ".jpg"

                    if os.path.exists(expected_thumb_path):
                        thumbnail_file_path = expected_thumb_path
                        output_queue.put(f"{MSG_LOG_PREFIX} Thumbnail/AlbumArt found: {os.path.basename(thumbnail_file_path)}")
                    elif item_type_for_history == "video":
                        def log_to_queue_func(msg): output_queue.put(f"{MSG_LOG_PREFIX} (ffmpeg) {msg}")
                        if generate_thumbnail_func(final_filename_with_path, expected_thumb_path, log_to_queue_func):
                            thumbnail_file_path = expected_thumb_path
            else:
                output_queue.put(f"{MSG_LOG_PREFIX} WARNING: yt-dlp process finished, but no output filename was definitively captured. Check logs.")
        else:
            download_success = False
            specific_error_message = parse_yt_dlp_error(yt_dlp_output_lines)

            if specific_error_message:
                output_queue.put((MSG_DOWNLOAD_ERROR_DETAILS, specific_error_message))
                output_queue.put(f"{MSG_LOG_PREFIX} Download Failed: {specific_error_message}")
            else:
                error_summary_lines = [line for line in yt_dlp_output_lines if "ERROR:" in line.upper() or "WARNING:" in line.upper()]
                error_message = f"Download Error: yt-dlp exited with code {return_code}."
                if error_summary_lines:
                    error_message += f" Details: {' '.join(error_summary_lines[-5:])[:300]}"
                    if len(' '.join(error_summary_lines[-5:])) > 300: error_message += "..."
                output_queue.put(f"{MSG_LOG_PREFIX} {error_message}")

    except FileNotFoundError:
        download_success = False
        output_queue.put((MSG_DOWNLOAD_ERROR_DETAILS, "yt-dlp (or python) command not found. Please ensure yt-dlp is installed and in your system PATH."))
        output_queue.put(f"{MSG_LOG_PREFIX} Download Error: yt-dlp or Python not found.")
        download_timestamp_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    except subprocess.TimeoutExpired:
        download_success = False
        output_queue.put((MSG_DOWNLOAD_ERROR_DETAILS, f"yt-dlp download timed out (exceeded {FFMPEG_TIMEOUT} seconds). This may indicate a network issue or a very large file taking too long."))
        output_queue.put(f"{MSG_LOG_PREFIX} Download Error: yt-dlp command timed out.")
        download_timestamp_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    except Exception as e:
        download_success = False
        output_queue.put((MSG_DOWNLOAD_ERROR_DETAILS, f"An unexpected error occurred: {type(e).__name__} - {e}. Check log for details."))
        output_queue.put(f"{MSG_LOG_PREFIX} Download Error: {type(e).__name__} - {e}")
        download_timestamp_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    finally:
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
            output_queue.put(f"{MSG_LOG_PREFIX} Forcibly terminated yt-dlp process in finally block.")

        history_file_basename = "Unknown Media"
        history_file_path = None
        sub_indicator = ""

        if was_cancelled:
            # Already handled by returning early if was_cancelled is True
            pass
        elif download_success and final_filename_with_path and os.path.exists(final_filename_with_path):
            history_file_path = final_filename_with_path
            history_file_basename = os.path.basename(final_filename_with_path)
            if download_subtitles:
                media_base_no_ext, _ = os.path.splitext(history_file_basename)
                found_sub_file = False
                subtitle_globs = [f"{media_base_no_ext}.*{ext}" for ext in ['.srt', '.vtt', '.ass', '.ssa', '.sub']]
                for g in subtitle_globs:
                    if glob.glob(os.path.join(download_dir, g)):
                        found_sub_file = True
                        break

                if found_sub_file or (embed_subtitles and download_success):
                    sub_indicator = "+Subs"
        elif download_success and final_filename_with_path:
            history_file_basename = f"[File Missing] {os.path.basename(final_filename_with_path)}"
            download_success = False
        elif not download_success:
            url_part = url.split('/')[-1].split('?')[0]
            history_file_basename = f"[Failed] {url_part[:30]}"

        if not download_timestamp_str:
             download_timestamp_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

        if not was_cancelled: # Only send MSG_DONE_ID if not explicitly cancelled
            output_queue.put((MSG_DONE_ID, download_success, history_file_basename,
                              history_file_path, item_type_for_history, thumbnail_file_path,
                              sub_indicator, download_timestamp_str))