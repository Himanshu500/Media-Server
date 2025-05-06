import socket
import netifaces
import logging
import shutil
import os
from typing import List # Kept if other utils might need it, but not for get_local_ip

logger = logging.getLogger(__name__)

def find_free_port(start_port=5000, max_attempts=100):
    """
    Find a free port on the system starting from start_port
    
    Args:
        start_port (int): The port to start checking from
        max_attempts (int): Maximum number of ports to check
        
    Returns:
        int: A free port number, or None if no free port found
    """
    port = start_port
    attempts = 0
    
    while attempts < max_attempts:
        try:
            # Try to create a socket and bind it to the port
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(('', port))
            sock.close()
            return port
        except OSError:
            # Port is not available, try the next one
            port += 1
            attempts += 1
    
    # No free port found
    logger.error("No free port found after %d attempts", max_attempts)
    return None

def get_local_ip_addresses():
    """
    Get the local IP addresses of the machine
    
    Returns:
        list: List of IP addresses as strings
    """
    ip_addresses = []
    
    try:
        # Get all network interfaces
        interfaces = netifaces.interfaces()
        
        for interface in interfaces:
            # Skip loopback interface
            if interface.startswith('lo'):
                continue
            
            # Get interface addresses
            addrs = netifaces.ifaddresses(interface)
            
            # Check for IPv4 addresses
            if netifaces.AF_INET in addrs:
                for addr in addrs[netifaces.AF_INET]:
                    ip = addr['addr']
                    # Skip localhost and empty addresses
                    if ip != '127.0.0.1' and ip != '':
                        ip_addresses.append(ip)
    except Exception as e:
        logger.error("Error getting IP addresses: %s", str(e))
    
    return ip_addresses

def format_file_size(size_bytes):
    """
    Format a file size in bytes to a human-readable string
    
    Args:
        size_bytes (int): File size in bytes
        
    Returns:
        str: Formatted file size with units
    """
    # Define units and thresholds
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    
    # Handle zero size
    if size_bytes == 0:
        return "0B"
    
    # Calculate the appropriate unit
    size_index = 0
    size_value = float(size_bytes)
    
    while size_value >= 1024 and size_index < len(units) - 1:
        size_value /= 1024
        size_index += 1
    
    # Format with appropriate precision
    if size_index == 0:  # Bytes
        return f"{int(size_value)} {units[size_index]}"
    else:
        return f"{size_value:.2f} {units[size_index]}"

def get_local_ip() -> str:
    """Gets the primary local IP address of the machine.
    Connects to an external address to determine the socket's bound IP.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0.1) # Prevent long hang if network is down/misconfigured
    try:
        # Doesn't even have to be reachable, just initiates a socket with an outbound interface
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        # Fallback if connection fails (e.g., no network, firewall)
        try:
            # Try getting hostname and then IP from hostname
            # This might return 127.0.0.1 if not configured properly
            hostname = socket.gethostname()
            IP = socket.gethostbyname(hostname)
            if IP == '127.0.0.1' or IP.startswith('127.'): # Check if it's a loopback address
                 # Try another common method for local IP if loopback is found
                 # This is more platform-dependent and might require netifaces for robustness
                 # For simplicity without adding new deps, we'll stick to a simpler fallback or a prominent loopback.
                 # Consider if '0.0.0.0' is more appropriate for server binding in some contexts.
                 pass # Keep IP as 127.0.0.1 or hostname-derived if it's all we got
        except Exception:
            IP = '127.0.0.1' # Final fallback
    finally:
        s.close()
    return IP

# Placeholder for other potential utility functions:
# def find_free_port(start_port: int, host: str = '127.0.0.1', max_attempts: int = 100) -> Optional[int]:
#     """Finds an available TCP port starting from start_port."""
#     for i in range(max_attempts):
#         port = start_port + i
#         try:
#             with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
#                 s.bind((host, port))
#                 return port  # Port is available
#         except OSError:
#             continue  # Port is in use, try next
#     return None 