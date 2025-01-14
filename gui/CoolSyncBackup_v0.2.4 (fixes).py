import tkinter as tk
from tkinter import messagebox, filedialog
import threading
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
    return {"source_folder": "", "destination_folder": "", "safe_temp": 31.0, "high_temp": 42.0, "update_interval": 1}

def save_config(config):
    with open(CONFIG_FILE, 'w') as file:
        json.dump(config, file)

def run_smartctl_command(command, device_name):
    try:
        print(f'Running command: {command}')  # Debug print command
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        print("smartctl output:\n", result.stdout)  # Debug print the smartctl output
        temperature = None
        model_number = device_name  # Default to device name if model number is not found
        for line in result.stdout.splitlines():
            print(f'Processing line: {line}')  # Debug print each line processed
            if "Temperature_Celsius" in line:
                temp_str = line.split()[-1]
                if temp_str == '-' or not temp_str.replace('.', '', 1).isdigit():
                    print(f"Warning: Unexpected temperature value '{temp_str}'")
                    continue
                try:
                    temperature = float(temp_str)
                    print(f'Parsed temperature: {temperature}')  # Debug print parsed temperature
                except ValueError:
                    print(f"Warning: Could not parse temperature value '{temp_str}'")
            elif device_name == "/dev/sda" and "Model Number" in line:
                model_number = ' '.join(line.split()[2:])  # Extract model number for /dev/sda
                print(f'Parsed model number for /dev/sda: {model_number}')  # Debug print model number
            elif device_name == "/dev/sdb" and "Device Model" in line:
                model_number = ' '.join(line.split()[2:])  # Extract device model for /dev/sdb
                print(f'Parsed device model for /dev/sdb: {model_number}')  # Debug print device model
        return temperature, model_number
    except Exception as e:
        print(f'Error fetching data with command {command}: {e}')
    return None, device_name  # Default to device name if there's an error

def get_specific_device_temperatures():
    print('Fetching device temperatures...')  # Debug print
    temperatures = {}
    commands = {
        "/dev/sda": ["smartctl", "-A", "/dev/sda"],
        "/dev/sdb": ["smartctl", "-A", "/dev/sdb"]
    }
    for device, command in commands.items():
        print(f'Running command for {device}: {command}')  # Debug print command
        temp, model = run_smartctl_command(command, device)
        if temp is None:
            print(f'Error: Unable to fetch temperature for {device}. Possible reasons include:')
            print('1. Smartctl is not installed or lacks permissions.')
            print('2. The device does not support temperature monitoring through smartctl.')
            print('3. The command syntax needs adjustment.')
            temperatures[model] = 'N/A'
        else:
            temperatures[model] = temp
    print(f'Device temperatures: {temperatures}')  # Debug print
    return temperatures

