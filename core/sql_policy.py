"""Centralized AST-based SQL Authorization Policy and Secure Query Execution Boundary.

Enforces:
- Single-statement read-only execution (SELECT and read-only CTEs)
- Strict rejection of DDL, DML, multi-statements, transactions, and pragma/system commands
- Blocking of all DuckDB file-reading, extension, and system-state inspection functions
- Catalog/schema authorization restricting access strictly to approved tables
- Database-level isolation settings (disable external access, memory ceiling, execution deadline)
- Structured results distinguishing SUCCESS, SECURITY_VIOLATION, SYNTAX_ERROR, and TIMEOUT
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

import duckdb
import pandas as pd
import sqlglot
from sqlglot import exp

logger = logging.getLogger("TabularSwarm")


class SQLPolicyViolationType(str, Enum):
    EMPTY_QUERY = "EMPTY_QUERY"
    SYNTAX_ERROR = "SYNTAX_ERROR"
    MULTI_STATEMENT = "MULTI_STATEMENT"
    FORBIDDEN_STATEMENT = "FORBIDDEN_STATEMENT"
    FORBIDDEN_CONSTRUCT = "FORBIDDEN_CONSTRUCT"
    DANGEROUS_FUNCTION = "DANGEROUS_FUNCTION"
    UNAUTHORIZED_TABLE = "UNAUTHORIZED_TABLE"
    SCHEMA_QUALIFICATION = "SCHEMA_QUALIFICATION"
    PATH_INJECTION = "PATH_INJECTION"
    IDENTIFIER_INJECTION = "IDENTIFIER_INJECTION"
    EXECUTION_TIMEOUT = "EXECUTION_TIMEOUT"
    RESOURCE_LIMIT = "RESOURCE_LIMIT"
    EXECUTION_ERROR = "EXECUTION_ERROR"


# AST statement types strictly forbidden from executing
FORBIDDEN_STATEMENTS = tuple([
    getattr(exp, name) for name in [
        "Create", "Drop", "Insert", "Update", "Delete", "Alter",
        "Command", "Transaction", "Commit", "Rollback", "Set",
        "Pragma", "Copy", "Attach", "Detach", "Install",
        "Merge", "TruncateTable", "LoadData"
    ] if hasattr(exp, name)
])

# Dangerous DuckDB functions capable of file access, network requests, code loading, or system discovery
DANGEROUS_FUNCTIONS: Set[str] = {
    "read_csv", "read_csv_auto", "read_parquet", "parquet_scan", "scan_csv",
    "scan_parquet", "read_json", "read_json_auto", "read_blob", "read_text",
    "from_csv", "write_csv", "write_parquet", "glob", "load", "install",
    "copy", "export", "import_database", "checkpoint", "pragma", "system",
    "system_call", "query_table", "current_setting", "set_variable",
    "get_variable", "sniff_csv", "httpfs", "post", "get", "sql", "query"
}

# Dangerous Oracle functions, packages, and system procedures
ORACLE_DANGEROUS_FUNCTIONS: Set[str] = {
    "dbms_lob", "dbms_output", "dbms_sql", "dbms_scheduler", "dbms_pipe",
    "utl_file", "utl_http", "utl_tcp", "utl_smtp", "utl_inaddr",
    "ctxsys", "sys", "ora_hash", "execute", "exec"
}

# Suspicious substrings in table names or raw identifiers indicating path traversal or stacking attempts
SUSPICIOUS_PATH_PATTERNS = ["/", "\\", "..", ".csv", ".parquet", ".json", ".txt", ".db", ";", "--", "/*"]


@dataclass
class SQLValidationResult:
    is_valid: bool
    sanitized_sql: str
    error: Optional[str] = None
    violation_type: Optional[SQLPolicyViolationType] = None
    tables_referenced: Set[str] = field(default_factory=set)


@dataclass
class SQLQueryResult:
    success: bool
    dataframe: Optional[pd.DataFrame] = None
    total_rows: int = 0
    preview_df: Optional[pd.DataFrame] = None
    is_truncated: bool = False
    error: Optional[str] = None
    violation_type: Optional[SQLPolicyViolationType] = None
    execution_time_ms: float = 0.0
    sql: str = ""


class SQLPolicy:
    """Centralized SQL parsing and validation policy engine using sqlglot."""

    def __init__(
        self,
        default_timeout_seconds: float = 30.0,
        max_memory_mb: int = 512,
        threads: int = 4
    ):
        self.default_timeout_seconds = default_timeout_seconds
        self.max_memory_mb = max_memory_mb
        self.threads = threads

    @staticmethod
    def configure_connection(conn: duckdb.DuckDBPyConnection, max_memory_mb: int = 512, threads: int = 4):
        """Applies defense-in-depth database-level security and resource limits independently of query validation."""
        try:
            conn.execute("SET enable_external_access = false;")
        except Exception as e:
            logger.debug(f"enable_external_access configuration note: {e}")

        try:
            conn.execute(f"SET max_memory = '{max_memory_mb}MB';")
        except Exception as e:
            logger.debug(f"max_memory configuration note: {e}")

        try:
            conn.execute(f"SET threads = {threads};")
        except Exception as e:
            logger.debug(f"threads configuration note: {e}")

    def validate_sql(
        self,
        query: str,
        allowed_tables: Optional[Set[str]] = None,
        dialect: str = "duckdb",
        allowed_schemas: Optional[Set[str]] = None
    ) -> SQLValidationResult:
        """Validates that a SQL query is a single read-only SELECT or CTE, and checks all tables,

        functions, identifiers, and constructs against authorization policies.
        Supports both DuckDB and Oracle dialects.
        """
        if not query or not query.strip():
            return SQLValidationResult(
                is_valid=False,
                sanitized_sql="",
                error="SQL Policy Violation: Empty SQL query provided.",
                violation_type=SQLPolicyViolationType.EMPTY_QUERY
            )

        clean_query = query.strip().rstrip(";")
        clean_dialect = dialect.lower()

        # Oracle-specific upfront checks
        if clean_dialect == "oracle":
            if "@" in clean_query:
                return SQLValidationResult(
                    is_valid=False,
                    sanitized_sql=clean_query,
                    error="SQL Policy Violation: Database links (@) are prohibited.",
                    violation_type=SQLPolicyViolationType.FORBIDDEN_CONSTRUCT
                )
            if clean_query.strip().upper().startswith(("DECLARE", "BEGIN", "CALL", "EXEC")):
                return SQLValidationResult(
                    is_valid=False,
                    sanitized_sql=clean_query,
                    error="SQL Policy Violation: PL/SQL blocks and procedure execution are prohibited.",
                    violation_type=SQLPolicyViolationType.FORBIDDEN_STATEMENT
                )

        # 1. Parse AST with sqlglot for specified dialect
        try:
            parsed = sqlglot.parse(clean_query, read=clean_dialect)
        except Exception as parse_err:
            return SQLValidationResult(
                is_valid=False,
                sanitized_sql=clean_query,
                error=f"SQL Policy Violation: Failed to parse SQL statement: {parse_err}",
                violation_type=SQLPolicyViolationType.SYNTAX_ERROR
            )

        # 2. Reject multi-statement queries (SQL injection stacking)
        non_empty = [p for p in parsed if p is not None]
        if len(non_empty) != 1:
            return SQLValidationResult(
                is_valid=False,
                sanitized_sql=clean_query,
                error=f"SQL Policy Violation: Multiple SQL statements detected ({len(non_empty)}). Exactly one read-only statement is permitted.",
                violation_type=SQLPolicyViolationType.MULTI_STATEMENT
            )

        stmt = non_empty[0]

        # 3. Root statement must be a SELECT or UNION of SELECTs
        if not isinstance(stmt, (exp.Select, exp.Union)):
            stmt_name = type(stmt).__name__
            return SQLValidationResult(
                is_valid=False,
                sanitized_sql=clean_query,
                error=f"SQL Policy Violation: Statement type '{stmt_name}' is not permitted. Only read-only SELECT queries are allowed.",
                violation_type=SQLPolicyViolationType.FORBIDDEN_STATEMENT
            )

        # 4. Deep traversal of every AST node to reject nested DDL/DML and dangerous functions
        for node in stmt.walk():
            # Check for forbidden statement types nested anywhere in AST
            if isinstance(node, FORBIDDEN_STATEMENTS):
                return SQLValidationResult(
                    is_valid=False,
                    sanitized_sql=clean_query,
                    error=f"SQL Policy Violation: Forbidden construct '{type(node).__name__}' found within query AST.",
                    violation_type=SQLPolicyViolationType.FORBIDDEN_CONSTRUCT
                )

            # Check functions for dangerous / external operations
            if isinstance(node, (exp.Func, exp.Anonymous)):
                if isinstance(node, exp.Anonymous):
                    fname = str(getattr(node, "name", getattr(node, "this", ""))).lower()
                elif hasattr(node, "sql_name"):
                    fname = node.sql_name().lower()
                else:
                    fname = getattr(node, "name", str(node.key)).lower()

                if fname in DANGEROUS_FUNCTIONS or (clean_dialect == "oracle" and (fname in ORACLE_DANGEROUS_FUNCTIONS or fname.startswith(("dbms_", "utl_")))):
                    return SQLValidationResult(
                        is_valid=False,
                        sanitized_sql=clean_query,
                        error=f"SQL Policy Violation: Dangerous {clean_dialect.capitalize()} function '{fname}' is blocked.",
                        violation_type=SQLPolicyViolationType.DANGEROUS_FUNCTION
                    )

        # 5. Extract defined CTE aliases so they are treated as valid local tables
        cte_aliases: Set[str] = set()
        for cte in stmt.find_all(exp.CTE):
            if cte.alias_or_name:
                cte_aliases.add(cte.alias_or_name.lower())

        # 6. Validate table references
        tables_referenced: Set[str] = set()
        norm_allowed = {t.lower() for t in allowed_tables} if allowed_tables is not None else None
        norm_allowed_schemas = {s.lower() for s in allowed_schemas} if allowed_schemas is not None else None

        for tbl in stmt.find_all(exp.Table):
            tname = tbl.name
            if not tname:
                continue

            tname_lower = tname.lower()

            # Local CTE names are permitted
            if tname_lower in cte_aliases:
                continue

            # In DuckDB, reject all schema qualifications. In Oracle, allow only explicitly authorized schema
            if tbl.db:
                schema_name_lower = tbl.db.lower()
                if clean_dialect == "oracle" and norm_allowed_schemas and schema_name_lower in norm_allowed_schemas:
                    pass  # Authorized schema qualification permitted
                else:
                    return SQLValidationResult(
                        is_valid=False,
                        sanitized_sql=clean_query,
                        error=f"SQL Policy Violation: Schema qualification '{tbl.sql()}' is not permitted.",
                        violation_type=SQLPolicyViolationType.SCHEMA_QUALIFICATION
                    )

            # Reject path injection or file syntax in table names
            for bad in SUSPICIOUS_PATH_PATTERNS:
                if bad in tname_lower:
                    return SQLValidationResult(
                        is_valid=False,
                        sanitized_sql=clean_query,
                        error=f"SQL Policy Violation: Table name contains invalid path or injection pattern: '{tname}'.",
                        violation_type=SQLPolicyViolationType.PATH_INJECTION
                    )

            tables_referenced.add(tname_lower)

            # If an allowed catalog is provided, enforce that table is authorized
            if norm_allowed is not None and tname_lower not in norm_allowed:
                allowed_str = sorted(list(allowed_tables))
                return SQLValidationResult(
                    is_valid=False,
                    sanitized_sql=clean_query,
                    error=f"SQL Policy Violation: Table '{tname}' is not in the authorized catalog. Permitted tables: {allowed_str}",
                    violation_type=SQLPolicyViolationType.UNAUTHORIZED_TABLE
                )

        sanitized = stmt.sql(dialect=clean_dialect)
        return SQLValidationResult(
            is_valid=True,
            sanitized_sql=sanitized,
            tables_referenced=tables_referenced
        )

    def execute_secure_query(
        self,
        conn: duckdb.DuckDBPyConnection,
        query: str,
        query_lock: threading.Lock,
        allowed_tables: Optional[Set[str]] = None,
        params: Optional[Union[List[Any], Dict[str, Any], Tuple[Any, ...]]] = None,
        max_rows: Optional[int] = None,
        preview_limit: int = 15,
        timeout_seconds: Optional[float] = None
    ) -> SQLQueryResult:
        """Validates and executes a SQL query against DuckDB under lock, deadline, and safety checks."""
        start_time = time.time()

        # Step 1: AST validation
        validation = self.validate_sql(query, allowed_tables=allowed_tables)
        if not validation.is_valid:
            duration_ms = round((time.time() - start_time) * 1000, 2)
            logger.warning(f"SQL Rejected: {validation.error} | Raw Query: {query}")
            return SQLQueryResult(
                success=False,
                error=validation.error,
                violation_type=validation.violation_type,
                execution_time_ms=duration_ms,
                sql=query
            )

        sanitized_sql = validation.sanitized_sql

        # Deterministic Identity Disambiguation Check (DEF-02 mitigation)
        try:
            from core.identity_resolver import DeterministicIdentityResolver
            ambiguity = DeterministicIdentityResolver.check_query_ambiguity(sanitized_sql, oracle_engine, dialect="oracle")
            if ambiguity is not None:
                duration_ms = round((time.time() - start_time) * 1000, 2)
                rejection_msg = ambiguity.to_rejection_string()
                logger.warning(f"Oracle Query Blocked by DeterministicIdentityResolver: {rejection_msg}")
                return SQLQueryResult(
                    success=False,
                    error=rejection_msg,
                    violation_type=SQLPolicyViolationType.FORBIDDEN_CONSTRUCT,
                    execution_time_ms=duration_ms,
                    sql=sanitized_sql
                )
        except Exception as e:
            logger.debug(f"Error checking identity ambiguity: {e}")

        timeout = timeout_seconds or self.default_timeout_seconds

        # Step 2: Execute with timeout interrupt under the database lock
        with query_lock:
            timer = None
            interrupted = threading.Event()

            def _on_timeout():
                interrupted.set()
                try:
                    conn.interrupt()
                except Exception as e:
                    logger.debug(f"Interrupt notice: {e}")

            if timeout and timeout > 0:
                timer = threading.Timer(timeout, _on_timeout)
                timer.daemon = True
                timer.start()

            try:
                if params is not None:
                    res_cursor = conn.execute(sanitized_sql, params)
                else:
                    res_cursor = conn.execute(sanitized_sql)

                result_df = res_cursor.fetchdf()
                duration_ms = round((time.time() - start_time) * 1000, 2)

                total_rows = len(result_df) if result_df is not None else 0
                is_truncated = False

                if max_rows and total_rows > max_rows:
                    logger.warning(f"Query returned {total_rows} rows; truncating to max_rows={max_rows}.")
                    full_df = result_df
                    result_df = result_df.head(max_rows)
                    is_truncated = True

                preview_df = result_df.head(preview_limit) if result_df is not None else None

                return SQLQueryResult(
                    success=True,
                    dataframe=result_df,
                    total_rows=total_rows,
                    preview_df=preview_df,
                    is_truncated=is_truncated,
                    execution_time_ms=duration_ms,
                    sql=sanitized_sql
                )

            except duckdb.InterruptException:
                duration_ms = round((time.time() - start_time) * 1000, 2)
                err_msg = f"SQL Execution Timeout: Query exceeded deadline of {timeout}s and was terminated."
                logger.error(err_msg)
                return SQLQueryResult(
                    success=False,
                    error=err_msg,
                    violation_type=SQLPolicyViolationType.EXECUTION_TIMEOUT,
                    execution_time_ms=duration_ms,
                    sql=sanitized_sql
                )
            except duckdb.OutOfMemoryException as mem_err:
                duration_ms = round((time.time() - start_time) * 1000, 2)
                err_msg = f"SQL Resource Limit Exceeded: {mem_err}"
                logger.error(err_msg)
                return SQLQueryResult(
                    success=False,
                    error=err_msg,
                    violation_type=SQLPolicyViolationType.RESOURCE_LIMIT,
                    execution_time_ms=duration_ms,
                    sql=sanitized_sql
                )
            except duckdb.Error as ddb_err:
                duration_ms = round((time.time() - start_time) * 1000, 2)
                err_msg = f"DuckDB Execution Error: {type(ddb_err).__name__}: {str(ddb_err)}"
                logger.error(f"{err_msg} | SQL: {sanitized_sql}")
                return SQLQueryResult(
                    success=False,
                    error=err_msg,
                    violation_type=SQLPolicyViolationType.EXECUTION_ERROR,
                    execution_time_ms=duration_ms,
                    sql=sanitized_sql
                )
            except Exception as exc:
                duration_ms = round((time.time() - start_time) * 1000, 2)
                err_msg = f"Unexpected SQL Error: {type(exc).__name__}: {str(exc)}"
                logger.error(f"{err_msg} | SQL: {sanitized_sql}")
                return SQLQueryResult(
                    success=False,
                    error=err_msg,
                    violation_type=SQLPolicyViolationType.EXECUTION_ERROR,
                    execution_time_ms=duration_ms,
                    sql=sanitized_sql
                )
            finally:
                if timer is not None:
                    timer.cancel()

    def execute_secure_oracle_query(
        self,
        oracle_engine: Any,
        query: str,
        allowed_tables: Optional[Set[str]] = None,
        allowed_schemas: Optional[Set[str]] = None,
        params: Optional[Union[List[Any], Dict[str, Any], Tuple[Any, ...]]] = None,
        max_rows: Optional[int] = None,
        preview_limit: int = 15,
        timeout_seconds: Optional[float] = None
    ) -> SQLQueryResult:
        """Validates and executes a SQL query against Oracle in a read-only transaction under policy enforcement."""
        start_time = time.time()

        effective_allowed_schemas = allowed_schemas
        if effective_allowed_schemas is None and hasattr(oracle_engine, "allowed_schemas"):
            effective_allowed_schemas = set(oracle_engine.allowed_schemas)

        effective_allowed_tables = allowed_tables
        if effective_allowed_tables is None and hasattr(oracle_engine, "allowed_tables"):
            effective_allowed_tables = set(oracle_engine.allowed_tables)

        validation = self.validate_sql(
            query,
            allowed_tables=effective_allowed_tables,
            dialect="oracle",
            allowed_schemas=effective_allowed_schemas
        )
        if not validation.is_valid:
            duration_ms = round((time.time() - start_time) * 1000, 2)
            logger.warning(f"Oracle SQL Policy Violation: {validation.error} | Raw Query: {query}")
            return SQLQueryResult(
                success=False,
                error=validation.error,
                violation_type=validation.violation_type,
                execution_time_ms=duration_ms,
                sql=query
            )

        sanitized_sql = validation.sanitized_sql

        # Deterministic Identity Disambiguation Check (DEF-02 mitigation)
        try:
            from core.identity_resolver import DeterministicIdentityResolver
            ambiguity = DeterministicIdentityResolver.check_query_ambiguity(sanitized_sql, oracle_engine, dialect="oracle")
            if ambiguity is not None:
                duration_ms = round((time.time() - start_time) * 1000, 2)
                rejection_msg = ambiguity.to_rejection_string()
                logger.warning(f"Oracle Query Blocked by DeterministicIdentityResolver: {rejection_msg}")
                return SQLQueryResult(
                    success=False,
                    error=rejection_msg,
                    violation_type=SQLPolicyViolationType.FORBIDDEN_CONSTRUCT,
                    execution_time_ms=duration_ms,
                    sql=sanitized_sql
                )
        except Exception as e:
            logger.debug(f"Error checking identity ambiguity: {e}")

        timeout = timeout_seconds or self.default_timeout_seconds

        df, err = oracle_engine.execute_sql(
            sanitized_sql,
            params=params,
            max_rows=max_rows,
            timeout_seconds=timeout
        )
        duration_ms = round((time.time() - start_time) * 1000, 2)

        if err:
            v_type = SQLPolicyViolationType.EXECUTION_TIMEOUT if "Timeout" in err else SQLPolicyViolationType.EXECUTION_ERROR
            return SQLQueryResult(
                success=False,
                error=err,
                violation_type=v_type,
                execution_time_ms=duration_ms,
                sql=sanitized_sql
            )

        total_rows = len(df) if df is not None else 0
        is_truncated = False
        if max_rows and total_rows > max_rows:
            df = df.head(max_rows)
            is_truncated = True

        preview_df = df.head(preview_limit) if df is not None else None

        return SQLQueryResult(
            success=True,
            dataframe=df,
            total_rows=total_rows,
            preview_df=preview_df,
            is_truncated=is_truncated,
            execution_time_ms=duration_ms,
            sql=sanitized_sql
        )
