
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import asyncio
from adare.hypervisor.qemu.mixins.commands import CommandExecutionMixin

@pytest.fixture
def command_mixin():
    mixin = CommandExecutionMixin()
    mixin.guest_os = "ubuntu"
    mixin.username = "testuser"
    mixin.password = "password"
    mixin._cached_guest_path = "/usr/bin"
    return mixin

class TestCommandExecutionMixin:

    @pytest.mark.asyncio
    async def test_execute_streaming_command_async_success(self, command_mixin):
        args = ["echo", "hello"]
        
        # Mock process
        process = MagicMock()
        process.returncode = 0
        process.stdout.readline = AsyncMock(side_effect=[b"hello\n", b""])
        process.stderr.read = AsyncMock(return_value=b"")
        process.wait = AsyncMock()
        
        with patch('asyncio.create_subprocess_exec', return_value=process) as mock_exec:
            code, stdout, stderr = await command_mixin._execute_streaming_command_async(args)
            
            assert code == 0
            assert stdout.strip() == "hello"
            mock_exec.assert_called_once()

    def test_build_guest_command_args_linux(self, command_mixin):
        cmd = "ls -la"
        args = command_mixin._build_guest_command_args(cmd)
        
        assert len(args) == 3
        assert args[0] == '/bin/bash'
        assert args[1] == '-c'
        assert args[2] == "ls -la"

    def test_build_guest_command_args_linux_admin(self, command_mixin):
        cmd = "apt update"
        args = command_mixin._build_guest_command_args(cmd, admin=True)
        
        expected_cmd = 'sudo env "PATH=$PATH" "DISPLAY=$DISPLAY" "XAUTHORITY=$XAUTHORITY" bash -c \'apt update\''
        assert args[2] == expected_cmd

    def test_build_guest_command_args_windows(self, command_mixin):
        command_mixin.guest_os = "windows 11"
        cmd = "dir"
        args = command_mixin._build_guest_command_args(cmd)
        
        assert args[0] == "powershell.exe"
        assert args[1] == "-EncodedCommand"
        # We don't check the base64 content strictly unless we decode it, 
        # but asserting we got powershell encoded command is usually enough

    def test_build_guest_environment(self, command_mixin):
        env = command_mixin._build_guest_environment()
        
        env_dict = dict(s.split('=', 1) for s in env)
        assert env_dict['HOME'] == "/home/testuser"
        assert env_dict['USER'] == "testuser"
        assert "/usr/bin" in env_dict['PATH']
        assert env_dict['DISPLAY'] == ":0"

    def test_build_guest_environment_windows(self, command_mixin):
        command_mixin.guest_os = "windows 11"
        env = command_mixin._build_guest_environment()
        
        env_dict = dict(s.split('=', 1) for s in env)
        assert env_dict['HOME'] == "C:\\Users\\testuser"
        assert "C:\\Windows" in env_dict['PATH']
