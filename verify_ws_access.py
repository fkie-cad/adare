import asyncio
import websockets
import sys
import json

async def check_connection(host, port):
    uri = f"ws://{host}:{port}"
    print(f"Attempting to connect to {uri}...", end=" ", flush=True)
    try:
        async with websockets.connect(uri, ping_interval=None) as websocket:
            print("SUCCESS!")
            # Wait for welcome message
            try:
                message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                data = json.loads(message)
                if data.get('type') == 'log' and 'message' in data.get('data', {}):
                    print(f"Server says: {data['data']['message']}")
                else:
                    print(f"Received: {message[:100]}...")
            except asyncio.TimeoutError:
                print("Connected, but timed out waiting for welcome message.")
            except Exception as e:
                print(f"Error reading message: {e}")
            return True
    except ConnectionRefusedError:
        print("Connection refused.")
        return False
    except Exception as e:
        print(f"Failed: {type(e).__name__}: {e}")
        return False

async def main():
    host = "localhost"
    # Default port range defined in port_manager.py
    start_port = 18765
    end_port = 18799
    
    print(f"Checking connectivity to adarevm on {host}...")
    
    # Try ports
    found = False
    for port in range(start_port, end_port + 1):
        if await check_connection(host, port):
            found = True
            print(f"\n[+] Successfully verified connection to adarevm on port {port}")
            break
            
    if not found:
        print("\n[-] Could not connect to any standard adarevm ports.")
        print("Reasons might be:")
        print("1. The VM is not running.")
        print("2. The adarevm service inside the VM is not started.")
        print("3. Port forwarding is not configured correctly.")
        print("4. Firewall is blocking the connection.")
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nAborted.")
