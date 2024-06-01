from adarelib.types.experiment import Stage, SetupStage, BootStage, InstallStage, MountStage, ExperimentStage, DumpStage, TeardownStage, CleanupStage


class StageManager:
    stages: list[Stage]

    def __init__(self):
        self.stages = []

    def _search_stage(self, stage: Stage):
        pass


    def add_stage(self, stage: Stage, parent: Stage = None):
        if parent is not None:
            # search for the parent stage recursively in substages of each stage
            pass

