# download_logic.py
import subprocess
import sys
import os
import re
import datetime
import glob
import threading
import time
import uuid

from constants import (
    MSG_LOG_PREFIX, MSG_PROGRESS_PREFIX, FFMPEG_TIMEOUT, # MSG_PROGRESS_PREFIX now primarily for log
    MSG_DONE_ID, MSG_DOWNLOAD_ERROR_DETAILS, MSG_DOWNLOAD_CANCELLED_SIGNAL,
    MSG_DOWNLOAD_ITEM_UPDATE, MSG_DOWNLOAD_ITEM_STATUS, MSG_DOWNLOAD_ITEM_ADDED
)

# Constant for subprocess flags (Windows-specific)
CREATE_NO_WINDOW = 0x08000000


def _get_subprocess_startupinfo():
    """Returns platform-specific startupinfo to prevent console window."""
    if sys.platform.startswith('win'):
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        return si
    return None


def detect_platform(url):
    """Detects the video platform from the URL."""
    if re.search(r"youtube\.com|youtu\.be", url, re.IGNORECASE):
        return "youtube"
    elif re.search(r"instagram\.com", url, re.IGNORECASE):
        return "instagram"
    elif re.search(r"tiktok\.com", url, re.IGNORECASE):
        return "tiktok"
    else:
        return "other"


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
            creationflags=CREATE_NO_WINDOW if sys.platform.startswith('win') else 0,
            startupinfo=_get_subprocess_startupinfo() if sys.platform.startswith('win') else None
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
            creationflags=CREATE_NO_WINDOW if sys.platform.startswith('win') else 0,
            startupinfo=_get_subprocess_startupinfo() if sys.platform.startswith('win') else None
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


def extract_album_art_logic(audio_path, output_art_path, log_func):
    """
    Attempts to extract embedded album art from an audio file using ffmpeg.
    Returns True if art is extracted, False otherwise.
    """
    if not os.path.exists(audio_path):
        log_func(f"Audio file not found for album art extraction: {audio_path}")
        return False
    try:
        # Check if there's an attached picture stream (often stream 0:0 or 0:V)
        # Using -dn to disable data stream, -vn to disable video stream, -an to disable audio stream (for output only)
        # -vframes 1 to extract just one frame
        # -map 0:v:0 to map the first video/picture stream (if any) from input
        # -map 0:m:handler_name:pict to map specifically by metadata tag (more robust for album art)
        # Try a few common approaches:
        # 1. Map any video stream (often embedded cover art is treated as video stream)
        ffmpeg_cmd_attempt_1 = ["ffmpeg", "-i", audio_path, "-map", "0:v", "-map", "-0:V?", "-c:v", "copy", "-f", "mjpeg", "-vframes", "1", "-y", output_art_path]
        # 2. Map attachments that are images (more specific for ID3 art)
        # This requires identifying stream type. Simpler to let ffmpeg pick best available picture.
        # Let's try the general 'map 0:v' first as it often captures embedded art.

        log_func(f"Attempting to extract album art from {os.path.basename(audio_path)}")
        process = subprocess.run(
            ffmpeg_cmd_attempt_1,
            capture_output=True,
            check=False, # Don't raise CalledProcessError if extraction fails
            timeout=FFMPEG_TIMEOUT,
            creationflags=CREATE_NO_WINDOW if sys.platform.startswith('win') else 0,
            startupinfo=_get_subprocess_startupinfo() if sys.platform.startswith('win') else None
        )
        stderr_str = process.stderr.decode('utf-8', errors='replace').strip()

        if process.returncode == 0 and os.path.exists(output_art_path):
            log_func(f"Successfully extracted album art: {os.path.basename(output_art_path)}")
            return True
        else:
            log_func(f"Failed to extract album art from {os.path.basename(audio_path)}. Stderr: {stderr_str}")
            # Fails silently if no video stream found (which is correct for non-art audio)
            return False
    except FileNotFoundError:
        log_func("ffmpeg not found. Please ensure it is installed and in your system PATH for album art extraction.")
        return False
    except subprocess.TimeoutExpired:
        log_func(f"ffmpeg album art extraction timed out for {os.path.basename(audio_path)}.")
        return False
    except Exception as e:
        log_func(f"Error extracting album art for {os.path.basename(audio_path)}: {type(e).__name__} - {e}")
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
            creationflags=CREATE_NO_WINDOW if sys.platform.startswith('win') else 0,
            startupinfo=_get_subprocess_startupinfo() if sys.platform.startswith('win') else None
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


