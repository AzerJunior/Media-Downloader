# download_process_core.py
import subprocess
import sys
import os
import re
import datetime
import threading
import time
import json
import queue
import uuid  # 1. ADDED MISSING IMPORT

from constants import (
    MSG_LOG_PREFIX,
    FFMPEG_TIMEOUT,
    MSG_DOWNLOAD_ITEM_UPDATE,
    MSG_DOWNLOAD_ITEM_STATUS,
    MSG_DOWNLOAD_ITEM_ADDED,
)
from ui_elements.subprocess_output_processor import SubprocessOutputProcessor


def get_subprocess_startupinfo():
    """Returns platform-specific startupinfo to prevent console window."""
    if sys.platform.startswith("win"):
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        return si
    return None


def detect_platform(url):
    """Detects the platform based on the URL."""
    if re.search(r"youtube\.com|youtu\.be", url, re.IGNORECASE):
        return "youtube"
    # Add other platform detections as needed
    return "other"


# 2. ADDED MISSING HELPER FUNCTIONS (MOVED FROM OLD download_logic.py)
def generate_thumbnail_from_video_logic(video_path, output_thumb_path, log_func):
    """Generates a thumbnail from a video file using ffmpeg."""
    if not os.path.exists(video_path):
        log_func(f"Video file not found for thumbnail generation: {video_path}")
        return False
    try:
        ffprobe_cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            video_path,
        ]
        duration_str = subprocess.check_output(
            ffprobe_cmd,
            timeout=FFMPEG_TIMEOUT,
            startupinfo=get_subprocess_startupinfo(),
            env=os.environ.copy(),
        ).decode("utf-8")
        duration = float(duration_str)
        mid_point = duration / 2

        ffmpeg_cmd = [
            "ffmpeg",
            "-ss",
            str(mid_point),
            "-i",
            video_path,
            "-vframes",
            "1",
            "-q:v",
            "2",
            "-y",
            output_thumb_path,
        ]
        subprocess.run(
            ffmpeg_cmd,
            check=True,
            capture_output=True,
            timeout=FFMPEG_TIMEOUT,
            startupinfo=get_subprocess_startupinfo(),
            env=os.environ.copy(),
        )
        log_func(
            f"Successfully generated thumbnail: {os.path.basename(output_thumb_path)}"
        )
        return True
    except Exception as e:
        log_func(
            f"Error generating thumbnail for {os.path.basename(video_path)}: {e}"
        )
        return False


def extract_album_art_logic(audio_path, output_art_path, log_func):
    """Extracts album art from an audio file using ffmpeg."""
    if not os.path.exists(audio_path):
        log_func(f"Audio file not found for album art extraction: {audio_path}")
        return False
    try:
        ffmpeg_cmd = [
            "ffmpeg",
            "-i",
            audio_path,
            "-map",
            "0:v",
            "-map",
            "-0:V?",
            "-c:v",
            "copy",
            "-f",
            "mjpeg",
            "-vframes",
            "1",
            "-y",
            output_art_path,
        ]
        subprocess.run(
            ffmpeg_cmd,
            check=True,
            capture_output=True,
            timeout=FFMPEG_TIMEOUT,
            startupinfo=get_subprocess_startupinfo(),
            env=os.environ.copy(),
        )
        log_func(
            f"Successfully extracted album art: {os.path.basename(output_art_path)}"
        )
        return True
    except Exception as e:
        log_func(
            f"Failed to extract album art from {os.path.basename(audio_path)}: {e}"
        )
        return False


def get_media_duration_logic(file_path, log_func):
    """Gets the duration of a media file using ffprobe."""
    if not os.path.exists(file_path):
        log_func(f"File not found for duration probe: {file_path}")
        return None
    try:
        ffprobe_cmd = [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            file_path,
        ]
        duration_str = subprocess.check_output(
            ffprobe_cmd,
            timeout=FFMPEG_TIMEOUT,
            startupinfo=get_subprocess_startupinfo(),
            env=os.environ.copy(),
        ).decode("utf-8")
        return float(duration_str)
    except Exception as e:
        log_func(f"Error getting duration for {os.path.basename(file_path)}: {e}")
        return None


