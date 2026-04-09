# external imports
import sqlite3
from pathlib import Path
from typing import Optional

# internal imports
from adarelib.testset.api import testfunction, TestContext
from adarelib.testset.basictest import HostModeCategory
from adarelib.event.event import TestResult

# configure logging
import logging
log = logging.getLogger(__name__)


@testfunction(
    name='query_result',
    description='executes SQL query against SQLite database and validates result',
    category=HostModeCategory.FILE_CONTENT,
)
def query_result(ctx: TestContext, dst: str, query: str, expected_rows: int = None, expected_result: list = None):
    try:
        dst_resolved, status = ctx.resolve_globfilepath(dst)
        if not dst_resolved:
            return TestResult.error([f'database file {dst} can\'t be used, because no unambiguous file could be identified (because {status})'])

        log.debug(f'dst database {dst_resolved} will be used for test query_result')

        try:
            conn = sqlite3.connect(dst_resolved)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute(query)
            rows = cursor.fetchall()

            # Convert to list of dicts for easier comparison
            result = [dict(row) for row in rows]

            conn.close()

            # Check expected row count
            if expected_rows is not None:
                if len(result) != expected_rows:
                    return TestResult.failed([f'expected {expected_rows} rows, got {len(result)}'])

            # Check expected result content
            if expected_result is not None:
                # Check if expected_result has placeholders
                expected_str = str(expected_result)
                if ctx.has_placeholders(expected_str):
                    # For complex result comparison with placeholders, convert to string and use placeholder system
                    try:
                        success, message = ctx.handle_placeholders_comparison(str(result), expected_str)
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
            return TestResult.failed([f'database file {dst_resolved} does not exist'])

    except Exception as e:
        log.error(f"Unexpected error in SQLite query test: {e}", exc_info=True)
        return TestResult.execution_error(e, "Unexpected error in SQLite query test")
