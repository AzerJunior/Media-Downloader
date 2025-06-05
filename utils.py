# utils.py
import customtkinter as ctk

def get_ctk_color_from_theme_path(path_string):
    """
    Helper function to get a color from the CustomTkinter theme dictionary.
    This function handles the nested dictionary structure and (light_color, dark_color) tuples.
    """
    parts = path_string.split(".")
    current_dict = ctk.ThemeManager.theme
    
    for i, part in enumerate(parts):
        if part in current_dict:
            current_dict = current_dict[part]
        else:
            # print(f"Warning: Theme path part '{part}' not found in {path_string}") # Less noisy
            return "gray" # Default fallback color

    final_color_value = current_dict

    # If it's a tuple (light_color, dark_color), return based on current appearance mode
    if ctk.get_appearance_mode() == "Dark":
        mode_index = 1
    else:
        mode_index = 0

    if isinstance(final_color_value, (list, tuple)) and len(final_color_value) == 2:
        return final_color_value[mode_index]
    else:
        # Otherwise, return the value as is (it should already be a color string)
        return final_color_value