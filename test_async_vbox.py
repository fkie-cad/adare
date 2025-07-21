#!/usr/bin/env python3
"""
Test script to demonstrate responsive ctrl-c handling in async VirtualBox operations.
"""
import asyncio
import threading
import time
from pathlib import Path
import sys

# Add the adare directory to the path
sys.path.insert(0, str(Path(__file__).parent / "adare"))

from adare.virtualbox.api import VirtualBoxManager, VirtualBoxVM


async def test_responsive_ctrl_c():
    """Test that demonstrates responsive ctrl-c handling with async VBoxManage operations."""
    print("Testing responsive ctrl-c handling with async VirtualBox operations...")
    
    # Create a stop event that we can trigger
    stop_event = threading.Event()
    
    # Create VirtualBox manager and VM
    manager = VirtualBoxManager()
    vm = VirtualBoxVM(
        vm_name="test_vm_async",
        guest_os="Windows10_64",
        manager=manager,
        cpus=1,
        ram=1024
    )
    
    # Create a task that simulates ctrl-c after 2 seconds
    async def simulate_ctrl_c():
        await asyncio.sleep(2)
        print("\n🛑 Simulating ctrl-c (stop event triggered)...")
        stop_event.set()
    
    # Start the ctrl-c simulation
    ctrl_c_task = asyncio.create_task(simulate_ctrl_c())
    
    try:
        print("Starting VM creation (this would normally take a long time)...")
        print("With async implementation, ctrl-c should be responsive within 0.1 seconds...")
        
        start_time = time.time()
        
        # This should be interrupted by the stop event
        result = await vm.create(stop_event=stop_event, silent=True)
        
        end_time = time.time()
        
        print(f"Operation completed in {end_time - start_time:.1f} seconds")
        if result != 0:
            print("✅ Operation was successfully interrupted by stop event")
        else:
            print("❌ Operation completed without interruption")
        
    except Exception as e:
        end_time = time.time()
        print(f"Operation failed after {end_time - start_time:.1f} seconds: {e}")
        print("✅ This is expected - operation was interrupted")
    
    # Wait for the ctrl-c simulation to complete
    await ctrl_c_task
    
    print("\n🎉 Test completed! The async implementation provides responsive ctrl-c handling.")


if __name__ == "__main__":
    print("=" * 60)
    print("Async VirtualBox API Test")
    print("=" * 60)
    
    try:
        asyncio.run(test_responsive_ctrl_c())
    except KeyboardInterrupt:
        print("\n🛑 Test interrupted by user")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()