# Universal Media Downloader

## Table of Contents

1.  [About](#about)
2.  [Features](#features)
3.  [Installation](#installation)
    *   [Prerequisites](#prerequisites)
    *   [Running from Source (Recommended for Developers)](#running-from-source-recommended-for-developers)
    *   [Running the Executable (For End-Users)](#running-the-executable-for-end-users)
4.  [Usage](#usage)
    *   [Downloading Media](#downloading-media)
    *   [History & Playback](#history--playback)
    *   [Settings](#settings)
    *   [Global Hotkey](#global-hotkey)
5.  [Troubleshooting](#troubleshooting)
6.  [Contributing](#contributing)
7.  [License](#license)
8.  [Credits](#credits)

---

## 1. About

The **Universal Media Downloader** is a powerful and user-friendly desktop application built with Python and CustomTkinter, designed to simplify downloading videos and audio from various online platforms. Leveraging the robust `yt-dlp` library, it offers a clean graphical interface to fetch your favorite online content with ease.

## 2. Features

*   **Multi-Platform Support:** Download from YouTube, Instagram, TikTok, and many other supported `yt-dlp` platforms.
*   **Video & Audio Downloads:** Choose to download content as video (MP4) or audio (M4A).
*   **Format Selection:** Fetch and select specific video/audio formats and qualities from a detailed list.
*   **Customizable Download Directory:** Easily set where your downloaded media is saved.
*   **Download History:** Keep track of your past downloads with thumbnails, file sizes, and dates.
*   **Integrated Playback:** Open downloaded media directly with your preferred media player (or system default).
*   **Subtitle Support:** Option to download and embed subtitles for various languages.
*   **Global Hotkey:** Trigger a clipboard download instantly with a customizable global hotkey.
*   **Automatic Clipboard Pasting:** Automatically paste URLs from your clipboard when the application gains focus.
*   **Enhanced Error Reporting:** Receive specific and user-friendly error messages if a download fails (e.g., age-restricted, unavailable, geo-blocked).
*   **Download Cancellation:** Stop ongoing downloads at any time.
*   **Detailed Progress Display:** Monitor download speed and estimated time of arrival (ETA) in real-time.
*   **Dependency Checker:** On first launch (or major updates), the app automatically checks for necessary dependencies (Python modules, `ffmpeg`, `yt-dlp`) and guides you through installation, ensuring a smooth setup.

## 3. Installation

### Prerequisites

To run this application, you will need:

*   **Python 3.8+**
*   **`ffmpeg` and `ffprobe`:** Essential for media processing (thumbnail generation, duration detection, format merging). Download from [ffmpeg.org/download.html](https://ffmpeg.org/download.html) and ensure they are added to your system's PATH environment variable.
*   **Internet Connection**

### Running from Source (Recommended for Developers)

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/your-username/universal-media-downloader.git
    cd universal-media-downloader
    ```
    *(Replace `https://github.com/your-username/universal-media-downloader.git` with your actual repository URL)*

2.  **Create a Virtual Environment (Recommended):**
    ```bash
    python -m venv venv
    # On Windows:
    .\venv\Scripts\activate
    # On macOS/Linux:
    source venv/bin/activate
    ```

3.  **Install Required Python Packages:**
    ```bash
    pip install -r requirements.txt
    ```
    *(If `requirements.txt` is missing, you can create it with `pip freeze > requirements.txt` or manually list them: `pip install customtkinter Pillow pynput pyperclip yt-dlp`)*

4.  **Run the Application:**
    ```bash
    python main.py
    ```
    On first run, the **Dependency Checker** window will appear. It will guide you through installing any missing prerequisites. Follow its instructions for `ffmpeg`, `ffprobe`, and any Python packages.

    To skip the dependency check on subsequent runs (if all dependencies are met), use:
    ```bash
    python main.py --skip-deps-check
    ```
    *(Note: The app also attempts to automatically skip the checker if a recent successful check was recorded and no major version update occurred.)*

### Running the Executable (For End-Users)

1.  **Download the latest executable:**
    Go to the [Releases page](https://github.com/your-username/universal-media-downloader/releases) *(create a "Releases" section on your GitHub repo if you distribute binaries)* and download the appropriate version for your operating system (e.g., `.exe` for Windows).

2.  **Extract the contents:**
    Extract the downloaded archive (if it's a `.zip` or `.tar.gz`) to a folder on your computer.

3.  **Run the executable:**
    Navigate to the extracted folder and double-click `UniversalMediaDownloader.exe` (or the equivalent file for your OS).

    On first run, the **Dependency Checker** window will appear. It will guide you through installing any missing prerequisites like `ffmpeg` and `ffprobe`, or specific Python modules if the executable is a leaner bundle. **It is crucial to install `ffmpeg` and `ffprobe` and add them to your system PATH for full functionality.**

## 3. Usage

### Downloading Media

1.  **Copy Media URL:** Copy the URL of the video or audio you want to download from your browser (e.g., a YouTube video link, an Instagram reel link).
2.  **Auto-Paste:** When the application is in focus, the URL will automatically be pasted into the "Media URL" field if "Auto-paste on focus" is enabled in settings. Otherwise, manually paste it.
3.  **Select Download Type:** Choose "Video" or "Audio" using the segmented button.
4.  **Get Formats (Optional):** Click "🎞️ Get Formats" to see available qualities and file types. You can select a specific format code from the new window. By default, it downloads the "best" available.
5.  **Start Download:** Click "⬇️ Download from Clipboard". The download will start in the background, and progress will be shown.
6.  **Cancel Download:** Click "✖️ Cancel Download" at any time to stop an ongoing download.

### History & Playback

The "Download History" section displays all your past downloads.

*   **Single Click:** Highlights an item.
*   **Double Click:** Opens the downloaded file with your system's default media player, or your custom preferred player (configured in settings).
*   **Right Click:** Opens a context menu with options:
    *   `Open with Player`
    *   `Open File Location`
    *   `Copy File Path`
    *   `Remove from History` (Does NOT delete the file from your disk).

### Settings

Click the "⚙️ Settings" button to open the settings window. Here you can configure:

*   **Download Directory:** Where files are saved.
*   **Default Download Type:** Video or Audio.
*   **Font Settings:** Adjust font family and size.
*   **Preferred Media Player:** Set a custom command to open files (e.g., `mpv "{file}"`). Use `{file}` as a placeholder for the media path.
*   **Subtitle Options:** Download subtitles, embed them, and specify languages.
*   **History Management:** Refresh or clear your download history and thumbnail cache.
*   **General Behavior:** Enable/disable auto-paste from clipboard.
*   **Global Hotkey:** Enable, disable, or set a custom keyboard shortcut to trigger a clipboard download even when the app is minimized.

### Global Hotkey

If enabled in settings, you can press your configured hotkey combination (default: `Ctrl+Shift+D`) to instantly paste the clipboard URL and start a download, even if the app is in the background.

## 4. Troubleshooting

*   **"Dependency Checker: Missing" Error:** If the dependency checker pops up, follow its instructions carefully. The most common issues are missing `ffmpeg`/`ffprobe` or them not being correctly added to your system's PATH.
*   **"yt-dlp (or python) command not found":** This is a critical error often reported by the Dependency Checker. Ensure `yt-dlp` is installed via `pip install yt-dlp` in your active environment or that its executable is in your PATH.
*   **"Video Unavailable", "Age-Restricted", "Geo-Restricted":** These specific errors indicate issues with the video source, not necessarily your setup. Try logging into the platform in a browser, using a VPN, or checking if the video is publicly accessible.
*   **Download stuck/slow:** Check your internet connection. Large files can take time. If the download stalls, try cancelling and restarting.
*   **No Thumbnail/Duration:** Ensure `ffmpeg` and `ffprobe` are correctly installed and in your system PATH. These tools are used to generate thumbnails and calculate durations from downloaded media.
*   **Application doesn't launch after building with PyInstaller:**
    *   Temporarily change `console=False` to `console=True` in your `.spec` file and rebuild. This will open a console window that might show a Python traceback.
    *   Check your `hiddenimports` in the `.spec` file. Modules like `pynput` and `customtkinter` might need specific hidden imports.
    *   Verify your `datas` array is correctly pointing to your `assets` folder.

## 5. Contributing

Contributions are welcome! If you find a bug, have a feature request, or want to improve the codebase, please:

1.  Fork the repository.
2.  Create a new branch (`git checkout -b feature/your-feature-name`).
3.  Make your changes.
4.  Commit your changes (`git commit -m 'feat: Add new feature'`).
5.  Push to the branch (`git push origin feature/your-feature-name`).
6.  Open a Pull Request.

Please ensure your code adheres to existing style and passes basic testss
## 6. Credits

*   Developed by: Your Name / Your GitHub Handle / T3 Chat
*   Built with [Python](https://www.python.org/)
*   GUI powered by [CustomTkinter](https://customtkinter.tomschimansky.com/)
*   Downloading powered by [yt-dlp](https://github.com/yt-dlp/yt-dlp)
*   Media processing facilitated by [FFmpeg](https://ffmpeg.org/)
*   Global hotkeys handled by [pynput](https://pynput.readthedocs.io/en/latest/)
*   Clipboard operations handled by [pyperclip](https://pyperclip.readthedocs.io/en/latest/)git 