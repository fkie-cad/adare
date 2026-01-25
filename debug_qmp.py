
import socket
import json
import time

SOCK_PATH = "/home/miq/.adare/qemu/run/Win11QemuAutopy2_exp_01KFTWK4.qmp"
DUMP_PATH = "/tmp/debug_screendump.ppm"

def send(sock, cmd):
    print(f"Sending: {cmd}")
    sock.sendall(json.dumps(cmd).encode() + b"\n")
    
def recv(sock):
    data = sock.recv(4096).decode()
    print(f"Received: {data}")
    return data

try:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(SOCK_PATH)
    
    # Read greeting
    recv(s)
    
    # Handshake
    send(s, {"execute": "qmp_capabilities"})
    recv(s)
    
    # Screendump
    print(f"Attempting screendump to {DUMP_PATH}")
    send(s, {"execute": "screendump", "arguments": {"filename": DUMP_PATH}})
    recv(s)
    
    s.close()
    
except Exception as e:
    print(f"Error: {e}")
