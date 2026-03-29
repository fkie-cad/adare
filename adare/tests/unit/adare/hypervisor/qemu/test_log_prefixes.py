from pathlib import Path


def test_no_claude_log_prefixes():
    """Regression test: no CLAUDE: prefixes in log messages."""
    hypervisor_dir = Path(__file__).parents[5] / 'adare' / 'hypervisor'
    violations = []
    for py_file in hypervisor_dir.rglob('*.py'):
        content = py_file.read_text()
        for i, line in enumerate(content.splitlines(), 1):
            if 'CLAUDE:' in line and not line.strip().startswith('#'):
                violations.append(f"{py_file.relative_to(hypervisor_dir)}:{i}: {line.strip()}")
    assert not violations, f"Found CLAUDE: prefixes:\n" + "\n".join(violations)
