from adare.breakpoint import BreakPoint
import attrs


@attrs.define
class ExperimentConfig:
    experiment: str

    testset: str
    action: str
    testfunction_directory: str

    breakpoint_directory: str
    tessdata: str
    img: str
    breakpoints: list[BreakPoint]

    logfile: str
    eventfile: str
    statusfile: str


@attrs.define
class RecordConfig:
    directory: str
    logfile: str
    start_stop_key_combination: list[str]