def _get_yt_dlp_command_base():
    """
    Determines the correct base command for yt-dlp, handling frozen
    (PyInstaller) and source-code execution environments.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base_path = sys._MEIPASS
        possible_names = ["yt-dlp.exe", "yt-dlp"]
        for name in possible_names:
            path = os.path.join(base_path, name)
            if os.path.exists(path):
                return [path]
        return None
    else:
        python_dir = os.path.dirname(sys.executable)
        scripts_dir = os.path.join(python_dir, "Scripts")
        possible_paths = [
            os.path.join(scripts_dir, "yt-dlp.exe"),
            os.path.join(scripts_dir, "yt-dlp"),
        ]
        for path in possible_paths:
            if os.path.exists(path):
                return [path]
        return [sys.executable, "-m", "yt_dlp"]


def run_download_process(
    url,
    platform,
    download_type,
    download_dir,
    output_queue,
    generate_thumbnail_func,
    selected_format_code="best",
    download_subtitles=False,
    subtitle_languages="en",
    embed_subtitles=True,
    cancel_event: threading.Event = None,
    is_playlist_item: bool = False,
):
    """
    Constructs the yt-dlp command and starts a SubprocessOutputProcessor
    to manage the download process.
    """
    download_id = str(uuid.uuid4())

    try:
        output_queue.put(
            (
                MSG_DOWNLOAD_ITEM_ADDED,
                download_id,
                {
                    "url": url,
                    "title": url,
                    "type": download_type,
                    "platform": detect_platform(url),
                    "is_playlist_item": is_playlist_item,
                    "status": "starting",
                },
            ),
            timeout=0.05,
        )
    except queue.Full:
        pass

    command_base = _get_yt_dlp_command_base()
    if command_base is None:
        error_msg = "CRITICAL BUILD ERROR: yt-dlp executable not found in the application bundle."
        output_queue.put(
            (
                MSG_DOWNLOAD_ITEM_STATUS,
                download_id,
                {"status": "failed", "message": error_msg},
            )
        )
        return

    format_options = []
    output_template_base = "%(title)s.%(ext)s"
    additional_args = [
        "--no-warnings",
        "--write-thumbnail",
        "--convert-thumbnails",
        "jpg",
        "--print-json",
    ]

    if platform in ["instagram", "tiktok"]:
        output_template_base = "%(uploader)s - %(title)s.%(ext)s"

    if selected_format_code and selected_format_code.lower() != "best":
        format_options = ["-f", selected_format_code]
        if download_type == "Video":
            additional_args.extend(["--merge-output-format", "mp4"])
    else:
        if download_type == "Audio":
            format_options = [
                "-f",
                "bestaudio[ext=m4a]/bestaudio",
                "--extract-audio",
                "--audio-format",
                "m4a",
            ]
        else:
            format_options = [
                "-f",
                "bestvideo[ext=mp4][vcodec^=avc]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                "--merge-output-format",
                "mp4",
            ]

    if download_subtitles:
        additional_args.append("--write-subs")
        if subtitle_languages and subtitle_languages.lower() == "all":
            additional_args.append("--all-subs")
        elif subtitle_languages:
            additional_args.extend(["--sub-lang", subtitle_languages])
        if embed_subtitles:
            additional_args.append("--embed-subs")

    command = (
        command_base
        + format_options
        + ["-P", download_dir, "-o", output_template_base]
        + additional_args
        + [url]
    )

    process_env = os.environ.copy()
    process_env["PYTHONIOENCODING"] = "utf-8"
    subtitle_options_tuple = (
        download_subtitles,
        subtitle_languages,
        embed_subtitles,
    )

    processor = SubprocessOutputProcessor(
        command=command,
        download_id=download_id,
        download_dir=download_dir,
        output_queue=output_queue,
        generate_thumbnail_func=generate_thumbnail_from_video_logic
        if download_type == "video"
        else extract_album_art_logic,
        is_playlist_item=is_playlist_item,
        initial_title=url,
        download_type=download_type,
        subprocess_env_path=process_env,
        subtitle_options=subtitle_options_tuple,
        cancel_event=cancel_event,
    )
    processor.start()