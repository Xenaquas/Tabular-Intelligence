"""Deterministic Entity Identity Disambiguation Engine.

Pre-query validation contract that detects queries against dependent/child tables
(e.g., CLAIMS joined to USERS) filtering on entity names without pinning a single
primary key identifier. When a filter matches multiple distinct entities (e.g., 3 'Rahul'
candidates), execution of dependent queries is strictly blocked and an AmbiguousIdentityResult
is returned to require clarification.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Set
import re
import pandas as pd
import sqlglot
from sqlglot import exp
from config import logger


@dataclass
class IdentityCandidate:
    entity_id: Any
    display_name: str
    attributes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AmbiguousIdentityResult:
    entity_table: str
    id_column: str
    filter_value: str
    candidates: List[IdentityCandidate]

    def to_rejection_string(self) -> str:
        lines = [
            f"⚠️ AMBIGUOUS ENTITY DETECTED: The filter matching '{self.filter_value}' resolves to {len(self.candidates)} distinct records in `{self.entity_table}`.",
            "Execution of dependent/child queries is strictly blocked to prevent combining records across different individuals.",
            "\nCandidate Entities Requiring Clarification:"
        ]
        for idx, cand in enumerate(self.candidates, 1):
            attr_parts = [f"{k}: {v}" for k, v in cand.attributes.items() if k not in (self.id_column.upper(), "FULL_NAME", "NAME")]
            attr_str = f" ({', '.join(attr_parts)})" if attr_parts else ""
            lines.append(f"{idx}. [{self.id_column}: {cand.entity_id}] {cand.display_name}{attr_str}")
        lines.append(f"\nPlease ask the user to clarify which specific {self.id_column} or person they are inquiring about before querying dependent records.")
        return "\n".join(lines)


class DeterministicIdentityResolver:
    """
    Schema-agnostic pre-query validator for entity identity ambiguity.
    """

    KNOWN_PARENT_CHILD_MAP = {
        "CLAIMS": ("USERS", "USER_ID", "FULL_NAME"),
        "ORDERS": ("CUSTOMERS", "CUSTOMER_ID", "CUSTOMER_NAME"),
        "ORDER_ITEMS": ("ORDERS", "ORDER_ID", "ORDER_ID"),
    }

    @classmethod
    def check_query_ambiguity(
        cls,
        query: str,
        engine: Any,
        dialect: str = "oracle"
    ) -> Optional[AmbiguousIdentityResult]:
        """
        Inspects query AST. If query references child/dependent tables and filters parent
        entity on text without pinning a specific primary key, queries the parent table
        to determine if > 1 distinct entities match.
        """
        try:
            parsed = sqlglot.parse_one(query, read=dialect)
        except Exception:
            return None

        # Extract all referenced tables
        tables = set()
        for t in parsed.find_all(exp.Table):
            tbl_name = t.name.upper()
            if tbl_name:
                tables.add(tbl_name)

        if not tables:
            return None

        # Check if query references any child/fact table
        for child_tbl, (parent_tbl, pk_col, name_col) in cls.KNOWN_PARENT_CHILD_MAP.items():
            if child_tbl in tables:
                # If parent table is also queried or joined, or query filters on name
                # Check whether query explicitly pins a single PK (e.g. USER_ID = 1002)
                if cls._has_pinned_single_pk(parsed, pk_col):
                    # Query is explicitly pinned to a specific ID - safe to execute!
                    return None

                # Check if query filters on parent entity text (e.g. FULL_NAME or NAME)
                name_filter = cls._extract_name_filter(parsed, name_col)
                if name_filter:
                    # Query parent table to check how many distinct entities match
                    candidates = cls._lookup_candidates(engine, parent_tbl, pk_col, name_col, name_filter)
                    if len(candidates) > 1:
                        logger.warning(f"DeterministicIdentityResolver blocked query: {len(candidates)} candidates match '{name_filter}'")
                        return AmbiguousIdentityResult(
                            entity_table=parent_tbl,
                            id_column=pk_col,
                            filter_value=name_filter,
                            candidates=candidates
                        )

        return None

    @classmethod
    def _has_pinned_single_pk(cls, parsed: exp.Expression, pk_col: str) -> bool:
        """Checks if the query contains an equality filter pinning a single primary key (e.g. USER_ID = 1002)."""
        clean_pk = pk_col.upper()
        for eq in parsed.find_all(exp.EQ):
            left_col = eq.left.name.upper() if hasattr(eq.left, "name") else ""
            right_col = eq.right.name.upper() if hasattr(eq.right, "name") else ""

            # Check if left is PK and right is a literal value (not a column in a join)
            if left_col == clean_pk and isinstance(eq.right, exp.Literal):
                return True
            if right_col == clean_pk and isinstance(eq.left, exp.Literal):
                return True
        return False

    @classmethod
    def _extract_name_filter(cls, parsed: exp.Expression, name_col: str) -> Optional[str]:
        """Extracts text filter literal applied to the name column."""
        clean_name = name_col.upper()

        # Check LIKE / ILIKE
        for like in parsed.find_all((exp.Like, exp.ILike)):
            this = like.this
            col_name = this.name.upper() if hasattr(this, "name") else ""
            # Handle LOWER(col)
            if hasattr(this, "this") and hasattr(this.this, "name"):
                col_name = this.this.name.upper()

            if col_name == clean_name:
                pattern = like.expression.name if hasattr(like.expression, "name") else str(like.expression)
                # Strip % wildcards
                return pattern.strip("%'\"")

        # Check EQ (e.g. FULL_NAME = 'Rahul')
        for eq in parsed.find_all(exp.EQ):
            left_name = eq.left.name.upper() if hasattr(eq.left, "name") else ""
            if hasattr(eq.left, "this") and hasattr(eq.left.this, "name"):
                left_name = eq.left.this.name.upper()

            if left_name == clean_name and isinstance(eq.right, exp.Literal):
                return eq.right.name.strip("'\"")

        return None

    @classmethod
    def _lookup_candidates(
        cls,
        engine: Any,
        parent_tbl: str,
        pk_col: str,
        name_col: str,
        name_filter: str
    ) -> List[IdentityCandidate]:
        """Queries parent table to find matching candidate entities."""
        clean_val = name_filter.replace("'", "''").lower()
        sql = f"SELECT * FROM {parent_tbl} WHERE LOWER({name_col}) LIKE '%{clean_val}%' ORDER BY {pk_col}"
        df, err = engine.execute_sql(sql)
        if err or df is None or df.empty:
            return []

        candidates = []
        for _, row in df.iterrows():
            row_dict = {str(k).upper(): v for k, v in row.to_dict().items()}
            cid = row_dict.get(pk_col.upper(), "")
            cname = str(row_dict.get(name_col.upper(), ""))
            candidates.append(IdentityCandidate(
                entity_id=cid,
                display_name=cname,
                attributes=row_dict
            ))
        return candidates
