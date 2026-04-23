"""Comprehensive unit tests for SQLite testfunctions."""

import pytest
import sys
from pathlib import Path

pytestmark = pytest.mark.unit

# Add paths for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
ADARELIB_ROOT = PROJECT_ROOT.parent / "adarelib"

# Add to sys.path if not already there
if str(ADARELIB_ROOT) not in sys.path:
    sys.path.insert(0, str(ADARELIB_ROOT))

# Import from adarelib.constants as required
from adarelib.constants import StatusEnum

# Import testfunctions dynamically
from adare.helperfunctions.module import import_module_from_pyfile

# Load SQLite testfunctions module
sqlite_module_path = PROJECT_ROOT / "appdata" / "testfunctions" / "sqlite" / "sqlite.py"
sqlite_module = import_module_from_pyfile(sqlite_module_path)

# Extract testfunctions from module (decorator pattern: access generated classes via decorated function)
QueryResult = sqlite_module.query_result._test_class
QueryResultParameter = sqlite_module.query_result._parameter_class

# Import test helpers
import importlib.util
helpers_path = Path(__file__).parent / "helpers.py"
spec = importlib.util.spec_from_file_location("helpers", helpers_path)
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)

assert_test_success = helpers.assert_test_success
assert_test_failed = helpers.assert_test_failed
assert_test_error = helpers.assert_test_error


# ============================================================================
# QueryResult Tests
# ============================================================================

