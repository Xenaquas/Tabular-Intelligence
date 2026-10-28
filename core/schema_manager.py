from sqlalchemy import create_engine, inspect, text
from config import SETTINGS

class SchemaManager:
    def __init__(self):
        self.engine = create_engine(f"sqlite:///{SETTINGS.DB_PATH}")

    def schema_text(self, table_name: str, sample_rows: int = 3) -> str:
        insp = inspect(self.engine)
        cols = insp.get_columns(table_name)
        col_lines = []
        for c in cols:
            col_lines.append(f"  - {c['name']} ({c['type']})")
        # Sample rows
        with self.engine.connect() as conn:
            samples = conn.execute(
                text(f"SELECT * FROM {table_name} LIMIT {sample_rows}")
            ).fetchall()
        col_names = [c['name'] for c in cols]
        sample_str = "\n".join(
            "  " + " | ".join(f"{k}={v}" for k, v in zip(col_names, row))
            for row in samples
        )
        return (
            f"Table: {table_name}\nColumns:\n" + "\n".join(col_lines) +
            f"\n\nSample rows:\n{sample_str}"
        )