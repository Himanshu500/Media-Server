#!/usr/bin/env python3
"""
Video Streaming Server - CLI Interactive Launcher
-------------------------------------------------
Prompts user for port and video file, then starts the server
and displays a QR code for the stream's M3U playlist.
"""

import os
import sys
import logging
import re # Added for natural sorting
# import signal # signal_handler is defined but not used if server.stop_server() is not implemented
# import time
import qrcode # For QR code generation
import utils # Ensures utils is imported
import server
import tkinter as tk
from tkinter import filedialog
import socket # socket is used by prompt_for_port and was used by old get_local_ip
from typing import List, Dict, Any, Optional

# --- Configuration ---
DEFAULT_PORT = 5000

# Configure logging (optional, can be simplified if debug arg removed)
logging.basicConfig(level=logging.INFO, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Define common video extensions
VIDEO_EXTENSIONS = ('.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.webm')

# --- Natural Sort Helper ---
def natural_sort_key(s: str, _nsre=re.compile(r'([0-9]+)')) -> List[Any]:
    """Key for natural sorting (handles numbers in strings properly)."""
    return [int(text) if text.isdigit() else text.lower() for text in _nsre.split(s)]

# --- Functions ---

# Removed local get_local_ip() definition, will use utils.get_local_ip()

# def signal_handler(sig, frame):
# """Handle Ctrl+C and other termination signals"""
#     print("\nShutting down server...")
# server.stop_server() # Attempt graceful shutdown. server.stop_server() needs to be implemented
# sys.exit(0)

def prompt_for_port() -> int:
    """Asks the user for a port number."""
    default_port = 5000
    while True:
        try:
            port_str = input(f"Enter port number (default: {default_port}, range 1024-65535): ")
            if not port_str:
                port = default_port
                print(f"Using default port: {port}")
                return port
            port = int(port_str)
            if 1024 <= port <= 65535:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    if s.connect_ex(('localhost', port)) == 0:
                        print(f"Port {port} is already in use. Please choose another.")
                    else:
                        return port
            else:
                print("Port out of valid range (1024-65535).")
        except ValueError:
            print("Invalid input. Please enter a number.")
        except Exception as e:
            print(f"An error occurred: {e}")

def select_video_directory() -> Optional[str]:
    """Opens a dialog to select a directory and returns its absolute path."""
    root = tk.Tk()
    root.withdraw()  # Hide the main Tkinter window
    directory_path = filedialog.askdirectory(title="Select Directory Containing Video Files")
    root.destroy() # Destroy the Tk window after selection
    if directory_path:
        print(f"Selected directory: {directory_path}")
        return os.path.abspath(directory_path)
    else:
        print("No directory selected.")
        return None

def scan_directory_for_videos(directory_path: str) -> List[Dict[str, str]]:
    """Scans the given directory for video files and returns a list of dictionaries."""
    video_files = []
    if not os.path.isdir(directory_path):
        print(f"Error: {directory_path} is not a valid directory.")
        return video_files

    print(f"Scanning for videos in: {directory_path}...")
    temp_video_list = []
    for item in os.listdir(directory_path):
        item_path = os.path.join(directory_path, item)
        if os.path.isfile(item_path):
            _ , ext_part = os.path.splitext(item)
            ext_lower = ext_part.lower()
            if ext_lower in VIDEO_EXTENSIONS:
                temp_video_list.append({
                    "filename": item, 
                    "path": os.path.abspath(item_path)
                })
    
    # Sort the collected video files naturally by filename
    # The key for sorting is a dictionary's 'filename' value
    video_files = sorted(temp_video_list, key=lambda x: natural_sort_key(x['filename']))

    if video_files:
        print(f"Found and sorted {len(video_files)} video file(s):")
        for video in video_files: # Print sorted list for confirmation
            print(f"  - {video['filename']}")
    else:
        print("No video files found with extensions:", VIDEO_EXTENSIONS)
    return video_files

def display_qr_code_for_web_interface(port: int) -> None:
    """Displays QR code for the web interface URL."""
    local_ip = utils.get_local_ip() # Changed to use utils.get_local_ip()
    web_interface_url = f"http://{local_ip}:{port}/"

    print("\n" + "="*50)
    print("        VIDEO STREAM SERVER - WEB INTERFACE")
    print("="*50)
    print(f"Access the web interface at: {web_interface_url}")
    print("Scan the QR code below with your phone/tablet to open the web interface:")

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(web_interface_url)
    qr.make(fit=True)
    
    # Print QR code to terminal
    # The 'invert' argument was removed as it caused issues.
    # If your terminal has a light background, this might be hard to scan.
    # Consider using a QR code app that can invert colors if needed.
    try:
        qr.print_tty()
    except Exception as e:
        print(f"Could not print QR code to terminal: {e}")
        print("You can still access the web interface using the URL above.")
    print("="*50 + "\n")

def main() -> None:
    """Main function to run the CLI application."""
    # signal.signal(signal.SIGINT, signal_handler) # Commented out as server.stop_server() needs review

    print("Starting Video Stream Server Setup...")
    selected_port = prompt_for_port()
    video_directory = select_video_directory()
    if not video_directory:
        print("No video directory selected. Exiting.")
        return

    video_files_list = scan_directory_for_videos(video_directory)
    if not video_files_list:
        print("No video files found in the selected directory. Exiting.")
        return

    # For server.py, video_info_cache might be populated directly in server.py
    # based on the list of files. Or server.py is adapted to handle a list.
    # We are passing the list of video dicts.
    
    print(f"\nAttempting to start server on port {selected_port} with {len(video_files_list)} videos...")
    
    try:
        # Modify how server is started to pass the list of videos
        # server.start_server will need to be adapted to accept this list
        server.init_server_state(video_files=video_files_list) # New function to set up video list
        
        display_qr_code_for_web_interface(selected_port)
        
        # Use utils.get_local_ip() for the informational print message
        print(f"Server starting on http://{utils.get_local_ip()}:{selected_port}")
        print("Press Ctrl+C to stop the server.")
        
        # Changed debug to False as a general good practice for "release"
        server.app.run(host='0.0.0.0', port=selected_port, threaded=True, debug=False) 
        
    except OSError as e:
        if e.errno == 98: # Address already in use
            print(f"ERROR: Port {selected_port} is already in use. Please try a different port.")
        else:
            print(f"An OS error occurred: {e}")
    except Exception as e:
        print(f"Failed to start server: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main() 