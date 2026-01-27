
import pytest
from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path
from adare.validators.vm_validators import (
    VMValidatorFactory, 
    VirtualBoxValidator, 
    QEMUValidator, 
    VMValidationError
)

class TestVirtualBoxValidator:
    def test_get_supported_extensions(self):
        validator = VirtualBoxValidator()
        assert validator.get_supported_extensions() == ['.ova']

    @patch('adare.validators.vm_validators.validate_tarfile_with_progress')
    def test_validate_file_success(self, mock_validate_tar, tmp_path):
        # Create a dummy file
        ova_file = tmp_path / "test.ova"
        ova_file.touch()
        
        # Mock successful tar validation
        mock_validate_tar.return_value = True
        
        validator = VirtualBoxValidator()
        # Should not raise exception
        validator.validate_file(ova_file, "TestVM")
        
        mock_validate_tar.assert_called_once()

    @patch('adare.validators.vm_validators.validate_tarfile_with_progress')
    def test_validate_file_invalid_tar(self, mock_validate_tar, tmp_path):
        ova_file = tmp_path / "test.ova"
        ova_file.touch()
        
        # Mock failed tar validation
        mock_validate_tar.return_value = False
        
        validator = VirtualBoxValidator()
        with pytest.raises(VMValidationError) as excinfo:
            validator.validate_file(ova_file, "TestVM")
        
        assert "not a valid OVA" in str(excinfo.value)

    def test_validate_file_not_exist(self):
        validator = VirtualBoxValidator()
        with pytest.raises(VMValidationError) as excinfo:
            validator.validate_file(Path("/non/existent/file.ova"), "TestVM")
        assert "does not exist" in str(excinfo.value)

    def test_validate_file_not_a_file(self, tmp_path):
        # Create a directory instead of a file
        directory = tmp_path / "dir.ova"
        directory.mkdir()
        
        validator = VirtualBoxValidator()
        with pytest.raises(VMValidationError) as excinfo:
            validator.validate_file(directory, "TestVM")
        assert "not a regular file" in str(excinfo.value)


class TestQEMUValidator:
    def test_get_supported_extensions(self):
        validator = QEMUValidator()
        expected = ['.qcow2', '.img', '.raw', '.vmdk', '.vdi']
        assert set(validator.get_supported_extensions()) == set(expected)

    def test_validate_file_generic_success(self, tmp_path):
        img_file = tmp_path / "test.img"
        img_file.touch()
        
        validator = QEMUValidator()
        validator.validate_file(img_file, "TestVM")

    def test_validate_qcow2_magic_success(self, tmp_path):
        qcow2_file = tmp_path / "test.qcow2"
        # Write valid magic bytes QFI\xfb
        with open(qcow2_file, 'wb') as f:
            f.write(b'QFI\xfb')
            
        validator = QEMUValidator()
        validator.validate_file(qcow2_file, "TestVM")

    def test_validate_qcow2_magic_invalid(self, tmp_path, caplog):
        qcow2_file = tmp_path / "test.qcow2"
        # Write invalid magic bytes
        with open(qcow2_file, 'wb') as f:
            f.write(b'ABCD')
            
        validator = QEMUValidator()
        # Should just log a warning, not raise exception
        import logging
        with caplog.at_level(logging.WARNING):
            validator.validate_file(qcow2_file, "TestVM")
        
        assert "does not have valid qcow2 magic bytes" in caplog.text

    def test_validate_file_read_error(self, tmp_path):
        qcow2_file = tmp_path / "test.qcow2"
        qcow2_file.touch()
        
        validator = QEMUValidator()
        
        # Mock open to raise IOError
        with patch("builtins.open", mock_open()) as mock_file:
            mock_file.side_effect = IOError("Read error")
            
            with pytest.raises(VMValidationError) as excinfo:
                validator.validate_file(qcow2_file, "TestVM")
            
            assert "Cannot read VM file" in str(excinfo.value)


class TestVMValidatorFactory:
    def test_get_validator_vbox(self):
        validator = VMValidatorFactory.get_validator('virtualbox')
        assert isinstance(validator, VirtualBoxValidator)

    def test_get_validator_qemu(self):
        validator = VMValidatorFactory.get_validator('qemu')
        assert isinstance(validator, QEMUValidator)

    def test_get_validator_unknown(self):
        # Should return VirtualBoxValidator by default
        validator = VMValidatorFactory.get_validator('unknown_hypervisor')
        assert isinstance(validator, VirtualBoxValidator)
