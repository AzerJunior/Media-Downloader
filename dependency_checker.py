import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import sys
import os
import importlib.util
import threading
import webbrowser
import time

# Import settings manager and constants
from settings_manager import load_settings, save_settings
# CORRECTED: Import FONT_ROBOTO_REGULAR directly from constants
from constants import APP_VERSION, SETTINGS_FILE, FONT_ROBOTO_REGULAR


class DependencyCheckerApp(tk.Tk):
    def __init__(self, dependencies, initial_settings):
        super().__init__()
        self.title("Dependency Checker")
        self.geometry("650x550")
        self.resizable(False, False)

        self.dependencies = dependencies
        self.all_critical_installed = True
        self.can_proceed = True
        self.current_settings = initial_settings

        self._center_window()
        self._create_widgets()
        self._check_dependencies()  # Initial check

    def _center_window(self):
        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def _create_widgets(self):
        main_frame = ttk.Frame(self, padding="15")
        main_frame.pack(fill="both", expand=True)

        title_label = ttk.Label(main_frame, text="Application Dependency Check", font=("Helvetica", 16, "bold"))
        title_label.pack(pady=10)

        info_label = ttk.Label(main_frame, text="Checking for required Python libraries and external tools. Use 'Install' buttons for Python packages, or follow manual instructions for others.", wraplength=600)
        info_label.pack(pady=5)

        self.status_frame = ttk.Frame(main_frame, borderwidth=2, relief="groove", padding=10)
        self.status_frame.pack(fill="both", expand=True, pady=10)

        self.canvas = tk.Canvas(self.status_frame)
        self.scrollbar = ttk.Scrollbar(self.status_frame, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(
                scrollregion=self.canvas.bbox("all")
            )
        )

        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")


        self.button_frame = ttk.Frame(main_frame)
        self.button_frame.pack(pady=10)

        self.continue_button = ttk.Button(self.button_frame, text="Continue Anyway", command=self.on_continue)
        self.continue_button.pack(side="left", padx=5)

        self.exit_button = ttk.Button(self.button_frame, text="Exit", command=self.on_exit)
        self.exit_button.pack(side="left", padx=5)

    def _check_dependencies(self):
        # Clear previous status
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()

        self.all_critical_installed = True
        self.can_proceed = True
        any_missing = False

        self.dep_buttons = [] # Store references to buttons to disable during installation

        for i, dep in enumerate(self.dependencies):
            name = dep["name"]
            check_func = dep["check_func"]
            instructions = dep["instructions"]
            critical = dep.get("critical", False)
            install_action = dep.get("install_action")
            install_button_text = dep.get("install_button_text", "Install")

            status_text = ""
            status_color = "black"

            # Create a row frame for each dependency
            row_frame = ttk.Frame(self.scrollable_frame)
            row_frame.grid(row=i*2, column=0, columnspan=3, sticky="ew", pady=(2,0))
            inst_row_frame = ttk.Frame(self.scrollable_frame)
            inst_row_frame.grid(row=i*2+1, column=0, columnspan=3, sticky="ew", pady=(0, 5))

            status_label = ttk.Label(row_frame, text=f"{name}: ", font=("Helvetica", 10, "bold"))
            status_label.pack(side="left", padx=5, pady=2)

            result = check_func()
            if result:
                status_text = "INSTALLED"
                status_color = "green"
            else:
                any_missing = True
                status_text = "MISSING"
                status_color = "red"
                if critical:
                    self.all_critical_installed = False
                    self.can_proceed = False

            status_status_label = ttk.Label(row_frame, text=status_text, foreground=status_color, font=("Helvetica", 10, "bold"))
            status_status_label.pack(side="left", padx=5, pady=2)

            if not result and install_action:
                install_btn = ttk.Button(row_frame, text=install_button_text,
                                        command=lambda a=install_action, b=status_status_label, c=status_label: self.run_install_action(a, b, c))
                install_btn.pack(side="right", padx=5, pady=2)
                self.dep_buttons.append(install_btn)

            inst_label = ttk.Label(inst_row_frame, text=f"  {instructions}", wraplength=550, font=("Helvetica", 9))
            inst_label.pack(side="left", padx=5, pady=0)


        # Update settings based on check results
        self._update_settings_after_check()

        # Final UI update based on all checks
        if any_missing:
            if not self.all_critical_installed:
                messagebox.showerror("Critical Dependencies Missing",
                                     "One or more critical dependencies are missing. "
                                     "Please install them to use the application. The 'Continue Anyway' button is disabled.", parent=self)
                self.continue_button.config(state="disabled")
            else:
                messagebox.showwarning("Dependencies Missing",
                                      "Some non-critical dependencies are missing. "
                                      "The application may have limited functionality. "
                                      "You can continue, but features might be disabled or have errors.", parent=self)
                self.continue_button.config(state="normal")
        else:
            messagebox.showinfo("All Dependencies Met", "All required dependencies are installed. You can proceed.", parent=self)
            self.continue_button.config(state="normal")
            self.continue_button.config(text="Launch Application")

    def _update_settings_after_check(self):
        """Updates the settings file with the result of the dependency check."""
        if self.all_critical_installed:
            self.current_settings["last_deps_check_timestamp"] = time.time()
            self.current_settings["app_version_at_last_deps_check"] = APP_VERSION
            print(f"Dependency check successful. Saving timestamp: {self.current_settings['last_deps_check_timestamp']}")
        else:
            self.current_settings["last_deps_check_timestamp"] = 0.0  # Reset timestamp on failure
            self.current_settings["app_version_at_last_deps_check"] = "0.0.0"  # Reset version
            print("Critical dependencies missing. Resetting dependency check timestamp.")

        save_settings(self.current_settings)  # Save the updated settings

    def run_install_action(self, action_func, status_label_widget, name_label_widget):
        """Runs an installation action in a new thread."""
        for btn in self.dep_buttons:
            btn.config(state="disabled")
        self.continue_button.config(state="disabled")
        self.exit_button.config(state="disabled")  # Disable exit during install

        original_name_text = name_label_widget.cget("text")
        status_label_widget.config(text="INSTALLING...", foreground="orange")
        name_label_widget.config(text=f"{original_name_text} (Installing...)")

        def install_thread_target():
            try:
                success = action_func()
                self.after(0, lambda: self._update_status_after_install(success, status_label_widget, name_label_widget, original_name_text))
            except Exception as e:
                print(f"Error during install thread: {e}")
                self.after(0, lambda: self._update_status_after_install(False, status_label_widget, name_label_widget, original_name_text, error_msg=str(e)))

        threading.Thread(target=install_thread_target, daemon=True).start()

    def _update_status_after_install(self, success, status_label_widget, name_label_widget, original_name_text, error_msg=None):
        """Updates the UI after an installation attempt."""
        name_label_widget.config(text=original_name_text)

        if success:
            status_label_widget.config(text="INSTALLED", foreground="green")
            messagebox.showinfo("Installation Complete", "Dependency installed successfully! Re-checking all dependencies...", parent=self)
        else:
            status_label_widget.config(text="FAILED", foreground="red")
            error_message = f"Installation failed. Please check console for details.\n{error_msg}" if error_msg else "Installation failed. Please check console for details."
            messagebox.showerror("Installation Failed", error_message, parent=self)

        self._check_dependencies()  # This will re-enable all dep buttons and update final button states
        self.exit_button.config(state="normal")  # Re-enable exit button

    def on_continue(self):
        self.destroy()

    def on_exit(self):
        self.can_proceed = False
        self.destroy()


