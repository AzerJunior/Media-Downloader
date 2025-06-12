# ui_elements/about_window.py
import customtkinter as ctk
from constants import APP_VERSION  # Import the version constant


class AboutWindow(ctk.CTkToplevel):
    def __init__(self, master, app_instance):
        super().__init__(master)
        self.app = app_instance

        self.title("About Universal Media Downloader")
        self.geometry("400x300")
        self.transient(master)
        self.grab_set()

        self.update_idletasks()
        x = master.winfo_x() + (master.winfo_width() // 2) - (
            self.winfo_width() // 2
        )
        y = master.winfo_y() + (master.winfo_height() // 2) - (
            self.winfo_height() // 2
        )
        self.geometry(f"+{x}+{y}")

        main_frame = ctk.CTkFrame(self)
        main_frame.pack(expand=True, fill="both", padx=20, pady=20)

        ctk.CTkLabel(
            main_frame,
            text="Universal Media Downloader",
            font=self.app.ui_font_bold,
            pady=10,
        ).pack()

        # Use the imported APP_VERSION constant
        ctk.CTkLabel(
            main_frame, text=f"Version: v{APP_VERSION}", font=self.app.ui_font, pady=5
        ).pack()

        ctk.CTkLabel(
            main_frame,
            text="A versatile tool for downloading videos and audio from various online platforms.",
            font=self.app.ui_font,
            wraplength=300,
            justify="center",
            pady=10,
        ).pack()

        ctk.CTkLabel(
            main_frame,
            text="Developed by: MrAether/AzerJunior With T3 Chat",
            font=self.app.ui_font,
            text_color="gray",
            pady=5,
        ).pack()

        close_button = ctk.CTkButton(
            self, text="Close", command=self.destroy, font=self.app.ui_font
        )
        close_button.pack(pady=(0, 20))

        self.protocol("WM_DELETE_WINDOW", self.destroy)