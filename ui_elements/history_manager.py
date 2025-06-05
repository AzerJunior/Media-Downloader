# history_manager.py
import customtkinter as ctk
from PIL import Image # Ensure PIL.Image is imported
import os
import datetime
import threading
from tkinter import messagebox, Menu, font as tkfont
import pyperclip

from constants import (
    THUMBNAIL_SIZE, VIDEO_EXTENSIONS, AUDIO_EXTENSIONS, MSG_LOG_PREFIX,
    HISTORY_ITEM_SIZES, DEFAULT_HISTORY_ITEM_SIZE_NAME
)

from utils import get_ctk_color_from_theme_path

MSG_DURATION_DONE = "DURATION_DONE"

class HistoryManager:
    def __init__(self, app_instance):
        self.app = app_instance
        self.history_item_frames = []
        self.currently_highlighted_item_frame = None

        self.app.history_context_menu = Menu(self.app, tearoff=0)
        self.app.history_scrollable_frame.grid_columnconfigure(0, weight=1)

    def _clear_history_display(self):
        for frame in self.history_item_frames:
            if frame.winfo_exists():
                frame.destroy()
        self.history_item_frames.clear()
        self.currently_highlighted_item_frame = None

    def redraw_history_listbox(self):
        self._clear_history_display()

        highlight_bg_color = get_ctk_color_from_theme_path("CTkButton.hover_color")
        item_default_bg = get_ctk_color_from_theme_path("CTkFrame.fg_color")

        current_item_ipady = HISTORY_ITEM_SIZES.get(
            self.app.settings.get("history_item_size_name", DEFAULT_HISTORY_ITEM_SIZE_NAME),
            HISTORY_ITEM_SIZES[DEFAULT_HISTORY_ITEM_SIZE_NAME]
        )

        if not self.app.history_items_with_paths:
            no_items_label = ctk.CTkLabel(
                self.app.history_scrollable_frame, text="No history items to display.", font=self.app.ui_font
            )
            no_items_label.pack(pady=20, padx=10, anchor="center")
            self.history_item_frames.append(no_items_label)
            return

        for index, item_data in enumerate(self.app.history_items_with_paths):
            item_frame = ctk.CTkFrame(
                self.app.history_scrollable_frame, corner_radius=3, fg_color=item_default_bg
            )
            item_frame.pack(fill="x", pady=(1, 2), padx=2, ipady=current_item_ipady)
            self.history_item_frames.append(item_frame)
            setattr(item_frame, "_original_fg_color", item_default_bg)

            item_frame.grid_columnconfigure(0, weight=0, minsize=THUMBNAIL_SIZE[0] + 10)
            item_frame.grid_columnconfigure(1, weight=1)

            ctk_image_to_display = None
            thumb_path = item_data.get("thumbnail_path")
            item_type = item_data.get("item_type", "video")

            if thumb_path and os.path.exists(thumb_path):
                if thumb_path in self.app.thumbnail_cache:
                    ctk_image_to_display = self.app.thumbnail_cache[thumb_path]
                else:
                    try:
                        pil_img = Image.open(thumb_path)
                        pil_img.thumbnail(THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
                        # --- FIX START ---
                        ctk_image = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=THUMBNAIL_SIZE) # Corrected class name
                        # --- FIX END ---
                        self.app.thumbnail_cache[thumb_path] = ctk_image
                        ctk_image_to_display = ctk_image
                    except Exception as e:
                        self.app.log_message(f"Error loading thumbnail {thumb_path} as CTkImage: {e}")

            if not ctk_image_to_display:
                if item_type == "audio" and self.app.placeholder_audio_ctk_image:
                    ctk_image_to_display = self.app.placeholder_audio_ctk_image
                elif item_type == "video" and self.app.placeholder_video_ctk_image:
                    ctk_image_to_display = self.app.placeholder_video_ctk_image
                if not ctk_image_to_display:
                     if self.app.placeholder_video_ctk_image:
                         ctk_image_to_display = self.app.placeholder_video_ctk_image
                     else:
                         blank_img_pil = Image.new('RGB', THUMBNAIL_SIZE, color=(200, 200, 200))
                         ctk_image_to_display = ctk.CTkImage(light_image=blank_img_pil, dark_image=blank_img_pil, size=THUMBNAIL_SIZE)


            thumb_label = ctk.CTkLabel(item_frame, text="", image=ctk_image_to_display)
            thumb_label.grid(row=0, column=0, rowspan=3, padx=5, pady=3, sticky="w")

            name_text = item_data.get("display_name_base", "Unknown Item")
            calculated_wraplength = self.app.winfo_width() - THUMBNAIL_SIZE[0] - 80
            if calculated_wraplength < 100: calculated_wraplength = 100
            name_label = ctk.CTkLabel(
                item_frame, text=name_text, font=self.app.ui_font, anchor="w",
                wraplength=calculated_wraplength
            )
            name_label.grid(row=0, column=1, padx=5, pady=(3, 0), sticky="new")

            duration_text = item_data.get("formatted_duration", "Duration: Calculating...")
            duration_label = ctk.CTkLabel(
                item_frame, text=duration_text,
                font=self.app.ui_font_small,
                anchor="w", text_color="gray"
            )
            duration_label.grid(row=1, column=1, padx=5, pady=(0, 0), sticky="new")

            size_date_text = (
                f"Size: {item_data.get('formatted_size', '-')}   Date: {item_data.get('download_date_str', 'N/A')}"
            )
            size_date_label = ctk.CTkLabel(
                item_frame, text=size_date_text,
                font=self.app.ui_font_small,
                anchor="w", text_color="gray"
            )
            size_date_label.grid(row=2, column=1, padx=5, pady=(0, 3), sticky="new")

            if self.currently_highlighted_item_frame == item_frame:
                item_frame.configure(fg_color=highlight_bg_color)
            else:
                item_frame.configure(fg_color=getattr(item_frame, "_original_fg_color", item_default_bg))

            widgets_to_bind = [item_frame, thumb_label, name_label, duration_label, size_date_label]
            for widget in widgets_to_bind:
                widget.bind(
                    "<Button-1>",
                    lambda event, idx=index, frm=item_frame: self.on_history_single_click(event, idx, frm)
                )
                widget.bind(
                    "<Double-Button-1>", lambda event, idx=index: self.on_history_double_click(event, idx)
                )
                widget.bind(
                    "<Button-3>", lambda event, idx=index: self.show_history_context_menu(event, idx)
                )
                widget.configure(cursor="hand2")

    def on_history_single_click(self, event, item_index, clicked_item_frame):
        if not (0 <= item_index < len(self.app.history_items_with_paths)):
            return

        if self.currently_highlighted_item_frame == clicked_item_frame:
            return

        if self.currently_highlighted_item_frame:
            original_color = getattr(self.currently_highlighted_item_frame, "_original_fg_color",
                                     get_ctk_color_from_theme_path("CTkFrame.fg_color"))
            self.currently_highlighted_item_frame.configure(fg_color=original_color)

        highlight_bg = get_ctk_color_from_theme_path("CTkButton.hover_color")
        clicked_item_frame.configure(fg_color=highlight_bg)
        self.currently_highlighted_item_frame = clicked_item_frame

    def on_history_double_click(self, event, item_index):
        if not (0 <= item_index < len(self.app.history_items_with_paths)):
            return

        if self.history_item_frames and 0 <= item_index < len(self.history_item_frames):
            clicked_frame = self.history_item_frames[item_index]
            self.on_history_single_click(event, item_index, clicked_frame)
        else:
            self.app.log_message(
                f"Warning: Frame for index {item_index} not found for double click selection."
            )

        item_data = self.app.history_items_with_paths[item_index]
        file_path = item_data.get("file_path")
        if file_path and os.path.exists(file_path):
            self.app.app_logic.open_file_with_player(file_path)
        elif file_path:
            self.app.messagebox.showwarning("Open Error", f"File not found:\n{file_path}", parent=self.app)
        else:
            self.app.messagebox.showwarning("Open Error", "No valid file path for this item.", parent=self.app)

    def show_history_context_menu(self, event, item_index):
        if not (0 <= item_index < len(self.app.history_items_with_paths)):
            return

        if self.history_item_frames and 0 <= item_index < len(self.history_item_frames):
            clicked_frame = self.history_item_frames[item_index]
            self.on_history_single_click(event, item_index, clicked_frame)
        else:
            self.app.log_message(
                f"Warning: Frame for index {item_index} not found for context menu."
            )
            if 0 <= item_index < len(self.history_item_frames):
                self.currently_highlighted_item_frame = self.history_item_frames[item_index]
            else:
                self.currently_highlighted_item_frame = None

        self.app.history_context_menu.delete(0, ctk.END)
        if not self.app.context_menu_tk_font:
            self.app.ui_manager._create_font_objects()

        self.app.history_context_menu.add_command(
            label="Open with Player", command=lambda idx=item_index: self._context_open_with_player(idx),
            font=self.app.context_menu_tk_font
        )
        self.app.history_context_menu.add_command(
            label="Open File Location", command=lambda idx=item_index: self._context_open_file_location(idx),
            font=self.app.context_menu_tk_font
        )
        self.app.history_context_menu.add_separator()
        self.app.history_context_menu.add_command(
            label="Copy File Path", command=lambda idx=item_index: self._context_copy_file_path(idx),
            font=self.app.context_menu_tk_font
        )
        self.app.history_context_menu.add_command(
            label="Remove from History", command=lambda idx=item_index: self._context_remove_from_history(idx),
            font=self.app.context_menu_tk_font
        )
        try:
            self.app.history_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.app.history_context_menu.grab_release()

    def _context_open_with_player(self, item_index):
        if 0 <= item_index < len(self.app.history_items_with_paths):
            item = self.app.history_items_with_paths[item_index]
            file_path = item.get("file_path")
            if file_path and os.path.exists(file_path):
                self.app.app_logic.open_file_with_player(file_path)
            elif file_path:
                self.app.messagebox.showwarning("Open Error", f"File not found:\n{file_path}", parent=self.app)
            else:
                self.app.messagebox.showwarning("Open Error", "No valid file path for this item.", parent=self.app)

    def _context_open_file_location(self, item_index):
        if 0 <= item_index < len(self.app.history_items_with_paths):
            item = self.app.history_items_with_paths[item_index]
            file_path = item.get("file_path")
            if file_path and os.path.exists(file_path):
                folder_path = os.path.dirname(file_path)
                try:
                    if sys.platform.startswith("win"):
                        os.startfile(folder_path)
                    elif sys.platform.startswith("darwin"):
                        subprocess.Popen(["open", folder_path])
                    else:
                        subprocess.Popen(["xdg-open", folder_path])
                    self.app.log_message(f"Opened folder: {folder_path}")
                except Exception as e:
                    self.app.log_message(f"Error opening folder {folder_path}: {e}")
                    self.app.messagebox.showerror(
                        "Error", f"Could not open folder location:\n{e}", parent=self.app
                    )
            else:
                self.app.messagebox.showwarning(
                    "Error", "Cannot open location: File path is invalid or file does not exist.", parent=self.app
                )

    def _context_copy_file_path(self, item_index):
        if 0 <= item_index < len(self.app.history_items_with_paths):
            item = self.app.history_items_with_paths[item_index]
            file_path = item.get("file_path")
            if file_path:
                try:
                    pyperclip.copy(file_path)
                    self.app.log_message(f"Copied to clipboard: {file_path}")
                except pyperclip.PyperclipException:
                    self.app.messagebox.showerror(
                        "Clipboard Error", "Could not copy path to clipboard.", parent=self.app
                    )
            else:
                self.app.log_message("No file path to copy for selected item.")

    def _context_remove_from_history(self, item_index):
        if 0 <= item_index < len(self.app.history_items_with_paths):
            item_data = self.app.history_items_with_paths[item_index]
            display_name = item_data.get("display_name_base", "Unknown item")
            if self.app.messagebox.askyesno(
                "Remove Item",
                f"Remove '{display_name}' from history?\n(This will not delete the file from your disk.)",
                parent=self.app
            ):
                if self.currently_highlighted_item_frame == self.history_item_frames[item_index]:
                    self.currently_highlighted_item_frame = None

                del self.app.history_items_with_paths[item_index]
                self.redraw_history_listbox()
                self.app.log_message(f"Removed '{display_name}' from history.")

    def update_history(self, display_name_base, file_path, item_type,
                       thumbnail_path=None, sub_indicator="", download_date_str=None):
        file_size_bytes = 0
        if file_path and os.path.exists(file_path):
            try:
                file_size_bytes = os.path.getsize(file_path)
            except OSError as e:
                self.app.log_message(f"Could not get size for downloaded file {file_path}: {e}")

        formatted_size = self._format_filesize(file_size_bytes)
        display_prefix_item = "[Video]" if item_type == "video" else "[Audio]"

        date_display = f" [{download_date_str}]" if download_date_str else ""

        new_item = {
            "display_name_base": display_name_base,
            "file_path": file_path,
            "item_type": item_type,
            "thumbnail_path": thumbnail_path,
            "file_size_bytes": file_size_bytes,
            "formatted_size": formatted_size,
            "download_date_str": download_date_str,
            "sub_indicator": sub_indicator,
            "duration": None,
            "formatted_duration": "Duration: Calculating..."
        }
        self.app.history_items_with_paths.append(new_item)
        original_item_index_before_sort = len(self.app.history_items_with_paths) - 1

        self.app.history_items_with_paths.sort(
            key=lambda x: x.get("download_date_str") or "0", reverse=True
        )
        self.redraw_history_listbox()

        if file_path and os.path.exists(file_path) and (item_type == "video" or item_type == "audio"):
            self.app.log_message(f"INFO: Queued duration calculation for new item: {os.path.basename(file_path)}")
            self.app.app_logic.start_duration_calculation_for_files([{
                "file_path": file_path,
                "original_index": original_item_index_before_sort
            }])

    def load_existing_downloads_to_history(self):
        self.app.log_message(f"Scanning '{self.app.download_dir}' for existing media files...")
        found_count = 0
        current_history_items = []
        videos_needing_thumbnails = []
        files_needing_duration = []

        try:
            if not os.path.isdir(self.app.download_dir):
                self.app.log_message(f"Download directory '{self.app.download_dir}' not found. Skipping scan.")
                if self.app.history_items_with_paths:
                    self.app.history_items_with_paths.clear()
                    self.redraw_history_listbox()
                return

            for filename in os.listdir(self.app.download_dir):
                full_path = os.path.join(self.app.download_dir, filename)
                if not os.path.isfile(full_path):
                    continue

                item_type, display_prefix = (None, "")
                if filename.lower().endswith(VIDEO_EXTENSIONS):
                    item_type, display_prefix = "video", "[Video]"
                elif filename.lower().endswith(AUDIO_EXTENSIONS):
                    item_type, display_prefix = "audio", "[Audio]"
                else:
                    continue

                base, _ = os.path.splitext(full_path)
                expected_thumb_path = base + ".jpg"
                thumbnail_path_to_use = None

                if os.path.exists(expected_thumb_path):
                    thumbnail_path_to_use = expected_thumb_path
                elif item_type == "video":
                    videos_needing_thumbnails.append(
                        {"video_path": full_path, "thumb_output_path": expected_thumb_path}
                    )

                file_size_bytes = 0
                try:
                    file_size_bytes = os.path.getsize(full_path)
                except OSError as e:
                    self.app.log_message(f"Could not get size for {filename}: {e}")

                formatted_size = self._format_filesize(file_size_bytes)
                download_date_str = "N/A"
                try:
                    mtime = os.path.getmtime(full_path)
                    download_date_str = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
                except Exception as e:
                    self.app.log_message(f"Could not get modification time for {filename}: {e}")

                new_item = {
                    "display_name_base": f"{display_prefix} {filename}",
                    "file_path": full_path,
                    "item_type": item_type,
                    "thumbnail_path": thumbnail_path_to_use,
                    "file_size_bytes": file_size_bytes,
                    "formatted_size": formatted_size,
                    "download_date_str": download_date_str,
                    "sub_indicator": "",
                    "duration": None,
                    "formatted_duration": "Duration: Calculating..." if item_type in ["video", "audio"] else "Duration: N/A"
                }
                current_history_items.append(new_item)
                files_needing_duration.append({
                    "file_path": full_path,
                    "original_index": len(current_history_items) - 1
                })
                found_count += 1

            current_history_items.sort(
                key=lambda x: x.get("download_date_str") or "0", reverse=True
            )
            self.app.history_items_with_paths = current_history_items
            self.redraw_history_listbox()
            self.app.log_message(f"Found {found_count} existing media files. Scan complete.")

            if videos_needing_thumbnails:
                self.app.app_logic.thumbnail_gen_threads = [t for t in self.app.app_logic.thumbnail_gen_threads if t.is_alive()]
                if not any(t.is_alive() for t in self.app.app_logic.thumbnail_gen_threads):
                    thumb_gen_thread = threading.Thread(
                        target=self.app.app_logic._process_thumbnail_generation_tasks,
                        args=(videos_needing_thumbnails,), daemon=True
                    )
                    thumb_gen_thread.start()
                    self.app.app_logic.thumbnail_gen_threads.append(thumb_gen_thread)
                else:
                    self.app.log_message("INFO: Thumbnail generation for existing files is already in progress.")

            if files_needing_duration:
                self.app.log_message(f"INFO: Queued duration calculation for {len(files_needing_duration)} existing file(s).")
                self.app.app_logic.start_duration_calculation_for_files(files_needing_duration)

        except Exception as e:
            self.app.log_message(f"ERROR: Error scanning directory for existing files: {e}")

    def _format_filesize(self, size_bytes):
        if size_bytes is None:
            return "-"
        try:
            size_bytes = float(size_bytes)
            if size_bytes == 0:
                return "0 B"
            if size_bytes < 0:
                return "- (invalid size)"
            units = ["B", "KiB", "MiB", "GiB", "TiB"]
            i = 0
            while size_bytes >= 1024 and i < len(units) - 1:
                size_bytes /= 1024
                i += 1
            return f"{size_bytes:.1f} {units[i]}"
        except (ValueError, TypeError):
            return "-"

    def clear_download_history_data(self):
        self.app.history_items_with_paths.clear()
        self._clear_history_display()
        self.redraw_history_listbox()
        self.app.log_message("Download history list cleared.")

    def clear_thumbnail_cache_data(self):
        self.app.log_message("Starting to clear thumbnail cache...")
        self.app.thumbnail_cache.clear()
        self.app.log_message("In-memory Python thumbnail cache (CTkImage objects) cleared.")

        deleted_files_count = 0
        failed_deletions_count = 0

        for item in self.app.history_items_with_paths:
            thumb_path = item.get("thumbnail_path")
            if thumb_path and os.path.exists(thumb_path) and thumb_path.lower().endswith(".jpg"):
                try:
                    os.remove(thumb_path)
                    deleted_files_count += 1
                    item["thumbnail_path"] = None
                except OSError as e:
                    self.app.log_message(f"Failed to delete {thumb_path}: {e}")
                    failed_deletions_count += 1
            elif thumb_path:
                item["thumbnail_path"] = None

        if os.path.isdir(self.app.download_dir):
            for filename in os.listdir(self.app.download_dir):
                full_path = os.path.join(self.app.download_dir, filename)
                if not os.path.isfile(full_path):
                    continue

                if full_path.lower().endswith(".jpg"):
                    base_name_without_ext = os.path.splitext(filename)[0]
                    corresponding_media_found = False
                    for ext in VIDEO_EXTENSIONS + AUDIO_EXTENSIONS:
                        media_file_path = os.path.join(self.app.download_dir, base_name_without_ext + ext)
                        if os.path.exists(media_file_path):
                            corresponding_media_found = True
                            break

                    if not corresponding_media_found:
                        try:
                            os.remove(full_path)
                            deleted_files_count += 1
                        except OSError as e:
                            self.app.log_message(f"Failed to delete orphaned thumb {full_path}: {e}")
                            failed_deletions_count += 1

        self.redraw_history_listbox()
        summary_msg = (
            f"Thumbnail cache clearing finished. Deleted: {deleted_files_count} files. "
            f"Failed: {failed_deletions_count}."
        )
        self.app.log_message(summary_msg)
        if failed_deletions_count > 0:
            self.app.messagebox.showwarning(
                "Thumbnail Deletion Issues",
                f"Could not delete {failed_deletions_count} thumbnail file(s). "
                "Check logs and file permissions.",
                parent=self.app.settings_window_instance or self.app
            )