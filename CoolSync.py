import os
import shutil
import sys
import logging
import hashlib
from collections import deque
from datetime import datetime
import time
from pySMART import Device
import threading
import tkinter as tk
# Add the settings imports here
try:
    from settings_local import DEFAULT_SRC_PATH, DEFAULT_DEST_PATH, DEFAULT_START_TEMP, DEFAULT_STOP_TEMP
except ImportError:
    from settings import DEFAULT_SRC_PATH, DEFAULT_DEST_PATH, DEFAULT_START_TEMP, DEFAULT_STOP_TEMP

# Configure logging
log_file = 'sync_log.log'
max_entries = 10
DEBUG = True

# Events to control temperature monitoring and pause/resume
monitoring_active = threading.Event()
sync_paused = threading.Event()

def write_log_entry(message):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"{timestamp} - {message}\n\n"
    if os.path.exists(log_file):
        with open(log_file, 'r') as file:
            lines = deque(file.readlines(), max_entries * 3)
    else:
        lines = deque(maxlen=max_entries * 3)
    lines.append(log_entry)
    with open(log_file, 'w') as file:
        file.writelines(lines)

def debug_print(message):
    if DEBUG:
        print(message)
    write_log_entry(message)

def get_drive_temperature(drive_path):
    device = Device(drive_path)
    temp = device.temperature
    return temp

def monitor_drive_temperature(drive_paths, start_temp, stop_temp, interval=60):
    while monitoring_active.is_set():
        all_below_start_temp = True
        any_above_stop_temp = False
        for drive in drive_paths:
            temp = get_drive_temperature(drive)
            debug_print(f"Drive {drive} temperature: {temp}°C")
            if temp >= stop_temp:
                any_above_stop_temp = True
            if temp > start_temp:
                all_below_start_temp = False
        if any_above_stop_temp:
            debug_print(f"Drive temperature is above {stop_temp}°C. Pausing sync...")
            while any(get_drive_temperature(drive) >= stop_temp for drive in drive_paths) and monitoring_active.is_set():
                debug_print("Waiting for drive to cool down... checking temperature in 60 seconds")
                time.sleep(60)  # Check every minute
            debug_print("Drive temperature is below threshold. Resuming sync...")
        if all_below_start_temp:
            debug_print(f"Drive temperature is below {start_temp}°C. Condition met, starting sync.")
            monitoring_active.clear()  # Stop monitoring before starting sync
            break
        time.sleep(interval)

def calculate_file_hash(file_path):
    hasher = hashlib.sha256()
    with open(file_path, 'rb') as f:
        buf = f.read()
        hasher.update(buf)
    return hasher.hexdigest()

def mirror_sync(src, dest, preview=False):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    changes_made = []
    for root, dirs, files in os.walk(src):
        dest_path = os.path.join(dest, os.path.relpath(root, src))
        os.makedirs(dest_path, exist_ok=True)
        for file in files:
            src_file = os.path.join(root, file)
            dest_file = os.path.join(dest_path, file)
            if os.path.exists(dest_file):
                src_size = os.path.getsize(src_file)
                dest_size = os.path.getsize(dest_file)
                if src_size == dest_size:
                    src_hash = calculate_file_hash(src_file)
                    dest_hash = calculate_file_hash(dest_file)
                    if src_hash == dest_hash:
                        debug_print(f"Skipped: {dest_file} (up-to-date)")
                        if preview:
                            print(f"Skipped: {dest_file} (up-to-date)")
                        continue
            while sync_paused.is_set():
                debug_print("Sync paused. Waiting to resume...")
                time.sleep(1)  # Check every second if sync is paused
            if preview:
                print(f"Would copy: {src_file} to {dest_file}")
                changes_made.append(f"Would copy: {src_file} to {dest_file}")
            else:
                shutil.copy2(src_file, dest_file)
                debug_print(f"Copied: {src_file} to {dest_file}")
                changes_made.append(f"Copied: {src_file} to {dest_file}")
    for root, dirs, files in os.walk(dest, topdown=False):
        for file in files:
            dest_file = os.path.join(root, file)
            src_file = os.path.join(src, os.path.relpath(dest_file, dest))
            if os.path.commonpath([dest_file, script_dir]) == script_dir:
                continue
            if not os.path.exists(src_file):
                while sync_paused.is_set():
                    debug_print("Sync paused. Waiting to resume...")
                    time.sleep(1)  # Check every second if sync is paused
                if preview:
                    print(f"Would delete: {dest_file}")
                    changes_made.append(f"Would delete: {dest_file}")
                else:
                    os.remove(dest_file)
                    debug_print(f"Deleted: {dest_file}")
                    changes_made.append(f"Deleted: {dest_file}")
    for root, dirs, files in os.walk(dest, topdown=False):
        for dir in dirs:
            dir_path = os.path.join(root, dir)
            if os.path.commonpath([dir_path, script_dir]) == script_dir:
                continue
            if not os.listdir(dir_path):
                while sync_paused.is_set():
                    debug_print("Sync paused. Waiting to resume...")
                    time.sleep(1)  # Check every second if sync is paused
                if preview:
                    print(f"Would remove empty directory: {dir_path}")
                    changes_made.append(f"Would remove empty directory: {dir_path}")
                else:
                    os.rmdir(dir_path)
                    debug_print(f"Removed empty directory: {dir_path}")
                    changes_made.append(f"Removed empty directory: {dir_path}")
    return changes_made