# --- Helper Functions for Dependency Checks & Installation ---

def check_pip_module(module_name, pip_name=None):
    """Checks if a Python module can be imported."""
    if pip_name is None:
        pip_name = module_name
    try:
        importlib.util.find_spec(module_name)
        return True
    except ImportError:
        return False

def install_pip_module(pip_name):
    """Attempts to install a Python package using pip."""
    print(f"Attempting to install Python package: {pip_name}")
    process = subprocess.run([sys.executable, "-m", "pip", "install", pip_name], capture_output=True, text=True)
    print(f"Pip stdout for {pip_name}:\n{process.stdout}")
    if process.stderr:
        print(f"Pip stderr for {pip_name}:\n{process.stderr}")
    return process.returncode == 0

def check_executable(cmd):
    """Checks if an executable can be found in the system's PATH."""
    try:
        if sys.platform.startswith('win'):
            subprocess.run(['where', cmd], check=True, capture_output=True, text=True, shell=True)
        else:
            subprocess.run(['which', cmd], check=True, capture_output=True, text=True, shell=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
    except Exception as e:
        print(f"Error checking executable '{cmd}': {e}")
        return False

def open_url_in_browser(url):
    """Opens a URL in the default web browser."""
    print(f"Opening URL: {url}")
    try:
        webbrowser.open_new(url)
        return True
    except Exception as e:
        print(f"Failed to open browser: {e}")
        messagebox.showerror("Browser Error", f"Could not open browser. Please visit {url} manually.", parent=None)
        return False

def check_font_file(file_path):
    """Checks if a font file exists at the given path."""
    return os.path.exists(file_path)

# --- Updated run_dependency_check function ---
def run_dependency_check(project_root):
    """
    Sets up and runs the dependency checker GUI.
    Returns True if dependencies are met and user chooses to proceed, False otherwise.
    Takes `project_root` as an argument to correctly locate relative files.
    """
    # Use constants.FONT_ROBOTO_REGULAR which is already built using PROJECT_ROOT
    font_file_path = FONT_ROBOTO_REGULAR 

    dependencies = [
        {
            "name": "Python 3.8+ (for yt-dlp)",
            "check_func": lambda: sys.version_info >= (3, 8),
            "instructions": "Please install Python 3.8 or newer. Ensure it's in your system PATH.",
            "critical": True,
            "install_action": None
        },
        {
            "name": "yt-dlp (Python Package)",
            "check_func": lambda: check_pip_module("yt_dlp"),
            "instructions": "Install using pip for core functionality.",
            "critical": True,
            "install_action": lambda: install_pip_module("yt-dlp"),
            "install_button_text": "pip install"
        },
        {
            "name": "ffmpeg",
            "check_func": lambda: check_executable("ffmpeg"),
            "instructions": "Download from official site and add to your system PATH.",
            "critical": True,
            "install_action": lambda: open_url_in_browser("https://ffmpeg.org/download.html"),
            "install_button_text": "Download Page"
        },
        {
            "name": "ffprobe",
            "check_func": lambda: check_executable("ffprobe"),
            "instructions": "Comes with ffmpeg. Ensure ffmpeg is installed and in PATH.",
            "critical": True,
            "install_action": lambda: open_url_in_browser("https://ffmpeg.org/download.html"),
            "install_button_text": "Download Page"
        },
        {
            "name": "CustomTkinter",
            "check_func": lambda: check_pip_module("customtkinter"),
            "instructions": "Install using pip for the modern UI.",
            "critical": True,
            "install_action": lambda: install_pip_module("customtkinter"),
            "install_button_text": "pip install"
        },
        {
            "name": "Pillow (PIL)",
            "check_func": lambda: check_pip_module("PIL", "Pillow"),
            "instructions": "Install using pip for image processing (thumbnails).",
            "critical": True,
            "install_action": lambda: install_pip_module("Pillow"),
            "install_button_text": "pip install"
        },
        {
            "name": "pynput",
            "check_func": lambda: check_pip_module("pynput"),
            "instructions": "Install using pip for global hotkeys (optional).",
            "critical": False,
            "install_action": lambda: install_pip_module("pynput"),
            "install_button_text": "pip install"
        },
        {
            "name": "pyperclip",
            "check_func": lambda: check_pip_module("pyperclip"),
            "instructions": "Install using pip for clipboard operations (optional).",
            "critical": False,
            "install_action": lambda: install_pip_module("pyperclip"),
            "install_button_text": "pip install"
        },
        {
            "name": "Roboto-Regular.ttf (font)",
            "check_func": lambda: check_font_file(font_file_path),
            "instructions": f"Missing font file at: {font_file_path}. Please restore 'assets/fonts/Roboto-Regular.ttf' in your application directory.",
            "critical": False,
            "install_action": None
        }
    ]

    initial_settings = load_settings() # Load settings to pass to DependencyCheckerApp
    app = DependencyCheckerApp(dependencies, initial_settings) # Pass settings
    app.mainloop()

    # The settings object held by app.current_settings has been updated and saved by _update_settings_after_check
    return app.can_proceed