import threading
import tkinter as tk
from tkinter import filedialog

# Your existing code...

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
        # Your create_widgets code here...

        # Start/Stop Sync buttons
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

    def start_sync(self):
        if not self.sync_in_progress:
            self.sync_in_progress = True
            self.stop_event.clear()
            self.queue.put(self.safe_temp.get())
            self.queue.put(self.high_temp.get())
            # Make sure sync_thread is correctly defined and started
            self.sync_thread = threading.Thread(target=sync_files, args=(self.source_folder.get(), self.destination_folder.get(), self.stop_event, self, self.queue))
            self.sync_thread.start()
            self.update_status("Sync started")

    def stop_sync(self):
        self.stop_event.set()
        self.update_status("Sync stopped by user")

    def update_temperature_display(self):
        self.temp_display.configure(state='normal')
        self.temp_display.delete(1.0, tk.END)
        temperatures = get_specific_device_temperatures()
        for device, temp in temperatures.items():
            self.temp_display.insert(tk.END, f"{device}: {temp}°C\n")
        self.temp_display.configure(state='disabled')
        self.root.after(60000, self.update_temperature_display)  # Update every 60 seconds

    def browse_source(self):
        folder_selected = filedialog.askdirectory()
        self.source_folder.set(folder_selected)

    def browse_destination(self):
        folder_selected = filedialog.askdirectory()
        self.destination_folder.set(folder_selected)

    def on_closing(self):
        if self.sync_in_progress:
            self.stop_sync()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = CoolSyncBackup(root)
    root.mainloop()
