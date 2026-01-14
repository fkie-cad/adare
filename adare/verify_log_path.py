import asyncio
import threading
from pathlib import Path
from adare.backend.experiment.agent_command_builders import WindowsAgentCommandBuilder, EnvironmentInfo

async def verify():
    print("Verifying Windows Agent Command Builder...")
    
    # Mock data
    wheels_dir = Path("/tmp/wheels") # Assumed to not exist for this test, or we can mock exists
    # To test wheels_available=True paths, we might need to mock Path.exists/glob or create a temp dir
    
    # Case 1: QEMU, Conda, Wheels available
    builder_qemu = WindowsAgentCommandBuilder(
        wheels_dir=wheels_dir,
        shared_folders={},
        websocket_port=8080,
        hypervisor_type='qemu'
    )
    # Mock wheels available
    builder_qemu.wheels_available = True
    
    env_conda = EnvironmentInfo(
        use_conda=True,
        conda_env_exists=True,
        miniforge_path=r'%USERPROFILE%\.miniforge3',
        platform='windows'
    )
    
    cmd, cwd = builder_qemu.build_run_command(env_conda)
    print(f"\n[QEMU, Conda, Wheels] Command: {cmd}")
    
    # Case 2: QEMU, Non-Conda, Wheels (System Python)
    env_system = EnvironmentInfo(
        use_conda=False,
        conda_env_exists=False,
        miniforge_path=None,
        platform='windows'
    )
    # Mock python path resolution
    class MockVM:
        _cached_guest_path = r"C:\Windows\System32;C:\Users\User\AppData\Local\Programs\Python\Python312"
    
    cmd, cwd = builder_qemu.build_run_command(env_system, vm=MockVM())
    print(f"\n[QEMU, System, Wheels] Command: {cmd}")
    
    # Case 3: VirtualBox, Conda, No Wheels (Editable)
    builder_vbox = WindowsAgentCommandBuilder(
        wheels_dir=wheels_dir,
        shared_folders={},
        websocket_port=8080,
        hypervisor_type='virtualbox'
    )
    builder_vbox.wheels_available = False
    
    cmd, cwd = builder_vbox.build_run_command(env_conda)
    print(f"\n[VBox, Conda, Editable] Command: {cmd}")

if __name__ == "__main__":
    asyncio.run(verify())
