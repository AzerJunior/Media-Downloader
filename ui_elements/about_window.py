# ui_elements/about_window.py
import customtkinter as ctk

class AboutWindow(ctk.CTkToplevel):
    def __init__(self, master, app_instance):
        super().__init__(master)
        self.app = app_instance # Reference to the main app for font settings etc.

        self.title("About Universal Media Downloader")
        self.geometry("400x300")
        self.transient(master) # Make it appear on top of the main window
        self.grab_set() # Make it modal

        # Center the window relative to its master (main app window)
        self.update_idletasks()
        x = master.winfo_x() + (master.winfo_width() // 2) - (self.winfo_width() // 2)
        y = master.winfo_y() + (master.winfo_height() // 2) - (self.winfo_height() // 2)
        self.geometry(f"+{x}+{y}")

        main_frame = ctk.CTkFrame(self)
        main_frame.pack(expand=True, fill="both", padx=20, pady=20)

        # App Name
        ctk.CTkLabel(
            main_frame,
            text="Universal Media Downloader",
            font=self.app.ui_font_bold,
            pady=10
        ).pack()

        # Version
        ctk.CTkLabel(
            main_frame,
            text="Version: v0.4.0",
            font=self.app.ui_font,
            pady=5
        ).pack()

        # Description
        ctk.CTkLabel(
            main_frame,
            text="A versatile tool for downloading videos and audio from various online platforms.",
            font=self.app.ui_font,
            wraplength=300,
            justify="center",
            pady=10
        ).pack()

        # Author/Credits
        ctk.CTkLabel(
            main_frame,
            text="Developed by: MrAether/AzerJunior With T3 Chat",
            font=self.app.ui_font,
            text_color="gray",
            pady=5
        ).pack()

        # Close Button
        close_button = ctk.CTkButton(
            self,
            text="Close",
            command=self.destroy,
            font=self.app.ui_font
        )
        close_button.pack(pady=(0, 20))

        # Handle window close protocol
        self.protocol("WM_DELETE_WINDOW", self.destroy)