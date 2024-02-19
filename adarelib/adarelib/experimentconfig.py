import attrs


@attrs.define
class ExperimentConfig:
    experiment: str

    testset: str
    action: str
    testfunction_directory: str

    tessdata: str
    img: str

    logfile: str
    eventfile: str
    statusfile: str
