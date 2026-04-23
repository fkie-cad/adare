"""
Input parsing helpers for DevMode service.

These are standalone module-level functions that parse actions and playbooks
from various sources (files, YAML strings, stdin, URLs).
"""

import sys
from pathlib import Path

import yaml

from adare.types.playbook import _structure_action, parse_playbook


def parse_action_from_file(file_path: str):
    """Parse single action from YAML file."""
    with open(file_path) as f:
        yaml_content = f.read()
    return parse_action_from_yaml(yaml_content)


def parse_action_from_yaml(yaml_content: str):
    """Parse single action from YAML string."""
    action_dict = yaml.safe_load(yaml_content)
    return _structure_action(action_dict)


def parse_action_from_stdin():
    """Read and parse action from stdin."""
    yaml_content = sys.stdin.read()
    return parse_action_from_yaml(yaml_content)


def parse_playbook_from_file(file_path: str):
    """Parse playbook from file."""
    return parse_playbook(Path(file_path))


def fetch_playbook_from_url(url: str):
    """Fetch and parse playbook from URL."""
    try:
        import httpx
        response = httpx.get(url, timeout=30, follow_redirects=True)
        response.raise_for_status()

        # Write to temp file and parse
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            f.write(response.text)
            temp_path = f.name

        playbook = parse_playbook(Path(temp_path))

        # Clean up temp file
        Path(temp_path).unlink()

        return playbook
    except ImportError:
        raise RuntimeError("httpx package required for URL fetching. Install with: pip install httpx")
    except (OSError, yaml.YAMLError, ValueError) as e:
        raise RuntimeError(f"Failed to fetch playbook from URL: {str(e)}")


def parse_playbook_from_stdin():
    """Read and parse playbook from stdin."""
    import tempfile

    # Read stdin content
    yaml_content = sys.stdin.read()

    # Write to temp file and parse
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        f.write(yaml_content)
        temp_path = f.name

    playbook = parse_playbook(Path(temp_path))

    # Clean up temp file
    Path(temp_path).unlink()

    return playbook
