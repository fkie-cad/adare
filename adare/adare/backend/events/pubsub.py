from collections import defaultdict
from collections.abc import Generator
from queue import Queue

cli_queues: dict[str, Queue] = defaultdict(Queue)
db_queues: dict[str, Queue] = defaultdict(Queue)

def publish_cli(ulid: str, message: dict) -> None:
    cli_queues[ulid].put(message)


def subscribe_cli(ulid: str) -> Generator[dict]:
    queue = cli_queues[ulid]
    while True:
        yield queue.get()

def publish_db(ulid: str, message: dict) -> None:
    db_queues[ulid].put(message)

def subscribe_db(ulid: str) -> Generator[dict]:
    queue = db_queues[ulid]
    while True:
        yield queue.get()

def publish(ulid: str, message: dict) -> None:
    publish_cli(ulid, message)
    publish_db(ulid, message)
