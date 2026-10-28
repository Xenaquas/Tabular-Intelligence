import time
from typing import Optional, Dict, Any, List
import pandas as pd
from core.oracle_engine import OracleEngine
from config import logger

class OracleCatalog:
    """
    Dynamic metadata catalog and relationship discovery engine for Oracle schemas.
    Inspects Oracle data dictionary views (ALL_TABLES, ALL_TAB_COLUMNS, ALL_CONSTRAINTS)
    to discover schemas, tables, columns, types, primary keys, and foreign-key join paths
    without hardcoded schema assumptions.
    """
    def __init__(self, engine: Optional[OracleEngine] = None):
        self.engine = engine or OracleEngine.get_instance()
        self.schema = self.engine.schema
        self._catalog_cache: Optional[Dict[str, Any]] = None

    def discover_metadata(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Dynamically extracts tables, columns, constraints, and relationships for the schema.
        """
        if self._catalog_cache is not None and not force_refresh:
            return self._catalog_cache

        schema_owner = self.schema.upper()

        # 1. Discover authorized tables
        q_tables = """
        SELECT table_name, num_rows
        FROM all_tables
        WHERE owner = :schema_owner
        ORDER BY table_name
        """
        df_tables, err = self.engine.execute_sql(q_tables, {"schema_owner": schema_owner})
        if err or df_tables is None:
            logger.error(f"Failed to query ALL_TABLES: {err}")
            return {"tables": {}, "relationships": []}

        table_names = df_tables["TABLE_NAME"].tolist()
        if self.engine.allowed_tables:
            table_names = [t for t in table_names if t in self.engine.allowed_tables]

        # 2. Discover columns
        q_cols = """
        SELECT table_name, column_name, data_type, data_length, data_precision, data_scale, nullable
        FROM all_tab_columns
        WHERE owner = :schema_owner
        ORDER BY table_name, column_id
        """
        df_cols, err_cols = self.engine.execute_sql(q_cols, {"schema_owner": schema_owner})
        if err_cols or df_cols is None:
            logger.error(f"Failed to query ALL_TAB_COLUMNS: {err_cols}")
            return {"tables": {}, "relationships": []}

        # 3. Discover constraints (PK, FK, Unique)
        q_cons = """
        SELECT 
            c.constraint_name,
            c.constraint_type,
            c.table_name,
            cc.column_name,
            c.r_constraint_name,
            rc.table_name AS r_table_name,
            rcc.column_name AS r_column_name
        FROM all_constraints c
        JOIN all_cons_columns cc 
            ON c.owner = cc.owner AND c.constraint_name = cc.constraint_name
        LEFT JOIN all_constraints rc 
            ON c.r_owner = rc.owner AND c.r_constraint_name = rc.constraint_name
        LEFT JOIN all_cons_columns rcc 
            ON rc.owner = rcc.owner AND rc.constraint_name = rcc.constraint_name AND cc.position = rcc.position
        WHERE c.owner = :schema_owner
          AND c.constraint_type IN ('P', 'R', 'U')
        ORDER BY c.table_name, c.constraint_type, cc.position
        """
        df_cons, err_cons = self.engine.execute_sql(q_cons, {"schema_owner": schema_owner})

        # Build structured catalog
        tables_meta: Dict[str, Any] = {}
        for tbl in table_names:
            tables_meta[tbl] = {
                "table_name": tbl,
                "columns": [],
                "primary_key": [],
                "unique_keys": [],
                "foreign_keys": []
            }

        if df_cols is not None:
            for _, row in df_cols.iterrows():
                tbl = row["TABLE_NAME"]
                if tbl in tables_meta:
                    tables_meta[tbl]["columns"].append({
                        "name": row["COLUMN_NAME"],
                        "type": row["DATA_TYPE"],
                        "precision": row["DATA_PRECISION"],
                        "scale": row["DATA_SCALE"],
                        "nullable": row["NULLABLE"] == "Y",
                        "is_pk": False,
                        "is_fk": False
                    })

        relationships: List[Dict[str, Any]] = []

        if df_cons is not None:
            for _, row in df_cons.iterrows():
                tbl = row["TABLE_NAME"]
                ctype = row["CONSTRAINT_TYPE"]
                col = row["COLUMN_NAME"]

                if tbl not in tables_meta:
                    continue

                if ctype == "P":
                    tables_meta[tbl]["primary_key"].append(col)
                    for c_dict in tables_meta[tbl]["columns"]:
                        if c_dict["name"] == col:
                            c_dict["is_pk"] = True
                elif ctype == "U":
                    tables_meta[tbl]["unique_keys"].append(col)
                elif ctype == "R":
                    r_tbl = row["R_TABLE_NAME"]
                    r_col = row["R_COLUMN_NAME"]
                    fk_info = {
                        "name": row["CONSTRAINT_NAME"],
                        "column": col,
                        "ref_table": r_tbl,
                        "ref_column": r_col
                    }
                    tables_meta[tbl]["foreign_keys"].append(fk_info)
                    for c_dict in tables_meta[tbl]["columns"]:
                        if c_dict["name"] == col:
                            c_dict["is_fk"] = True

                    relationships.append({
                        "from_table": tbl,
                        "from_column": col,
                        "to_table": r_tbl,
                        "to_column": r_col,
                        "type": "MANY_TO_ONE",
                        "cardinality": f"N ({tbl}) : 1 ({r_tbl})",
                        "join_sql": f"{tbl}.{col} = {r_tbl}.{r_col}"
                    })

        self._catalog_cache = {
            "schema": schema_owner,
            "tables": tables_meta,
            "relationships": relationships
        }
        return self._catalog_cache

    def get_schema_markdown(self) -> str:
        """
        Formats discovered schema into a human- and agent-readable markdown specification.
        """
        meta = self.discover_metadata()
        schema_owner = meta.get("schema", self.schema)
        tables = meta.get("tables", {})
        relationships = meta.get("relationships", [])

        md = [f"### 🏛️ Oracle Relational Schema: `{schema_owner}`\n"]

        for tbl_name, tbl_info in tables.items():
            pks = tbl_info.get("primary_key", [])
            pk_str = f" [PK: {', '.join(pks)}]" if pks else ""
            md.append(f"#### Table: `{tbl_name}`{pk_str}")
            col_lines = []
            for c in tbl_info.get("columns", []):
                flags = []
                if c["is_pk"]:
                    flags.append("PK")
                if c["is_fk"]:
                    flags.append("FK")
                if not c["nullable"]:
                    flags.append("NOT NULL")
                flag_str = f" ({', '.join(flags)})" if flags else ""
                col_lines.append(f"- `{c['name']}`: {c['type']}{flag_str}")
            md.append("\n".join(col_lines) + "\n")

        if relationships:
            md.append("#### 🔗 Verified Foreign Key Relationships:")
            for r in relationships:
                md.append(f"- `{r['from_table']}.{r['from_column']}` $\\rightarrow$ `{r['to_table']}.{r['to_column']}` ({r['cardinality']})")
                md.append(f"  *Join Condition:* `ON {r['join_sql']}`")

        return "\n".join(md)

    def load_table_samples_for_indexing(self, max_rows_per_table: int = 500) -> Dict[str, pd.DataFrame]:
        """
        Fetches representative categorical data across discovered tables to populate SemanticValueIndex.
        """
        meta = self.discover_metadata()
        tables = meta.get("tables", {})
        dfs: Dict[str, pd.DataFrame] = {}

        for tbl_name, tbl_info in tables.items():
            cols = [c["name"] for c in tbl_info.get("columns", [])]
            col_str = ", ".join(cols)
            q = f"SELECT {col_str} FROM {tbl_name} WHERE ROWNUM <= {max_rows_per_table}"
            df, err = self.engine.execute_sql(q)
            if df is not None and not df.empty:
                dfs[tbl_name] = df

        return dfs
