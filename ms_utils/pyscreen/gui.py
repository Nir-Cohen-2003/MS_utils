import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import json
import threading
import traceback
from pathlib import Path
import os
from main import main as run_pyscreen_analysis
from pyscreen_config import pyscreen_config, blank_config, search_config, isotopic_pattern_config, suspect_list_config

# -- Configuration for default values and advanced fields --
# These would ideally be derived from the actual config classes or a schema
# For simplicity, we define them here.
# (parameter_name, label_text, default_value, type, is_advanced)
# type can be 'str', 'float', 'int', 'bool', 'path', 'dir', 'choice'
# For 'choice', default_value should be a tuple: (options_list, default_option)

CONFIG_STRUCTURE = {
    "blank": {
        # Based on blank_config from ms_utils.interfaces.msdial (as inferred from pyscreen_raw.txt)
        # Defaults from the dataclass:
        # ms1_mass_tolerance: float = 3e-6
        # dRT_min: float = 0.1
        # ratio: float | int = 5
        # use_ms2: bool = False
        # dRT_min_with_ms2: float = 0.3
        # ms2_fit: float = 0.85
        "ms1_mass_tolerance": ("Blank MS1 Mass Tolerance (abs)", 3e-6, 'float', False),
        "dRT_min": ("Blank RT Tolerance (min)", 0.1, 'float', False),
        "ratio": ("Blank Intensity Fold Change Ratio", 5.0, 'float', False),
        "use_ms2": ("Blank Use MS2 Subtraction", False, 'bool', False),
        "dRT_min_with_ms2": ("Blank RT Tolerance with MS2 (min)", 0.3, 'float', False),
        "ms2_fit": ("Blank MS2 Fit Threshold", 0.85, 'float', False),
    },
    "search": {
        # Based on search_config from ms_utils.pyscreen.spectral_search (as inferred from pyscreen_raw.txt)
        # Defaults from the dataclass:
        # polarity: str (Required)
        # ms1_mass_tolerance: float = 5e-6
        # ms2_mass_tolerance: float = 10e-6
        # DotProd_threshold: dict (default_factory)
        # search_engine: str = 'entropy'
        # noise_threshold: float = 0.005
        "polarity": ("Polarity", (["positive", "negative"], "positive"), 'choice', False),
        "ms1_mass_tolerance": ("Search MS1 Mass Tolerance (abs)", 5e-6, 'float', False),
        "ms2_mass_tolerance": ("Search MS2 Mass Tolerance (abs)", 10e-6, 'float', False),
        "DotProd_threshold_haz0": ("DotProd Threshold Haz0", 650.0, 'float', False), # Default from factory: 0:650
        "DotProd_threshold_haz1": ("DotProd Threshold Haz1", 700.0, 'float', False), # Default from factory: 1:700
        "DotProd_threshold_haz2": ("DotProd Threshold Haz2", 800.0, 'float', False), # Default from factory: 2:800
        "DotProd_threshold_haz3": ("DotProd Threshold Haz3", 900.0, 'float', False), # Default from factory: 3:900
        "search_engine": ("Search Engine", (["nist", "custom", "entropy"], "entropy"), 'choice', False),
        "noise_threshold": ("Search MS2 Noise Threshold (relative)", 0.005, 'float', False),
        # GUI-specific parameters, not directly in search_config dataclass but handled by GUI/workflow
        "NIST_db_path": ("NIST DB Path (.msp)", "", 'path', False),
        "custom_library_path": ("Custom Library Path (.msp)", "", 'path', False),
        "min_peaks_for_search": ("Min MS2 Peaks for Search", 3, 'int', False),
    },
    "isotopic_pattern": {
        # Based on isotopic_pattern_config from ms_utils.formula_annotation.isotopic_pattern
        # (as inferred from pyscreen_raw.txt and pyscreen_config.py example)
        # Defaults from the dataclass:
        # mass_tolerance: float (Required)
        # ms1_resolution: float (Required)
        # minimum_intensity: float = 5e5
        # max_intensity_ratio: float = 1.7
        "mass_tolerance": ("Isotope Mass Tolerance (abs)", 3e-6, 'float', False), # Default from pyscreen_config.py example
        "ms1_resolution": ("MS1 Resolution for Isotopes", 70000.0, 'float', False), # Default from pyscreen_config.py example (0.7e5)
        "minimum_intensity": ("Min Isotope Absolute Intensity", 500000.0, 'float', False), # Default from dataclass (5e5)
        "max_intensity_ratio": ("Max Isotope Intensity Ratio", 1.7, 'float', False),
        # Parameters previously in GUI but not in this specific dataclass version:
        # "min_relative_intensity": ("Min Relative Isotope Intensity (%)", 1.0, 'float', False),
        # "charge_state": ("Assumed Charge State", 1, 'int', False),
    },
    "suspect_list": {
        # Based on suspect_list_config from ms_utils.pyscreen.epa
        # Defaults from the dataclass:
        # exclusion_list: str = None
        "exclusion_list": ("Exclusion List Name", (["None", "boring_compounds"], "None"), 'choice', False),
        # GUI-specific parameters, not directly in suspect_list_config dataclass but handled by GUI/workflow
        "epa_db_path": ("EPA CompTox DB Path (.csv/.xlsx)", "", 'path', False),
        "filter_by_presence_in_epa": ("Filter by EPA Presence", True, 'bool', False),
    }
}

