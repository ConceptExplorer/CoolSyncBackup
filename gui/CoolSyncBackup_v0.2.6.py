import tkinter as tk
from tkinter import messagebox, filedialog
import threading
import queue
import os
import shutil
import subprocess
import json

CONFIG_FILE = "config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as file:
            config = json.load(file)
            return config
    return {"source_folder": "", "destination_folder": "", "safe_temp": 31.0, "high_temp": 42.0, "monitor_interval": 1}

def save_config(config):
    with open(CONFIG_FILE, 'w') as file:
        json.dump(config, file)

def run_smartctl_command(command, device_name):
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        temperature = None
        model_number = device_name  # Default to device name if model number is not found
        for line in result.stdout.splitlines():
            if "Temperature_Celsius" in line:
                temp_str = line.split()[-1]
                if temp_str == '-' or not temp_str.replace('.', '', 1).isdigit():
                    continue
                try:
                    temperature = float(temp_str)
                except ValueError:
                    pass
            elif device_name == "/dev/sda" and "Model Number" in line:
                model_number = ' '.join(line.split()[2:])  # Extract model number for /dev/sda
            elif device_name == "/dev/sdb" and "Device Model" in line:
                model_number = ' '.join(line.split()[2:])  # Extract device model for /dev/sdb
            elif "Temperature" in line:  # Try alternative keyword for temperature
                temp_str = line.split()[-2]
                if temp_str.isdigit():
                    try:
                        temperature = float(temp_str)
                    except ValueError:
                        pass
        return temperature, model_number
    except Exception as e:
        print(f'Error fetching data with command {command}: {e}')
    return None, device_name  # Default to device name if there's an error

def get_specific_device_temperatures():
    temperatures = {}
    commands = {
        "/dev/sda": ["smartctl", "-A", "/dev/sda"],
        "/dev/sdb": ["smartctl", "-A", "/dev/sdb"]
    }
    for device, command in commands.items():
        temp, model = run_smartctl_command(command, device)
        if temp is None:
            temperatures[model] = 'N/A'
        else:
            temperatures[model] = temp
    return temperatures

def sync_files(source, destination, stop_event, app, queue):
    app.update_status("Sync in progress...")

    while not stop_event.is_set():
        temperatures = get_specific_device_temperatures()
        safe_temp = queue.get()  # Get safe_temp from the queue
        high_temp = queue.get()  # Get high_temp from the queue
        
        safe_temp_met = all(temp <= safe_temp for temp in temperatures.values() if temp != 'N/A')
        high_temp_met = any(temp >= high_temp for temp in temperatures.values() if temp != 'N/A')

        if high_temp_met:
            app.update_status("High temperature detected. Pausing sync.")
            while high_temp_met:
                if stop_event.is_set():
                    app.update_status("Sync stopped by user")
                    return
                temperatures = get_specific_device_temperatures()
                high_temp_met = any(temp >= high_temp for temp in temperatures.values() if temp != 'N/A')
            app.update_status("Temperature dropped to safe level. Resuming sync.")

        if not safe_temp_met:
            app.update_status("Safe temperature not met. Waiting to start sync.")
            while not safe_temp_met:
                if stop_event.is_set():
                    app.update_status("Sync stopped by user")
                    return
                temperatures = get_specific_device_temperatures()
                safe_temp_met = all(temp <= safe_temp for temp in temperatures.values() if temp != 'N/A')
            app.update_status("Safe temperature met. Starting sync.")

        sync_performed = False
        file_count = 0  # Counter for the number of synced files

        # Add or update files from source to destination
        for root_dir, dirs, files in os.walk(source):
            if stop_event.is_set():
                app.update_status("Sync stopped by user")
                return
            dest_dir = root_dir.replace(source, destination)
            if not os.path.exists(dest_dir):
                os.makedirs(dest_dir)
            for file in files:
                if stop_event.is_set():
                    app.update_status("Sync stopped by user")
                    return
                src_file = os.path.join(root_dir, file)
                dest_file = os.path.join(dest_dir, file)
                if not os.path.exists(dest_file) or os.path.getmtime(src_file) > os.path.getmtime(dest_file):
                    shutil.copy2(src_file, dest_file)
                    sync_performed = True
                    file_count += 1  # Increment file count

        # Remove files from destination that no longer exist in source
        for root_dir, dirs, files in os.walk(destination):
            if stop_event.is_set():
                app.update_status("Sync stopped by user")
                return
            src_dir = root_dir.replace(destination, source)
            for file in files:
                if stop_event.is_set():
                    app.update_status("Sync stopped by user")
                    return
                dest_file = os.path.join(root_dir, file)
                src_file = os.path.join(src_dir, file)
                if not os.path.exists(src_file):
                    os.remove(dest_file)
                    sync_performed = True

        if sync_performed:
            app.update_status(f"Sync completed successfully.\nSource: {source}\nDestination: {destination}\nFiles synced: {file_count}")
        else:
            app.update_status("No files to sync or already synced")

        # Wait for the monitor interval before checking temperatures again
        stop_event.wait(app.monitor_interval.get() * 60)

