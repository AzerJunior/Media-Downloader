# global_hotkey_manager.py
from pynput import keyboard
import threading
import time

class GlobalHotkeyManager:
    """
    Manages a global hotkey listener using pynput.
    """
    def __init__(self, hotkey_combination_str, callback_func, log_func):
        self.hotkey_combination_str = hotkey_combination_str
        self.callback_func = callback_func
        self.log_func = log_func
        self.listener = None
        self.listener_thread = None
        self._last_trigger_time = 0 # For debouncing hotkey presses
        self._debounce_delay = 1.0 # Seconds to wait between triggers

        self.log_func(f"Hotkey Manager initialized for: '{hotkey_combination_str}'")

    def _on_activate(self):
        """Called when the hotkey is pressed."""
        current_time = time.time()
        if current_time - self._last_trigger_time > self._debounce_delay:
            self.log_func(f"Global hotkey '{self.hotkey_combination_str}' pressed. Triggering callback.")
            self._last_trigger_time = current_time
            # Execute callback in a separate thread to prevent blocking the listener
            threading.Thread(target=self.callback_func, daemon=True).start()
        else:
            self.log_func(f"Global hotkey '{self.hotkey_combination_str}' pressed, but debounced.")

    def update_hotkey(self, new_hotkey_combination_str):
        """Updates the hotkey combination and restarts the listener."""
        self.hotkey_combination_str = new_hotkey_combination_str
        self.log_func(f"Hotkey combination updated to: '{new_hotkey_combination_str}'")
        self.stop_listener()
        self.start_listener()

    def start_listener(self):
        """Starts the global hotkey listener in a non-blocking thread."""
        if not self.hotkey_combination_str or self.hotkey_combination_str.lower() == "none":
            self.log_func("No hotkey combination set. Listener not started.")
            return

        if self.listener_thread and self.listener_thread.is_alive():
            self.log_func("Hotkey listener already running.")
            return

        try:
            # The hotkey string uses pynput's syntax, e.g., '<ctrl>+<shift>+a'
            self.listener = keyboard.GlobalHotKeys({
                self.hotkey_combination_str: self._on_activate
            })
            self.listener_thread = threading.Thread(target=self.listener.run, daemon=True)
            self.listener_thread.start()
            self.log_func(f"Global hotkey listener started for '{self.hotkey_combination_str}'")
        except ValueError as e:
            self.log_func(f"ERROR: Invalid hotkey combination '{self.hotkey_combination_str}': {e}. Hotkey listener not started.")
        except Exception as e:
            self.log_func(f"ERROR: Failed to start hotkey listener: {e}")


    def stop_listener(self):
        """Stops the global hotkey listener."""
        if self.listener:
            try:
                self.listener.stop()
                self.listener = None
                self.log_func(f"Global hotkey listener for '{self.hotkey_combination_str}' stopped.")
            except Exception as e:
                self.log_func(f"ERROR: Failed to stop hotkey listener: {e}")
        if self.listener_thread and self.listener_thread.is_alive():
            # A small delay to allow the thread to properly shut down
            # Or you might need more robust thread management depending on pynput's internals
            # self.listener_thread.join(timeout=0.1)
            pass # Daemon threads will exit with the main app

# Example usage (for testing purposes, remove in main app)
# if __name__ == '__main__':
#     def my_callback():
#         print("Hotkey triggered! Performing action...")

#     def print_log(msg):
#         print(f"[HotkeyManager Log] {msg}")

#     # hotkey_str = "<ctrl>+<alt>+a" # Example hotkey
#     hotkey_str = "<cmd>+<shift>+d" # For macOS users, cmd is the 'super' key

#     manager = GlobalHotkeyManager(hotkey_str, my_callback, print_log)
#     manager.start_listener()

#     print(f"Press {hotkey_str} to trigger the callback. Press Ctrl+C to exit.")
#     try:
#         # Keep the main thread alive indefinitely to allow the daemon thread to run
#         import time
#         while True:
#             time.sleep(1)
#     except KeyboardInterrupt:
#         manager.stop_listener()
#         print("Exiting.")