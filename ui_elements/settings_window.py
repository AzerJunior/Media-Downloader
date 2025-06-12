import customtkinter as ctk
from tkinter import filedialog, messagebox
import os
import threading
from pynput import keyboard # For global hotkey listening

from constants import (
    DEFAULT_FONT_FAMILY, FONT_FAMILIES, FONT_SIZES, DEFAULT_FONT_SIZE_NAME,
    DEFAULT_PLAYER_COMMAND,
    HISTORY_ITEM_SIZES, DEFAULT_HISTORY_ITEM_SIZE_NAME
)

from .about_window import AboutWindow
from .tooltip import Tooltip

class SettingsWindow(ctk.CTkToplevel):
    def __init__(self, master, app_instance):
        super().__init__(master)
        self.app = app_instance # Reference to the main app instance
        self.title("Settings")
        self.geometry("600x750")
        self.transient(master) # Makes the settings window appear on top of the main window
        self.grab_set() # Makes the settings window modal

        # Center the window relative to its master (main app window)
        self.update_idletasks()
        x = master.winfo_x() + (master.winfo_width() // 2) - (self.winfo_width() // 2)
        y = master.winfo_y() + (master.winfo_height() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")

        self._hotkey_listener = None
        self._hotkey_listening_thread = None
        self._hotkey_current_modifiers = set()
        self._hotkey_main_key = None
        self._main_hotkey_paused = False # Flag to track if main hotkey listener was paused

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

        # --- History/Active Item Size Setting ---
        item_size_group = ctk.CTkFrame(settings_frame)
        item_size_group.pack(fill="x", pady=5)
        ctk.CTkLabel(item_size_group, text="List Item Size:", font=self.app.ui_font).pack(side="left", padx=5, pady=5)
        self.history_item_size_var = ctk.StringVar(value=self.app.settings.get("history_item_size_name", DEFAULT_HISTORY_ITEM_SIZE_NAME))
        history_item_size_menu = ctk.CTkOptionMenu(
            item_size_group, values=list(HISTORY_ITEM_SIZES.keys()), variable=self.history_item_size_var,
            command=self.change_history_item_size, font=self.app.ui_font, dropdown_font=self.app.ui_font
        )
        history_item_size_menu.pack(side="left", padx=5, pady=5)

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

        # NEW: Show Download Complete Pop-up setting
        self.show_download_complete_popup_var = ctk.BooleanVar(value=self.app.settings.get("show_download_complete_popup", True))
        show_popup_switch = ctk.CTkSwitch(
            behavior_group, text="Show 'Download Complete' pop-up",
            variable=self.show_download_complete_popup_var, command=self.save_general_settings,
            font=self.app.ui_font
        )
        show_popup_switch.pack(side="top", anchor="w", padx=15, pady=2)


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

        # Set protocol for window close (e.g., clicking X button)
        self.protocol("WM_DELETE_WINDOW", self.on_close)


    def on_close(self):
        """Callback when the settings window is closed."""
        self.stop_hotkey_listening() # Ensure temp listener is stopped
        # Re-enable the main app's global hotkey listener if it was paused
        if self._main_hotkey_paused:
            self.app.app_logic.update_global_hotkey_listener()
            self.app.log_message("Main app's global hotkey listener re-enabled after settings window close.")

        # Save all settings fields on close
        self.save_player_command()
        self.save_subtitle_settings()
        self.save_general_settings()
        self.save_global_hotkey_settings() # This also calls toggle_global_hotkey which updates main listener
        self.destroy()

    def browse_download_directory(self):
        """Opens a file dialog to select the download directory."""
        new_dir = filedialog.askdirectory(initialdir=self.download_dir_var.get())
        if new_dir:
            self.download_dir_var.set(new_dir)
            self.app.settings["download_directory"] = new_dir
            self.app.download_dir = new_dir # Update main app's directory
            self.app.save_app_settings() # Save settings to file
            self.app.log_message(f"Download directory changed to: {new_dir}")
            # Consider prompting to re-scan history if directory changed, or automatically re-scan.
            # self.app.history_manager.load_existing_downloads_to_history() # Optional: re-scan immediately

    def change_default_download_type(self, new_type):
        """Updates the default download type setting."""
        self.app.settings["default_download_type"] = new_type
        self.app.download_type_var.set(new_type) # Update main app's variable immediately
        self.app.save_app_settings()

    def change_font_settings(self, _=None):
        """Updates font settings and triggers UI refresh."""
        font_family = self.font_family_var.get()
        font_size_name = self.font_size_name_var.get()
        
        # Only save and apply if there's an actual change
        if self.app.settings.get("font_family") != font_family or \
           self.app.settings.get("font_size_name") != font_size_name:
            self.app.settings["font_family"] = font_family
            self.app.settings["font_size_name"] = font_size_name
            self.app.save_app_settings()
            self.app.ui_manager.apply_font_settings() # Re-apply fonts to main app UI

    def change_history_item_size(self, new_size_name):
        """Updates the history/active list item size setting and redraws history."""
        if self.app.settings.get("history_item_size_name") != new_size_name:
            self.app.settings["history_item_size_name"] = new_size_name
            self.app.save_app_settings()
            self.app.log_message(f"History/Active list item size changed to: {new_size_name}")
            self.app.history_manager.redraw_history_listbox() # Redraw history to apply size

    def save_player_command(self, _=None):
        """Saves the preferred media player command."""
        player_cmd = self.player_command_var.get().strip()
        if player_cmd != self.app.settings.get("player_command", DEFAULT_PLAYER_COMMAND): # Only save if changed
            self.app.settings["player_command"] = player_cmd
            self.app.save_app_settings()
            self.app.log_message(f"Preferred player command set to: '{player_cmd if player_cmd else 'OS Default'}'")

    def save_subtitle_settings(self, _=None):
        """Saves subtitle-related settings."""
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
        """Saves general behavior settings."""
        changed = False
        if self.app.settings.get("auto_paste_on_focus") != self.auto_paste_on_focus_var.get():
            self.app.settings["auto_paste_on_focus"] = self.auto_paste_on_focus_var.get()
            changed = True
        # NEW: Save show_download_complete_popup setting
        if self.app.settings.get("show_download_complete_popup") != self.show_download_complete_popup_var.get():
            self.app.settings["show_download_complete_popup"] = self.show_download_complete_popup_var.get()
            changed = True

        if changed:
            self.app.save_app_settings()
            self.app.log_message("General behavior settings updated.")

    def toggle_global_hotkey(self):
        """Toggles the global hotkey enable state and updates the listener."""
        enabled = self.global_hotkey_enabled_var.get()
        self.app.settings["global_hotkey_enabled"] = enabled
        self.app.save_app_settings() # Persist state
        self.app.app_logic.update_global_hotkey_listener() # Tell main app to update its listener
        if enabled:
            self.app.log_message(f"Global hotkey enabled. Hotkey: {self.global_hotkey_combination_var.get()}")
        else:
            self.app.log_message("Global hotkey disabled.")

    def save_global_hotkey_settings(self):
        """Wrapper to ensure hotkey state is saved."""
        self.toggle_global_hotkey()

    def start_hotkey_listening(self):
        """Starts a temporary pynput listener to capture a new global hotkey combination."""
        # Pause the main app's hotkey listener to avoid conflicts while setting new one
        if self.app.app_logic.global_hotkey_manager and \
           self.app.app_logic.global_hotkey_manager.listener_thread and \
           self.app.app_logic.global_hotkey_manager.listener_thread.is_alive():
            self.app.app_logic.global_hotkey_manager.stop_listener()
            self.app.log_message("Temporarily paused main app's global hotkey listener.")
            self._main_hotkey_paused = True # Set flag

        self.global_hotkey_combination_var.set("Press your hotkey combination...")
        self.set_hotkey_button.configure(text="Listening...", state="disabled")
        self.hotkey_entry.configure(state="readonly") # Keep entry read-only
        self.app.log_message("Listening for new global hotkey combination...")

        self._hotkey_current_modifiers = set()
        self._hotkey_main_key = None

        if self._hotkey_listener is not None: # Stop any previous temporary listener
            self.stop_hotkey_listening()

        self._hotkey_listener = keyboard.Listener(
            on_press=self._on_key_press_for_setting,
            on_release=self._on_key_release_for_setting
        )
        self._hotkey_listening_thread = threading.Thread(target=self._hotkey_listener.start, daemon=True)
        self._hotkey_listening_thread.start()

    def _on_key_press_for_setting(self, key):
        """Callback for key press events when setting a new hotkey."""
        try:
            if key in [keyboard.Key.ctrl_l, keyboard.Key.ctrl_r]: self._hotkey_current_modifiers.add("<ctrl>")
            elif key in [keyboard.Key.alt_l, keyboard.Key.alt_r]: self._hotkey_current_modifiers.add("<alt>")
            elif key in [keyboard.Key.shift_l, keyboard.Key.shift_r]: self._hotkey_current_modifiers.add("<shift>")
            elif key in [keyboard.Key.cmd_l, keyboard.Key.cmd_r, keyboard.Key.super_l, keyboard.Key.super_r]: self._hotkey_current_modifiers.add("<cmd>") # macOS Command key
            elif key == keyboard.Key.alt_gr: self._hotkey_current_modifiers.add("<alt_gr>")
            else:
                # If a non-modifier key is pressed, it's the main key
                if self._hotkey_main_key is None or key != self._hotkey_main_key: # Only set if not already set or changed
                    self._hotkey_main_key = key

            self.app.after(0, self._update_hotkey_display) # Update UI on main thread

        except Exception as e:
            self.app.log_message(f"Error in hotkey listener (press): {e}")

    def _on_key_release_for_setting(self, key):
        """Callback for key release events when setting a new hotkey."""
        try:
            # If the main key was released, finalize the combination
            if key == self._hotkey_main_key:
                self.app.after(0, self.finish_hotkey_listening)
            # Remove modifiers on release
            elif key in [keyboard.Key.ctrl_l, keyboard.Key.ctrl_r]: self._hotkey_current_modifiers.discard("<ctrl>")
            elif key in [keyboard.Key.alt_l, keyboard.Key.alt_r]: self._hotkey_current_modifiers.discard("<alt>")
            elif key in [keyboard.Key.shift_l, keyboard.Key.shift_r]: self._hotkey_current_modifiers.discard("<shift>")
            elif key in [keyboard.Key.cmd_l, keyboard.Key.cmd_r, keyboard.Key.super_l, keyboard.Key.super_r]: self._hotkey_current_modifiers.discard("<cmd>")
            elif key == keyboard.Key.alt_gr: self._hotkey_current_modifiers.discard("<alt_gr>")

        except Exception as e:
            self.app.log_message(f"Error in hotkey listener (release): {e}")

    def _convert_pynput_key_to_display(self, key):
        """Converts a pynput Key object to a display string."""
        if hasattr(key, 'char') and key.char is not None:
            return key.char.upper() if key.char.isalpha() else key.char
        elif isinstance(key, keyboard.Key):
            if key == keyboard.Key.space: return "Space"
            if key == keyboard.Key.enter: return "Enter"
            # Generic key names (e.g., 'Key.f1' -> 'F1')
            return str(key).split('.')[1].replace("_l", "").replace("_r", "").capitalize() if '.' in str(key) else str(key)
        return str(key)

    def _format_hotkey_combination_string(self):
        """Formats the captured hotkey combination into a pynput-compatible string."""
        parts = []
        modifiers_canonical = sorted(list(self._hotkey_current_modifiers)) # Sort for consistent order

        for mod in modifiers_canonical:
            parts.append(mod)

        if self._hotkey_main_key:
            if hasattr(self._hotkey_main_key, 'char') and self._hotkey_main_key.char is not None:
                parts.append(self._hotkey_main_key.char.lower())
            elif isinstance(self._hotkey_main_key, keyboard.Key):
                key_name = str(self._hotkey_main_key).split('.')[1].lower()
                parts.append(f"<{key_name}>") # pynput syntax for special keys
            else:
                parts.append(str(self._hotkey_main_key).lower()) # Fallback for other key types

        return "+".join(parts) if parts else "None" # "None" if no keys pressed

    def _update_hotkey_display(self):
        """Updates the hotkey entry with the currently pressed keys."""
        display_parts = sorted(list(self._hotkey_current_modifiers)) # Sort for display consistency
        if self._hotkey_main_key:
            display_parts.append(self._convert_pynput_key_to_display(self._hotkey_main_key))
        display_text = "+".join(display_parts) if display_parts else "Press your hotkey combination..."
        self.global_hotkey_combination_var.set(display_text)

    def finish_hotkey_listening(self):
        """Finalizes hotkey setting after a combination is captured."""
        if self._hotkey_listener is None:
            return

        self.stop_hotkey_listening() # Stop the temporary listener

        new_hotkey_combo_string = self._format_hotkey_combination_string()

        if new_hotkey_combo_string == "None" or not new_hotkey_combo_string:
            self.app.log_message("No valid hotkey combination detected. Hotkey cleared.")
            final_combo_to_save = "None"
        else:
             self.app.log_message(f"New hotkey captured: '{new_hotkey_combo_string}'")
             final_combo_to_save = new_hotkey_combo_string

        self.global_hotkey_combination_var.set(final_combo_to_save)
        self.save_global_hotkey_combination_now(final_combo_to_save) # Persist the new combination

        self.set_hotkey_button.configure(text="Set Hotkey", state="normal") # Re-enable button
        self._hotkey_current_modifiers = set() # Reset internal state
        self._hotkey_main_key = None

        # Re-enable main app's global hotkey listener if it was paused
        if self._main_hotkey_paused:
            self.app.app_logic.update_global_hotkey_listener()
            self._main_hotkey_paused = False


    def stop_hotkey_listening(self):
        """Stops the temporary pynput hotkey listener."""
        if self._hotkey_listener:
            try:
                self._hotkey_listener.stop()
                self._hotkey_listener = None
                self.app.log_message("Stopped listening for new hotkey.")
            except Exception as e:
                self.app.log_message(f"ERROR: Failed to stop temporary hotkey listener: {e}")
        if self._hotkey_listening_thread and self._hotkey_listening_thread.is_alive():
            # Not strictly necessary to join a daemon thread, but good practice if you want to ensure it's fully gone
            # self._hotkey_listening_thread.join(timeout=0.1)
            pass

    def save_global_hotkey_combination_now(self, new_combination):
        """Saves the hotkey combination immediately to settings."""
        self.app.settings["global_hotkey_combination"] = new_combination
        self.app.save_app_settings()
        self.app.log_message(f"Global hotkey combination set to: '{new_combination}' (persisted).")

    def refresh_history(self):
        """Refreshes the download history by re-scanning the directory."""
        self.app.log_message("Refreshing download history from disk...")
        self.app.history_items_with_paths.clear() # Clear existing in-memory history
        self.app.thumbnail_cache.clear() # Clear thumbnail cache too
        self.app.history_manager.load_existing_downloads_to_history() # Reload from disk
        self.app.log_message("History refreshed and thumbnail/duration generation re-initiated if needed.")

    def confirm_clear_download_history(self):
        """Prompts for confirmation before clearing download history."""
        if messagebox.askyesno("Confirm Clear History",
                               "Are you sure you want to clear the entire download history?\n"
                               "This action cannot be undone and does not delete files from disk.",
                               icon='warning', parent=self):
            self.app.history_manager.clear_download_history_data() # Call history manager to clear

    def confirm_clear_thumbnail_cache(self):
        """Prompts for confirmation before clearing thumbnail cache files."""
        if messagebox.askyesno("Confirm Clear Thumbnail Cache",
                               "Are you sure you want to clear the thumbnail cache?\n"
                               "This will delete all .jpg thumbnail files from your download directory "
                               "that appear to be associated with media files.\n"
                               "This action cannot be undone.",
                               icon='warning', parent=self):
            self.app.history_manager.clear_thumbnail_cache_data() # Call history manager to clear cache files

    def open_about_window(self):
        """Opens or brings to front the About window."""
        # Use a single instance, create if not exists, otherwise just show
        if not hasattr(self, '_about_window_instance') or \
           self._about_window_instance is None or \
           not self._about_window_instance.winfo_exists():
            self._about_window_instance = AboutWindow(self, app_instance=self.app)
            self._about_window_instance.focus_force() # Ensure it gets focus
        else:
            self._about_window_instance.lift()
            self._about_window_instance.focus_force()