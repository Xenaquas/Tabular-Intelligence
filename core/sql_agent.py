import re
import time
from sqlalchemy import create_engine, text
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from config import SETTINGS, logger
from core.semantic_index import SemanticIndex

SQL_GEN_SYS = """You are a SQLite expert. Convert the user question into ONE syntactically
correct SQLite SELECT query.

Rules:
- Use ONLY the provided table name and columns.
- The table name is: {table_name}
- NEVER use INSERT/UPDATE/DELETE/DROP — only SELECT.
- Return ONLY the SQL inside a ```sql code block. Do NOT include any explanations or extra text.
- For 'top N' questions use ORDER BY ... LIMIT N.
- For aggregations use GROUP BY.
- If the user mentions a value that does not exactly match a column value, use the
  resolved values provided (they are exact strings present in the table).
  Example: if the user asks for 'Product A' and the resolved value is column='product_name', value='Product A (Standard)', your WHERE clause should use:
  WHERE product_name = 'Product A (Standard)'
"""

SQL_FIX_SYS = """You are a SQLite expert. The previous query failed with this error:
{error}

Original query:
{sql}

Schema:
{schema}

Return a corrected SQLite query ONLY inside a ```sql code block. Do NOT include any explanations or extra text."""

class SQLAgent:
    def __init__(self, schema_text: str, table_name: str, semantic: SemanticIndex):
        self.schema_text = schema_text
        self.table_name = table_name
        self.semantic = semantic
        self.llm = ChatOpenAI(
            model=SETTINGS.LLM_MODEL,
            base_url=SETTINGS.LLM_BASE_URL,
            api_key="not-needed",
            temperature=SETTINGS.LLM_TEMP,
        )
        self.engine = create_engine(f"sqlite:///{SETTINGS.DB_PATH}")

    def _extract_sql(self, txt: str) -> str:
        # Match ```sql ... ```
        m = re.search(r"```sql\s*(.*?)\s*```", txt, re.DOTALL | re.IGNORECASE)
        if not m:
            # Fallback to plain ``` ... ```
            m = re.search(r"```\s*(.*?)\s*```", txt, re.DOTALL | re.IGNORECASE)
        sql = (m.group(1) if m else txt).strip()
        # Remove SQL comments
        sql = re.sub(r"^--.*$", "", sql, flags=re.MULTILINE)
        return sql.strip().rstrip(";")

    def generate(self, question: str) -> str:
        logger.info(f"Generating SQL for question: '{question}'")
        
        # 1. Resolve fuzzy terms
        resolved = self.semantic.resolve(question, k=3)
        resolved_str = "\n".join(
            f"- column={r['column']}, value={r['value']!r}" for r in resolved
        ) or "(none)"
        
        # 2. Build prompt
        system_content = f"{SQL_GEN_SYS.format(table_name=self.table_name)}\n\nSchema:\n{self.schema_text}\n\nResolved candidate values:\n{resolved_str}"
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_content),
            ("human", "{question}"),
        ])
        chain = prompt | self.llm | StrOutputParser()
        
        logger.info("Invoking LLM for SQL generation...")
        raw_out = chain.invoke({"question": question})
        logger.info(f"Raw LLM Output:\n{raw_out}")
        
        sql = self._extract_sql(raw_out)
        logger.info(f"Extracted SQL: {sql}")
        return sql

    def execute(self, sql: str):
        start_time = time.time()
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql)).fetchall()
            cols = list(rows[0]._mapping.keys()) if rows else []
        elapsed = time.time() - start_time
        logger.info(f"SQL executed in {elapsed:.3f}s. Rows returned: {len(rows)}")
        return cols, [dict(r._mapping) for r in rows]

    def safe_run(self, question: str):
        sql = self.generate(question)
        for attempt in range(SETTINGS.MAX_SQL_RETRY + 1):
            try:
                logger.info(f"Execution Attempt {attempt + 1}: Running SQL...")
                cols, rows = self.execute(sql)
                return sql, cols, rows, None
            except Exception as e:
                err = str(e)
                logger.error(f"SQL Execution Attempt {attempt + 1} failed: {err}")
                if attempt == SETTINGS.MAX_SQL_RETRY:
                    logger.error("Max retries reached. Returning SQL failure.")
                    return sql, [], [], err
                
                logger.info("Asking LLM to fix the SQL error...")
                fix_prompt = ChatPromptTemplate.from_messages([
                    ("system", SQL_FIX_SYS.format(error=err, sql=sql, schema=self.schema_text)),
                    ("human", "Fix this SQLite query. Output only the corrected query in a ```sql block."),
                ])
                chain = fix_prompt | self.llm | StrOutputParser()
                raw_fix = chain.invoke({})
                logger.info(f"Raw Fix LLM Output:\n{raw_fix}")
                sql = self._extract_sql(raw_fix)
                logger.info(f"Extracted fixed SQL: {sql}")
                
        return sql, [], [], "unknown error"