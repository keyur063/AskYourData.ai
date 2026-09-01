"""
Tests for app.execution.safety_validator — L4.2 acceptance criteria.

Adversarial fixture set: 5 mandatory cases (DROP, DELETE, UPDATE, INSERT,
ALTER embedded various ways) — 100% rejected pre-execution.  Plus additional
coverage for edge cases, false-positive avoidance, and valid SQL passthrough.
"""
import pytest

from app.execution.safety_validator import validate_sql_safety, SQLSafetyError


# =========================================================================
# Valid SQL — must pass (no false positives)
# =========================================================================

class TestValidSQL:
    """Legitimate read-only queries that must NOT be rejected."""

    def test_simple_select(self):
        validate_sql_safety("SELECT * FROM users")

    def test_select_with_where(self):
        validate_sql_safety("SELECT name, email FROM users WHERE id = 1")

    def test_with_cte(self):
        validate_sql_safety(
            "WITH recent AS (SELECT * FROM orders WHERE date > '2024-01-01') "
            "SELECT * FROM recent"
        )

    def test_select_count(self):
        validate_sql_safety("SELECT COUNT(*) FROM transactions")

    def test_select_with_subquery(self):
        validate_sql_safety(
            "SELECT * FROM users WHERE id IN (SELECT user_id FROM active_sessions)"
        )

    def test_column_name_updated_at(self):
        """Column name 'updated_at' must not trigger the UPDATE blocklist."""
        validate_sql_safety("SELECT updated_at FROM records")

    def test_column_name_created_at(self):
        """Column name 'created_at' must not trigger the CREATE blocklist."""
        validate_sql_safety("SELECT created_at, deleted_at FROM audit")

    def test_column_name_deleted_at(self):
        """Column name 'deleted_at' must not trigger the DELETE blocklist."""
        validate_sql_safety("SELECT id, deleted_at FROM soft_deletes")

    def test_column_name_insert_date(self):
        """Column name 'insert_date' must not trigger the INSERT blocklist."""
        validate_sql_safety("SELECT insert_date FROM logs")

    def test_column_name_copy_number(self):
        """Column name 'copy_number' must not trigger the COPY blocklist."""
        validate_sql_safety("SELECT copy_number FROM inventory")

    def test_column_name_execution_time(self):
        """'execution_time' must not trigger EXEC/EXECUTE blocklist."""
        validate_sql_safety("SELECT execution_time FROM benchmarks")

    def test_string_literal_containing_keyword_substring(self):
        """'Dropbox' in a string should not trigger DROP (word boundary)."""
        validate_sql_safety("SELECT * FROM files WHERE name = 'Dropbox_backup'")

    def test_lowercase_select(self):
        validate_sql_safety("select name from users")

    def test_mixed_case_select(self):
        validate_sql_safety("SeLeCt name FROM users")

    def test_leading_whitespace(self):
        validate_sql_safety("   SELECT * FROM t")

    def test_with_lowercase(self):
        validate_sql_safety("with x as (select 1) select * from x")


# =========================================================================
# Adversarial fixture set — the 5 mandatory cases per L4.2
# Each tests a different blocked keyword embedded in a non-obvious way.
# ALL must be rejected (100%).
# =========================================================================

class TestAdversarial5:
    """The 5 adversarial cases required by L4.2 accept criteria."""

    def test_drop_in_mixed_case(self):
        """Case 1: DROP disguised with mixed case."""
        with pytest.raises(SQLSafetyError, match="DROP"):
            validate_sql_safety("SELECT 1 FROM t WHERE 1=1 OR DrOp TABLE t")

    def test_delete_after_semicolon(self):
        """Case 2: DELETE hidden after a semicolon (multi-statement)."""
        with pytest.raises(SQLSafetyError):
            validate_sql_safety("SELECT * FROM users; DELETE FROM users")

    def test_update_in_inline_comment(self):
        """Case 3: UPDATE embedded in an inline comment."""
        with pytest.raises(SQLSafetyError, match="UPDATE"):
            validate_sql_safety("SELECT * FROM t -- UPDATE t SET x=1")

    def test_insert_in_block_comment(self):
        """Case 4: INSERT embedded in a block comment."""
        with pytest.raises(SQLSafetyError, match="INSERT"):
            validate_sql_safety("SELECT /* INSERT INTO t VALUES (1) */ * FROM t")

    def test_alter_as_opener(self):
        """Case 5: ALTER as the statement opener (not SELECT/WITH)."""
        with pytest.raises(SQLSafetyError):
            validate_sql_safety("ALTER TABLE users ADD COLUMN evil text")


# =========================================================================
# Extended adversarial — additional blocked keywords and evasion patterns
# =========================================================================

class TestBlockedKeywords:
    """Every blocked keyword in the list must be caught."""

    @pytest.mark.parametrize("keyword", [
        "DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE",
        "CREATE", "REPLACE", "MERGE", "GRANT", "REVOKE",
        "EXECUTE", "EXEC", "COPY", "ATTACH", "DETACH", "PRAGMA", "VACUUM",
    ])
    def test_keyword_in_trailing_clause(self, keyword):
        """Each blocked keyword appended after a valid SELECT is rejected."""
        sql = f"SELECT * FROM t WHERE 1=1 OR {keyword} TABLE t"
        with pytest.raises(SQLSafetyError):
            validate_sql_safety(sql)

    @pytest.mark.parametrize("keyword", [
        "drop", "Delete", "uPdAtE", "INSERT", "alter",
    ])
    def test_case_variations(self, keyword):
        with pytest.raises(SQLSafetyError):
            validate_sql_safety(f"SELECT 1 FROM t WHERE {keyword} = 1")

    def test_opener_is_delete(self):
        with pytest.raises(SQLSafetyError):
            validate_sql_safety("DELETE FROM users WHERE id = 1")

    def test_opener_is_insert(self):
        with pytest.raises(SQLSafetyError):
            validate_sql_safety("INSERT INTO users (name) VALUES ('evil')")

    def test_opener_is_update(self):
        with pytest.raises(SQLSafetyError):
            validate_sql_safety("UPDATE users SET name = 'evil'")

    def test_opener_is_create(self):
        with pytest.raises(SQLSafetyError):
            validate_sql_safety("CREATE TABLE evil (id int)")

    def test_opener_is_truncate(self):
        with pytest.raises(SQLSafetyError):
            validate_sql_safety("TRUNCATE TABLE users")

    def test_drop_after_newline(self):
        with pytest.raises(SQLSafetyError, match="DROP"):
            validate_sql_safety("SELECT *\nFROM t\nWHERE DROP = 1")

    def test_multiple_statements_via_semicolon(self):
        with pytest.raises(SQLSafetyError):
            validate_sql_safety("SELECT 1; SELECT 2")


class TestEdgeCases:
    """Edge cases: empty, None, whitespace-only, etc."""

    def test_empty_string(self):
        with pytest.raises(SQLSafetyError, match="non-empty"):
            validate_sql_safety("")

    def test_whitespace_only(self):
        with pytest.raises(SQLSafetyError, match="non-empty"):
            validate_sql_safety("   \n\t  ")

    def test_none_input(self):
        with pytest.raises(SQLSafetyError, match="non-empty"):
            validate_sql_safety(None)  # type: ignore[arg-type]

    def test_integer_input(self):
        with pytest.raises(SQLSafetyError, match="non-empty"):
            validate_sql_safety(42)  # type: ignore[arg-type]

    def test_just_a_keyword(self):
        """A bare keyword with no SELECT/WITH opener."""
        with pytest.raises(SQLSafetyError):
            validate_sql_safety("DROP")
