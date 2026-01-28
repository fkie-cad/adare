
import sys
import os
print(f"sys.path: {sys.path}")
try:
    import adare
    print(f"adare: {adare}")
    print(f"adare path: {adare.__path__}")
except ImportError as e:
    print(f"Failed to import adare: {e}")

try:
    import adare.backend
    print(f"adare.backend: {adare.backend}")
except ImportError as e:
    print(f"Failed to import adare.backend: {e}")

try:
    from adare.backend.experiment.execution.simple_actions import SimpleActionsExecutor
    print("SUCCESS")
except ImportError as e:
    print(f"Failed to import SimpleActionsExecutor: {e}")