def sync_files(source, destination, stop_event, app):
    print('Starting file sync...')  # Debug print
    app.update_status("Sync in progress...")

    while not stop_event.is_set():
        temperatures = get_specific_device_temperatures()

        # Check temperatures against safe and high temp settings
        for device, temp in temperatures.items():
            if temp != 'N/A' and temp > app.high_temp.get():
                print(f'{device} temperature ({temp}°C) exceeds high temp ({app.high_temp.get()}°C). Stopping sync.')
                app.update_status(f"{device} temperature ({temp}°C) exceeds high temp. Stopping sync.")
                return
            elif temp != 'N/A' and temp <= app.safe_temp.get():
                print(f'{device} temperature ({temp}°C) is below safe temp ({app.safe_temp.get()}°C). Starting/resuming sync.')
                app.update_status(f"{device} temperature ({temp}°C) is below safe temp. Starting/resuming sync.")
                break
        else:
            print('No devices are within the safe temperature range. Waiting...')
            app.update_status("No devices are within the safe temperature range. Waiting...")
            stop_event.wait(60)  # Wait for 1 minute before checking the temperatures again
            continue

        sync_performed = False
        file_count = 0  # Counter for the number of synced files

        # Add or update files from source to destination
        for root_dir, dirs, files in os.walk(source):
            if stop_event.is_set():
                print('Sync stopped by user')
                app.update_status("Sync stopped by user")
                return
            dest_dir = root_dir.replace(source, destination)
            if not os.path.exists(dest_dir):
                os.makedirs(dest_dir)
            for file in files:
                if stop_event.is_set():
                    print('Sync stopped by user')
                    app.update_status("Sync stopped by user")
                    return
                src_file = os.path.join(root_dir, file)
                dest_file = os.path.join(dest_dir, file)
                if not os.path.exists(dest_file) or os.path.getmtime(src_file) > os.path.getmtime(dest_file):
                    shutil.copy2(src_file, dest_file)
                    print(f'Synced: {file}')
                    sync_performed = True
                    file_count += 1  # Increment file count

        # Remove files from destination that no longer exist in source
        for root_dir, dirs, files in os.walk(destination):
            if stop_event.is_set():
                print('Sync stopped by user')
                app.update_status("Sync stopped by user")
                return
            src_dir = root_dir.replace(destination, source)
            for file in files:
                if stop_event.is_set():
                    print('Sync stopped by user')
                    app.update_status("Sync stopped by user")
                    return
                dest_file = os.path.join(root_dir, file)
                src_file = os.path.join(src_dir, file)
                if not os.path.exists(src_file):
                    os.remove(dest_file)
                    print(f'Removed: {file}')
                    sync_performed = True

        if sync_performed:
            print(f'File sync complete.\nSource: {source}\nDestination: {destination}\nFiles synced: {file_count}')  # Debug print
            app.update_status(f"Sync completed successfully.\nSource: {source}\nDestination: {destination}\nFiles synced: {file_count}")
        else:
            print('No files to sync or already synced')  # Debug print
            app.update_status("No files to sync or already synced")

        stop_event.wait(60)  # Wait for 1 minute before checking the temperatures again

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
        self.update_interval = tk.IntVar(value=config.get('update_interval', 1))
        self.device_temps = {}  # Store current temperatures for all devices
        self.sync_in_progress = False
        self.sync_thread = None
        self.stop_event = threading.Event()  # Stop event for clean stopping

        self.create_widgets()
        self.update_temperature_display()  # Start updating the temperature display

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

        # Update Interval
        tk.Label(self.root, text='Update Interval (minutes)').pack()
        interval_frame = tk.Frame(self.root)
        interval_frame.pack()
        tk.Entry(interval_frame, textvariable=self.update_interval).pack(side=tk.LEFT)
        tk.Button(interval_frame, text='💾', command=self.save_update_interval).pack(side=tk.LEFT)

        # Temperature Monitor Display
        tk.Label(self.root, text='Current Temps (°C)').pack()
        self.temp_display = tk.Text(self.root, height=5, width=50)
        self.temp_display.pack()

        # Sync Controls
        self.start_button = tk.Button(self.root, text='Start Sync', command=self.start_sync)
        self.start_button.pack(pady=10)

        self.stop_button = tk.Button(self.root, text='Stop Sync', command=self.stop_sync_func)
        self.stop_button.pack(pady=10)

        # Status Label
        self.status_label = tk.Label(self.root, text='', fg='green')
        self.status_label.pack()

    def save_safe_temp(self):
        config = load_config()
        config['safe_temp'] = self.safe_temp.get()
        save_config(config)
        print(f'Safe temperature set to: {self.safe_temp.get()}°C')  # Debug print
        messagebox.showinfo('Saved', f'Safe temperature saved: {self.safe_temp.get()}°C')

    def save_high_temp(self):
        config = load_config()
        config['high_temp'] = self.high_temp.get()
        save_config(config)
        print(f'High temperature set to: {self.high_temp.get()}°C')  # Debug print
        messagebox.showinfo('Saved', f'High temperature saved: {self.high_temp.get()}°C')

    def save_update_interval(self):
        config = load_config()
        config['update_interval'] = self.update_interval.get()
        save_config(config)
        print(f'Update interval set to: {self.update_interval.get()} minutes')  # Debug print
        messagebox.showinfo('Saved', f'Update interval saved: {self.update_interval.get()} minutes')

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
            "update_interval": self.update_interval.get()
        }
        save_config(config)

    def start_sync(self):
        source_path = self.source_folder.get()
        destination_path = self.destination_folder.get()
        if not source_path or not destination_path or source_path == destination_path:
            messagebox.showerror('Error', 'Invalid source or destination path')
            return
        self.stop_event.clear()
        self.sync_thread = threading.Thread(target=sync_files, args=(source_path, destination_path, self.stop_event, self))
        self.sync_thread.start()

    def stop_sync_func(self):
        self.stop_event.set()
        if self.sync_thread:
            self.sync_thread.join()
        self.update_status("Sync stopped by user")

    def update_temperature_display(self):
        self.device_temps = get_specific_device_temperatures()
        self.temp_display.delete(1.0, tk.END)
        for device, temp in self.device_temps.items():
            self.temp_display.insert(tk.END, f"{device}: {temp}°C\n")
        # Schedule next update
        self.root.after(self.update_interval.get() * 60000, self.update_temperature_display)

    def update_status(self, message):
        self.status_label.config(text=message)

if __name__ == '__main__':
    root = tk.Tk()
    app = CoolSyncBackup(root)
    root.mainloop()

