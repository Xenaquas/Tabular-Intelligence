import pandas as pd
import re
from sqlalchemy import create_engine, text
from config import SETTINGS, logger

class Ingestor:
    def __init__(self, table_name: str):
        self.table_name = table_name
        self.engine = create_engine(f"sqlite:///{SETTINGS.DB_PATH}")

    def load(self, file_path: str) -> dict:
        """Loads a file (CSV or Excel) into SQLite.
        Returns a dict with:
          - 'row_count': int
          - 'columns': list of sanitized column names
          - 'text_cols': list of text columns suitable for semantic indexing
        """
        logger.info(f"Ingesting file: {file_path} into table '{self.table_name}'")
        df = pd.read_csv(file_path) if file_path.lower().endswith(".csv") \
             else pd.read_excel(file_path)
        
        # Sanitize columns: keep only alphanumeric and underscore, strip, lower
        sanitized_cols = []
        for col in df.columns:
            c = re.sub(r"[^a-zA-Z0-9_]", "_", str(col).strip()).lower()
            c = re.sub(r"_+", "_", c).strip("_")
            if not c:
                c = "column"
            # Handle duplicate column names
            base_c = c
            counter = 1
            while c in sanitized_cols:
                c = f"{base_c}_{counter}"
                counter += 1
            sanitized_cols.append(c)
            
        df.columns = sanitized_cols
        
        # Load into SQLite
        logger.info(f"Writing {len(df)} rows to SQLite table '{self.table_name}'")
        df.to_sql(self.table_name, self.engine, if_exists="replace", index=False)
        
        # Identify text columns based on object dtype and moderate cardinality (2 to 2000 unique values)
        text_cols = []
        for col in df.columns:
            if df[col].dtype == "object":
                unique_count = df[col].dropna().nunique()
                if 2 <= unique_count <= 2000:
                    text_cols.append(col)
                    
        logger.info(f"Ingested successfully: {len(df)} rows, {len(df.columns)} columns. Text columns: {text_cols}")
        
        return {
            "row_count": len(df),
            "columns": list(df.columns),
            "text_cols": text_cols
        }

    def preview(self, n=5):
        with self.engine.connect() as conn:
            return pd.read_sql(text(f"SELECT * FROM {self.table_name} LIMIT {n}"), conn)