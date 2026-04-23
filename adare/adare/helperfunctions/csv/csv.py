import csv
import logging
from pathlib import Path

log = logging.getLogger(__name__)


def csv_to_dict(path: Path, delimiter=',', newline='\n', quotechar='"'):
    data = dict()
    with open(path.as_posix(), newline=newline) as f:
        reader = csv.reader(f, delimiter=delimiter, quotechar=quotechar)
        for row in reader:
            if len(row) != 2:
                log.warning(f'csv to dict ignores row {row} due to a length not equal 2')
            data[row[0]] = row[1]
    return data
