# ui_elements/settings_window.py
import customtkinter as ctk
from tkinter import filedialog, messagebox
import os
import threading
from pynput import keyboard

# Assuming constants are in the parent directory
from constants import (
    DEFAULT_FONT_FAMILY, FONT_FAMILIES, FONT_SIZES, DEFAULT_FONT_SIZE_NAME,
    DEFAULT_PLAYER_COMMAND,
    HISTORY_ITEM_SIZES, DEFAULT_HISTORY_ITEM_SIZE_NAME # NEW: Import new constants
)

from .about_window import AboutWindow
from .tooltip import Tooltip # Ensure Tooltip is imported

class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, master, app_instance):
        super().__init__(master)
        self.app = app_instance
        self.title("Settings")
        self.geometry("600x750") # Slightly wider to accommodate new button
        self.transient(master)
        self.grab_set()

        self._hotkey_listener = None
        self._hotkey_listening_thread = None
        self._hotkey_current_modifiers = set()
        self._hotkey_main_key = None
        self._main_hotkey_paused = False

        settings_frame = ctk.CTkScrollableFrame(self)
        settings_frame.pack(expand=True, fill="both", padx=10, pady=10)

        # --- Download Directory ---
        dir_group = ctk.CTkFrame(settings_frame)
        dir_group.pack(fill="x", pady=(10,5))
        ctk.CTkLabel(dir_group, text="Download Directory:", font=self.app.ui_font).pack(side="left", padx=5, pady=5)
        self.download_dir_var = ctk.StringVar(value=self.app.settings.get("download_directory", os.getcwd()))
        dir_entry = ctk.CTkEntry(dir_group, textvariable=self.download_dir_var, state="readonly", font=self.app.ui_font)
        dir_entry.pack(side="left", expand=True, fill="x", padx=5, pady=5)
        browse_button = ctk.CTkButton(dir_group, text="Browse", command=self.browse_download_directory, font=self.app.ui_font)
        browse_button.pack(side="left", padx=5, pady=5)

        # --- Default Download Type ---
        default_type_group = ctk.CTkFrame(settings_frame)
        default_type_group.pack(fill="x", pady=5)
        ctk.CTkLabel(default_type_group, text="Default Download Type:", font=self.app.ui_font).pack(side="left", padx=5, pady=5)
        self.default_download_type_var = ctk.StringVar(value=self.app.settings.get("default_download_type", "Video"))
        default_type_selector = ctk.CTkSegmentedButton(
            default_type_group, values=["Video", "Audio"],
            variable=self.default_download_type_var, command=self.change_default_download_type,
            font=self.app.ui_font
        )
        default_type_selector.pack(side="left", padx=5, pady=5)

        # --- Font Settings ---
        font_group = ctk.CTkFrame(settings_frame)
        font_group.pack(fill="x", pady=5)
        ctk.CTkLabel(font_group, text="Font Family:", font=self.app.ui_font).pack(side="left", padx=5, pady=5)
        self.font_family_var = ctk.StringVar(value=self.app.settings.get("font_family", DEFAULT_FONT_FAMILY))
        font_family_menu = ctk.CTkOptionMenu(
            font_group, values=FONT_FAMILIES, variable=self.font_family_var,
            command=self.change_font_settings, font=self.app.ui_font, dropdown_font=self.app.ui_font
        )
        font_family_menu.pack(side="left", padx=5, pady=5)

        ctk.CTkLabel(font_group, text="Font Size:", font=self.app.ui_font).pack(side="left", padx=(10,5), pady=5)
        self.font_size_name_var = ctk.StringVar(value=self.app.settings.get("font_size_name", DEFAULT_FONT_SIZE_NAME))
        font_size_menu = ctk.CTkOptionMenu(
            font_group, values=list(FONT_SIZES.keys()), variable=self.font_size_name_var,
            command=self.change_font_settings, font=self.app.ui_font, dropdown_font=self.app.ui_font
        )
        font_size_menu.pack(side="left", padx=5, pady=5)

        # --- NEW: History/Active Item Size Setting ---
        item_size_group = ctk.CTkFrame(settings_frame)
        item_size_group.pack(fill="x", pady=5)
        ctk.CTkLabel(item_size_group, text="List Item Size:", font=self.app.ui_font).pack(side="left", padx=5, pady=5)
        self.history_item_size_var = ctk.StringVar(value=self.app.settings.get("history_item_size_name", DEFAULT_HISTORY_ITEM_SIZE_NAME))
        history_item_size_menu = ctk.CTkOptionMenu(
            item_size_group, values=list(HISTORY_ITEM_SIZES.keys()), variable=self.history_item_size_var,
            command=self.change_history_item_size, font=self.app.ui_font, dropdown_font=self.app.ui_font
        )
        history_item_size_menu.pack(side="left", padx=5, pady=5)
        # --- END NEW ---

        # --- Player Command ---
        player_group = ctk.CTkFrame(settings_frame)
        player_group.pack(fill="x", pady=(10,5))
        ctk.CTkLabel(player_group, text="Preferred Media Player:", font=self.app.ui_font).pack(side="left", padx=5, pady=5)
        self.player_command_var = ctk.StringVar(value=self.app.settings.get("player_command", DEFAULT_PLAYER_COMMAND))
        player_entry = ctk.CTkEntry(player_group, textvariable=self.player_command_var, font=self.app.ui_font)
        player_entry.pack(side="left", expand=True, fill="x", padx=5, pady=5)
        player_entry.bind("<FocusOut>", self.save_player_command)
        player_entry.bind("<Return>", self.save_player_command)
        ctk.CTkLabel(settings_frame, text="Use {file} as placeholder for the file path. Leave empty for OS default.",
                     font=(self.app.ui_font.cget("family"), int(self.app.ui_font.cget("size")*0.8)),
                     text_color="gray").pack(fill="x", padx=15, pady=(0,10))

        # --- Subtitle Settings ---
        subtitle_group = ctk.CTkFrame(settings_frame)
        subtitle_group.pack(fill="x", pady=(10,5))
        ctk.CTkLabel(subtitle_group, text="Subtitles:", font=self.app.ui_font_bold).pack(side="left", padx=5, pady=5, anchor="w")

        self.download_subs_var = ctk.BooleanVar(value=self.app.settings.get("download_subtitles", False))
        subs_switch = ctk.CTkSwitch(subtitle_group, text="Download Subtitles", variable=self.download_subs_var,
                                     command=self.save_subtitle_settings, font=self.app.ui_font)
        subs_switch.pack(side="top", anchor="w", padx=15, pady=2)

        self.embed_subs_var = ctk.BooleanVar(value=self.app.settings.get("embed_subtitles", True))
        embed_switch = ctk.CTkSwitch(subtitle_group, text="Embed Subtitles (if possible)", variable=self.embed_subs_var,
                                     command=self.save_subtitle_settings, font=self.app.ui_font)
        embed_switch.pack(side="top", anchor="w", padx=15, pady=2)

        lang_frame = ctk.CTkFrame(subtitle_group, fg_color="transparent")
        lang_frame.pack(fill="x", padx=15, pady=2)
        ctk.CTkLabel(lang_frame, text="Languages (e.g., en,es or all):", font=self.app.ui_font).pack(side="left", padx=0, pady=5)
        self.subs_langs_var = ctk.StringVar(value=self.app.settings.get("subtitle_languages", "en"))
        subs_langs_entry = ctk.CTkEntry(lang_frame, textvariable=self.subs_langs_var, font=self.app.ui_font)
        subs_langs_entry.pack(side="left", expand=True, fill="x", padx=5, pady=5)
        subs_langs_entry.bind("<FocusOut>", self.save_subtitle_settings)
        subs_langs_entry.bind("<Return>", self.save_subtitle_settings)

        # --- History Management ---
        history_management_group = ctk.CTkFrame(settings_frame)
        history_management_group.pack(fill="x", pady=(10,5))
        ctk.CTkLabel(history_management_group, text="History & Cache:", font=self.app.ui_font_bold).pack(side="left", padx=5, pady=5, anchor="w")

        refresh_history_button = ctk.CTkButton(
            history_management_group, text="Refresh History List", command=self.refresh_history, font=self.app.ui_font
        )
        refresh_history_button.pack(side="left", padx=15, pady=5)

        clear_buttons_frame = ctk.CTkFrame(settings_frame)
        clear_buttons_frame.pack(fill="x", pady=(0,10), padx=5)

        clear_history_button = ctk.CTkButton(
            clear_buttons_frame, text="Clear Download History", command=self.confirm_clear_download_history,
            font=self.app.ui_font, fg_color="firebrick", hover_color="darkred"
        )
        clear_history_button.pack(side="left", padx=(10,5), pady=5)

        clear_cache_button = ctk.CTkButton(
            clear_buttons_frame, text="Clear Thumbnail Cache", command=self.confirm_clear_thumbnail_cache,
            font=self.app.ui_font, fg_color="chocolate", hover_color="saddlebrown"
        )
        clear_cache_button.pack(side="left", padx=5, pady=5)

        # --- About Button ---
        about_group = ctk.CTkFrame(settings_frame)
        about_group.pack(fill="x", pady=(10,5))
        ctk.CTkLabel(about_group, text="About:", font=self.app.ui_font_bold).pack(side="left", padx=5, pady=5, anchor="w")

        about_button = ctk.CTkButton(
            about_group, text="About This App", command=self.open_about_window,
            font=self.app.ui_font
        )
        about_button.pack(side="left", padx=15, pady=5)

        # --- General Behavior Settings ---
        behavior_group = ctk.CTkFrame(settings_frame)
        behavior_group.pack(fill="x", pady=(10,5))
        ctk.CTkLabel(behavior_group, text="General Behavior:", font=self.app.ui_font_bold).pack(side="left", padx=5, pady=5, anchor="w")

        self.auto_paste_on_focus_var = ctk.BooleanVar(value=self.app.settings.get("auto_paste_on_focus", True))
        auto_paste_switch = ctk.CTkSwitch(
            behavior_group, text="Auto-paste URL from clipboard on app focus",
            variable=self.auto_paste_on_focus_var, command=self.save_general_settings,
            font=self.app.ui_font
        )
        auto_paste_switch.pack(side="top", anchor="w", padx=15, pady=2)

        # --- Global Hotkey Settings ---
        hotkey_group = ctk.CTkFrame(settings_frame)
        hotkey_group.pack(fill="x", pady=(10,5))
        ctk.CTkLabel(hotkey_group, text="Global Hotkey:", font=self.app.ui_font_bold).pack(side="left", padx=5, pady=5, anchor="w")

        self.global_hotkey_enabled_var = ctk.BooleanVar(value=self.app.settings.get("global_hotkey_enabled", False))
        hotkey_enable_switch = ctk.CTkSwitch(
            hotkey_group, text="Enable Global Hotkey",
            variable=self.global_hotkey_enabled_var, command=self.toggle_global_hotkey,
            font=self.app.ui_font
        )
        hotkey_enable_switch.pack(side="top", anchor="w", padx=15, pady=2)

        hotkey_combo_frame = ctk.CTkFrame(hotkey_group, fg_color="transparent")
        hotkey_combo_frame.pack(fill="x", padx=15, pady=2)
        ctk.CTkLabel(hotkey_combo_frame, text="Combination:", font=self.app.ui_font).pack(side="left", padx=0, pady=5)
        self.global_hotkey_combination_var = ctk.StringVar(value=self.app.settings.get("global_hotkey_combination", "<ctrl>+<shift>+D"))
        self.hotkey_entry = ctk.CTkEntry(hotkey_combo_frame, textvariable=self.global_hotkey_combination_var, font=self.app.ui_font, state="readonly", width=150)
        self.hotkey_entry.pack(side="left", padx=5, pady=5)

        self.set_hotkey_button = ctk.CTkButton(hotkey_combo_frame, text="Set Hotkey", command=self.start_hotkey_listening, font=self.app.ui_font)
        self.set_hotkey_button.pack(side="left", padx=5, pady=5)
        Tooltip(self.set_hotkey_button, "Click to listen for your next key combination. Press modifiers then the final key.")
        ctk.CTkLabel(hotkey_group, text="Press the desired modifier keys (e.g., Ctrl, Alt, Shift, Cmd) and then the trigger key.",
                     font=(self.app.ui_font.cget("family"), int(self.app.ui_font.cget("size")*0.8)),
                     text_color="gray", wraplength=400).pack(fill="x", padx=15, pady=(0,10))


        # --- Close Button ---
        button_frame = ctk.CTkFrame(self)
        button_frame.pack(fill="x", padx=20, pady=(5,20), side="bottom")
        close_button = ctk.CTkButton(button_frame, text="Close", command=self.on_close, font=self.app.ui_font)
        close_button.pack(side="right")

        self.protocol("WM_DELETE_WINDOW", self.on_close)


    def on_close(self):
        self.stop_hotkey_listening()
        if self._main_hotkey_paused:
            self.app.app_logic.update_global_hotkey_listener()
            self.app.log_message("Main app's global hotkey listener re-enabled after settings window close.")

        self.save_player_command()
        self.save_subtitle_settings()
        self.save_general_settings()
        self.save_global_hotkey_settings()
        self.destroy()

    def browse_download_directory(self):
        new_dir = filedialog.askdirectory(initialdir=self.download_dir_var.get())
        if new_dir:
            self.download_dir_var.set(new_dir)
            self.app.settings["download_directory"] = new_dir
            self.app.download_dir = new_dir
            self.app.save_app_settings()
            self.app.log_message(f"Download directory changed to: {new_dir}")

    def change_default_download_type(self, new_type):
        self.app.settings["default_download_type"] = new_type
        self.app.download_type_var.set(new_type)
        self.app.save_app_settings()

    def change_font_settings(self, _=None):
        font_family = self.font_family_var.get()
        font_size_name = self.font_size_name_var.get()
        self.app.settings["font_family"] = font_family
        self.app.settings["font_size_name"] = font_size_name
        self.app.save_app_settings()
        self.app.ui_manager.apply_font_settings() # Re-apply fonts across app

    # NEW: Method to change history item size
    def change_history_item_size(self, new_size_name):
        self.app.settings["history_item_size_name"] = new_size_name
        self.app.save_app_settings()
        self.app.log_message(f"History/Active list item size changed to: {new_size_name}")
        # Trigger redraw of history and active downloads to apply new size
        self.app.history_manager.redraw_history_listbox()
        # Active download items are added dynamically, but if any are active, they'll
        # use the new default. New ones will apply this. Existing ones won't change unless rebuilt.
        # For simplicity, we just trigger redraw of history, active items are more transient.


    def save_player_command(self, _=None):
        player_cmd = self.player_command_var.get().strip()
        if player_cmd != self.app.settings.get("player_command", DEFAULT_PLAYER_COMMAND):
            self.app.settings["player_command"] = player_cmd
            self.app.save_app_settings()
            self.app.log_message(f"Preferred player command set to: '{player_cmd if player_cmd else 'OS Default'}'")

    def save_subtitle_settings(self, _=None):
        changed = False
        if self.app.settings.get("download_subtitles") != self.download_subs_var.get():
            self.app.settings["download_subtitles"] = self.download_subs_var.get()
            changed = True
        if self.app.settings.get("embed_subtitles") != self.embed_subs_var.get():
            self.app.settings["embed_subtitles"] = self.embed_subs_var.get()
            changed = True

        new_langs = self.subs_langs_var.get().strip()
        if self.app.settings.get("subtitle_languages") != new_langs:
            self.app.settings["subtitle_languages"] = new_langs
            changed = True

        if changed:
            self.app.save_app_settings()
            self.app.log_message("Subtitle settings updated.")

    def save_general_settings(self, _=None):
        changed = False
        if self.app.settings.get("auto_paste_on_focus") != self.auto_paste_on_focus_var.get():
            self.app.settings["auto_paste_on_focus"] = self.auto_paste_on_focus_var.get()
            changed = True

        if changed:
            self.app.save_app_settings()
            self.app.log_message("General behavior settings updated.")

    def toggle_global_hotkey(self):
        enabled = self.global_hotkey_enabled_var.get()
        self.app.settings["global_hotkey_enabled"] = enabled
        self.app.save_app_settings()
        self.app.app_logic.update_global_hotkey_listener()
        if enabled:
            self.app.log_message(f"Global hotkey enabled. Hotkey: {self.global_hotkey_combination_var.get()}")
        else:
            self.app.log_message("Global hotkey disabled.")

    def save_global_hotkey_settings(self):
        self.toggle_global_hotkey()

    def start_hotkey_listening(self):
        if self.app.app_logic.global_hotkey_manager and \
           self.app.app_logic.global_hotkey_manager.listener_thread and \
           self.app.app_logic.global_hotkey_manager.listener_thread.is_alive():
            self.app.app_logic.global_hotkey_manager.stop_listener()
            self.app.log_message("Temporarily paused main app's global hotkey listener.")
            self._main_hotkey_paused = True
        else:
            self._main_hotkey_paused = False

        self.global_hotkey_combination_var.set("Press your hotkey combination...")
        self.set_hotkey_button.configure(text="Listening...", state="disabled")
        self.hotkey_entry.configure(state="readonly")
        self.app.log_message("Listening for new global hotkey combination...")

        self._hotkey_current_modifiers = set()
        self._hotkey_main_key = None

        if self._hotkey_listener is not None:
            self.stop_hotkey_listening()

        self._hotkey_listener = keyboard.Listener(
            on_press=self._on_key_press_for_setting,
            on_release=self._on_key_release_for_setting
        )
        self._hotkey_listening_thread = threading.Thread(target=self._hotkey_listener.start, daemon=True)
        self._hotkey_listening_thread.start()

    def _on_key_press_for_setting(self, key):
        try:
            if key in [keyboard.Key.ctrl_l, keyboard.Key.ctrl_r]: self._hotkey_current_modifiers.add("<ctrl>")
            elif key in [keyboard.Key.alt_l, keyboard.Key.alt_r]: self._hotkey_current_modifiers.add("<alt>")
            elif key in [keyboard.Key.shift_l, keyboard.Key.shift_r]: self._hotkey_current_modifiers.add("<shift>")
            elif key in [keyboard.Key.cmd_l, keyboard.Key.cmd_r]: self._hotkey_current_modifiers.add("<cmd>")
            elif key == keyboard.Key.alt_gr: self._hotkey_current_modifiers.add("<alt_gr>")
            else:
                if self._hotkey_main_key is None or key != self._hotkey_main_key:
                    self._hotkey_main_key = key

            self.app.after(0, self._update_hotkey_display)

        except Exception as e:
            self.app.log_message(f"Error in hotkey listener (press): {e}")

    def _on_key_release_for_setting(self, key):
        try:
            if key == self._hotkey_main_key:
                self.app.after(0, self.finish_hotkey_listening)
            elif key in [keyboard.Key.ctrl_l, keyboard.Key.ctrl_r]: self._hotkey_current_modifiers.discard("<ctrl>")
            elif key in [keyboard.Key.alt_l, keyboard.Key.alt_r]: self._hotkey_current_modifiers.discard("<alt>")
            elif key in [keyboard.Key.shift_l, keyboard.Key.shift_r]: self._hotkey_current_modifiers.discard("<shift>")
            elif key in [keyboard.Key.cmd_l, keyboard.Key.cmd_r]: self._hotkey_current_modifiers.discard("<cmd>")
            elif key == keyboard.Key.alt_gr: self._hotkey_current_modifiers.discard("<alt_gr>")


        except Exception as e:
            self.app.log_message(f"Error in hotkey listener (release): {e}")

    def _convert_pynput_key_to_display(self, key):
        if hasattr(key, 'char') and key.char is not None:
            return key.char.upper() if key.char.isalpha() else key.char
        elif isinstance(key, keyboard.Key):
            if key == keyboard.Key.space: return "Space"
            if key == keyboard.Key.enter: return "Enter"
            return str(key).split('.')[1].replace("_l", "").replace("_r", "").capitalize() if '.' in str(key) else str(key)
        return str(key)

    def _format_hotkey_combination_string(self):
        parts = []
        modifiers_canonical = sorted(list(self._hotkey_current_modifiers))

        for mod in modifiers_canonical:
            parts.append(mod)

        if self._hotkey_main_key:
            if hasattr(self._hotkey_main_key, 'char') and self._hotkey_main_key.char is not None:
                parts.append(self._hotkey_main_key.char.lower())
            elif isinstance(self._hotkey_main_key, keyboard.Key):
                key_name = str(self._hotkey_main_key).split('.')[1].lower()
                parts.append(f"<{key_name}>")
            else:
                parts.append(str(self._hotkey_main_key).lower())


        return "+".join(parts) if parts else "None"


    def _update_hotkey_display(self):
        display_parts = sorted(list(self._hotkey_current_modifiers))
        if self._hotkey_main_key:
            display_parts.append(self._convert_pynput_key_to_display(self._hotkey_main_key))
        display_text = "+".join(display_parts) if display_parts else "Press your hotkey combination..."
        self.global_hotkey_combination_var.set(display_text)


    def finish_hotkey_listening(self):
        if self._hotkey_listener is None:
            return

        self.stop_hotkey_listening()

        new_hotkey_combo_string = self._format_hotkey_combination_string()

        if new_hotkey_combo_string == "None" or not new_hotkey_combo_string:
            self.app.log_message("No valid hotkey combination detected. Hotkey cleared.")
            final_combo_to_save = "None"
        else:
             self.app.log_message(f"New hotkey captured: '{new_hotkey_combo_string}'")
             final_combo_to_save = new_hotkey_combo_string

        self.global_hotkey_combination_var.set(final_combo_to_save)
        self.save_global_hotkey_combination_now(final_combo_to_save)

        self.set_hotkey_button.configure(text="Set Hotkey", state="normal")
        self._hotkey_current_modifiers = set()
        self._hotkey_main_key = None

        if self._main_hotkey_paused:
            self.app.app_logic.update_global_hotkey_listener()
            self._main_hotkey_paused = False


    def stop_hotkey_listening(self):
        if self._hotkey_listener:
            try:
                self._hotkey_listener.stop()
                self._hotkey_listener = None
                self.app.log_message("Stopped listening for new hotkey.")
            except Exception as e:
                self.app.log_message(f"ERROR: Failed to stop temporary hotkey listener: {e}")
        if self._hotkey_listening_thread and self._hotkey_listening_thread.is_alive():
            pass

    def save_global_hotkey_combination_now(self, new_combination):
        self.app.settings["global_hotkey_combination"] = new_combination
        self.app.save_app_settings()
        self.app.log_message(f"Global hotkey combination set to: '{new_combination}' (persisted).")

    def refresh_history(self):
        self.app.log_message("Refreshing download history from disk...")
        self.app.history_items_with_paths.clear()
        self.app.thumbnail_cache.clear()
        self.app.history_manager.load_existing_downloads_to_history()
        self.app.log_message("History refreshed and thumbnail/duration generation re-initiated if needed.")

    def confirm_clear_download_history(self):
        if messagebox.askyesno("Confirm Clear History",
                               "Are you sure you want to clear the entire download history?\n"
                               "This action cannot be undone and does not delete files from disk.",
                               icon='warning', parent=self):
            self.app.history_manager.clear_download_history_data()

    def confirm_clear_thumbnail_cache(self):
        if messagebox.askyesno("Confirm Clear Thumbnail Cache",
                               "Are you sure you want to clear the thumbnail cache?\n"
                               "This will delete all .jpg thumbnail files from your download directory "
                               "that appear to be associated with media files.\n"
                               "This action cannot be undone.",
                               icon='warning', parent=self):
            self.app.history_manager.clear_thumbnail_cache_data()

    def open_about_window(self):
        if not hasattr(self, '_about_window_instance') or \
           self._about_window_instance is None or \
           not self._about_window_instance.winfo_exists():
            self._about_window_instance = AboutWindow(self, app_instance=self.app)
            self._about_window_instance.focus_force()
        else:
            self._about_window_instance.lift()
            self._about_window_instance.focus_force()

    def _reset_ui_on_download_completion(self, is_full_reset=True):
        if is_full_reset:
            if self.url_input_type_var.get() == "Single URL":
                 self.download_button.configure(text="⬇️ Download from Clipboard")
            else:
                 self.download_button.configure(text="⬇️ Download Playlist/Batch")

            self.cancel_button.configure(state="disabled")
            self.progress_bar.set(0)
            self.progress_details_label.configure(text="Current Task: N/A | Overall Progress: N/A")
            self.current_active_download_id = None
            self.current_download_cancel_event = None
            self.app_logic.current_playlist_download_info = {
                "total_items": 0, "completed_items": 0, "failed_items": 0, "skipped_items": 0, "cancelled": False
            }
        else:
            self.progress_bar.set(0) # Reset progress for next item in playlist
            # progress_details_label is managed by the playlist logic itself
            self.current_active_download_id = None

    def _create_active_download_item_ui(self, download_id, item_data):
        """
        Creates and returns a UI frame for a new active download item.
        Also adds it to self.active_downloads.
        """
        # Get current item size preference
        current_item_ipady = HISTORY_ITEM_SIZES.get(self.settings.get("history_item_size_name"), HISTORY_ITEM_SIZES["Normal"])

        item_frame = ctk.CTkFrame(self.active_downloads_scrollable_frame, corner_radius=5)
        item_frame.pack(fill="x", pady=2, padx=5, ipady=current_item_ipady) # Apply ipady here

        # Title Label
        title_text = item_data.get("title", item_data.get("url", "Unknown Title"))
        # Add index for playlist items
        if item_data.get("is_playlist_item") and item_data.get("playlist_item_index"):
            title_text = f"#{item_data['playlist_item_index']}: {title_text}"

        title_label = ctk.CTkLabel(item_frame, text=title_text, font=self.ui_font, anchor="w", wraplength=450)
        title_label.pack(fill="x", padx=5, pady=(5,0))

        # Progress Bar for individual item
        progress_bar = ctk.CTkProgressBar(item_frame, orientation="horizontal")
        progress_bar.set(0)
        progress_bar.pack(fill="x", padx=5, pady=(2,0))

        # Details Label (Progress, Speed | ETA)
        details_label = ctk.CTkLabel(item_frame, text="Progress: 0% | Speed: N/A | ETA: N/A", font=self.ui_font_small, text_color="gray", anchor="w")
        details_label.pack(fill="x", padx=5, pady=(0,5))

        # Status Label (e.g., "Queued", "Downloading...", "Completed", "Failed")
        status_text = item_data.get("status", "Queued")
        status_label = ctk.CTkLabel(item_frame, text=f"Status: {status_text.capitalize()}", font=self.ui_font_small, text_color="gray", anchor="w")
        status_label.pack(fill="x", padx=5, pady=(0,5))

        # Store UI elements by download_id for easy updates
        self.active_downloads[download_id] = {
            "frame": item_frame,
            "title_label": title_label,
            "progress_bar": progress_bar,
            "details_label": details_label,
            "status_label": status_label,
            "data": item_data # Store original data
        }
        return item_frame

    def _update_active_download_item_ui(self, download_id, update_data):
        """Updates the UI of an active download item."""
        if download_id not in self.active_downloads:
            self.log_message(f"WARN: Attempted to update non-existent download item UI for ID: {download_id[:8]}")
            return

        item_ui = self.active_downloads[download_id]
        item_data = item_ui["data"]
        item_data.update(update_data) # Update internal data dict

        # Update specific UI elements based on data
        if "title" in update_data:
            item_ui["title_label"].configure(text=item_data["title"])
        if "progress_percent" in update_data:
            item_ui["progress_bar"].set(update_data["progress_percent"] / 100.0)
            item_ui["details_label"].configure(
                text=f"Progress: {item_data['progress_percent']:.1f}% | Speed: {item_data.get('speed','N/A')} | ETA: {item_data.get('eta','N/A')}"
            )
        # Status update comes via MSG_DOWNLOAD_ITEM_STATUS, handled separately
        if "status" in update_data:
            status = update_data["status"]
            message = update_data.get("message", status)
            color = "gray"
            if status == "completed": color = "green"
            elif status == "failed": color = "red"
            elif status == "cancelled": color = "orange"
            elif status == "downloading" or status == "starting": color = "blue"

            item_ui["status_label"].configure(text=f"Status: {status.capitalize()} - {message}", text_color=color)
            # Finalize progress bar for completed/failed/cancelled states if it's the last update
            item_ui["progress_bar"].set(0 if status in ["failed", "cancelled"] else (1 if status == "completed" else item_ui["progress_bar"].get()))


    def _remove_active_download_item_ui(self, download_id):
        """Removes the UI frame for a completed/failed download item."""
        if download_id in self.active_downloads:
            item_ui = self.active_downloads.pop(download_id)
            item_ui["frame"].destroy()

    def process_download_queue(self):
        try:
            while True:
                message = self.download_queue.get_nowait()
                msg_type = message[0]
                payload = message[1:]

                if msg_type == MSG_DOWNLOAD_ITEM_ADDED:
                    # Payload: ("QUEUED_PLAYLIST_ITEM", {item_data}) OR (download_id, {item_data})
                    if payload[0] == "QUEUED_PLAYLIST_ITEM":
                        item_data = payload[1]
                        self.pending_downloads.put(item_data)
                        self.log_message(f"Playlist item queued: {item_data.get('url')[:50]}...")
                        # A new active download item UI will be created when it actually starts.
                        self.start_next_download_if_available()
                    else:
                        download_id = payload[0]
                        item_data = payload[1]
                        self.current_active_download_id = download_id # Mark as currently active

                        # Create UI for this active item
                        self._create_active_download_item_ui(download_id, item_data)
                        # Set initial status explicitly if not set in ADDED message
                        if not item_data.get("status"):
                            self.active_downloads[download_id]["status_label"].configure(text="Status: Downloading...", text_color="blue")
                        self.log_message(f"Download item '{item_data.get('title', item_data.get('url'))[:50]}' (ID: {download_id[:8]}) added to active downloads.")


                elif msg_type == MSG_DOWNLOAD_ITEM_UPDATE:
                    download_id, update_data = payload
                    self._update_active_download_item_ui(download_id, update_data)

                    if download_id == self.current_active_download_id:
                        # Update overall progress bar & details for the currently active download item
                        percent = update_data.get("progress_percent", self.active_downloads[download_id]["progress_bar"].get() * 100)

                        if self.app_logic.current_playlist_download_info["total_items"] > 0:
                            # Overall playlist progress for main bar
                            total = self.app_logic.current_playlist_download_info["total_items"]
                            completed = self.app_logic.current_playlist_download_info["completed_items"]
                            # Current item's contribution to overall progress
                            current_item_portion = percent / 100.0 / total if total > 0 else 0
                            overall_percentage = (completed / total if total > 0 else 0) + current_item_portion
                            self.progress_bar.set(overall_percentage) # Overall progress

                            speed_str = update_data.get("speed", "N/A")
                            eta_str = update_data.get("eta", "N/A")
                            self.progress_details_label.configure(
                                text=f"Item {completed+1}/{total} | Speed: {speed_str} | ETA: {eta_str}"
                            )
                        else: # Single download progress for main bar and details
                            self.progress_bar.set(percent / 100.0) # Main bar shows current item progress
                            speed_str = update_data.get("speed", "N/A")
                            eta_str = update_data.get("eta", "N/A")
                            self.progress_details_label.configure(
                                text=f"Speed: {speed_str} | ETA: {eta_str}"
                            )

                elif msg_type == MSG_DOWNLOAD_ITEM_STATUS:
                    download_id, status_payload = payload
                    self._update_active_download_item_ui(download_id, status_payload) # Update final status in UI

                    is_playlist_item = status_payload.get("is_playlist_item", False)
                    if is_playlist_item:
                        if status_payload["status"] == "completed":
                            self.app_logic.current_playlist_download_info["completed_items"] += 1
                        elif status_payload["status"] == "failed":
                            self.app_logic.current_playlist_download_info["failed_items"] += 1
                            # If it was a critical failure for the playlist, the _fetch_playlist_urls would have already set "cancelled"
                            # For individual item failures, we don't automatically cancel the whole playlist.
                        elif status_payload["status"] == "cancelled":
                            self.app_logic.current_playlist_download_info["cancelled"] = True # Mark overall playlist as cancelled
                            # No need to increment completed/failed for cancelled item here, that's done only for success/fail

                        # Add item to history if it completed or failed
                        if status_payload["status"] in ["completed", "failed"]:
                            history_basename = status_payload.get("file_path", status_payload.get("url", "Unknown Item")).split(os.sep)[-1]
                            if status_payload["status"] == "failed":
                                history_basename = f"[Failed] {history_basename}"
                            actual_display_name_base = status_payload.get("title", history_basename)
                            self.history_manager.update_history(
                                actual_display_name_base,
                                status_payload["file_path"],
                                status_payload["item_type_for_history"],
                                status_payload["thumbnail_path"],
                                status_payload["sub_indicator"],
                                status_payload["download_date_str"]
                            )

                        # Check if overall playlist is complete/cancelled
                        total_items = self.app_logic.current_playlist_download_info["total_items"]
                        processed_items = self.app_logic.current_playlist_download_info["completed_items"] + \
                                          self.app_logic.current_playlist_download_info["failed_items"] + \
                                          self.app_logic.current_playlist_download_info["skipped_items"]

                        if total_items > 0 and (processed_items == total_items or self.app_logic.current_playlist_download_info["cancelled"]):
                            # Playlist finished or cancelled
                            self.log_message(f"Playlist sequence finished. Total: {total_items}, Completed: {self.app_logic.current_playlist_download_info['completed_items']}, Failed: {self.app_logic.current_playlist_download_info['failed_items']}, Cancelled: {self.app_logic.current_playlist_download_info['cancelled']}.")

                            # Final overall progress bar update
                            self.progress_bar.set(1.0 if not self.app_logic.current_playlist_download_info["cancelled"] else 0)

                            if self.app_logic.current_playlist_download_info["cancelled"]:
                                messagebox.showinfo("Playlist Download Cancelled", "The playlist download has been cancelled.", parent=self)
                            else:
                                messagebox.showinfo(
                                    "Playlist Download Complete",
                                    f"Playlist download finished! {self.app_logic.current_playlist_download_info['completed_items']}/{total_items} items completed, {self.app_logic.current_playlist_download_info['failed_items']} failed.",
                                    parent=self
                                )
                            self._reset_ui_on_download_completion(is_full_reset=True) # Full UI reset
                            self._remove_active_download_item_ui(download_id) # Ensure this item is removed too
                            self.current_active_download_id = None # No current active download

                        else: # Playlist item completed, but playlist still active (not all items processed yet)
                            # Remove this item's UI, then start next queued item
                            self._remove_active_download_item_ui(download_id)
                            self.current_active_download_id = None # Clear active ID for next item
                            self.start_next_download_if_available() # Attempt to start next queued item


                    else: # This is a standalone single download (not part of a playlist)
                        self._reset_ui_on_download_completion(is_full_reset=True)
                        # Display message box based on status
                        if status_payload["status"] == "completed":
                            messagebox.showinfo("Download Complete", status_payload["message"], parent=self)
                            self.progress_bar.set(1.0)
                        elif status_payload["status"] == "failed":
                            messagebox.showerror("Download Failed", status_payload["message"], parent=self)
                            self.progress_bar.set(0)
                        elif status_payload["status"] == "cancelled":
                            messagebox.showinfo("Download Cancelled", status_payload["message"], parent=self)
                            self.progress_bar.set(0)

                        # Add to history if status is completed or failed
                        if status_payload["status"] in ["completed", "failed"]:
                            history_basename = status_payload.get("file_path", status_payload.get("url", "Unknown Item")).split(os.sep)[-1]
                            if status_payload["status"] == "failed":
                                history_basename = f"[Failed] {history_basename}"
                            actual_display_name_base = status_payload.get("title", history_basename)
                            self.history_manager.update_history(
                                actual_display_name_base,
                                status_payload["file_path"],
                                status_payload["item_type_for_history"],
                                status_payload["thumbnail_path"],
                                status_payload["sub_indicator"],
                                status_payload["download_date_str"]
                            )
                        self.download_threads = [t for t in self.download_threads if t.is_alive()] # Clean up running threads

                elif isinstance(message, str) and message.startswith(MSG_LOG_PREFIX):
                    self.log_message(message.replace(MSG_LOG_PREFIX, "").strip())
                else:
                    self.log_message(f"Unhandled message from download queue: {message}")
        except queue.Empty:
            pass

        # Process thumbnail generation queue
        try:
            while True:
                thumb_message = self.thumbnail_gen_queue.get_nowait()
                if isinstance(thumb_message, tuple) and thumb_message[0] == "THUMB_DONE":
                    _, video_path, new_thumb_path = thumb_message
                    updated = False
                    for item in self.history_items_with_paths:
                        if item.get("file_path") == video_path:
                            item["thumbnail_path"] = new_thumb_path
                            if new_thumb_path in self.thumbnail_cache:
                                del self.thumbnail_cache[new_thumb_path]
                            updated = True
                            break
                    if updated:
                        self.log_message(f"INFO: Updated thumbnail for {os.path.basename(video_path)} in history.")
                        self.history_manager.redraw_history_listbox()
                    else:
                        self.log_message(
                            f"WARN: Received THUMB_DONE for {video_path}, but item not found in history (may have been cleared)."
                        )
                elif isinstance(thumb_message, str) and thumb_message.startswith(MSG_LOG_PREFIX):
                    self.log_message(thumb_message.replace(MSG_LOG_PREFIX, "").strip())
        except queue.Empty:
            pass

        # Process duration calculation queue
        try:
            while True:
                duration_message = self.duration_queue.get_nowait()
                if isinstance(duration_message, tuple) and duration_message[0] == MSG_DURATION_DONE:
                    _, file_path_for_duration, duration_seconds, _ = duration_message
                    updated = False

                    item_to_update = None
                    current_idx = -1
                    for i, hist_item in enumerate(self.history_items_with_paths):
                        if hist_item.get("file_path") == file_path_for_duration:
                            item_to_update = hist_item
                            current_idx = i
                            break

                    if item_to_update:
                        item_to_update["duration"] = duration_seconds
                        item_to_update["formatted_duration"] = self.app_logic._format_duration(duration_seconds)
                        updated = True
                        self.log_message(f"INFO: Updated duration for {os.path.basename(file_path_for_duration)}: {item_to_update['formatted_duration']}.")

                        if 0 <= current_idx < len(self.history_manager.history_item_frames):
                            item_frame_widget = self.history_manager.history_item_frames[current_idx]
                            for child in item_frame_widget.winfo_children():
                                if isinstance(child, ctk.CTkLabel) and child.cget("text").startswith("Duration:"):
                                    child.configure(text=item_to_update["formatted_duration"])
                                    break
                            else:
                                self.history_manager.redraw_history_listbox()
                        else:
                            self.history_manager.redraw_history_listbox()
                    else:
                        self.log_message(
                            f"WARN: Received DURATION_DONE for {file_path_for_duration}, but item not found or mismatched in history."
                        )
                elif isinstance(duration_message, str) and duration_message.startswith(MSG_LOG_PREFIX):
                    self.log_message(duration_message.replace(MSG_LOG_PREFIX, "").strip())
        except queue.Empty:
            pass

        # Process format information queue
        try:
            while True:
                format_message = self.format_info_queue.get_nowait()
                self.get_formats_button.configure(state="normal", text="🎞️ Get Formats")

                if isinstance(format_message, tuple):
                    msg_type, data = format_message
                    if msg_type == "FORMAT_JSON_DATA":
                        self.log_message("Successfully fetched format JSON. Parsing...")
                        parsed_formats = self.format_fetcher._parse_formats_json(data)
                        if parsed_formats:
                            self.log_message(f"Parsed {len(parsed_formats)} formats. Opening selection window.")
                            self.open_format_selection_window(parsed_formats)
                        else:
                            self.log_message("No formats could be parsed from the JSON output.")
                            messagebox.showinfo(
                                "No Formats", "Could not parse any formats from the output. Check logs.", parent=self
                            )
                    elif msg_type == MSG_LOG_PREFIX:
                        self.log_message(data.replace(MSG_LOG_PREFIX, "(FormatFetch) ").strip())
                    elif msg_type == "FORMAT_ERROR":
                        self.log_message(f"Error fetching formats: {data}")
                        messagebox.showerror("Format Fetch Error", str(data), parent=self)
        except queue.Empty:
            pass

        # Schedule the next call to this method
        self.after(100, self.process_download_queue)

    def on_closing(self):
        active_downloads_from_thread_list = any(t.is_alive() for t in self.download_threads)
        active_thumb_gens = any(t.is_alive() for t in self.app_logic.thumbnail_gen_threads)
        active_duration_gens = any(t.is_alive() for t in self.app_logic.duration_gen_threads)
        active_format_fetch = self.format_fetcher.format_fetch_thread and self.format_fetcher.format_fetch_thread.is_alive()

        # Check if there are active downloads from our custom queue
        active_downloads_from_queue = not self.pending_downloads.empty() or self.current_active_download_id is not None

        # Signal current active download to stop if there is one
        if self.current_download_cancel_event and not self.current_download_cancel_event.is_set():
            self.current_download_cancel_event.set()
            self.log_message("Signaling active download to stop before closing.")
            time.sleep(0.1)

        if self.app_logic.global_hotkey_manager:
            self.app_logic.global_hotkey_manager.stop_listener()
            self.log_message("Global hotkey listener stopped.")

        active_downloads_from_thread_list = any(t.is_alive() for t in self.download_threads)
        active_downloads_from_queue = not self.pending_downloads.empty() or self.current_active_download_id is not None

        if active_downloads_from_thread_list or active_thumb_gens or active_duration_gens or active_format_fetch or active_downloads_from_queue:
            msg = "Warning: The following background processes or queued downloads are still active:\n"
            if active_downloads_from_thread_list or active_downloads_from_queue:
                msg += "- Downloads in progress or queued.\n"
            if active_thumb_gens:
                msg += "- Thumbnail generation in progress.\n"
            if active_duration_gens:
                msg += "- Media duration calculation in progress.\n"
            if active_format_fetch:
                msg += "- Format fetching in progress.\n"
            msg += "\nExiting now might terminate them abruptly. Continue anyway?"

            if messagebox.askyesno("Exit Application", msg, parent=self):
                self.destroy()
        else:
            self.destroy()