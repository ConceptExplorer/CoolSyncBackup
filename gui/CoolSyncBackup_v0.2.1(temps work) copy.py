import tkinter as tk
from tkinter import messagebox, filedialog
import threading
import time
import os
import shutil
import subprocess  # For running smartctl

# Mapping of device names for friendly display
FRIENDLY_NAMES = {
    "/dev/sda": "WD_Black SSD 2TB",
    "/dev/sdb": "WDC Gold Enterprise HDD 8TB"
}

# Function to run the command directly
def run_smartctl_command(command):
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for line in result.stdout.splitlines():
            # Check for SSD temperature format
            if "Temperature:" in line:
                temp_str = line.split()[-2]
                temp = float(temp_str)
                return temp
            # Check for HDD temperature format
            elif "Temperature_Celsius" in line:
                temp = float(line.split()[-1])
                return temp
    except Exception as e:
        print(f'Error fetching temperature data with command {command}: {e}')
    return None

# Function to get temperatures for specific devices
def get_specific_device_temperatures():
    temperatures = {}
    commands = {
        "WD_Black SSD 2TB": ["smartctl", "-A", "-d", "nvme", "/dev/sdb"],
        "WDC Gold Enterprise HDD 8TB": ["smartctl", "-A", "-d", "ata", "/dev/sda"]
    }
    for device_name, command in commands.items():
        temp = run_smartctl_command(command)
        if temp is not None:
            temperatures[device_name] = temp
        else:
            temperatures[device_name] = 'N/A'  # Indicate no data available
    return temperatures

# Function to sync files
def sync_files(source, destination):
    if not os.path.exists(source) or not os.path.exists(destination):
        print('Invalid source or destination path')
        return

    for root_dir, dirs, files in os.walk(source):
        dest_dir = root_dir.replace(source, destination)
        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir)
        for file in files:
            src_file = os.path.join(root_dir, file)
            dest_file = os.path.join(dest_dir, file)
            if not os.path.exists(dest_file) or os.path.getmtime(src_file) > os.path.getmtime(dest_file):
                shutil.copy2(src_file, dest_file)
                print(f'Synced: {file}')

class CoolSyncApp:
    def __init__(self, root):
        self.root = root
        self.root.title('CoolSync - Storage Sync and Temp Monitor')
        self.root.geometry('400x500')

        # Default source and destination folders
        self.source_folder = tk.StringVar(value='C:\\Test_Sync(SSD)\\Source Folder(SDD)')
        self.destination_folder = tk.StringVar(value='D:\\Test_Sync(HDD)\\Dest Folder(HDD)')
        self.safe_temp = tk.DoubleVar(value=31.0)  # Default safe temperature
        self.high_temp = tk.DoubleVar(value=42.0)  # Default high temperature
        self.device_temps = {}  # Store current temperatures for all devices
        self.sync_in_progress = False
        self.sync_thread = None
        self.stop_sync = False

        self.create_widgets()

    def create_widgets(self):
        # Source Folder
        tk.Label(self.root, text='Source Folder').pack()
        frame_source = tk.Frame(self.root)
        frame_source.pack()
        self.source_folder_display = tk.Entry(frame_source, textvariable=tk.StringVar(value=os.path.basename(self.source_folder.get())), state='readonly')
        self.source_folder_display.pack(side=tk.LEFT)
        tk.Button(frame_source, text='Browse', command=self.browse_source).pack(side=tk.LEFT)

        # Destination Folder
        tk.Label(self.root, text='Destination Folder').pack()
        frame_destination = tk.Frame(self.root)
        frame_destination.pack()
        self.destination_folder_display = tk.Entry(frame_destination, textvariable=tk.StringVar(value=os.path.basename(self.destination_folder.get())), state='readonly')
        self.destination_folder_display.pack(side=tk.LEFT)
        tk.Button(frame_destination, text='Browse', command=self.browse_destination).pack(side=tk.LEFT)

        # Safe and High Temps
        tk.Label(self.root, text='Safe Temp (°C)').pack()
        tk.Entry(self.root, textvariable=self.safe_temp).pack()
        tk.Label(self.root, text='High Temp (°C)').pack()
        tk.Entry(self.root, textvariable=self.high_temp).pack()

        # Temperature Monitor Display
        tk.Label(self.root, text='Current Temps (°C)').pack()
        self.temp_display = tk.Text(self.root, height=5, width=50)
        self.temp_display.pack()

        # Sync Controls
        self.start_button = tk.Button(self.root, text='Start Sync', command=self.start_sync)
        self.start_button.pack(pady=10)

        self.stop_button = tk.Button(self.root, text='Stop Sync', command=self.stop_sync_func)
        self.stop_button.pack(pady=10)

    def browse_source(self):
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            self.source_folder.set(folder_selected)
            self.source_folder_display.config(textvariable=tk.StringVar(value=os.path.basename(folder_selected)))

    def browse_destination(self):
        folder_selected = filedialog.askdirectory()
        if folder_selected:
            self.destination_folder.set(folder_selected)
            self.destination_folder_display.config(textvariable=tk.StringVar(value=os.path.basename(folder_selected)))

    def update_temperature_display(self):
        self.temp_display.delete('1.0', tk.END)
        self.device_temps = get_specific_device_temperatures()
        if self.device_temps:
            for device, temp in self.device_temps.items():
                self.temp_display.insert(tk.END, f'{device}: {temp}°C\n')
        else:
            self.temp_display.insert(tk.END, 'No temperature data available')

    def monitor_temperature(self):
        while self.sync_in_progress and not self.stop_sync:
            self.update_temperature_display()

            high_temp_reached = any(temp != 'N/A' and temp >= self.high_temp.get() for temp in self.device_temps.values())
            safe_temp_reached = all(temp == 'N/A' or temp <= self.safe_temp.get() for temp in self.device_temps.values())

            if high_temp_reached:
                print('Pausing sync, temperature too high')
                self.pause_sync()
            elif safe_temp_reached:
                print('Resuming sync, temperature back to safe level')
                self.resume_sync()
            time.sleep(30)  # Check temperature every 30 seconds

    def sync_process(self):
        while not self.stop_sync:
            sync_files(self.source_folder.get(), self.destination_folder.get())
            print('Sync completed')
            self.sync_in_progress = False
            break

    def start_sync(self):
        if self.sync_in_progress:
            messagebox.showwarning('Warning', 'Sync already in progress')
            return
        if not self.source_folder.get() or not self.destination_folder.get():
            messagebox.showerror('Error', 'Please select source and destination folders')
            return
        if not self.safe_temp.get() or not self.high_temp.get():
            messagebox.showerror('Error', 'Please set safe and high temperature limits')
            return
        self.sync_in_progress = True
        self.stop_sync = False
        self.sync_thread = threading.Thread(target=self.sync_process)
        self.sync_thread.start()
        threading.Thread(target=self.monitor_temperature).start()

    def pause_sync(self):
        self.sync_in_progress = False
        print('Sync paused')

    def resume_sync(self):
        self.sync_in_progress = True
        print('Sync resumed')

    def stop_sync_func(self):
        self.stop_sync = True
        self.sync_in_progress = False
        messagebox.showinfo('Info', 'Sync stopped by user')

if __name__ == '__main__':
    root = tk.Tk()
    app = CoolSyncApp(root)
    root.mainloop()
