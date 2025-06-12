import customtkinter as ctk
from tkinter import StringVar as tkStringVar # Keep tk import for StringVar

class FormatSelectionWindow(ctk.CTkToplevel):
    def __init__(self, master, app_instance, formats_data):
        super().__init__(master)
        self.app = app_instance # app_instance is the VideoDownloaderApp
        self.formats_data = formats_data
        self.initial_format_code = self.app.settings.get("selected_format_code", "best")
        self.selected_format_code_var = tkStringVar(value=self.initial_format_code)

        self.title("Select Media Format")
        self.geometry("850x550")
        self.transient(master)
        self.grab_set() # Make the window modal

        # Center the window relative to its master (main app window)
        self.update_idletasks()
        x = master.winfo_x() + (master.winfo_width() // 2) - (self.winfo_width() // 2)
        y = master.winfo_y() + (master.winfo_height() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")


        self.headers_config = [
            {"text": "ID", "key": "id", "width": 60},
            {"text": "Ext", "key": "ext", "width": 40},
            {"text": "Resolution", "key": "resolution", "width": 100},
            {"text": "FPS", "key": "fps", "width": 40},
            {"text": "VCodec", "key": "vcodec", "width": 70},
            {"text": "ACodec", "key": "acodec", "width": 70},
            {"text": "Bitrate", "key": "tbr", "width": 70},
            {"text": "Filesize", "key": "filesize", "width": 80},
            {"text": "Note", "key": "note", "width": 150, "stretch": True},
        ]

        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.pack(pady=(10,0), fill="x", padx=10)

        # For Radiobutton column header (empty label but occupies space)
        ctk.CTkLabel(header_frame, text="", font=self.app.ui_font_bold, width=30).pack(side="left", padx=(0,5))

        # Create column headers
        for config in self.headers_config:
            lbl_width = config["width"]
            header_lbl = ctk.CTkLabel(header_frame, text=config["text"], font=self.app.ui_font_bold,
                                      width=lbl_width, anchor="w")
            header_lbl.pack(side="left", padx=3, fill="x" if config.get("stretch") else None, expand=config.get("stretch", False))

        scrollable_frame = ctk.CTkScrollableFrame(self)
        scrollable_frame.pack(expand=True, fill="both", padx=10, pady=5)

        # "Best" option radio button
        best_option_frame = ctk.CTkFrame(scrollable_frame, fg_color="transparent")
        best_option_frame.pack(fill="x", pady=2)
        ctk.CTkRadioButton(
            best_option_frame, text=" Best (yt-dlp default)", variable=self.selected_format_code_var,
            value="best", font=self.app.ui_font
        ).pack(side="left", anchor="w", padx=5)

        if not formats_data:
            ctk.CTkLabel(scrollable_frame, text="No specific formats found or error fetching formats.", font=self.app.ui_font).pack(pady=20)
        else:
            for i, fmt_entry in enumerate(formats_data):
                row_fg_color = "gray35" if i % 2 == 0 else "gray30"
                if ctk.get_appearance_mode() == "Light":
                    row_fg_color = "gray85" if i % 2 == 0 else "gray80" # Lighter shades for light mode

                row_frame = ctk.CTkFrame(scrollable_frame, fg_color=row_fg_color)
                row_frame.pack(fill="x", pady=1, ipady=2)

                rb_value = fmt_entry.get('id', f'unknown_{i}') # Use format_id as value
                rb = ctk.CTkRadioButton(row_frame, text="", variable=self.selected_format_code_var,
                                        value=rb_value, width=20)
                rb.pack(side="left", padx=(5,5))

                for config in self.headers_config:
                    detail_text = str(fmt_entry.get(config["key"], "-"))
                    lbl_width = config["width"]

                    # Truncate text if it's too long for the column width
                    # This is a heuristic, adjust as needed
                    if not config.get("stretch") and lbl_width > 0:
                         # Calculate max characters based on rough char width (e.g., 6 pixels per char for a 12pt font)
                         # This is very approximate and depends on font and actual characters
                         max_chars = int(lbl_width / (self.app.ui_font.cget("size") * 0.6)) if self.app.ui_font.cget("size") > 0 else 10
                         if len(detail_text) > max_chars + 3: # +3 for "..."
                             detail_text = detail_text[:max_chars] + "..."

                    lbl = ctk.CTkLabel(row_frame, text=detail_text, font=self.app.ui_font,
                                       anchor="w", width=lbl_width)
                    lbl.pack(side="left", padx=3, fill="x" if config.get("stretch") else None, expand=config.get("stretch", False))

        button_frame = ctk.CTkFrame(self)
        button_frame.pack(fill="x", padx=10, pady=(5,10))

        select_button = ctk.CTkButton(button_frame, text="Select Format", command=self.on_select, font=self.app.ui_font)
        select_button.pack(side="left", padx=5)

        reset_button = ctk.CTkButton(button_frame, text="Reset to Best", command=self.on_reset_to_best, font=self.app.ui_font)
        reset_button.pack(side="left", padx=5)

        cancel_button = ctk.CTkButton(button_frame, text="Cancel", command=self.destroy, font=self.app.ui_font)
        cancel_button.pack(side="right", padx=5)

    def on_select(self):
        selected_code = self.selected_format_code_var.get()
        self.app.settings["selected_format_code"] = selected_code
        self.app.save_app_settings()
        self.app.ui_manager.update_selected_format_display() # Call through UIManager
        self.app.log_message(f"Selected format code: {selected_code}")
        self.destroy()

    def on_reset_to_best(self):
        self.selected_format_code_var.set("best")
        self.app.log_message("Format selection reset to 'best' in window.")