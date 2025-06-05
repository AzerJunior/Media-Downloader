# ui_manager.py
import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont, ImageColor # Added ImageColor
from tkinter import messagebox, font as tkfont
import os
import sys

from constants import (
    DEFAULT_FONT_FAMILY, FONT_SIZES, DEFAULT_FONT_SIZE_NAME, THUMBNAIL_SIZE
)
from utils import get_ctk_color_from_theme_path
from settings_manager import save_settings # Import save_settings directly for UI preferences

class UIManager:
    def __init__(self, app_instance):
        self.app = app_instance
        self._create_font_objects()
        self._create_placeholder_images()

    def _tk_color_to_rgb(self, tk_color_string):
        """Converts a Tkinter color string (e.g., '#RRGGBB') to an RGB tuple."""
        if not tk_color_string:
            return (128, 128, 128)  # Default to gray if color string is empty
        try:
            # winfo_rgb returns a 16-bit RGB tuple (65535, 65535, 65535)
            rgb_16bit = self.app.winfo_rgb(tk_color_string)
            rgb_8bit = tuple(c // 256 for c in rgb_16bit)
            return rgb_8bit
        except Exception:
            try:
                # Fallback to Pillow's ImageColor for named colors or other formats
                return ImageColor.getrgb(tk_color_string)
            except (ValueError, AttributeError, ImportError):
                self.app.log_message(
                    f"WARN: Could not convert color string '{tk_color_string}' to RGB. Using default gray."
                )
                return (128, 128, 128)

    def _create_font_objects(self):
        """Creates and updates font objects used throughout the application."""
        family = self.app.settings.get("font_family", DEFAULT_FONT_FAMILY)
        size_name = self.app.settings.get("font_size_name", DEFAULT_FONT_SIZE_NAME)
        size = FONT_SIZES.get(size_name, FONT_SIZES[DEFAULT_FONT_SIZE_NAME])

        ctk_family = family if family != "System" else None
        self.app.ui_font = ctk.CTkFont(family=ctk_family, size=size)
        self.app.ui_font_bold = ctk.CTkFont(family=ctk_family, size=size, weight="bold")
        self.app.ui_font_small = ctk.CTkFont(family=ctk_family, size=int(size * 0.9))

        # Determine the actual Tkinter font family name for the context menu
        tk_font_family_name = self.app.ui_font.cget("family")
        if tk_font_family_name is None or tk_font_family_name.lower() == "system":
            # Fallback to TkDefaultFont's actual family if CTkFont returns None or "System"
            try:
                tk_font_family_name = tkfont.nametofont("TkDefaultFont").actual("family")
            except Exception as e:
                self.app.log_message(f"WARN: Could not get TkDefaultFont family: {e}. Using a generic fallback.")
                tk_font_family_name = "TkTextFont" # Another common Tkinter font
                if not tkfont.families():
                    self.app.log_message("ERROR: No Tkinter font families available.")

        # Create context menu font
        try:
            self.app.context_menu_tk_font = tkfont.Font(
                family=tk_font_family_name,
                size=self.app.ui_font.cget("size"),
                weight=self.app.ui_font.cget("weight")
            )
        except Exception as e:
            self.app.log_message(f"ERROR: Failed to create context menu font: {e}. Context menu might use default system font.")
            self.app.context_menu_tk_font = None # Set to None to indicate failure

    def apply_font_settings(self):
        """Applies font settings to all relevant UI elements."""
        old_ui_font_size = (
            self.app.ui_font.cget("size")
            if self.app.ui_font
            else FONT_SIZES[DEFAULT_FONT_SIZE_NAME]
        )
        self._create_font_objects() # Re-create fonts based on new settings
        new_ui_font_size = self.app.ui_font.cget("size")


        # List of core UI widgets to re-configure their fonts
        widget_list = [
            self.app.url_text_label, self.app.url_entry, self.app.platform_label,
            self.app.selected_format_label, self.app.get_formats_button,
            self.app.download_type_label, self.app.download_type_selector,
            self.app.download_button, self.app.log_label, self.app.log_text, self.app.history_label,
            self.app.open_folder_button, self.app.clear_log_button, self.app.settings_button,
            self.app.theme_toggle_button
        ]

        for widget in widget_list:
            if widget and widget.winfo_exists():
                # For CTk segmented button, the font is set for the whole widget
                if widget == self.app.download_type_selector:
                    widget.configure(font=self.app.ui_font)
                else:
                    # Generic handling for labels, buttons, entries, etc.
                    # Check if the widget has a font property and if it was using CTkFont
                    current_font_obj = widget.cget("font")
                    if isinstance(current_font_obj, ctk.CTkFont):
                        if current_font_obj.cget("weight") == "bold":
                            widget.configure(font=self.app.ui_font_bold)
                        else:
                            widget.configure(font=self.app.ui_font)
                    # For custom widgets or if font is not CTkFont instance, we might need specific handling
                    # For example, if a widget sets its font to a string "Helvetica 12 bold"
                    # you'd have to parse that and reconstruct. CustomTkinter usually manages this for its widgets.


        self.app.history_manager.redraw_history_listbox() # Redraw history items with new fonts

        # Reopen settings/format windows to apply fonts, as CTk Toplevels don't automatically update children's fonts
        if self.app.settings_window_instance and self.app.settings_window_instance.winfo_exists():
            self.app.settings_window_instance.destroy()
            self.app.open_settings_window() # Reopen settings window via main app
            self.app.log_message("Settings window reopened to apply font changes.")

        if self.app.format_selection_window_instance and self.app.format_selection_window_instance.winfo_exists():
            self.app.format_selection_window_instance.destroy()
            self.app.log_message("Format selection window closed; will use new fonts if reopened.")

        if old_ui_font_size != new_ui_font_size:
            self.app.log_message(
                "Font size changed, consider manually resizing window if layout is affected."
            )

    def _create_placeholder_images(self):
        """Creates placeholder images for video and audio items in history."""
        # Ensure font objects are created before attempting to draw text with them.
        if self.app.ui_font is None or self.app.ui_font_bold is None or self.app.ui_font_small is None:
            self._create_font_objects()
        if self.app.ui_font is None:
            self.app.log_message(
                "ERROR: self.app.ui_font is still None. Cannot create placeholders with custom text font styling."
            )

        # Get CTk theme colors for drawing
        bg_color_video_str = get_ctk_color_from_theme_path("CTkFrame.fg_color")
        bg_color_audio_str = get_ctk_color_from_theme_path("CTkButton.fg_color")
        text_color_str = get_ctk_color_from_theme_path("CTkLabel.text_color")

        pil_bg_video = self._tk_color_to_rgb(bg_color_video_str)
        pil_bg_audio = self._tk_color_to_rgb(bg_color_audio_str)
        pil_text_color = self._tk_color_to_rgb(text_color_str)

        try:
            # Video Placeholder (simple solid color)
            img_video_pil = Image.new('RGB', THUMBNAIL_SIZE, color=pil_bg_video)
            self.app.placeholder_video_ctk_image = ctk.CTkImage(
                light_image=img_video_pil, dark_image=img_video_pil, size=THUMBNAIL_SIZE
            )

            # Audio Placeholder (solid color with "AUDIO" text)
            img_audio_pil = Image.new('RGB', THUMBNAIL_SIZE, color=pil_bg_audio)
            draw_audio = ImageDraw.Draw(img_audio_pil)
            text = "AUDIO"

            pil_font_for_drawing = None
            # Set font size for drawing, larger than UI font
            font_size_for_drawing = int(FONT_SIZES[DEFAULT_FONT_SIZE_NAME] * 1.5)
            if self.app.ui_font and isinstance(self.app.ui_font, ctk.CTkFont):
                font_size_for_drawing = int(self.app.ui_font.cget("size") * 1.5)

            try:
                # Construct path to the bundled font (Roboto-Regular.ttf)
                current_script_dir = os.path.dirname(os.path.abspath(__file__))
                project_root = os.path.abspath(os.path.join(current_script_dir, ".."))
                font_path = os.path.join(project_root, "assets", "fonts", "Roboto-Regular.ttf")

                if not os.path.exists(font_path):
                    self.app.log_message(f"WARN: Bundled font at '{font_path}' not found. Using Pillow's default.")
                    pil_font_for_drawing = ImageFont.load_default()
                else:
                    pil_font_for_drawing = ImageFont.truetype(font_path, font_size_for_drawing)

            except IOError as e:
                self.app.log_message(f"WARN: IOError loading bundled font: {e}. Using Pillow's default.")
                pil_font_for_drawing = ImageFont.load_default()
            except Exception as e:
                self.app.log_message(f"WARN: Error loading bundled font: {type(e).__name__} - {e}. Using Pillow's default.")
                pil_font_for_drawing = ImageFont.load_default()

            # Fallback if font loading failed
            if pil_font_for_drawing is None:
                try:
                    pil_font_for_drawing = ImageFont.load_default()
                except Exception as final_fallback_e:
                    self.app.log_message(
                        f"CRITICAL: Could not load any font for placeholder: {final_fallback_e}"
                    )
            
            # Calculate text width and height based on the loaded font
            text_width, text_height = THUMBNAIL_SIZE[0] // 2, THUMBNAIL_SIZE[1] // 3 # Initial guess

            if pil_font_for_drawing:
                try:
                    # textbbox is preferred for accurate size calculation
                    bbox = draw_audio.textbbox((0, 0), text, font=pil_font_for_drawing)
                    text_width = bbox[2] - bbox[0]
                    text_height = bbox[3] - bbox[1]
                except AttributeError:
                    # Fallback for older Pillow versions that might not have textbbox
                    try:
                        text_size_tuple = draw_audio.textsize(text, font=pil_font_for_drawing)
                        text_width, text_height = text_size_tuple[0], text_size_tuple[1]
                    except AttributeError:
                        self.app.log_message(
                            "WARN: Could not determine text size for placeholder using Pillow font."
                        )

            x = (THUMBNAIL_SIZE[0] - text_width) / 2
            y = (THUMBNAIL_SIZE[1] - text_height) / 2

            if pil_font_for_drawing:
                draw_audio.text((x, y), text, fill=pil_text_color, font=pil_font_for_drawing)
            else:
                # Draw a simple cross if no font is available
                draw_audio.line(
                    [(10, 10), (THUMBNANAIL_SIZE[0] - 10, THUMBNAIL_SIZE[1] - 10)],
                    fill=pil_text_color, width=2
                )
                draw_audio.line(
                    [(10, THUMBNAIL_SIZE[1] - 10), (THUMBNAIL_SIZE[0] - 10, 10)],
                    fill=pil_text_color, width=2
                )
                self.app.log_message(
                    "WARN: No font available for placeholder text; drawing fallback graphic."
                )


            self.app.placeholder_audio_ctk_image = ctk.CTkImage(
                light_image=img_audio_pil, dark_image=img_audio_pil, size=THUMBNAIL_SIZE
            )

        except ImportError:
            self.app.placeholder_video_ctk_image = None
            self.app.placeholder_audio_ctk_image = None
            self.app.log_message("Pillow library (or ImageFont) not found. Placeholders disabled.")
        except Exception as e:
            self.app.placeholder_video_ctk_image = None
            self.app.placeholder_audio_ctk_image = None
            self.app.log_message(
                f"ERROR: Error creating placeholder CTkImages: {type(e).__name__} - {e}"
            )

    def toggle_theme(self):
        """Toggles the application's appearance mode between Light and Dark."""
        current_mode = ctk.get_appearance_mode()
        new_mode = "Light" if current_mode == "Dark" else "Dark"
        ctk.set_appearance_mode(new_mode)
        self.app.settings["appearance_mode"] = new_mode
        self.save_app_settings()
        self.update_theme_toggle_button_text()
        self.refresh_main_ui_after_theme_change()

    def save_app_settings(self):
        """Saves the current application settings to file."""
        save_settings(self.app.settings) # Delegate to settings_manager

    def update_theme_toggle_button_text(self):
        """Updates the text on the theme toggle button based on current mode."""
        current_mode = ctk.get_appearance_mode()
        if current_mode == "Dark":
            self.app.theme_toggle_button.configure(text="☀️ Light Mode")
        else:
            self.app.theme_toggle_button.configure(text="🌙 Dark Mode")

    def refresh_main_ui_after_theme_change(self):
        """Refreshes UI elements affected by theme changes."""
        self._create_placeholder_images() # Recreate images with new colors
        self.app.history_manager.redraw_history_listbox() # Redraw history with new colors
        if self.app.format_selection_window_instance and self.app.format_selection_window_instance.winfo_exists():
            self.app.format_selection_window_instance.destroy()
            self.app.log_message("Format selection window closed due to theme change. Reopen if needed.")
        if self.app.settings_window_instance and self.app.settings_window_instance.winfo_exists():
            self.app.settings_window_instance.destroy()
            self.app.open_settings_window() # Reopen settings window (calls UI elements creation)
            self.app.log_message("Settings window reopened to reflect theme change.")

    def clear_log(self):
        """Clears the text from the download log display."""
        self.app.log_text.configure(state="normal")
        self.app.log_text.delete("1.0", ctk.END)
        self.app.log_text.configure(state="disabled")
        self.app.log_message("Log cleared.")

    def open_download_folder(self):
        """Opens the configured download directory using the OS default file explorer."""
        try:
            if not os.path.exists(self.app.download_dir):
                self.app.messagebox.showerror(
                    "Error", f"Download directory not found:\n{self.app.download_dir}", parent=self.app
                )
                return
            if sys.platform.startswith("win"):
                os.startfile(self.app.download_dir)
            elif sys.platform.startswith("darwin"):
                subprocess.call(["open", self.app.download_dir])
            else:
                subprocess.call(["xdg-open", self.app.download_dir])
            self.app.log_message(f"Opened download folder: {self.app.download_dir}")
        except Exception as e:
            self.app.messagebox.showerror("Error", f"Could not open download folder:\n{e}", parent=self.app)
            self.app.log_message(f"Error opening download folder: {e}")

    def update_selected_format_display(self):
        """Updates the label showing the currently selected download format."""
        self.app.selected_format_label_var.set(
            f"Format: {self.app.settings.get('selected_format_code', 'best')}"
        )