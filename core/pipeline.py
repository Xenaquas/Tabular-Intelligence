import json
import re
import pandas as pd
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from config import SETTINGS, logger
from core.schema_manager import SchemaManager
from core.semantic_index import SemanticIndex
from core.sql_agent import SQLAgent

ANSWER_SYS = """You are a senior data analyst. Synthesize a professional response and analysis based on the user's question, the SQL query executed, and the resulting dataset.

Format your output as a JSON object with the following keys:
1. "summary": A concise yet thorough natural-language analysis and answer to the user's question. Max 4 sentences. Highlight key takeaways.
2. "structured": (Optional) If the user's query asked for lists, rankings, statistics, breakdown, or metrics, provide it as a structured JSON object or array of objects. Otherwise, leave this as null.

Example format:
{{
  "summary": "The data shows that product sales peaked in Q3. Product X was the top performer, generating $50k in revenue, followed by Product Y at $30k.",
  "structured": {{
    "rankings": [
      {{"product": "Product X", "sales": 50000}},
      {{"product": "Product Y", "sales": 30000}}
    ]
  }}
}}

Return ONLY the JSON. No prose outside the JSON.
"""

class TabularRAG:
    def __init__(self, table_name: str, text_like_cols: list[str]):
        self.table_name = table_name
        self.schema_mgr = SchemaManager()
        self.schema_text = self.schema_mgr.schema_text(table_name)
        self.semantic = SemanticIndex()
        self.semantic.build(table_name, text_like_cols)
        self.sql_agent = SQLAgent(self.schema_text, table_name, self.semantic)
        self.llm = ChatOpenAI(
            model=SETTINGS.LLM_MODEL,
            base_url=SETTINGS.LLM_BASE_URL,
            api_key="not-needed",
            temperature=SETTINGS.LLM_TEMP,
        )

    def _parse_synthesis_response(self, text: str) -> dict:
        """Robustly extracts summary and optional structured dictionary from LLM response."""
        text = text.strip()
        
        # Match markdown JSON blocks
        m = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
        if not m:
            m = re.search(r"```\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
        
        candidate = m.group(1).strip() if m else text
        
        # Try to find curly braces boundary
        if not candidate.startswith("{") and "{" in candidate:
            start = candidate.find("{")
            end = candidate.rfind("}")
            if end > start:
                candidate = candidate[start:end+1]
                
        try:
            parsed = json.loads(candidate)
            summary = parsed.get("summary", "")
            structured = parsed.get("structured", None)
            
            # If summary is blank, try other common keys
            if not summary:
                for k in ["explanation", "answer", "response", "message"]:
                    if k in parsed:
                        summary = parsed[k]
                        break
                if not summary and parsed:
                    summary = str(parsed)
            return {"summary": summary, "structured": structured}
        except Exception as e:
            logger.warning(f"Failed to parse LLM synthesis response as JSON: {e}. Falling back to raw text.")
            clean_text = re.sub(r"```(?:json)?\s*", "", text).strip()
            return {"summary": clean_text, "structured": None}

    def ask(self, question: str) -> dict:
        logger.info(f"Pipeline processing question: '{question}'")
        sql, cols, rows, err = self.sql_agent.safe_run(question)
        if err:
            logger.error(f"Pipeline SQL generation/execution failed: {err}")
            return {"error": err, "sql": sql, "rows": [], "columns": [], "full_row_count": 0}

        df = pd.DataFrame(rows, columns=cols) if rows else pd.DataFrame()
        preview_rows = df.head(20).to_dict(orient="records")
        
        # Construct markdown table in Python
        if not df.empty:
            table_markdown = df.head(20).to_markdown(index=False)
        else:
            table_markdown = "No rows returned."

        logger.info(f"Synthesizing explanation for question: '{question}' using query results.")
        prompt = ChatPromptTemplate.from_messages([
            ("system", ANSWER_SYS),
            ("human",
             "Question: {q}\nSQL: {sql}\nRows JSON: {rows}\nRow count: {n}"),
        ])
        chain = prompt | self.llm | StrOutputParser()
        
        try:
            raw_response = chain.invoke({
                "q": question, 
                "sql": sql,
                "rows": preview_rows, 
                "n": len(rows),
            })
            logger.info(f"Raw Synthesis Response:\n{raw_response}")
            parsed = self._parse_synthesis_response(raw_response)
        except Exception as e:
            logger.error(f"LLM synthesis invocation failed: {e}")
            parsed = {"summary": "Error running synthesis. Here is the raw SQL and results.", "structured": None}

        result = {
            "summary": parsed.get("summary", ""),
            "structured": parsed.get("structured"),
            "sql": sql,
            "columns": cols,
            "all_rows": rows,
            "full_row_count": len(rows),
            "table_markdown": table_markdown
        }
        logger.info(f"Pipeline finished processing. Summary length: {len(result['summary'])} chars, Row count: {result['full_row_count']}")
        return result