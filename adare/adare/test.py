from pathlib import Path

from adarelib.types import EventSystemData
import cattrs
import yaml

file = Path('/home/miq/Documents/adare/TestProjects/Tproj/run/deletefile/2024-03-28_15-37-05/events.yml')


def main():
    # load yaml file
    with open(file, 'r') as stream:
        data = yaml.safe_load(stream)

    # convert to EventSystemData
    event_system_data = cattrs.structure(data, EventSystemData)
    print(event_system_data)
