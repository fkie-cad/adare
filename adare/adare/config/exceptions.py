from adare import exception_baseclasses


class ConfigDirectoryError(exception_baseclasses.LoggedException):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)
