import os
import time
import shutil
import subprocess
import re
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import configparser

# CoolSync Backup
# Version: v0.2.0
# GUI Version

# Path to config.ini in the root folder
config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.ini')
config = configparser.ConfigParser()
config.read(config_path)

DEFAULT_SOURCE_DIR = config.get('SETTINGS', 'SOURCE_DIR', fallback='Your/Default/Source/Directory').replace("\\", "/")
DEFAULT_DEST_DIR = config.get('SETTINGS', 'DEST_DIR', fallback='Your/Default/Destination/Directory').replace("\\", "/")
DEFAULT_START_TEMP = config.getfloat('SETTINGS', 'START_TEMP', fallback=30)  # Example start temperature in Celsius
DEFAULT_STOP_TEMP = config.getfloat('SETTINGS', 'STOP_TEMP', fallback=47)  # Updated default stop temperature in Celsius
DEFAULT_DARK_MODE = config.getboolean('SETTINGS', 'DARK_MODE', fallback=False)

class CoolSyncBackupApp:
    def __init__(self, root):
        self.root = root
        self.root.title("CoolSync Backup v0.2.0")

        self.source_dir = tk.StringVar(value=DEFAULT_SOURCE_DIR)
        self.dest_dir = tk.StringVar(value=DEFAULT_DEST_DIR)
        self.start_temp = tk.DoubleVar(value=DEFAULT_START_TEMP)
        self.stop_temp = tk.DoubleVar(value=DEFAULT_STOP_TEMP)
        self.is_dark_mode = tk.BooleanVar(value=DEFAULT_DARK_MODE)
        self.stop_backup_flag = threading.Event()

        self.create_widgets()
        self.apply_saved_mode()  # Apply the saved mode on initialization

    def create_widgets(self):
        self.style = ttk.Style()

        # Create the toggle switch style
        self.style.configure("TButton", font=("Arial", 10))
        self.style.configure("DarkMode.TCheckbutton", indicatoron=False, relief="flat", background="#333", foreground="white")
        self.style.configure("LightMode.TCheckbutton", indicatoron=False, relief="flat", background="#fff", foreground="black")

        tk.Label(self.root, text="Source Directory:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        tk.Entry(self.root, textvariable=self.source_dir, width=50).grid(row=0, column=1, padx=5, pady=5)
        tk.Button(self.root, text="Browse", command=self.browse_source).grid(row=0, column=2, padx=5, pady=5)

        tk.Label(self.root, text="Destination Directory:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        tk.Entry(self.root, textvariable=self.dest_dir, width=50).grid(row=1, column=1, padx=5, pady=5)
        tk.Button(self.root, text="Browse", command=self.browse_dest).grid(row=1, column=2, padx=5, pady=5)

        tk.Label(self.root, text="Start Temperature (°C):").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        tk.Entry(self.root, textvariable=self.start_temp).grid(row=2, column=1, padx=5, pady=5)

        tk.Label(self.root, text="Stop Temperature (°C):").grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
        tk.Entry(self.root, textvariable=self.stop_temp).grid(row=3, column=1, padx=5, pady=5)

        tk.Button(self.root, text="Start Backup", command=self.start_backup).grid(row=4, column=0, columnspan=1, pady=10)
        tk.Button(self.root, text="Stop Backup", command=self.stop_backup).grid(row=4, column=1, columnspan=1, pady=10)
        tk.Button(self.root, text="Save Settings", command=self.save_settings).grid(row=5, column=0, columnspan=2, pady=5)

        self.dark_mode_button = ttk.Checkbutton(self.root, text="Dark Mode", variable=self.is_dark_mode, command=self.toggle_dark_mode, style="DarkMode.TCheckbutton")
        self.dark_mode_button.grid(row=5, column=2, padx=5, pady=5)
        self.update_checkbox_state()

        self.log_text = tk.Text(self.root, state="disabled", width=80, height=10)
        self.log_text.grid(row=6, column=0, columnspan=3, padx=5, pady=5)

    def apply_light_mode(self):
        self.root.config(bg="white")
        for widget in self.root.winfo_children():
            if isinstance(widget, (tk.Label, tk.Button, tk.Entry)):
                widget.config(bg="white", fg="black")
        self.log_text.config(bg="white", fg="black")
        self.dark_mode_button.config(style="LightMode.TCheckbutton")

    def apply_dark_mode(self):
        self.root.config(bg="black")
        for widget in self.root.winfo_children():
            if isinstance(widget, (tk.Label, tk.Button, tk.Entry)):
                widget.config(bg="black", fg="white")
        self.log_text.config(bg="black", fg="white")
        self.dark_mode_button.config(style="DarkMode.TCheckbutton")

    def apply_saved_mode(self):
        if self.is_dark_mode.get():
            self.apply_dark_mode()
        else:
            self.apply_light_mode()
        self.update_checkbox_state()

    def update_mode(self):
        if self.is_dark_mode.get():
            self.apply_dark_mode()
        else:
            self.apply_light_mode()
        self.save_settings()
        self.update_checkbox_state()

    def update_checkbox_state(self):
        if self.is_dark_mode.get():
            self.dark_mode_button.state(["!alternate", "selected"])
        else:
            self.dark_mode_button.state(["!alternate", "!selected"])

    def toggle_dark_mode(self):
        self.is_dark_mode.set(not self.is_dark_mode.get())  # Toggle the boolean variable
        self.update_mode()

    def apply_light_mode(self):
        self.root.config(bg="white")
        for widget in self.root.winfo_children():
            if isinstance(widget, (tk.Label, tk.Button, tk.Entry)):
                widget.config(bg="white", fg="black")
        self.log_text.config(bg="white", fg="black")
        self.dark_mode_button.config(style='LightMode.TButton')

    def apply_dark_mode(self):
        self.root.config(bg="black")
        for widget in self.root.winfo_children():
            if isinstance(widget, (tk.Label, tk.Button, tk.Entry)):
                widget.config(bg="black", fg="white")
        self.log_text.config(bg="black", fg="white")
        self.dark_mode_button.config(style='DarkMode.TButton')

    def browse_source(self):
        directory = filedialog.askdirectory()
        if directory:
            self.source_dir.set(directory)

    def browse_dest(self):
        directory = filedialog.askdirectory()
        if directory:
            self.dest_dir.set(directory)

    def save_settings(self):
        if not config.has_section('SETTINGS'):
            config.add_section('SETTINGS')
        config.set('SETTINGS', 'SOURCE_DIR', self.source_dir.get())
        config.set('SETTINGS', 'DEST_DIR', self.dest_dir.get())
        config.set('SETTINGS', 'START_TEMP', str(self.start_temp.get()))
        config.set('SETTINGS', 'STOP_TEMP', str(self.stop_temp.get()))
        config.set('SETTINGS', 'DARK_MODE', str(self.is_dark_mode.get()))
        with open(config_path, 'w') as configfile:
            config.write(configfile)
        self.log("Settings saved successfully.")

    def log(self, message):
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)  # Ensure the most recent log message is visible
        self.log_text.config(state='disabled')

    def stop_backup(self):
        self.stop_backup_flag.set()
        self.log("Backup Stopped.\n-------------------")

    def start_backup(self):
        self.stop_backup_flag.clear()
        self.log("\n-------------------\nStarting backup...")
        backup_thread = threading.Thread(target=self.run_backup, daemon=True)
        backup_thread.start()

    def run_backup(self):
        source_dir = self.source_dir.get()
        dest_dir = self.dest_dir.get()
        start_temp = self.start_temp.get()
        stop_temp = self.stop_temp.get()

        if not os.path.exists(source_dir):
            self.log(f"Error: Source directory '{source_dir}' does not exist.")
            return
        if not os.path.exists(dest_dir):
            self.log(f"Error: Destination directory '{dest_dir}' does not exist.")
            return
        
        drive_letters = self.get_drive_letters([source_dir, dest_dir])
        self.log(f"Configuration Summary:\nSource Directory: {source_dir}\nDestination Directory: {dest_dir}\nStart Temperature: {start_temp}°C\nStop Temperature: {stop_temp}°C\nMonitoring Drives: {', '.join(drive_letters)}")

        backup_in_progress = False

        try:
            while not self.stop_backup_flag.is_set():
                for drive_letter in drive_letters:
                    temp = self.get_drive_temperature(drive_letter)
                    if temp is None:
                        self.log(f"Error: Could not get the temperature for drive {drive_letter}.")
                        return
                    
                    self.log(f"Current temperature for drive {drive_letter}: {temp}°C")

                    if temp <= start_temp:
                        if not backup_in_progress:
                            self.log("Temperature is within safe range. Starting backup...")
                            backup_in_progress = True
                            self.log("Running Sync and showing the first 5 files synced:")
                            self.mirror_sync(source_dir, dest_dir)
                            self.log("Backup process finished.")
                            backup_in_progress = False
                            return  # Exit after backup completes
                    elif temp >= stop_temp:
                        if backup_in_progress:
                            self.log("Temperature is too high. Pausing backup...")
                            backup_in_progress = False
                        self.log("Waiting for temperature to drop within the User specified safe range...")

                if not backup_in_progress:
                    self.log("Waiting for temperature to drop within the User specified safe range...")

                time.sleep(60)  # Wait 60 seconds before checking the temperature again
        except KeyboardInterrupt:
            self.log("Backup interrupted.")

    def get_drive_letters(self, paths):
        drive_letters = set()
        for path in paths:
            drive_letters.add(os.path.splitdrive(path)[0])
        return list(drive_letters)

    def get_drive_temperature(self, drive_letter):
        try:
            result = subprocess.run(['smartctl', '-A', f'{drive_letter}'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if result.returncode != 0:
                raise Exception(f"smartctl error: {result.stderr}")

            for line in result.stdout.split('\n'):
                if 'Temperature_Celsius' in line or 'Temperature' in line:
                    match = re.search(r'(\d+)', line)
                    if match:
                        temp = int(match.group(1))
                        return temp
                    else:
                        raise Exception("Temperature value not found")
        except Exception as e:
            self.log(f"Error getting temperature for drive {drive_letter}: {e}")
            return None

    def mirror_sync(self, source_dir, dest_dir):
        synced_files = []

        for root, dirs, files in os.walk(source_dir):
            for file in files:
                if self.stop_backup_flag.is_set():
                    self.log("Backup process stopped by the user during sync.")
                    return

                src_file = os.path.join(root, file)
                dest_file = os.path.join(dest_dir, os.path.relpath(src_file, source_dir))
                dest_dir_path = os.path.dirname(dest_file)
                os.makedirs(dest_dir_path, exist_ok=True)

                if os.path.exists(dest_file):
                    if os.path.getmtime(src_file) > os.path.getmtime(dest_file):
                        shutil.copy2(src_file, dest_file)
                        status = "changed"
                    else:
                        status = "same"
                else:
                    shutil.copy2(src_file, dest_file)
                    status = "new"

                if len(synced_files) < 5:
                    synced_files.append(f"{os.path.relpath(src_file, source_dir)} - {status}")

        for root, dirs, files in os.walk(dest_dir):
            for file in files:
                dest_file = os.path.join(root, file)
                src_file = os.path.join(source_dir, os.path.relpath(dest_file, dest_dir))
                if not os.path.exists(src_file):
                    os.remove(dest_file)
                    
            for dir in dirs:
                dest_dir_path = os.path.join(root, dir)
                src_dir_path = os.path.join(source_dir, os.path.relpath(dest_dir_path, dest_dir))
                if not os.path.exists(src_dir_path) and dest_dir_path != script_dir:
                    shutil.rmtree(dest_dir_path)

        self.log("Summary of Sync results:")
        for file in synced_files:
            self.log(file)

if __name__ == "__main__":
    root = tk.Tk()
    app = CoolSyncBackupApp(root)
    root.mainloop()
