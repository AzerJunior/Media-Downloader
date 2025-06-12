# ui_elements/ui_manager.py
import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont, ImageColor
from tkinter import messagebox, font as tkfont
import os
import sys
import subprocess # Added for open_download_folder

from constants import (
    DEFAULT_FONT_FAMILY, FONT_SIZES, DEFAULT_FONT_SIZE_NAME, THUMBNAIL_SIZE,
    FONT_ROBOTO_REGULAR, # Use the constant for font path
    HISTORY_ITEM_SIZES, DEFAULT_HISTORY_ITEM_SIZE_NAME # For active downloads theme refresh
)
from utils import get_ctk_color_from_theme_path
from settings_manager import save_settings

class UIManager:
    def __init__(self, app_instance):
        self.app = app_instance
        # _create_font_objects and _create_placeholder_images are called from app __init__
        # after UIManager is instantiated.

    def _tk_color_to_rgb(self, tk_color_string):
        if not tk_color_string: return (128, 128, 128) # Default gray
        try:
            # Ensure widget exists before calling winfo_rgb
            if self.app.winfo_exists():
                rgb_16bit = self.app.winfo_rgb(tk_color_string)
                rgb_8bit = tuple(c // 256 for c in rgb_16bit)
                return rgb_8bit
            else: # Fallback if app window is gone
                return ImageColor.getrgb(tk_color_string)
        except Exception:
            try: return ImageColor.getrgb(tk_color_string)
            except (ValueError, AttributeError, ImportError):
                self.app.log_message(f"WARN: Could not convert color '{tk_color_string}' to RGB. Using default gray.")
                return (128, 128, 128)

    def _create_font_objects(self):
        family = self.app.settings.get("font_family", DEFAULT_FONT_FAMILY)
        size_name = self.app.settings.get("font_size_name", DEFAULT_FONT_SIZE_NAME)
        size = FONT_SIZES.get(size_name, FONT_SIZES[DEFAULT_FONT_SIZE_NAME])

        ctk_family = family if family != "System" else None
        try:
            self.app.ui_font = ctk.CTkFont(family=ctk_family, size=size)
            self.app.ui_font_bold = ctk.CTkFont(family=ctk_family, size=size, weight="bold")
            self.app.ui_font_small = ctk.CTkFont(family=ctk_family, size=int(size * 0.9))
        except Exception as e:
            self.app.log_message(f"ERROR creating CTkFonts: {e}. Using fallbacks.")
            # Fallback to ensure fonts always exist
            self.app.ui_font = ctk.CTkFont(size=FONT_SIZES[DEFAULT_FONT_SIZE_NAME])
            self.app.ui_font_bold = ctk.CTkFont(size=FONT_SIZES[DEFAULT_FONT_SIZE_NAME], weight="bold")
            self.app.ui_font_small = ctk.CTkFont(size=int(FONT_SIZES[DEFAULT_FONT_SIZE_NAME] * 0.9))


        tk_font_family_name = self.app.ui_font.cget("family")
        if tk_font_family_name is None or tk_font_family_name.lower() == "system":
            try: tk_font_family_name = tkfont.nametofont("TkDefaultFont").actual("family")
            except Exception: tk_font_family_name = "TkTextFont" # Fallback

        try:
            self.app.context_menu_tk_font = tkfont.Font(
                family=tk_font_family_name,
                size=self.app.ui_font.cget("size"),
                weight=self.app.ui_font.cget("weight")
            )
        except Exception as e:
            self.app.log_message(f"ERROR: Failed to create context menu font: {e}.")
            self.app.context_menu_tk_font = None # Ensure it's None on failure

    def apply_font_settings(self):
        if not self.app.winfo_exists(): return

        old_ui_font_size = self.app.ui_font.cget("size") if self.app.ui_font else FONT_SIZES[DEFAULT_FONT_SIZE_NAME]
        self._create_font_objects()
        new_ui_font_size = self.app.ui_font.cget("size")

        widget_list = [
            self.app.url_text_label, self.app.url_entry, self.app.platform_label,
            self.app.selected_format_label, self.app.get_formats_button,
            self.app.download_type_label, self.app.download_type_selector,
            self.app.download_button, self.app.log_label, self.app.log_text, self.app.history_label,
            self.app.open_folder_button, self.app.clear_log_button, self.app.settings_button,
            self.app.theme_toggle_button, self.app.progress_details_label,
            self.app.active_downloads_label, self.app.url_type_toggle # Added segmented button
        ]

        for widget in widget_list:
            if widget and widget.winfo_exists():
                current_font = widget.cget("font")
                if isinstance(current_font, ctk.CTkFont):
                    font_to_set = self.app.ui_font # Default
                    if current_font.cget("weight") == "bold": font_to_set = self.app.ui_font_bold
                    elif widget in [self.app.progress_details_label, self.app.url_type_toggle]: font_to_set = self.app.ui_font_small
                    widget.configure(font=font_to_set)

        if self.app.history_manager and self.app.history_manager.app.winfo_exists():
            self.app.history_manager.redraw_history_listbox()

        if self.app.settings_window_instance and self.app.settings_window_instance.winfo_exists():
            self.app.settings_window_instance.destroy()
            self.app.open_settings_window()
        if self.app.format_selection_window_instance and self.app.format_selection_window_instance.winfo_exists():
            self.app.format_selection_window_instance.destroy()

        if old_ui_font_size != new_ui_font_size:
            self.app.log_message("Font size changed, consider resizing window if layout affected.")

    def _create_placeholder_images(self):
        if self.app.ui_font is None: self._create_font_objects()
        if self.app.ui_font is None: # Still None after trying to create
            self.app.log_message("ERROR: ui_font is None. Cannot create placeholders.")
            self.app.placeholder_video_ctk_image = None
            self.app.placeholder_audio_ctk_image = None
            return

        bg_color_video_str = get_ctk_color_from_theme_path("CTkFrame.fg_color")
        bg_color_audio_str = get_ctk_color_from_theme_path("CTkButton.fg_color")
        text_color_str = get_ctk_color_from_theme_path("CTkLabel.text_color")

        pil_bg_video = self._tk_color_to_rgb(bg_color_video_str)
        pil_bg_audio = self._tk_color_to_rgb(bg_color_audio_str)
        pil_text_color = self._tk_color_to_rgb(text_color_str)

        try:
            img_video_pil = Image.new('RGB', THUMBNAIL_SIZE, color=pil_bg_video)
            self.app.placeholder_video_ctk_image = ctk.CTkImage(light_image=img_video_pil, dark_image=img_video_pil, size=THUMBNAIL_SIZE)

            img_audio_pil = Image.new('RGB', THUMBNAIL_SIZE, color=pil_bg_audio)
            draw_audio = ImageDraw.Draw(img_audio_pil)
            text = "AUDIO"
            
            font_path = FONT_ROBOTO_REGULAR # Use constant
            pil_font_for_drawing = None
            font_size_for_drawing = int(self.app.ui_font.cget("size") * 1.5)

            try:
                if not os.path.exists(font_path):
                    self.app.log_message(f"WARN: Bundled font '{font_path}' not found. Using Pillow default.")
                    pil_font_for_drawing = ImageFont.load_default()
                else:
                    pil_font_for_drawing = ImageFont.truetype(font_path, font_size_for_drawing)
            except Exception as e:
                self.app.log_message(f"WARN: Error loading font '{font_path}': {e}. Using Pillow default.")
                pil_font_for_drawing = ImageFont.load_default()
            
            text_width, text_height = THUMBNAIL_SIZE[0] // 2, THUMBNAIL_SIZE[1] // 3 # Fallback sizes
            try:
                bbox = draw_audio.textbbox((0, 0), text, font=pil_font_for_drawing)
                text_width, text_height = bbox[2] - bbox[0], bbox[3] - bbox[1]
            except AttributeError: # Older Pillow might not have textbbox
                try: text_width, text_height = draw_audio.textsize(text, font=pil_font_for_drawing)
                except AttributeError: self.app.log_message("WARN: Could not get text size for placeholder.")

            x = (THUMBNAIL_SIZE[0] - text_width) / 2
            y = (THUMBNAIL_SIZE[1] - text_height) / 2
            draw_audio.text((x, y), text, fill=pil_text_color, font=pil_font_for_drawing)

            self.app.placeholder_audio_ctk_image = ctk.CTkImage(light_image=img_audio_pil, dark_image=img_audio_pil, size=THUMBNAIL_SIZE)
        except ImportError:
            self.app.placeholder_video_ctk_image = None
            self.app.placeholder_audio_ctk_image = None
            self.app.log_message("Pillow (or ImageFont) not found. Placeholders disabled.")
        except Exception as e:
            self.app.placeholder_video_ctk_image = None
            self.app.placeholder_audio_ctk_image = None
            self.app.log_message(f"ERROR creating placeholder CTkImages: {type(e).__name__} - {e}")


    def toggle_theme(self):
        if not self.app.winfo_exists(): return
        current_mode = ctk.get_appearance_mode()
        new_mode = "Light" if current_mode == "Dark" else "Dark"
        ctk.set_appearance_mode(new_mode)
        self.app.settings["appearance_mode"] = new_mode
        self.save_app_settings()
        self.update_theme_toggle_button_text()
        self.refresh_main_ui_after_theme_change()

    def save_app_settings(self):
        save_settings(self.app.settings)

    def update_theme_toggle_button_text(self):
        if not self.app.theme_toggle_button.winfo_exists(): return
        current_mode = ctk.get_appearance_mode()
        self.app.theme_toggle_button.configure(text="☀️ Light Mode" if current_mode == "Dark" else "🌙 Dark Mode")

    def refresh_main_ui_after_theme_change(self):
        if not self.app.winfo_exists(): return
        self._create_placeholder_images() # Recreate placeholders with new theme colors
        if self.app.history_manager and self.app.history_manager.app.winfo_exists():
            self.app.history_manager.redraw_history_listbox()
        
        # Recreate active download items to reflect theme changes
        if self.app.active_downloads_scrollable_frame.winfo_exists():
            for download_id in list(self.app.active_downloads.keys()): # Iterate copy
                item_ui = self.app.active_downloads.get(download_id)
                if item_ui and item_ui["frame"].winfo_exists():
                    item_data = item_ui["data"] # Save data
                    item_ui["frame"].destroy() # Destroy old frame
                    self.app.active_downloads.pop(download_id, None) # Remove from dict
                    # Re-create the UI element; it will use new theme colors
                    self.app._create_active_download_item_ui(download_id, item_data)
                    # Re-apply current status/progress to the new UI
                    self.app._update_active_download_item_ui(download_id, item_data)


        if self.app.format_selection_window_instance and self.app.format_selection_window_instance.winfo_exists():
            self.app.format_selection_window_instance.destroy()
        if self.app.settings_window_instance and self.app.settings_window_instance.winfo_exists():
            self.app.settings_window_instance.destroy()
            self.app.open_settings_window()

    def clear_log(self):
        if not self.app.log_text.winfo_exists(): return
        self.app.log_text.configure(state="normal")
        self.app.log_text.delete("1.0", ctk.END)
        self.app.log_text.configure(state="disabled")
        self.app.log_message("Log cleared.")

    def open_download_folder(self):
        if not self.app.winfo_exists(): return
        try:
            if not os.path.exists(self.app.download_dir):
                messagebox.showerror("Error", f"Download directory not found:\n{self.app.download_dir}", parent=self.app)
                return
            if sys.platform.startswith("win"): os.startfile(self.app.download_dir)
            elif sys.platform.startswith("darwin"): subprocess.call(["open", self.app.download_dir])
            else: subprocess.call(["xdg-open", self.app.download_dir])
            self.app.log_message(f"Opened download folder: {self.app.download_dir}")
        except Exception as e:
            messagebox.showerror("Error", f"Could not open download folder:\n{e}", parent=self.app)
            self.app.log_message(f"Error opening download folder: {e}")

    def update_selected_format_display(self):
        if not self.app.selected_format_label_var.get(): return # Should not happen if var exists
        if not self.app.winfo_exists(): return # Check if app window exists
        
        new_format_text = f"Format: {self.app.settings.get('selected_format_code', 'best')}"
        try:
            self.app.selected_format_label_var.set(new_format_text)
        except tk.TclError as e: # Catch error if widget is destroyed
            if "invalid command name" not in str(e).lower():
                 self.app.log_message(f"Error updating selected format label: {e}")