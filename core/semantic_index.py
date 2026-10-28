import numpy as np
import pandas as pd
from typing import List, Tuple, Dict, Any, Optional
from core.nomic_embeddings import NomicEmbeddingsClient
from config import logger

try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False

try:
    from rapidfuzz import process, fuzz
    RAPIDFUZZ_AVAILABLE = True
except ImportError:
    RAPIDFUZZ_AVAILABLE = False

class SemanticValueIndex:
    """
    FAISS index builder & vector search utilizing local Nomic Embeddings (port 8088).
    Includes deterministic fallback to RapidFuzz / substring ILIKE matching if local vector server is offline.
    """
    def __init__(self):
        self.client = NomicEmbeddingsClient()
        self.index = None
        self.metadata: List[Tuple[str, str]] = []  # List of (column_name, exact_value)
        self.indexed_columns: List[str] = []
        self.table_name: Optional[str] = None
        self.vector_enabled: bool = False

    def build_index(self, records: List[Tuple[str, str]]):
        """Indexes low-cardinality categorical values: records = [(col, val), ...]"""
        if not records:
            return
            
        self.metadata = records
        self.indexed_columns = sorted(list(set(col for col, _ in records)))
        texts = [f"{col}: {val}" for col, val in records]
        
        if FAISS_AVAILABLE:
            try:
                embeddings = self.client.get_embeddings(texts)
                embeddings_np = np.array(embeddings, dtype="float32")
                faiss.normalize_L2(embeddings_np)
                
                dim = embeddings_np.shape[1]
                self.index = faiss.IndexFlatIP(dim)
                self.index.add(embeddings_np)
                self.vector_enabled = True
                logger.info(f"FAISS IndexFlatIP built with {len(records)} vectors from local Nomic Embed (dim {dim}).")
                return
            except Exception as e:
                logger.warning(f"Local Nomic Embed not available ({e}). Seamlessly activating string/fuzzy fallback.")
                self.vector_enabled = False
                self.index = None
        else:
            self.vector_enabled = False
            self.index = None

    def build_index_from_dataframe(self, df: pd.DataFrame, table_name: str, max_cardinality: int = 2000) -> Dict[str, Any]:
        """Scans DataFrame for categorical/text columns with low-to-medium cardinality and builds index."""
        self.table_name = table_name
        records: List[Tuple[str, str]] = []
        
        for col in df.columns:
            dtype = df[col].dtype
            if pd.api.types.is_object_dtype(dtype) or pd.api.types.is_string_dtype(dtype) or pd.api.types.is_categorical_dtype(dtype):
                unique_vals = [str(v).strip() for v in df[col].dropna().unique() if str(v).strip()]
                if 1 <= len(unique_vals) <= max_cardinality:
                    for val in unique_vals:
                        records.append((col, val))
                        
        self.build_index(records)
        return {
            "indexed_columns": self.indexed_columns,
            "total_entities": len(self.metadata),
            "vector_mode": self.vector_enabled
        }

    def resolve_term(self, query_term: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Resolves a query term against the index, returning candidates list."""
        if not self.metadata:
            return []
            
        clean_query = query_term.strip()
        if not clean_query:
            return []

        results = []

        # 1. Vector Search via Nomic Embeddings + FAISS
        if self.vector_enabled and self.index is not None and self.index.ntotal > 0:
            try:
                query_emb = np.array(self.client.get_embeddings([clean_query]), dtype="float32")
                faiss.normalize_L2(query_emb)
                scores, indices = self.index.search(query_emb, min(top_k, self.index.ntotal))
                
                for score, idx in zip(scores[0], indices[0]):
                    if idx != -1 and idx < len(self.metadata):
                        col, val = self.metadata[idx]
                        if float(score) >= 0.55: # Cosine similarity threshold
                            results.append({
                                "column": col,
                                "value": val,
                                "score": float(score),
                                "sql_clause": f"{col} = '{val.replace("'", "''")}'"
                            })
                if results:
                    return results
            except Exception as e:
                logger.warning(f"Vector search failed ({e}); falling back to fuzzy matching.")

        # 2. String / RapidFuzz Matching Fallback
        if RAPIDFUZZ_AVAILABLE and self.metadata:
            try:
                choices = [f"{col}: {val}" for col, val in self.metadata]
                matches = process.extract(clean_query, choices, scorer=fuzz.token_sort_ratio, limit=top_k)
                for match_str, score, idx in matches:
                    if score >= 55:
                        col, val = self.metadata[idx]
                        results.append({
                            "column": col,
                            "value": val,
                            "score": float(score / 100.0),
                            "sql_clause": f"{col} = '{val.replace("'", "''")}'"
                        })
            except Exception as e:
                logger.warning(f"RapidFuzz matching failed: {e}")

        # 3. Direct Substring / Case-Insensitive Matching
        if not results and self.metadata:
            q_lower = clean_query.lower()
            for col, val in self.metadata:
                if q_lower in val.lower() or val.lower() in q_lower:
                    results.append({
                        "column": col,
                        "value": val,
                        "score": 0.8,
                        "sql_clause": f"{col} = '{val.replace("'", "''")}'"
                    })
                if len(results) >= top_k:
                    break

        return results

    def resolve_entity(self, query_term: str, top_k: int = 3) -> str:
        """
        Formats resolved candidates for agent consumption.
        Returns explicit deterministic fallback string if no match found.
        """
        candidates = self.resolve_term(query_term, top_k=top_k)
        if not candidates:
            return "No exact match found; proceed with ILIKE or standard SQL filtering."

        lines = [f"Semantic Categorical Resolution for '{query_term}':"]
        for c in candidates:
            col = c["column"]
            val = c["value"]
            sql_clause = c["sql_clause"]
            score_info = f" (similarity: {c['score']:.2f})"
            lines.append(f"- Column: `{col}`, Exact Literal: `'{val}'`{score_info} -> Filter: `{sql_clause}`")
            
        return "\n".join(lines)