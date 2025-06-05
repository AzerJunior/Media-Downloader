# Create a new file, e.g., ui_elements/tooltip.py (or add to utils.py if preferred)

import customtkinter as ctk

class Tooltip:
    def __init__(self, widget, text, delay=500, wraplength=200):
        self.widget = widget
        self.text = text
        self.delay = delay # Milliseconds to wait before showing tooltip
        self.wraplength = wraplength
        self.tooltip_window = None
        self.show_id = None
        self.hide_id = None

        self.widget.bind("<Enter>", self.schedule_show_tooltip)
        self.widget.bind("<Leave>", self.schedule_hide_tooltip)
        self.widget.bind("<ButtonPress>", self.hide_tooltip_immediately) # Hide on click

    def schedule_show_tooltip(self, event=None):
        # Cancel any pending hide operations
        if self.hide_id:
            self.widget.after_cancel(self.hide_id)
            self.hide_id = None
        # Schedule to show
        if not self.tooltip_window: # Only schedule if not already visible or pending show
            self.show_id = self.widget.after(self.delay, self.show_tooltip)

    def show_tooltip(self, event=None):
        if self.tooltip_window or not self.widget.winfo_exists(): # If already shown or widget destroyed
            return
        
        # Get widget position relative to screen
        x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5 # Below the widget

        self.tooltip_window = ctk.CTkToplevel(self.widget)
        self.tooltip_window.wm_overrideredirect(True) # Remove window decorations
        self.tooltip_window.wm_geometry(f"+{x}+{y}")
        self.tooltip_window.attributes("-topmost", True) # Keep on top

        # Use a frame for padding and background
        bg_color = get_ctk_color_from_theme_path("CTkToolTip.fg_color") or "gray20"
        text_color = get_ctk_color_from_theme_path("CTkToolTip.text_color") or "white"
        
        frame = ctk.CTkFrame(self.tooltip_window, corner_radius=3, fg_color=bg_color)
        frame.pack(ipadx=1, ipady=1) # Small internal padding for the frame itself

        label = ctk.CTkLabel(frame, text=self.text, wraplength=self.wraplength, 
                             font=(self.widget.cget("font").cget("family"), 
                                   int(self.widget.cget("font").cget("size") * 0.9)), # Slightly smaller
                             text_color=text_color,
                             padx=5, pady=3) # Padding inside the label
        label.pack()
        
        # Adjust position if tooltip goes off-screen (basic adjustment)
        self.tooltip_window.update_idletasks() # Ensure window size is calculated
        screen_width = self.widget.winfo_screenwidth()
        screen_height = self.widget.winfo_screenheight()
        tip_width = self.tooltip_window.winfo_width()
        tip_height = self.tooltip_window.winfo_height()

        if x + tip_width > screen_width:
            x = screen_width - tip_width - 5
        if y + tip_height > screen_height:
            y = self.widget.winfo_rooty() - tip_height - 5 # Place above widget
        
        self.tooltip_window.wm_geometry(f"+{x}+{y}")


    def schedule_hide_tooltip(self, event=None):
        # Cancel any pending show operations
        if self.show_id:
            self.widget.after_cancel(self.show_id)
            self.show_id = None
        # Schedule to hide
        if self.tooltip_window:
            self.hide_id = self.widget.after(100, self.hide_tooltip_immediately) # Short delay before hiding

    def hide_tooltip_immediately(self, event=None):
        if self.show_id: # If it was scheduled to show, cancel it
            self.widget.after_cancel(self.show_id)
            self.show_id = None
        if self.hide_id: # If it was scheduled to hide, cancel it (already hiding)
            self.widget.after_cancel(self.hide_id)
            self.hide_id = None

        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None

# Need to add get_ctk_color_from_theme_path to utils.py if it's not already there
# or define it locally for the tooltip if utils.py is not accessible directly.
# Assuming utils.py is in the parent directory:
# from ..utils import get_ctk_color_from_theme_path
# For now, let's assume it's available or we'll define a fallback.

def get_ctk_color_from_theme_path(path_string): # Local fallback for tooltip.py
    try:
        import customtkinter as ctk_theme_utils # Alias to avoid conflict
        parts = path_string.split(".")
        current_dict = ctk_theme_utils.ThemeManager.theme
        for part in parts:
            if part in current_dict: current_dict = current_dict[part]
            else: return None
        if ctk_theme_utils.get_appearance_mode() == "Dark": mode_index = 1
        else: mode_index = 0
        if isinstance(current_dict, (list, tuple)) and len(current_dict) == 2: return current_dict[mode_index]
        return current_dict
    except Exception:
        return None