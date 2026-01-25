
import pandas as pd
from rich.console import Console
from rich.layout import Layout
from adare.frontend.terminal.dev_session_list import DevSessionTablePanel

def verify_table():
    # Mock data that mimics what adare/cli/dev.py produces
    data = [
        {
            'session_id': '01HQ123456789ABCDEF0123456',
            'experiment_name': 'test_experiment',
            'environment_name': 'ubuntu24',
            'vm_running': True,
            'actions_executed': 5,
            'created_at': '2023-10-27 10:00:00',
            'status': 'running',
        },
        {
            'session_id': '01HQ987654321ABCDEF0654321',
            'experiment_name': 'another_exp',
            'environment_name': 'windows11',
            'vm_running': False,
            'actions_executed': 12,
            'created_at': '2023-10-26 15:30:00',
            'status': 'stopped',
        },
        {
            'session_id': '01HQ111111111ABCDEF0111111',
            'experiment_name': 'crashed_run',
            'environment_name': 'debian12',
            'vm_running': True, # Inconsistent state example
            'actions_executed': 0,
            'created_at': '2023-10-25 09:15:00',
            'status': 'crashed',
        }
    ]

    df = pd.DataFrame(data)

    console = Console()
    layout = Layout(name="root")
    panel = DevSessionTablePanel(df)
    layout.update(panel)
    console.print(layout)

if __name__ == "__main__":
    verify_table()