class TestQueryResult:
    """Tests for QueryResult testfunction."""

    def test_query_result_success_simple_select(self, create_sqlite_db):
        """Test successful query execution with simple SELECT."""
        db_file = create_sqlite_db(
            "test.db",
            "CREATE TABLE test_table (id INTEGER, name TEXT, age INTEGER)",
            [
                (1, "Alice", 30),
                (2, "Bob", 25),
                (3, "Charlie", 35),
            ]
        )

        test = QueryResult(
            name="test_query",
            parameter=QueryResultParameter(
                dst=str(db_file),
                query="SELECT * FROM test_table"
            )
        )
        result = test.test()

        assert_test_success(result)
        assert "3 rows" in result.details[0]

    def test_query_result_success_with_expected_rows(self, create_sqlite_db):
        """Test successful query with expected row count validation."""
        db_file = create_sqlite_db(
            "test.db",
            "CREATE TABLE test_table (id INTEGER, name TEXT)",
            [
                (1, "Alice"),
                (2, "Bob"),
            ]
        )

        test = QueryResult(
            name="test_query",
            parameter=QueryResultParameter(
                dst=str(db_file),
                query="SELECT * FROM test_table",
                expected_rows=2
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_query_result_failure_wrong_row_count(self, create_sqlite_db):
        """Test failure when row count doesn't match expected."""
        db_file = create_sqlite_db(
            "test.db",
            "CREATE TABLE test_table (id INTEGER, name TEXT)",
            [
                (1, "Alice"),
                (2, "Bob"),
                (3, "Charlie"),
            ]
        )

        test = QueryResult(
            name="test_query",
            parameter=QueryResultParameter(
                dst=str(db_file),
                query="SELECT * FROM test_table",
                expected_rows=2  # Expect 2, but will get 3
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "expected 2 rows, got 3" in result.details[0]

    def test_query_result_success_with_expected_result_exact_match(self, create_sqlite_db):
        """Test successful query with exact result content validation."""
        db_file = create_sqlite_db(
            "test.db",
            "CREATE TABLE test_table (id INTEGER, name TEXT)",
            [
                (1, "Alice"),
                (2, "Bob"),
            ]
        )

        test = QueryResult(
            name="test_query",
            parameter=QueryResultParameter(
                dst=str(db_file),
                query="SELECT id, name FROM test_table ORDER BY id",
                expected_result=[
                    {"id": 1, "name": "Alice"},
                    {"id": 2, "name": "Bob"},
                ]
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_query_result_failure_result_mismatch(self, create_sqlite_db):
        """Test failure when result content doesn't match expected."""
        db_file = create_sqlite_db(
            "test.db",
            "CREATE TABLE test_table (id INTEGER, name TEXT)",
            [
                (1, "Alice"),
                (2, "Bob"),
            ]
        )

        test = QueryResult(
            name="test_query",
            parameter=QueryResultParameter(
                dst=str(db_file),
                query="SELECT id, name FROM test_table ORDER BY id",
                expected_result=[
                    {"id": 1, "name": "Alice"},
                    {"id": 2, "name": "Charlie"},  # Wrong name
                ]
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "does not match expected result" in result.details[0]

    def test_query_result_success_empty_result(self, create_sqlite_db):
        """Test successful query with empty result set."""
        db_file = create_sqlite_db(
            "test.db",
            "CREATE TABLE test_table (id INTEGER, name TEXT)",
            []  # No data
        )

        test = QueryResult(
            name="test_query",
            parameter=QueryResultParameter(
                dst=str(db_file),
                query="SELECT * FROM test_table",
                expected_rows=0
            )
        )
        result = test.test()

        assert_test_success(result)
        assert "0 rows" in result.details[0]

    def test_query_result_failure_sql_syntax_error(self, create_sqlite_db):
        """Test failure with invalid SQL syntax."""
        db_file = create_sqlite_db(
            "test.db",
            "CREATE TABLE test_table (id INTEGER, name TEXT)",
            [(1, "Alice")]
        )

        test = QueryResult(
            name="test_query",
            parameter=QueryResultParameter(
                dst=str(db_file),
                query="SELECT * FORM test_table"  # Wrong SQL keyword
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "SQLite error" in result.details[0]

    def test_query_result_failure_table_not_exists(self, create_sqlite_db):
        """Test failure when querying non-existent table."""
        db_file = create_sqlite_db(
            "test.db",
            "CREATE TABLE test_table (id INTEGER, name TEXT)",
            [(1, "Alice")]
        )

        test = QueryResult(
            name="test_query",
            parameter=QueryResultParameter(
                dst=str(db_file),
                query="SELECT * FROM nonexistent_table"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "SQLite error" in result.details[0]

    def test_query_result_failure_database_not_found(self, tmp_path):
        """Test failure when database file doesn't exist (SQLite creates empty db)."""
        # Note: SQLite creates an empty database if the file doesn't exist,
        # so this test actually fails due to the table not existing, not the file.
        test = QueryResult(
            name="test_query",
            parameter=QueryResultParameter(
                dst=str(tmp_path / "nonexistent.db"),
                query="SELECT * FROM test_table"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "SQLite error" in result.details[0]

    def test_query_result_success_with_where_clause(self, create_sqlite_db):
        """Test successful query with WHERE clause."""
        db_file = create_sqlite_db(
            "test.db",
            "CREATE TABLE test_table (id INTEGER, name TEXT, age INTEGER)",
            [
                (1, "Alice", 30),
                (2, "Bob", 25),
                (3, "Charlie", 35),
            ]
        )

        test = QueryResult(
            name="test_query",
            parameter=QueryResultParameter(
                dst=str(db_file),
                query="SELECT name FROM test_table WHERE age > 28 ORDER BY name",
                expected_result=[
                    {"name": "Alice"},
                    {"name": "Charlie"},
                ]
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_query_result_success_with_order_by(self, create_sqlite_db):
        """Test successful query with ORDER BY clause."""
        db_file = create_sqlite_db(
            "test.db",
            "CREATE TABLE test_table (id INTEGER, name TEXT, score INTEGER)",
            [
                (1, "Alice", 85),
                (2, "Bob", 92),
                (3, "Charlie", 78),
            ]
        )

        test = QueryResult(
            name="test_query",
            parameter=QueryResultParameter(
                dst=str(db_file),
                query="SELECT name, score FROM test_table ORDER BY score DESC",
                expected_result=[
                    {"name": "Bob", "score": 92},
                    {"name": "Alice", "score": 85},
                    {"name": "Charlie", "score": 78},
                ]
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_query_result_success_with_join(self, create_sqlite_db, tmp_path):
        """Test successful query with JOIN operation."""
        db_file = tmp_path / "test.db"
        import sqlite3
        conn = sqlite3.connect(str(db_file))
        cursor = conn.cursor()

        # Create two tables
        cursor.execute("CREATE TABLE users (id INTEGER, name TEXT)")
        cursor.execute("CREATE TABLE orders (id INTEGER, user_id INTEGER, product TEXT)")

        # Insert data
        cursor.execute("INSERT INTO users VALUES (1, 'Alice')")
        cursor.execute("INSERT INTO users VALUES (2, 'Bob')")
        cursor.execute("INSERT INTO orders VALUES (1, 1, 'Laptop')")
        cursor.execute("INSERT INTO orders VALUES (2, 1, 'Mouse')")
        cursor.execute("INSERT INTO orders VALUES (3, 2, 'Keyboard')")

        conn.commit()
        conn.close()

        test = QueryResult(
            name="test_query",
            parameter=QueryResultParameter(
                dst=str(db_file),
                query="""
                    SELECT users.name, orders.product
                    FROM users
                    JOIN orders ON users.id = orders.user_id
                    WHERE users.name = 'Alice'
                    ORDER BY orders.product
                """,
                expected_rows=2
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_query_result_success_with_aggregation(self, create_sqlite_db):
        """Test successful query with aggregation functions."""
        db_file = create_sqlite_db(
            "test.db",
            "CREATE TABLE test_table (category TEXT, value INTEGER)",
            [
                ("A", 10),
                ("A", 20),
                ("B", 30),
                ("B", 40),
            ]
        )

        test = QueryResult(
            name="test_query",
            parameter=QueryResultParameter(
                dst=str(db_file),
                query="SELECT category, SUM(value) as total FROM test_table GROUP BY category ORDER BY category",
                expected_result=[
                    {"category": "A", "total": 30},
                    {"category": "B", "total": 70},
                ]
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_query_result_success_both_row_count_and_content(self, create_sqlite_db):
        """Test successful query with both row count and content validation."""
        db_file = create_sqlite_db(
            "test.db",
            "CREATE TABLE test_table (id INTEGER, value TEXT)",
            [
                (1, "alpha"),
                (2, "beta"),
                (3, "gamma"),
            ]
        )

        test = QueryResult(
            name="test_query",
            parameter=QueryResultParameter(
                dst=str(db_file),
                query="SELECT * FROM test_table WHERE id <= 2 ORDER BY id",
                expected_rows=2,
                expected_result=[
                    {"id": 1, "value": "alpha"},
                    {"id": 2, "value": "beta"},
                ]
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_query_result_failure_row_count_fails_first(self, create_sqlite_db):
        """Test that row count is validated before content."""
        db_file = create_sqlite_db(
            "test.db",
            "CREATE TABLE test_table (id INTEGER, value TEXT)",
            [
                (1, "alpha"),
                (2, "beta"),
                (3, "gamma"),
            ]
        )

        test = QueryResult(
            name="test_query",
            parameter=QueryResultParameter(
                dst=str(db_file),
                query="SELECT * FROM test_table",
                expected_rows=2,  # Wrong count
                expected_result=[
                    {"id": 1, "value": "alpha"},
                    {"id": 2, "value": "beta"},
                    {"id": 3, "value": "gamma"},
                ]
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "expected 2 rows, got 3" in result.details[0]

    def test_query_result_success_with_null_values(self, create_sqlite_db, tmp_path):
        """Test successful query with NULL values in result."""
        db_file = tmp_path / "test.db"
        import sqlite3
        conn = sqlite3.connect(str(db_file))
        cursor = conn.cursor()

        cursor.execute("CREATE TABLE test_table (id INTEGER, name TEXT, age INTEGER)")
        cursor.execute("INSERT INTO test_table VALUES (1, 'Alice', 30)")
        cursor.execute("INSERT INTO test_table VALUES (2, 'Bob', NULL)")

        conn.commit()
        conn.close()

        test = QueryResult(
            name="test_query",
            parameter=QueryResultParameter(
                dst=str(db_file),
                query="SELECT * FROM test_table WHERE name = 'Bob'",
                expected_result=[
                    {"id": 2, "name": "Bob", "age": None},
                ]
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_query_result_success_with_special_characters(self, create_sqlite_db):
        """Test successful query with special characters in data."""
        db_file = create_sqlite_db(
            "test.db",
            "CREATE TABLE test_table (id INTEGER, text TEXT)",
            [
                (1, "Hello 'World'"),
                (2, 'Quote: "test"'),
                (3, "Line1\nLine2"),
            ]
        )

        test = QueryResult(
            name="test_query",
            parameter=QueryResultParameter(
                dst=str(db_file),
                query="SELECT * FROM test_table WHERE id = 1",
                expected_result=[
                    {"id": 1, "text": "Hello 'World'"},
                ]
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_query_result_success_single_row(self, create_sqlite_db):
        """Test successful query returning single row."""
        db_file = create_sqlite_db(
            "test.db",
            "CREATE TABLE test_table (id INTEGER, name TEXT)",
            [
                (1, "Alice"),
                (2, "Bob"),
            ]
        )

        test = QueryResult(
            name="test_query",
            parameter=QueryResultParameter(
                dst=str(db_file),
                query="SELECT name FROM test_table WHERE id = 1",
                expected_rows=1,
                expected_result=[
                    {"name": "Alice"},
                ]
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_query_result_success_no_validation(self, create_sqlite_db):
        """Test successful query with no validation (only execution)."""
        db_file = create_sqlite_db(
            "test.db",
            "CREATE TABLE test_table (id INTEGER, name TEXT)",
            [
                (1, "Alice"),
                (2, "Bob"),
            ]
        )

        test = QueryResult(
            name="test_query",
            parameter=QueryResultParameter(
                dst=str(db_file),
                query="SELECT * FROM test_table"
            )
        )
        result = test.test()

        assert_test_success(result)
        assert "2 rows" in result.details[0]

    def test_query_result_success_with_placeholder(self, create_sqlite_db, variable_metadata_simple):
        """Test successful query with placeholder in expected result."""
        db_file = create_sqlite_db(
            "test.db",
            "CREATE TABLE test_table (id INTEGER, name TEXT, value TEXT)",
            [
                (1, "Alice", "value1"),
                (2, "Bob", "value2"),
            ]
        )

        test = QueryResult(
            name="test_query",
            parameter=QueryResultParameter(
                dst=str(db_file),
                query="SELECT id, name, value FROM test_table WHERE id = 2",
                expected_result=[
                    {"id": 2, "name": "Bob", "value": "{{VAR2}}"},
                ]
            ),
            variable_metadata=variable_metadata_simple
        )
        result = test.test()

        assert_test_success(result)

    def test_query_result_failure_placeholder_mismatch(self, create_sqlite_db, variable_metadata_simple):
        """Test failure when placeholder doesn't match."""
        db_file = create_sqlite_db(
            "test.db",
            "CREATE TABLE test_table (id INTEGER, name TEXT, value TEXT)",
            [
                (1, "Alice", "wrong_value"),
                (2, "Bob", "value2"),
            ]
        )

        test = QueryResult(
            name="test_query",
            parameter=QueryResultParameter(
                dst=str(db_file),
                query="SELECT id, name, value FROM test_table WHERE id = 1",
                expected_result=[
                    {"id": 1, "name": "Alice", "value": "{{VAR1}}"},
                ]
            ),
            variable_metadata=variable_metadata_simple
        )
        result = test.test()

        assert_test_failed(result)
        assert "placeholder comparison failed" in result.details[0]

    def test_query_result_success_with_multiple_placeholders(self, create_sqlite_db, variable_metadata_simple):
        """Test successful query with multiple placeholders in result."""
        db_file = create_sqlite_db(
            "test.db",
            "CREATE TABLE test_table (id INTEGER, name TEXT, value TEXT)",
            [
                (1, "Alice", "value1"),
                (2, "Bob", "value2"),
            ]
        )

        test = QueryResult(
            name="test_query",
            parameter=QueryResultParameter(
                dst=str(db_file),
                query="SELECT id, name, value FROM test_table ORDER BY id",
                expected_result=[
                    {"id": 1, "name": "Alice", "value": "{{VAR1}}"},
                    {"id": 2, "name": "Bob", "value": "{{VAR2}}"},
                ]
            ),
            variable_metadata=variable_metadata_simple
        )
        result = test.test()

        assert_test_success(result)

    def test_query_result_success_single_column(self, create_sqlite_db):
        """Test successful query selecting single column."""
        db_file = create_sqlite_db(
            "test.db",
            "CREATE TABLE test_table (id INTEGER, name TEXT, age INTEGER)",
            [
                (1, "Alice", 30),
                (2, "Bob", 25),
            ]
        )

        test = QueryResult(
            name="test_query",
            parameter=QueryResultParameter(
                dst=str(db_file),
                query="SELECT name FROM test_table ORDER BY id",
                expected_result=[
                    {"name": "Alice"},
                    {"name": "Bob"},
                ]
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_query_result_success_count_query(self, create_sqlite_db):
        """Test successful COUNT query."""
        db_file = create_sqlite_db(
            "test.db",
            "CREATE TABLE test_table (id INTEGER, name TEXT)",
            [
                (1, "Alice"),
                (2, "Bob"),
                (3, "Charlie"),
            ]
        )

        test = QueryResult(
            name="test_query",
            parameter=QueryResultParameter(
                dst=str(db_file),
                query="SELECT COUNT(*) as count FROM test_table",
                expected_result=[
                    {"count": 3},
                ]
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_query_result_failure_empty_result_expected_rows(self, create_sqlite_db):
        """Test failure when expecting rows but getting none."""
        db_file = create_sqlite_db(
            "test.db",
            "CREATE TABLE test_table (id INTEGER, name TEXT)",
            []  # Empty table
        )

        test = QueryResult(
            name="test_query",
            parameter=QueryResultParameter(
                dst=str(db_file),
                query="SELECT * FROM test_table",
                expected_rows=1  # Expect 1 row but will get 0
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "expected 1 rows, got 0" in result.details[0]

    def test_query_result_success_with_limit(self, create_sqlite_db):
        """Test successful query with LIMIT clause."""
        db_file = create_sqlite_db(
            "test.db",
            "CREATE TABLE test_table (id INTEGER, name TEXT)",
            [
                (1, "Alice"),
                (2, "Bob"),
                (3, "Charlie"),
                (4, "David"),
            ]
        )

        test = QueryResult(
            name="test_query",
            parameter=QueryResultParameter(
                dst=str(db_file),
                query="SELECT id, name FROM test_table ORDER BY id LIMIT 2",
                expected_rows=2,
                expected_result=[
                    {"id": 1, "name": "Alice"},
                    {"id": 2, "name": "Bob"},
                ]
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_query_result_with_real_numbers(self, create_sqlite_db):
        """Test query with real numbers (floats)."""
        db_file = create_sqlite_db(
            "test.db",
            "CREATE TABLE test_table (id INTEGER, price REAL)",
            [
                (1, 19.99),
                (2, 24.50),
            ]
        )

        test = QueryResult(
            name="test_query",
            parameter=QueryResultParameter(
                dst=str(db_file),
                query="SELECT id, price FROM test_table WHERE id = 1",
                expected_result=[
                    {"id": 1, "price": 19.99},
                ]
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_query_result_error_ambiguous_glob_pattern(self, create_sqlite_db, tmp_path):
        """Test error when glob pattern matches multiple files in single mode."""
        # Create multiple database files
        db_file1 = create_sqlite_db(
            "test1.db",
            "CREATE TABLE test_table (id INTEGER)",
            [(1,)]
        )
        db_file2 = create_sqlite_db(
            "test2.db",
            "CREATE TABLE test_table (id INTEGER)",
            [(2,)]
        )

        test = QueryResult(
            name="test_query",
            parameter=QueryResultParameter(
                dst=str(tmp_path / "*.db"),  # Matches multiple files
                query="SELECT * FROM test_table"
            )
        )
        result = test.test()

        assert_test_error(result)
        assert "no unambiguous file could be identified" in result.details[0]