class CoolSyncBackup:
    def __init__(self, root):
        self.root = root
        self.root.title('CoolSyncBackup - Storage Sync and Temp Monitor')
        self.root.geometry('400x500')

        config = load_config()

        # Load source and destination folders from config
        self.source_folder = tk.StringVar(value=config.get('source_folder', ''))
        self.destination_folder = tk.StringVar(value=config.get('destination_folder', ''))
        self.safe_temp = tk.DoubleVar(value=config.get('safe_temp', 31.0))
        self.high_temp = tk.DoubleVar(value=config.get('high_temp', 42.0))
        self.monitor_interval = tk.IntVar(value=config.get('monitor_interval', 1))
        self.device_temps = {}  # Store current temperatures for all devices
        self.sync_in_progress = False
        self.sync_thread = None
        self.stop_event = threading.Event()  # Stop event for clean stopping
        self.queue = queue.Queue()  # Create a queue to communicate with the sync thread

        # Define the temp_display widget
        self.temp_display = tk.Text(self.root, height=10, state='disabled')
        self.temp_display.pack()

        self.create_widgets()
        self.update_temperature_display()  # Start updating the temperature display

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)  # Handle window close event

    def create_widgets(self):
        # Source Folder
        tk.Label(self.root, text='Source Folder').pack()
        frame_source = tk.Frame(self.root)
        frame_source.pack()
        self.source_folder_display = tk.Entry(frame_source, textvariable=self.source_folder, state='readonly')
        self.source_folder_display.pack(side=tk.LEFT)
        tk.Button(frame_source, text='Browse', command=self.browse_source).pack(side=tk.LEFT)

        # Destination Folder
        tk.Label(self.root, text='Destination Folder').pack()
        frame_destination = tk.Frame(self.root)
        frame_destination.pack()
        self.destination_folder_display = tk.Entry(frame_destination, textvariable=self.destination_folder, state='readonly')
        self.destination_folder_display.pack(side=tk.LEFT)
        tk.Button(frame_destination, text='Browse', command=self.browse_destination).pack(side=tk.LEFT)

        # Safe and High Temps
        tk.Label(self.root, text='Safe Temp (°C)').pack()
        temp_frame = tk.Frame(self.root)
        temp_frame.pack()
        tk.Entry(temp_frame, textvariable=self.safe_temp).pack(side=tk.LEFT)
        tk.Button(temp_frame, text='💾', command=self.save_safe_temp).pack(side=tk.LEFT)

        tk.Label(self.root, text='High Temp (°C)').pack()
        high_temp_frame = tk.Frame(self.root)
        high_temp_frame.pack()
        tk.Entry(high_temp_frame, textvariable=self.high_temp).pack(side=tk.LEFT)
        tk.Button(high_temp_frame, text='💾', command=self.save_high_temp).pack(side=tk.LEFT)

        tk.Label(self.root, text='Monitor Interval (minutes)').pack()
        interval_frame = tk.Frame(self.root)
        interval_frame.pack()
        tk.Entry(interval_frame, textvariable=self.monitor_interval).pack(side=tk.LEFT)
        tk.Button(interval_frame, text='💾', command=self.save_monitor_interval).pack(side=tk.LEFT)

        # Status
        self.status = tk.StringVar(value="Status: Ready")
        self.status_label = tk.Label(self.root, textvariable=self.status, wraplength=300)
        self.status_label.pack()

        # Start/Stop Sync
        tk.Button(self.root, text='Start Sync', command=self.start_sync).pack()
        tk.Button(self.root, text='Stop Sync', command=self.stop_sync).pack()

    def update_status(self, message):
        self.status.set(f"Status: {message}")

    def save_safe_temp(self):
        config = load_config()
        config['safe_temp'] = self.safe_temp.get()
        save_config(config)

    def save_high_temp(self):
        config = load_config()
        config['high_temp'] = self.high_temp.get()
        save_config(config)

    def save_monitor_interval(self):
        config = load_config()
        config['monitor_interval'] = self.monitor_interval.get()
        save_config(config)
        print(f'Update interval set to: {self.monitor_interval.get()} minutes')  # Debug print
        messagebox.showinfo('Saved', f'Update interval saved: {self.monitor_interval.get()} minutes')

    def browse_source(self):
        folder_selected = filedialog.askdirectory(initialdir=self.source_folder.get())
        if folder_selected:
            print(f'Source folder selected: {folder_selected}')  # Debug print
            self.set_source_path(folder_selected)

    def browse_destination(self):
        folder_selected = filedialog.askdirectory(initialdir=self.destination_folder.get())
        if folder_selected:
            print(f'Destination folder selected: {folder_selected}')  # Debug print
            self.set_destination_path(folder_selected)

    def on_closing(self):
        if self.sync_in_progress:
            self.stop_sync()
        self.root.destroy()

    def set_source_path(self, path):
        if path == self.destination_folder.get():
            messagebox.showerror('Error', 'Source and destination paths cannot be the same')
            return
        print(f'Setting source folder to: {path}')  # Debug print
        self.source_folder.set(path)
        self.source_folder_display.config(textvariable=tk.StringVar(value=path))
        self.save_config()

    def set_destination_path(self, path):
        if path == self.source_folder.get():
            messagebox.showerror('Error', 'Source and destination paths cannot be the same')
            return
        print(f'Setting destination folder to: {path}')  # Debug print
        self.destination_folder.set(path)
        self.destination_folder_display.config(textvariable=tk.StringVar(value=path))
        self.save_config()

    def save_config(self):
        config = {
            "source_folder": self.source_folder.get(),
            "destination_folder": self.destination_folder.get(),
            "safe_temp": self.safe_temp.get(),
            "high_temp": self.high_temp.get(),
            "monitor_interval": self.monitor_interval.get()
        }
        save_config(config)

    def start_sync(self):
        if not self.sync_in_progress:
            self.sync_in_progress = True
            self.stop_event.clear()
            self.queue.put(self.safe_temp.get())
            self.queue.put(self.high_temp.get())
            self.sync_thread = threading.Thread(target=sync_files, args=(self.source_folder.get(), self.destination_folder.get(), self.stop_event, self, self.queue))
            self.sync_thread.start()
            self.update_status("Sync started")

    def stop_sync(self):
        self.stop_event.set()
        self.update_status("Sync stopped by user")

    def stop_sync_func(self):
        self.stop_event.set()
        if self.sync_thread:
            self.sync_thread.join()
        self.update_status("Sync stopped by user")

    def update_temperature_display(self):
        self.temp_display.configure(state='normal')
        self.temp_display.delete(1.0, tk.END)
        temperatures = get_specific_device_temperatures()
        for device, temp in temperatures.items():
            self.temp_display.insert(tk.END, f"{device}: {temp}°C\n")
        self.temp_display.configure(state='disabled')
        self.root.after(60000, self.update_temperature_display)  # Update every 60 seconds

    def update_status(self, message):
        self.status_label.config(text=message)

if __name__ == '__main__':
    root = tk.Tk()
    app = CoolSyncBackup(root)
    root.mainloop()

