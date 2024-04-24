from pathlib import Path

from adarelib.types import EventSystemData
import cattrs
import yaml

file = Path('/home/miq/Documents/adare/TestProjects/Tproj1/run/deletetest/2024-04-24_12-56-58/events.yml')


def main():
    # load yaml file
    with open(file, 'r') as stream:
        data = yaml.safe_load(stream)

    # convert to EventSystemData
    eventssystemdata = EventSystemData.from_dict(data)
    print(eventssystemdata)