def run_download_process(url, platform, download_type, download_dir,
                         output_queue, generate_thumbnail_func,
                         selected_format_code="best",
                         download_subtitles=False,
                         subtitle_languages="en",
                         embed_subtitles=True,
                         cancel_event: threading.Event = None,
                         is_playlist_item: bool = False):
    download_id = str(uuid.uuid4())

    download_success = False
    final_filename_with_path = None
    thumbnail_file_path = None
    item_type_for_history = "video" if download_type == "Video" else "audio"
    yt_dlp_output_lines = []
    was_cancelled = False
    download_title = url # Default title if not found later

    download_timestamp_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    output_queue.put((MSG_DOWNLOAD_ITEM_ADDED, download_id, {
        "url": url,
        "title": download_title, # Temporary title, will be updated by yt-dlp output
        "type": download_type,
        "platform": platform,
        "is_playlist_item": is_playlist_item,
        "status": "starting" # Initial status
    }))


    base_command = [sys.executable, "-m", "yt_dlp"]
    format_options = []
    output_template_base = "%(title)s.%(ext)s" # Default output template
    # Also request --print-json to parse actual title if different from templated filename
    # and to potentially use other metadata.
    additional_args = ["--no-warnings", "--write-thumbnail", "--convert-thumbnails", "jpg", "--print-json"]

    if platform in ["instagram", "tiktok"]:
        output_template_base = "%(uploader)s - %(title)s.%(ext)s"

    if selected_format_code and selected_format_code.lower() != "best":
        format_options = ["-f", selected_format_code]
        if download_type == "Video":
             additional_args.extend(["--merge-output-format", "mp4"])
    else:
        if download_type == "Audio":
            format_options = ["-f", "bestaudio[ext=m4a]/bestaudio", "--extract-audio", "--audio-format", "m4a"]
        else: # Default for Video (or fallback for others)
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
         ["-P", download_dir, "-o", output_template_base] + # Ensure output path is correct
         additional_args + [url]
    )
    output_queue.put(f"{MSG_LOG_PREFIX} Executing: {' '.join(command)}")

    process = None
    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, # Merge stderr into stdout for parsing unified output
            text=True,
            encoding='utf-8',
            errors='replace',
            creationflags=CREATE_NO_WINDOW if sys.platform.startswith('win') else 0,
            startupinfo=_get_subprocess_startupinfo() if sys.platform.startswith('win') else None
        )

        initial_metadata_json = [] # To capture initial metadata before download starts
        parsing_metadata = True

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

            yt_dlp_output_lines.append(line_strip) # Collect all lines for error parsing

            # Attempt to parse initial JSON metadata (if --print-json used)
            # This is typically the very first output before download starts.
            if parsing_metadata:
                try:
                    if line_strip.startswith("{") and line_strip.endswith("}"):
                        metadata = json.loads(line_strip)
                        download_title = metadata.get("title", url)
                        # The final file path from metadata (post-processing name)
                        # yt-dlp might provide 'filepath' or similar after processing.
                        # For --onefile, it's often the 'requested_downloads' path or 'filename'
                        final_filename_from_metadata = metadata.get("filepath") or \
                                                       metadata.get("_filename")
                        if final_filename_from_metadata:
                            # Normalize path to handle different OS separators
                            final_filename_from_metadata = os.path.normpath(final_filename_from_metadata)
                            # Prepend download_dir if it's not already absolute
                            if not os.path.isabs(final_filename_from_metadata):
                                final_filename_from_metadata = os.path.join(download_dir, final_filename_from_metadata)
                            final_filename_with_path = final_filename_from_metadata
                            
                        # Update the item with actual title
                        output_queue.put((MSG_DOWNLOAD_ITEM_UPDATE, download_id, {"title": download_title, "url": url})) # Title based on metadata
                        parsing_metadata = False # Stop trying to parse metadata after first successful one
                except json.JSONDecodeError:
                    pass # Not a JSON line, continue

            # Extract final filename from Destination/Merging lines (fallback if metadata parse failed or name changes post-proc)
            if "Merging formats into" in line_strip:
                merged_file_match = re.search(r'Merging formats into "(.+?)"', line_strip)
                if merged_file_match: final_filename_with_path = os.path.normpath(merged_file_match.group(1).strip())
            elif "Extracting audio to" in line_strip:
                audio_file_match = re.search(r'Extracting audio to (.+)', line_strip)
                if audio_file_match: final_filename_with_path = os.path.normpath(audio_file_match.group(1).strip())
            elif "Destination:" in line_strip and not final_filename_with_path: # Fallback to Destination
                dest_file_match = re.search(r'Destination: (.+)', line_strip)
                if dest_file_match:
                    potential_fn = os.path.normpath(dest_file_match.group(1).strip())
                    if not potential_fn.lower().endswith((".part", ".ytdl")):
                        final_filename_with_path = potential_fn


            # Extract progress, speed, ETA and send as structured update
            progress_match = re.search(r"\[download\]\s+([\d\.]+)%\s+of\s+.*?(?:at\s+([\d\.]+\s*(?:KiB/s|MiB/s|GiB/s|B/s))?)?\s*(?:ETA\s+(.*))?", line_strip)
            if progress_match:
                percent = float(progress_match.group(1))
                speed = progress_match.group(2).strip() if progress_match.group(2) else "N/A"
                eta = progress_match.group(3).strip() if progress_match.group(3) else "N/A"
                output_queue.put((MSG_DOWNLOAD_ITEM_UPDATE, download_id, {
                    "progress_percent": percent,
                    "speed": speed,
                    "eta": eta,
                    "status": "downloading"
                }))

            # Also log these lines to the main app's log for full console output reference
            output_queue.put(f"{MSG_LOG_PREFIX} {line_strip}")


        process.stdout.close()
        return_code = process.poll()

        # Handle cancellation separately
        if was_cancelled:
            output_queue.put((MSG_DOWNLOAD_ITEM_STATUS, download_id, {
                "status": "cancelled",
                "message": "Download cancelled by user.",
                "file_path": final_filename_with_path,
                "download_success": False,
                "download_date_str": download_timestamp_str,
                "item_type_for_history": item_type_for_history,
                "is_playlist_item": is_playlist_item,
                "title": download_title # Pass the best known title
            }))
            return

        # Determine final status and send MSG_DOWNLOAD_ITEM_STATUS
        final_status = "failed"
        final_message = "Download failed due to unexpected error."
        if return_code == 0:
            download_success = True
            if final_filename_with_path and os.path.exists(final_filename_with_path):
                final_status = "completed"
                final_message = "Download completed successfully."
            else:
                final_status = "failed"
                final_message = "Download completed, but output file not found on disk."
                download_success = False
        else: # Non-zero return code
            download_success = False
            specific_error_message = parse_yt_dlp_error(yt_dlp_output_lines)
            final_message = specific_error_message if specific_error_message else f"yt-dlp exited with code {return_code}. Check log for details."


        # Prepare payload for MSG_DOWNLOAD_ITEM_STATUS
        status_payload = {
            "status": final_status,
            "message": final_message,
            "file_path": final_filename_with_path,
            "download_success": download_success,
            "download_date_str": download_timestamp_str,
            "item_type_for_history": item_type_for_history,
            "is_playlist_item": is_playlist_item,
            "title": download_title # Pass the best known title
        }

        # Handle thumbnail if successfully downloaded
        if download_success and final_filename_with_path and os.path.exists(final_filename_with_path):
            base, _ = os.path.splitext(final_filename_with_path)
            expected_thumb_path = base + ".jpg" # yt-dlp's default

            # Prioritize yt-dlp's downloaded thumbnail
            if os.path.exists(expected_thumb_path):
                thumbnail_file_path = expected_thumb_path
                output_queue.put(f"{MSG_LOG_PREFIX} Thumbnail/AlbumArt found from yt-dlp: {os.path.basename(thumbnail_file_path)}")
            # If it's audio and yt-dlp didn't provide a thumbnail, try to extract embedded art
            elif item_type_for_history == "audio":
                expected_art_path = base + "_art.jpg" # Separate name for extracted art
                def log_to_queue_func(msg): output_queue.put(f"{MSG_LOG_PREFIX} (ffmpeg-art) {msg}")
                if extract_album_art_logic(final_filename_with_path, expected_art_path, log_to_queue_func):
                    thumbnail_file_path = expected_art_path
                    output_queue.put(f"{MSG_LOG_PREFIX} Extracted album art using ffmpeg: {os.path.basename(thumbnail_file_path)}")
                else:
                    output_queue.put(f"{MSG_LOG_PREFIX} No embedded album art found for {os.path.basename(final_filename_with_path)}.")
            # If it's video and no yt-dlp thumbnail, generate one from video
            elif item_type_for_history == "video":
                def log_to_queue_func(msg): output_queue.put(f"{MSG_LOG_PREFIX} (ffmpeg-thumb) {msg}")
                if generate_thumbnail_func(final_filename_with_path, expected_thumb_path, log_to_queue_func):
                    thumbnail_file_path = expected_thumb_path
            status_payload["thumbnail_path"] = thumbnail_file_path # Update payload with final path

            # Subtitle indicator
            if download_subtitles:
                media_base_no_ext, _ = os.path.splitext(os.path.basename(final_filename_with_path))
                found_sub_file = False
                subtitle_globs = [f"{media_base_no_ext}.*{ext}" for ext in ['.srt', '.vtt', '.ass', '.ssa', '.sub']]
                for g in subtitle_globs:
                    if glob.glob(os.path.join(download_dir, g)):
                        found_sub_file = True
                        break
                if found_sub_file or (embed_subtitles and download_success):
                    status_payload["sub_indicator"] = "+Subs"
                else:
                    status_payload["sub_indicator"] = ""
        else: # Download not successful or file not found, no thumbnail
            status_payload["thumbnail_path"] = None
            status_payload["sub_indicator"] = ""

        # Send final structured status message
        output_queue.put((MSG_DOWNLOAD_ITEM_STATUS, download_id, status_payload))

    except FileNotFoundError:
        error_msg = "yt-dlp (or python) command not found. Please ensure yt-dlp is installed and in your system PATH."
        output_queue.put((MSG_DOWNLOAD_ITEM_STATUS, download_id, {
            "status": "failed", "message": error_msg, "file_path": None,
            "download_success": False, "download_date_str": download_timestamp_str,
            "item_type_for_history": item_type_for_history,
            "is_playlist_item": is_playlist_item, "title": download_title
        }))
    except subprocess.TimeoutExpired:
        error_msg = f"yt-dlp download timed out (exceeded {FFMPEG_TIMEOUT} seconds). This may indicate a network issue or a very large file taking too long."
        output_queue.put((MSG_DOWNLOAD_ITEM_STATUS, download_id, {
            "status": "failed", "message": error_msg, "file_path": None,
            "download_success": False, "download_date_str": download_timestamp_str,
            "item_type_for_history": item_type_for_history,
            "is_playlist_item": is_playlist_item, "title": download_title
        }))
    except Exception as e:
        error_msg = f"An unexpected error occurred: {type(e).__name__} - {e}. Check log for details."
        output_queue.put((MSG_DOWNLOAD_ITEM_STATUS, download_id, {
            "status": "failed", "message": error_msg, "file_path": None,
            "download_success": False, "download_date_str": download_timestamp_str,
            "item_type_for_history": item_type_for_history,
            "is_playlist_item": is_playlist_item, "title": download_title
        }))
    finally:
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
            output_queue.put(f"{MSG_LOG_PREFIX} Forcibly terminated yt-dlp process in finally block.")