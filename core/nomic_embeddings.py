import os
from typing import List, Dict, Any, Optional
import requests
from dotenv import load_dotenv
from config import NOMIC_EMBED_BASE_URL, NOMIC_EMBED_MODEL, logger

# Load environment variables cleanly from .env
load_dotenv()

class NomicEmbeddingsClient:
    """
    Hardened HTTP client querying local Nomic Embed server running on llama-server (port 8088).
    Supports both OpenAI /v1/embeddings and llama.cpp native /embedding endpoints with dynamic model discovery.
    """
    def __init__(self, base_url: Optional[str] = None, model: Optional[str] = None):
        self.base_url = (base_url or os.getenv("NOMIC_EMBED_BASE_URL", NOMIC_EMBED_BASE_URL)).rstrip("/")
        self.model = (model or os.getenv("NOMIC_EMBED_MODEL", NOMIC_EMBED_MODEL)).strip()
        self._discovered_model: Optional[str] = None

    def _discover_active_model(self) -> str:
        """Dynamically fetches the exact loaded model identifier from llama-server /v1/models."""
        if self._discovered_model:
            return self._discovered_model
        try:
            r = requests.get(f"{self.base_url}/models", timeout=2)
            if r.status_code == 200:
                data = r.json()
                if "data" in data and len(data["data"]) > 0:
                    model_id = data["data"][0].get("id")
                    if model_id:
                        self._discovered_model = model_id
                        return model_id
        except Exception:
            pass
        return self.model

    def check_health(self) -> Dict[str, Any]:
        """
        Pings local embedding server at port 8088 and verifies whether embeddings are active.
        """
        try:
            active_model = self._discover_active_model()
            
            # 1. Test OpenAI-compatible endpoint /v1/embeddings
            test_res = requests.post(
                f"{self.base_url}/embeddings",
                json={"input": "ping", "model": active_model},
                timeout=2
            )
            if test_res.status_code == 200 and ("data" in test_res.json() or "embedding" in test_res.json()):
                return {"connected": True, "supported": True, "message": "🟢 Local Nomic Embeddings Active (Port 8088)"}
            
            # 2. Test native llama.cpp /embedding endpoint
            native_base = self.base_url.replace("/v1", "")
            test_native = requests.post(
                f"{native_base}/embedding",
                json={"content": "ping"},
                timeout=2
            )
            if test_native.status_code == 200:
                return {"connected": True, "supported": True, "message": "🟢 Local Nomic Embeddings Active (Port 8088)"}
            elif test_res.status_code == 501 or test_native.status_code == 501:
                return {
                    "connected": True,
                    "supported": False,
                    "message": "🟡 Port 8088 Active (Needs `--embedding` flag; Fallback Active)"
                }
            else:
                return {
                    "connected": True,
                    "supported": False,
                    "message": f"🟡 Server responded with status {test_res.status_code}"
                }
        except Exception as e:
            return {"connected": False, "supported": False, "message": "🔴 Port 8088 Offline (Fuzzy/ILIKE Fallback Active)"}

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Generates vector embeddings for a list of strings using the local llama-server.
        Tries OpenAI /v1/embeddings first, then falls back to native /embedding.
        """
        if not texts:
            return []

        active_model = self._discover_active_model()
        url = f"{self.base_url}/embeddings"
        payload = {"input": texts, "model": active_model}

        # 1. Try /v1/embeddings (OpenAI format)
        try:
            response = requests.post(url, json=payload, timeout=15)
            if response.status_code == 200:
                data = response.json()
                if "data" in data and len(data["data"]) > 0:
                    return [item["embedding"] for item in data["data"]]
        except Exception as e:
            logger.debug(f"OpenAI endpoint error on port 8088: {e}")

        # 2. Fallback to native llama-server /embedding
        native_url = f"{self.base_url.replace('/v1', '')}/embedding"
        results = []
        try:
            for text in texts:
                res = requests.post(native_url, json={"content": text}, timeout=15)
                res.raise_for_status()
                data = res.json()
                if isinstance(data, list) and len(data) > 0 and "embedding" in data[0]:
                    emb = data[0]["embedding"]
                    # If nested (e.g. [[...]])
                    if isinstance(emb, list) and len(emb) > 0 and isinstance(emb[0], list):
                        results.append(emb[0])
                    else:
                        results.append(emb)
                elif "embedding" in data:
                    results.append(data["embedding"])
                else:
                    raise ValueError(f"Unrecognized embedding response format: {data}")
            return results
        except Exception as e:
            raise RuntimeError(f"Failed to generate embeddings from local Nomic server at {url}: {e}")