def start_monitoring(drive_paths, start_temp, stop_temp, interval=60):
    monitoring_active.set()
    temp_monitor_thread = threading.Thread(target=monitor_drive_temperature, args=(drive_paths, start_temp, stop_temp, interval))
    temp_monitor_thread.daemon = True
    temp_monitor_thread.start()
    temp_monitor_thread.join()  # Wait for the monitoring thread to finish before starting the sync

def stop_monitoring():
    monitoring_active.clear()

def browse_source():
    src_path.set(filedialog.askdirectory())

def browse_dest():
    dest_path.set(filedialog.askdirectory())

def stop_sync():
    stop_monitoring()
    sync_paused.clear()
    messagebox.showinfo("Sync Stopped", "The sync process has been stopped.")

def pause_resume_sync():
    if sync_paused.is_set():
        sync_paused.clear()
        messagebox.showinfo("Sync Resumed", "The sync process has been resumed.")
    else:
        sync_paused.set()
        messagebox.showinfo("Sync Paused", "The sync process has been paused.")

def run_sync():
    if not src_path.get() or not dest_path.get():
        messagebox.showerror("Error", "Please select both source and destination paths.")
        return

    try:
        start_temp = int(entry_start_temp.get())
        stop_temp = int(entry_stop_temp.get())
    except ValueError:
        messagebox.showerror("Error", "Please enter valid temperatures.")
        return

    preview_mode = messagebox.askyesno("Preview Mode", "Do you want to run in preview mode?")
    drive_paths = [src_path.get()[:2], dest_path.get()[:2]]

    start_monitoring(drive_paths, start_temp, stop_temp, 60)

    changes = mirror_sync(src_path.get(), dest_path.get(), preview_mode)
    if preview_mode:
        messagebox.showinfo("Preview Mode", "Preview sync completed successfully!")
    else:
        messagebox.showinfo("Sync Complete", "Actual sync completed successfully!")

    stop_monitoring()

    if changes:
        changes_str = "\n".join(changes)
        messagebox.showinfo("Changes Made", f"Changes made during the sync:\n{changes_str}")
    else:
        messagebox.showinfo("No Changes", "No changes were made during the sync.")

# GUI Setup
root = tk.Tk()
root.title("CoolSync")

src_path = tk.StringVar(value=DEFAULT_SRC_PATH)
dest_path = tk.StringVar(value=DEFAULT_DEST_PATH)

frame = tk.Frame(root, padx=10, pady=10)
frame.pack(padx=10, pady=10)

lbl_src = tk.Label(frame, text="Source Path:")
lbl_src.grid(row=0, column=0, sticky=tk.W)
entry_src = tk.Entry(frame, textvariable=src_path, width=50)
entry_src.grid(row=0, column=1)
btn_src = tk.Button(frame, text="Browse", command=browse_source)
btn_src.grid(row=0, column=2)

lbl_dest = tk.Label(frame, text="Destination Path:")
lbl_dest.grid(row=1, column=0, sticky=tk.W)
entry_dest = tk.Entry(frame, textvariable=dest_path, width=50)
entry_dest.grid(row=1, column=1)
btn_dest = tk.Button(frame, text="Browse", command=browse_dest)
btn_dest.grid(row=1, column=2)

lbl_start_temp = tk.Label(frame, text="Start Sync Temperature (°C):")
lbl_start_temp.grid(row=2, column=0, sticky=tk.W)
entry_start_temp = tk.Entry(frame)
entry_start_temp.insert(0, DEFAULT_START_TEMP)  # Use the default start temp
entry_start_temp.grid(row=2, column=1)

lbl_stop_temp = tk.Label(frame, text="Stop Sync Temperature (°C):")
lbl_stop_temp.grid(row=3, column=0, sticky=tk.W)
entry_stop_temp = tk.Entry(frame)
entry_stop_temp.insert(0, DEFAULT_STOP_TEMP)  # Use the default stop temp
entry_stop_temp.grid(row=3, column=1)

btn_start = tk.Button(frame, text="Start", command=run_sync)
btn_start.grid(row=4, column=0)

btn_pause = tk.Button(frame, text="Pause/Resume", command=pause_resume_sync)
btn_pause.grid(row=4, column=1)

btn_stop = tk.Button(frame, text="Stop", command=stop_sync)
btn_stop.grid(row=4, column=2)

root.mainloop()
