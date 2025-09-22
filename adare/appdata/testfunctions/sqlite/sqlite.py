# external imports
import attrs
import sqlite3
from pathlib import Path
from typing import ClassVar, Optional, List

# internal imports
from adarelib.testset.basictest import BasicTest, Parameter
from adarelib.event.event import TestResult

# configure logging
import logging
log = logging.getLogger(__name__)


@attrs.define
class QueryResultParameter(Parameter):
    dst: str
    query: str
    expected_rows: Optional[int] = None
    expected_result: Optional[list] = None

@attrs.define
class QueryResult(BasicTest):
    testname: ClassVar[str] = 'query_result'
    testdescription: ClassVar[str] = 'executes SQL query against SQLite database and validates result'

    name: str
    parameter: QueryResultParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def test(self):
        try:
            dst, status = self.resolve_globfilepath(self.parameter.dst)
            if not dst:
                return TestResult.error([f'database file {self.parameter.dst} can\'t be used, because no unambiguous file could be identified (because {status})'])

            log.debug(f'dst database {dst} will be used for test {self.name}')

            query = self.parameter.query
            expected_result = self.parameter.expected_result

            try:
                conn = sqlite3.connect(dst)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                cursor.execute(query)
                rows = cursor.fetchall()

                # Convert to list of dicts for easier comparison
                result = [dict(row) for row in rows]

                conn.close()

                # Check expected row count
                if self.parameter.expected_rows is not None:
                    if len(result) != self.parameter.expected_rows:
                        return TestResult.failed([f'expected {self.parameter.expected_rows} rows, got {len(result)}'])

                # Check expected result content
                if expected_result is not None:
                    # Check if expected_result has placeholders
                    expected_str = str(expected_result)
                    if self.has_placeholders(expected_str):
                        # For complex result comparison with placeholders, convert to string and use placeholder system
                        try:
                            success, message = self._handle_placeholders_comparison(str(result), expected_str)
                            if not success:
                                return TestResult.failed([f'query result placeholder comparison failed: {message}'])
                        except Exception as e:
                            return TestResult.execution_error(e, f"Error in placeholder comparison: {e}")
                    else:
                        # Regular direct comparison
                        if result != expected_result:
                            return TestResult.failed([f'query result does not match expected result. Got: {result}'])

                return TestResult.success([f'query returned {len(result)} rows'])

            except sqlite3.Error as e:
                return TestResult.failed([f"SQLite error executing query: {query} - {e}"])
            except FileNotFoundError:
                return TestResult.failed([f'database file {dst} does not exist'])

        except Exception as e:
            log.error(f"Unexpected error in SQLite query test: {e}", exc_info=True)
            return TestResult.execution_error(e, "Unexpected error in SQLite query test")