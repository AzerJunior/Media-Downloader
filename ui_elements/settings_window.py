import customtkinter as ctk
from tkinter import filedialog, messagebox
import os
import threading
from pynput import keyboard

# Assuming constants are in the parent directory
from constants import (
    DEFAULT_FONT_FAMILY, FONT_FAMILIES, FONT_SIZES, DEFAULT_FONT_SIZE_NAME,
    DEFAULT_PLAYER_COMMAND
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

        self._hotkey_listener = None # Listener for setting new hotkey
        self._hotkey_listening_thread = None
        self._hotkey_current_modifiers = set() # To track currently pressed modifiers
        self._hotkey_main_key = None         # To store the last non-modifier key pressed
        self._main_hotkey_paused = False # Flag to track if main app hotkey was paused

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
        # Changed state to readonly, removed bind calls here
        self.hotkey_entry = ctk.CTkEntry(hotkey_combo_frame, textvariable=self.global_hotkey_combination_var, font=self.app.ui_font, state="readonly", width=150)
        self.hotkey_entry.pack(side="left", padx=5, pady=5)

        self.set_hotkey_button = ctk.CTkButton(hotkey_combo_frame, text="Set Hotkey", command=self.start_hotkey_listening, font=self.app.ui_font)
        self.set_hotkey_button.pack(side="left", padx=5, pady=5)
        Tooltip(self.set_hotkey_button, "Click to listen for your next key combination. Press modifiers then the final key.")
        # Info label for instructions
        ctk.CTkLabel(hotkey_group, text="Press the desired modifier keys (e.g., Ctrl, Alt, Shift, Cmd) and then the trigger key.",
                     font=(self.app.ui_font.cget("family"), int(self.app.ui_font.cget("size")*0.8)),
                     text_color="gray", wraplength=400).pack(fill="x", padx=15, pady=(0,10))


        # --- Close Button ---
        button_frame = ctk.CTkFrame(self)
        button_frame.pack(fill="x", padx=20, pady=(5,20), side="bottom")
        close_button = ctk.CTkButton(button_frame, text="Close", command=self.on_close, font=self.app.ui_font)
        close_button.pack(side="right")

        # Bind protocol for closing the window (to stop hotkey listener)
        self.protocol("WM_DELETE_WINDOW", self.on_close)


    def on_close(self):
        self.stop_hotkey_listening() # Stop any active listening if window closed
        # Ensure main app hotkey listener is re-enabled if it was paused by this window
        if self._main_hotkey_paused:
            self.app.app_logic.update_global_hotkey_listener() # Call through AppLogic
            self.app.log_message("Main app's global hotkey listener re-enabled after settings window close.")

        self.save_player_command()
        self.save_subtitle_settings()
        self.save_general_settings()
        self.save_global_hotkey_settings() # Call to ensure enable/disable state is saved
        self.destroy()

    def browse_download_directory(self):
        new_dir = filedialog.askdirectory(initialdir=self.download_dir_var.get())
        if new_dir:
            self.download_dir_var.set(new_dir)
            self.app.settings["download_directory"] = new_dir
            self.app.download_dir = new_dir # Update main app's download_dir directly
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
        self.app.ui_manager.apply_font_settings() # Call through UIManager

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
        self.app.app_logic.update_global_hotkey_listener() # Trigger update in AppLogic
        if enabled:
            self.app.log_message(f"Global hotkey enabled. Hotkey: {self.global_hotkey_combination_var.get()}")
        else:
            self.app.log_message("Global hotkey disabled.")

    def save_global_hotkey_settings(self):
        # This function is called from on_close to ensure the enable/disable state is saved.
        # The combination is saved by save_global_hotkey_combination_now during capture.
        self.toggle_global_hotkey() # Ensure enabled/disabled state is propagated and saved
        # No additional save needed here for the combination itself.


    # NEW METHODS for "Set Hotkey" button logic
    def start_hotkey_listening(self):
        """Starts a temporary listener to capture the next hotkey combination."""
        # Stop main app's global hotkey listener to prevent conflicts
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
        # Ensure the entry field is readonly when listening
        self.hotkey_entry.configure(state="readonly")
        self.app.log_message("Listening for new global hotkey combination...")

        self._hotkey_current_modifiers = set() # Reset active modifiers
        self._hotkey_main_key = None         # Reset main key

        if self._hotkey_listener is not None:
            self.stop_hotkey_listening() # Ensure previous listener is stopped before starting a new one

        # Create a new listener that monitors all key presses and releases
        self._hotkey_listener = keyboard.Listener(
            on_press=self._on_key_press_for_setting,
            on_release=self._on_key_release_for_setting
        )
        self._hotkey_listening_thread = threading.Thread(target=self._hotkey_listener.start, daemon=True)
        self._hotkey_listening_thread.start()

    def _on_key_press_for_setting(self, key):
        """Callback for key press while listening for new hotkey."""
        try:
            # Add common modifier keys to the set of current modifiers (canonical form)
            if key in [keyboard.Key.ctrl_l, keyboard.Key.ctrl_r]: self._hotkey_current_modifiers.add("<ctrl>")
            elif key in [keyboard.Key.alt_l, keyboard.Key.alt_r]: self._hotkey_current_modifiers.add("<alt>")
            elif key in [keyboard.Key.shift_l, keyboard.Key.shift_r]: self._hotkey_current_modifiers.add("<shift>")
            elif key in [keyboard.Key.cmd_l, keyboard.Key.cmd_r]: self._hotkey_current_modifiers.add("<cmd>") # macOS Cmd key
            elif key == keyboard.Key.alt_gr: self._hotkey_current_modifiers.add("<alt_gr>") # AltGr key
            else:
                # Any non-modifier key pressed means this is the primary hotkey
                # Only set if it hasn't been set yet or if a new primary key is pressed
                if self._hotkey_main_key is None or key != self._hotkey_main_key:
                    self._hotkey_main_key = key

            # Update display immediately (showing current modifiers + potential main key)
            # Use self.after to ensure UI updates happen on the main thread
            self.app.after(0, self._update_hotkey_display)

        except Exception as e:
            self.app.log_message(f"Error in hotkey listener (press): {e}")

    def _on_key_release_for_setting(self, key):
        """Callback for key release while listening for new hotkey."""
        try:
            # If the released key is the main key, then the combination is complete
            if key == self._hotkey_main_key:
                self.app.after(0, self.finish_hotkey_listening)
            # If a modifier key is released, remove it from current modifiers (canonical form)
            elif key in [keyboard.Key.ctrl_l, keyboard.Key.ctrl_r]: self._hotkey_current_modifiers.discard("<ctrl>")
            elif key in [keyboard.Key.alt_l, keyboard.Key.alt_r]: self._hotkey_current_modifiers.discard("<alt>")
            elif key in [keyboard.Key.shift_l, keyboard.Key.shift_r]: self._hotkey_current_modifiers.discard("<shift>")
            elif key in [keyboard.Key.cmd_l, keyboard.Key.cmd_r]: self._hotkey_current_modifiers.discard("<cmd>")
            elif key == keyboard.Key.alt_gr: self._hotkey_current_modifiers.discard("<alt_gr>")


        except Exception as e:
            self.app.log_message(f"Error in hotkey listener (release): {e}")

    def _convert_pynput_key_to_display(self, key):
        """Converts pynput key object to a displayable string for the UI."""
        if hasattr(key, 'char') and key.char is not None:
            # For regular characters, capitalize if it's a letter
            return key.char.upper() if key.char.isalpha() else key.char
        elif isinstance(key, keyboard.Key): # Special keys (e.g., Key.space, Key.enter, Key.f1)
            if key == keyboard.Key.space: return "Space"
            if key == keyboard.Key.enter: return "Enter"
            # Convert to string without 'Key.' prefix and capitalize (e.g., 'f1', 'esc')
            return str(key).split('.')[1].replace("_l", "").replace("_r", "").capitalize() if '.' in str(key) else str(key)
        return str(key) # Fallback

    def _format_hotkey_combination_string(self):
        """Formats the currently captured hotkey combination into pynput's string format (e.g., '<ctrl>+<shift>+a')."""
        parts = []
        # Add modifiers first, in a consistent sorted order for canonical representation
        # Use set() to ensure unique modifiers if both left/right are pressed simultaneously
        modifiers_canonical = sorted(list(self._hotkey_current_modifiers))

        for mod in modifiers_canonical:
            parts.append(mod)

        # Add the main key
        if self._hotkey_main_key:
            if hasattr(self._hotkey_main_key, 'char') and self._hotkey_main_key.char is not None:
                parts.append(self._hotkey_main_key.char.lower()) # pynput expects 'a', not 'A'
            elif isinstance(self._hotkey_main_key, keyboard.Key):
                # Convert special keys to pynput's string representation (e.g., '<enter>', '<space>', '<f1>')
                # Ensure it's lowercase with <>
                key_name = str(self._hotkey_main_key).split('.')[1].lower()
                parts.append(f"<{key_name}>")
            else:
                parts.append(str(self._hotkey_main_key).lower()) # Fallback for other keys, ensure lower


        return "+".join(parts) if parts else "None"


    def _update_hotkey_display(self):
        """Updates the temporary display string for the hotkey combination in the entry field."""
        display_parts = sorted(list(self._hotkey_current_modifiers)) # Sort modifiers for consistent display
        if self._hotkey_main_key:
            display_parts.append(self._convert_pynput_key_to_display(self._hotkey_main_key))
        display_text = "+".join(display_parts) if display_parts else "Press your hotkey combination..."
        self.global_hotkey_combination_var.set(display_text)


    def finish_hotkey_listening(self):
        """Stops the hotkey listening and saves the new combination."""
        if self._hotkey_listener is None:
            return

        self.stop_hotkey_listening() # Stops the Listener thread gracefully

        # Construct the final hotkey string for pynput
        new_hotkey_combo_string = self._format_hotkey_combination_string()

        if new_hotkey_combo_string == "None" or not new_hotkey_combo_string:
            self.app.log_message("No valid hotkey combination detected. Hotkey cleared.")
            final_combo_to_save = "None"
        else:
             self.app.log_message(f"New hotkey captured: '{new_hotkey_combo_string}'")
             final_combo_to_save = new_hotkey_combo_string

        self.global_hotkey_combination_var.set(final_combo_to_save)
        self.save_global_hotkey_combination_now(final_combo_to_save) # Call the dedicated save with the new string

        self.set_hotkey_button.configure(text="Set Hotkey", state="normal")
        # Clear the internal state for next capture
        self._hotkey_current_modifiers = set()
        self._hotkey_main_key = None

        # Restart main app's global hotkey listener if it was paused
        if self._main_hotkey_paused: # Check the flag
            self.app.log_message("Restarting main app's global hotkey listener.")
            self.app.app_logic.update_global_hotkey_listener() # Call through AppLogic
            self._main_hotkey_paused = False


    def stop_hotkey_listening(self):
        """Stops the temporary hotkey listener."""
        if self._hotkey_listener:
            try:
                self._hotkey_listener.stop()
                self._hotkey_listener = None
                self.app.log_message("Stopped listening for new hotkey.")
            except Exception as e:
                self.app.log_message(f"ERROR: Failed to stop temporary hotkey listener: {e}")
        if self._hotkey_listening_thread and self._hotkey_listening_thread.is_alive():
            # It's a daemon thread, so it will exit with the main app.
            # No need to join() unless we absolutely need it to finish immediately.
            pass

    def save_global_hotkey_combination_now(self, new_combination):
        """
        Saves the global hotkey combination to settings and triggers main app update.
        Called directly after a new hotkey is captured.
        """
        self.app.settings["global_hotkey_combination"] = new_combination
        self.app.save_app_settings()
        self.app.log_message(f"Global hotkey combination set to: '{new_combination}' (persisted).")

    def refresh_history(self):
        self.app.log_message("Refreshing download history from disk...")
        self.app.history_items_with_paths.clear()
        self.app.thumbnail_cache.clear()
        # This will be handled by history_manager.redraw_history_listbox()
        # self.app.currently_highlighted_item_frame = None
        self.app.history_manager.load_existing_downloads_to_history() # Call through HistoryManager
        self.app.log_message("History refreshed and thumbnail/duration generation re-initiated if needed.")

    def confirm_clear_download_history(self):
        if messagebox.askyesno("Confirm Clear History",
                               "Are you sure you want to clear the entire download history?\n"
                               "This action cannot be undone and does not delete files from disk.",
                               icon='warning', parent=self):
            self.app.history_manager.clear_download_history_data() # Call through HistoryManager

    def confirm_clear_thumbnail_cache(self):
        if messagebox.askyesno("Confirm Clear Thumbnail Cache",
                               "Are you sure you want to clear the thumbnail cache?\n"
                               "This will delete all .jpg thumbnail files from your download directory "
                               "that appear to be associated with media files.\n"
                               "This action cannot be undone.",
                               icon='warning', parent=self):
            self.app.history_manager.clear_thumbnail_cache_data() # Call through HistoryManager

    def open_about_window(self):
        """Opens or brings to front the About window."""
        if not hasattr(self, '_about_window_instance') or \
           self._about_window_instance is None or \
           not self._about_window_instance.winfo_exists():
            self._about_window_instance = AboutWindow(self, app_instance=self.app)
            self._about_window_instance.focus_force()
        else:
            self._about_window_instance.lift()
            self._about_window_instance.focus_force()