# -- Main Application Class --
class PyScreenApp(ctk.CTk):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.title("PyScreen Suite")
        self.geometry("900x700")
        ctk.set_appearance_mode("System")  # Modes: "System" (default), "Dark", "Light"
        ctk.set_default_color_theme("blue")  # Themes: "blue" (default), "green", "dark-blue"

        self.current_method_path = None
        self.sample_files = []
        self.blank_file = None
        self.config_vars = {} # To store CTk variables for config entries
        self.advanced_frames = {} # To store frames for advanced settings

        # Main container
        self.main_container = ctk.CTkFrame(self)
        self.main_container.pack(fill="both", expand=True, padx=10, pady=10)

        # Menu Bar
        menubar = tk.Menu(self)
        filemenu = tk.Menu(menubar, tearoff=0)
        filemenu.add_command(label="Load Method...", command=self.load_method_dialog)
        filemenu.add_command(label="Save Method As...", command=self.save_method_dialog)
        filemenu.add_separator()
        filemenu.add_command(label="Exit", command=self.quit)
        menubar.add_cascade(label="File", menu=filemenu)
        self.config(menu=menubar)

        # Tab View for different sections
        self.tab_view = ctk.CTkTabview(self.main_container)
        self.tab_view.pack(fill="both", expand=True, padx=5, pady=5)

        self.tab_view.add("File Selection")
        self.tab_view.add("Blank Config")
        self.tab_view.add("Search Config")
        self.tab_view.add("Isotopic Pattern Config")
        self.tab_view.add("Suspect List Config")

        self._create_file_selection_tab(self.tab_view.tab("File Selection"))
        self._create_config_tabs()

        # Progress Bar and Status
        self.status_frame = ctk.CTkFrame(self.main_container)
        self.status_frame.pack(fill="x", padx=5, pady=(0,5))

        self.progress_bar = ctk.CTkProgressBar(self.status_frame, orientation="horizontal", mode="determinate")
        self.progress_bar.set(0)
        self.progress_bar.pack(side="left", fill="x", expand=True, padx=5, pady=5)
        
        self.status_label = ctk.CTkLabel(self.status_frame, text="Ready", width=100)
        self.status_label.pack(side="left", padx=5, pady=5)

        # Run Button
        self.run_button = ctk.CTkButton(self.main_container, text="Run Analysis", command=self.run_analysis)
        self.run_button.pack(pady=10, padx=5, side="bottom", fill="x")

        # Error display area (initially hidden)
        self.error_details_visible = False
        self.error_frame = ctk.CTkFrame(self.main_container)
        # self.error_frame.pack(fill="x", padx=5, pady=5) # Packed when error occurs
        self.error_label = ctk.CTkLabel(self.error_frame, text="An error occurred. Click to expand details.", text_color="orange")
        self.error_label.pack(fill="x")
        self.error_label.bind("<Button-1>", self.toggle_error_details)
        self.error_text_area = ctk.CTkTextbox(self.error_frame, height=100, wrap="word", state="disabled")
        # self.error_text_area will be packed by toggle_error_details

    def _create_input_field(self, parent, param_key, label_text, default_value, param_type, config_category):
        frame = ctk.CTkFrame(parent)
        frame.pack(fill="x", pady=2)
        
        ctk.CTkLabel(frame, text=label_text, width=250, anchor="w").pack(side="left", padx=5)

        if config_category not in self.config_vars:
            self.config_vars[config_category] = {}

        var = None
        widget = None

        if param_type == 'bool':
            var = tk.BooleanVar(value=default_value)
            widget = ctk.CTkCheckBox(frame, text="", variable=var)
        elif param_type == 'path' or param_type == 'dir':
            var = tk.StringVar(value=str(default_value))
            entry = ctk.CTkEntry(frame, textvariable=var, width=300)
            entry.pack(side="left", expand=True, fill="x", padx=(0,5))
            browse_cmd = lambda v=var, t=param_type: self._browse_file_or_dir(v, t)
            button = ctk.CTkButton(frame, text="Browse...", width=80, command=browse_cmd)
            button.pack(side="left")
            widget = entry # The primary widget is the entry
        elif param_type == 'choice':
            options, default_opt = default_value
            var = tk.StringVar(value=default_opt)
            widget = ctk.CTkComboBox(frame, variable=var, values=options, width=300)
        else: # str, float, int
            var = tk.StringVar(value=str(default_value))
            widget = ctk.CTkEntry(frame, textvariable=var, width=300)
        
        if widget and not (param_type == 'path' or param_type == 'dir'): # Path/Dir already packed entry
             widget.pack(side="left", expand=True, fill="x", padx=(0,5) if param_type != 'bool' else 0)
        
        self.config_vars[config_category][param_key] = var
        return frame

    def _create_config_tabs(self):
        for config_category, params in CONFIG_STRUCTURE.items():
            tab_name_map = {
                "blank": "Blank Config",
                "search": "Search Config",
                "isotopic_pattern": "Isotopic Pattern Config",
                "suspect_list": "Suspect List Config"
            }
            tab = self.tab_view.tab(tab_name_map[config_category])
            
            # Scrollable Frame for content
            scrollable_frame = ctk.CTkScrollableFrame(tab)
            scrollable_frame.pack(fill="both", expand=True)

            basic_frame = ctk.CTkFrame(scrollable_frame)
            basic_frame.pack(fill="x", pady=5, padx=5)
            ctk.CTkLabel(basic_frame, text="Basic Parameters", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(0,5))

            self.advanced_frames[config_category] = ctk.CTkFrame(scrollable_frame)
            # self.advanced_frames[config_category].pack(fill="x", pady=5, padx=5) # Packed by toggle

            has_advanced = any(p[3] for p_key, p in params.items()) # p[3] is is_advanced flag

            for param_key, (label, default, p_type, is_advanced) in params.items():
                parent_frame = self.advanced_frames[config_category] if is_advanced else basic_frame
                self._create_input_field(parent_frame, param_key, label, default, p_type, config_category)

            if has_advanced:
                ctk.CTkLabel(self.advanced_frames[config_category], text="Advanced Parameters", font=ctk.CTkFont(weight="bold")).pack(anchor="w", pady=(0,5))
                toggle_button = ctk.CTkButton(
                    scrollable_frame, 
                    text="Show Advanced Parameters",
                    command=lambda cat=config_category: self._toggle_advanced(cat)
                )
                toggle_button.pack(pady=10, padx=5)
                # Initially hide advanced frame content (children are already packed into it)
                self.advanced_frames[config_category].pack_forget()


    def _toggle_advanced(self, category):
        frame = self.advanced_frames[category]
        button = [w for w in self.tab_view.tab(CONFIG_STRUCTURE[category]['tab_name'] if 'tab_name' in CONFIG_STRUCTURE[category] else category.replace("_", " ").title()).winfo_children() if isinstance(w, ctk.CTkScrollableFrame)][0]
        button = [w for w in button.winfo_children() if isinstance(w, ctk.CTkButton) and "Advanced" in w.cget("text")][0]

        if frame.winfo_ismapped():
            frame.pack_forget()
            button.configure(text="Show Advanced Parameters")
        else:
            frame.pack(fill="x", pady=5, padx=5, before=button) # Pack before the button
            button.configure(text="Hide Advanced Parameters")


    def _create_file_selection_tab(self, tab):
        # Sample Files Section
        sample_frame = ctk.CTkFrame(tab)
        sample_frame.pack(fill="x", expand=False, padx=10, pady=10)
        ctk.CTkLabel(sample_frame, text="Sample Files:").pack(side="left", padx=5)
        self.sample_listbox = tk.Listbox(sample_frame, height=5, width=70)
        self.sample_listbox.pack(side="left", fill="x", expand=True, padx=5)
        
        sample_buttons_frame = ctk.CTkFrame(sample_frame)
        sample_buttons_frame.pack(side="left", padx=5)
        ctk.CTkButton(sample_buttons_frame, text="Add Files", command=self._browse_sample_files).pack(fill="x", pady=2)
        ctk.CTkButton(sample_buttons_frame, text="Remove Selected", command=self._remove_selected_sample).pack(fill="x", pady=2)
        ctk.CTkButton(sample_buttons_frame, text="Clear All", command=self._clear_all_samples).pack(fill="x", pady=2)

        # Blank File Section
        blank_frame = ctk.CTkFrame(tab)
        blank_frame.pack(fill="x", expand=False, padx=10, pady=10)
        ctk.CTkLabel(blank_frame, text="Blank File (Optional):").pack(side="left", padx=5)
        self.blank_file_entry_var = tk.StringVar()
        self.blank_file_entry = ctk.CTkEntry(blank_frame, textvariable=self.blank_file_entry_var, width=300, state="readonly")
        self.blank_file_entry.pack(side="left", fill="x", expand=True, padx=5)
        ctk.CTkButton(blank_frame, text="Browse...", command=self._browse_blank_file).pack(side="left", padx=5)
        ctk.CTkButton(blank_frame, text="Clear", command=self._clear_blank_file).pack(side="left", padx=5)

    def _browse_sample_files(self):
        files = filedialog.askopenfilenames(
            title="Select Sample Files",
            filetypes=(("Text files", "*.txt"), ("All files", "*.*"))
        )
        if files:
            for f_path in files:
                if f_path not in self.sample_files:
                    self.sample_files.append(f_path)
                    self.sample_listbox.insert(tk.END, Path(f_path).name)
            self._update_file_paths_for_display()

    def _remove_selected_sample(self):
        selected_indices = self.sample_listbox.curselection()
        for i in reversed(selected_indices):
            self.sample_listbox.delete(i)
            del self.sample_files[i]
        self._update_file_paths_for_display()

    def _clear_all_samples(self):
        self.sample_listbox.delete(0, tk.END)
        self.sample_files.clear()
        self._update_file_paths_for_display()

    def _browse_blank_file(self):
        file = filedialog.askopenfilename(
            title="Select Blank File",
            filetypes=(("Text files", "*.txt"), ("All files", "*.*"))
        )
        if file:
            self.blank_file = file
            self.blank_file_entry_var.set(Path(file).name)
        self._update_file_paths_for_display()

    def _clear_blank_file(self):
        self.blank_file = None
        self.blank_file_entry_var.set("")
        self._update_file_paths_for_display()
        
    def _update_file_paths_for_display(self):
        self.sample_listbox.delete(0, tk.END)
        for f_path in self.sample_files:
            self.sample_listbox.insert(tk.END, Path(f_path).name)
        if self.blank_file:
            self.blank_file_entry_var.set(Path(self.blank_file).name)
        else:
            self.blank_file_entry_var.set("")

    def _browse_file_or_dir(self, var_tk, type_hint):
        initial_dir = Path(var_tk.get()).parent if var_tk.get() and Path(var_tk.get()).exists() else Path.home()
        if type_hint == 'path':
            # Adjust filetypes as needed
            filetypes = (("Database/Library files", "*.msp *.csv *.xlsx *.txt"), ("All files", "*.*"))
            filepath = filedialog.askopenfilename(title="Select File", initialdir=initial_dir, filetypes=filetypes)
            if filepath:
                var_tk.set(filepath)
        elif type_hint == 'dir':
            dirpath = filedialog.askdirectory(title="Select Directory", initialdir=initial_dir)
            if dirpath:
                var_tk.set(dirpath)

    def _collect_config_data(self):
        config_data = {}
        try:
            for category, params_vars in self.config_vars.items():
                config_data[category] = {}
                for param_key, tk_var in params_vars.items():
                    val = tk_var.get()
                    # Infer type from CONFIG_STRUCTURE or actual config class for conversion
                    param_type = CONFIG_STRUCTURE[category][param_key][2] # [2] is type in my tuple
                    
                    if param_type == 'float':
                        config_data[category][param_key] = float(val)
                    elif param_type == 'int':
                        config_data[category][param_key] = int(val)
                    elif param_type == 'bool':
                        config_data[category][param_key] = bool(val)
                    elif param_type == 'path' or param_type == 'dir':
                         config_data[category][param_key] = str(val) if val else None # Handle empty paths
                    elif param_type == 'choice':
                        config_data[category][param_key] = str(val)
                    else: # str
                        config_data[category][param_key] = str(val)
            
            # Special handling for DotProd_threshold if it's stored as separate fields
            # but expected as a list in the actual search_config
            if 'search' in config_data:
                thresholds = []
                haz_keys = ["DotProd_threshold_haz0", "DotProd_threshold_haz1", "DotProd_threshold_haz2", "DotProd_threshold_haz3"]
                all_present = True
                for key in haz_keys:
                    if key in config_data['search']:
                        thresholds.append(config_data['search'][key])
                        del config_data['search'][key] # Remove individual entries
                    else:
                        all_present = False # If one is missing, don't create the list
                        break 
                if all_present:
                     config_data['search']['DotProd_threshold'] = thresholds
                elif 'DotProd_threshold' not in config_data['search']: # if not fully defined and not already there
                    # Fallback or error, for now, let's assume it might be optional or handled by default in pyscreen_config
                    print("Warning: DotProd_threshold components not fully defined in GUI.")


        except ValueError as e:
            self.show_error_popup("Configuration Error", f"Invalid input for a numeric field: {e}\n{traceback.format_exc()}")
            return None
        except Exception as e:
            self.show_error_popup("Configuration Error", f"Error collecting configuration: {e}\n{traceback.format_exc()}")
            return None
        return config_data

    def save_method_dialog(self):
        filepath = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            title="Save Method As"
        )
        if not filepath:
            return

        gui_data_to_save = {
            "sample_files": self.sample_files,
            "blank_file": self.blank_file,
            "config": self._collect_config_data()
        }
        if gui_data_to_save["config"] is None: # Error during collection
            return

        try:
            with open(filepath, 'w') as f:
                json.dump(gui_data_to_save, f, indent=4)
            self.current_method_path = filepath
            self.status_label.configure(text=f"Method saved: {Path(filepath).name}")
        except Exception as e:
            self.show_error_popup("Save Error", f"Failed to save method: {e}\n{traceback.format_exc()}")

    def load_method_dialog(self):
        filepath = filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            title="Load Method"
        )
        if not filepath:
            return

        try:
            with open(filepath, 'r') as f:
                loaded_data = json.load(f)
            
            # Load file paths
            self.sample_files = loaded_data.get("sample_files", [])
            self.blank_file = loaded_data.get("blank_file", None)
            self._update_file_paths_for_display()

            # Load config
            loaded_config = loaded_data.get("config", {})
            for category, params in loaded_config.items():
                if category in self.config_vars:
                    for param_key, value in params.items():
                        # Handle DotProd_threshold list back to individual fields if necessary
                        if param_key == "DotProd_threshold" and isinstance(value, list) and category == "search":
                            haz_keys = ["DotProd_threshold_haz0", "DotProd_threshold_haz1", "DotProd_threshold_haz2", "DotProd_threshold_haz3"]
                            for i, key_suffix in enumerate(haz_keys):
                                if i < len(value) and key_suffix in self.config_vars[category]:
                                    self.config_vars[category][key_suffix].set(value[i])
                        elif param_key in self.config_vars[category]:
                             self.config_vars[category][param_key].set(value)
            
            self.current_method_path = filepath
            self.status_label.configure(text=f"Method loaded: {Path(filepath).name}")

        except Exception as e:
            self.show_error_popup("Load Error", f"Failed to load method: {e}\n{traceback.format_exc()}")
            
    def run_analysis(self):
        if not self.sample_files:
            messagebox.showerror("Input Error", "Please select at least one sample file.")
            return

        final_config = self._collect_config_data()
        if final_config is None: # Error during collection
            return

        self.run_button.configure(state="disabled", text="Running...")
        self.progress_bar.set(0)
        self.progress_bar.configure(mode="indeterminate")
        self.progress_bar.start()
        self.status_label.configure(text="Processing...")
        self.hide_error_details() # Hide previous errors

        # Run in a separate thread to keep GUI responsive
        thread = threading.Thread(target=self._run_analysis_thread, args=(list(self.sample_files), self.blank_file, final_config))
        thread.daemon = True # Allows main program to exit even if thread is running
        thread.start()

    def _run_analysis_thread(self, sample_paths, blank_path, config_dict):
        try:
            # The actual pyscreen.main function is called here
            # It might need a callback to update progress for multiple files
            # For now, we simulate progress based on the number of files if run_pyscreen_analysis doesn't provide it.
            
            # If your run_pyscreen_analysis processes files one by one and can call back:
            # num_files = len(sample_paths)
            # def progress_callback(current_file_index):
            #    progress = (current_file_index + 1) / num_files * 100
            #    self.after(0, self.update_gui_progress, progress, f"Processing file {current_file_index+1}/{num_files}")

            # run_pyscreen_analysis(sample_paths, blank_path, config_dict, progress_callback=progress_callback)
            
            # If not, we just let it run and show indeterminate progress
            run_pyscreen_analysis(sample_paths, blank_path, config=config_dict) # Pass the dict

            self.after(0, self.on_analysis_complete) # Schedule GUI update in main thread
        except Exception as e:
            tb_str = traceback.format_exc()
            self.after(0, self.on_analysis_error, e, tb_str) # Schedule GUI update

    def update_gui_progress(self, value, status_text):
        self.progress_bar.configure(mode="determinate") # Switch back if callback provides progress
        self.progress_bar.set(value / 100)
        self.status_label.configure(text=status_text)

    def on_analysis_complete(self):
        self.progress_bar.stop()
        self.progress_bar.set(1) # Full
        self.progress_bar.configure(mode="determinate")
        self.status_label.configure(text="Analysis Ended Successfully!")
        self.run_button.configure(state="normal", text="Run Analysis")
        messagebox.showinfo("Success", "Pyscreen analysis completed successfully.")

    def on_analysis_error(self, error_exception, traceback_str):
        self.progress_bar.stop()
        self.progress_bar.set(0)
        self.progress_bar.configure(mode="determinate")
        self.status_label.configure(text="Error Occurred!")
        self.run_button.configure(state="normal", text="Run Analysis")
        self.show_error_popup("Analysis Error", f"{str(error_exception)}\n\nFull traceback:\n{traceback_str}")

    def show_error_popup(self, title, message):
        # Simple messagebox for now, could be an internal panel
        # messagebox.showerror(title, message) 
        self.error_label.configure(text=f"{title}. Click to expand details.")
        self.error_text_area.configure(state="normal")
        self.error_text_area.delete("1.0", tk.END)
        self.error_text_area.insert("1.0", message)
        self.error_text_area.configure(state="disabled")
        
        if not self.error_frame.winfo_ismapped():
             self.error_frame.pack(fill="x", padx=5, pady=5, before=self.status_frame) # Pack above status
        
        # Ensure error details are initially hidden if they were visible from a previous error
        if self.error_details_visible:
            self.error_text_area.pack_forget()
            self.error_details_visible = False
            # self.toggle_error_details() # Call to reset view if needed

    def toggle_error_details(self, event=None):
        if self.error_details_visible:
            self.error_text_area.pack_forget()
            self.error_details_visible = False
        else:
            self.error_text_area.pack(fill="both", expand=True, padx=5, pady=(0,5))
            self.error_details_visible = True
            
    def hide_error_details(self):
        if self.error_frame.winfo_ismapped():
            self.error_frame.pack_forget()
        if self.error_details_visible:
            self.error_text_area.pack_forget()
            self.error_details_visible = False


if __name__ == "__main__":
    app = PyScreenApp()
    app.mainloop()

