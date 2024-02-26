# external imports
from datetime import datetime, timedelta, timezone
import pandas as pd
import attrs
from pathlib import Path
import datefinder
import csv
import re
from typing import ClassVar, Optional

# internal imports
from adarevm.testset.basictest import BasicTest, Parameter
from adarevm.testset.teststatus import TestStatus, TestSuccess, TestError, TestFailed, TestMissingKey, TestSyntaxError
import adarelib.helperfunctions as helper
from adarevm.event import TestEnd
import adarelib.customyaml.customtags as yml
from adarevm import VARIABLES

# configure logging
import logging

log = logging.getLogger(__name__)


@attrs.define
class FileExistsParameter(Parameter):
    dst: str


@attrs.define
class FileExists(BasicTest):
    testname: ClassVar[str] = 'file_exists'
    testdescription: ClassVar[str] = 'tests if a file with path destination(dst) is existing'

    name: str
    params: FileExistsParameter
    description: Optional[str] = ''

    def test(self):
        if Path(self.params.dst).is_file():
            event = TestEnd(
                test_name=self.name,
                status=TestSuccess()
            )
        else:
            event = TestEnd(
                test_name=self.name,
                status=TestFailed(),
                details=[f'file with path {self.params.dst} does not exist']
            )
        self.eventsystem.log(event)


