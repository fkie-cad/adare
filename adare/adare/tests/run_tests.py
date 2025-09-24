#!/usr/bin/env python3
"""
Test runner for ADARE global registry architecture.

This script runs the comprehensive test suite for the new multi-database architecture.
"""

import sys
import subprocess
from pathlib import Path

def main():
    """Run all tests."""
    test_dir = Path(__file__).parent

    print("🧪 Running ADARE Global Registry Architecture Tests")
    print("=" * 55)

    try:
        # Run pytest with coverage and detailed output
        cmd = [
            sys.executable, "-m", "pytest",
            str(test_dir),
            "-v",  # Verbose output
            "--tb=short",  # Short traceback format
            "--color=yes",  # Colored output
            # Add coverage if available
            # "--cov=adare.database",
            # "--cov-report=term-missing"
        ]

        result = subprocess.run(cmd, cwd=test_dir.parent)
        return result.returncode

    except FileNotFoundError:
        print("❌ pytest not found. Please install it with: pip install pytest")
        return 1
    except Exception as e:
        print(f"❌ Error running tests: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())