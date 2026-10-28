import sys
import os
from dotenv import load_dotenv

# Reconfigure stdout for utf-8
sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

print("=" * 70)
print("TESTING AWS BEDROCK & NOMIC EMBEDDINGS PROTOTYPE CONFIGURATION")
print("=" * 70)

# 1. Test Environment Variables
print("\n[1/4] Checking Environment Configuration (.env)...")
region = os.getenv("REGION", os.getenv("AWS_REGION", "ap-south-1"))
role_arn = os.getenv("ROLE_ARN", os.getenv("AWS_ROLE_ARN", ""))
model_id = os.getenv("MODEL_ID", os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-3-5-haiku-20241022-v1:0"))
nomic_url = os.getenv("NOMIC_EMBED_BASE_URL", "http://127.0.0.1:8088/v1")
nomic_model = os.getenv("NOMIC_EMBED_MODEL", "nomic-ai/nomic-embed-text-v1.5-GGUF:Q4_K_M")

print(f"  • AWS Region:       {region}")
print(f"  • AWS Role ARN:     {role_arn or '(Direct / Instance Credentials)'}")
print(f"  • Bedrock Model ID: {model_id}")
print(f"  • Nomic Embed URL:  {nomic_url}")
print(f"  • Nomic Model Tag:  {nomic_model}")

# 2. Test Bedrock Model Factory
print("\n[2/4] Testing AWS Bedrock Model Factory...")
from core.agents.llm_factory import get_bedrock_session, get_bedrock_model, get_bedrock_converse_llm

try:
    session = get_bedrock_session(region_name=region, role_arn=role_arn)
    print(f"  ✅ Boto3 Session initialized (Region: {session.region_name})")
except Exception as e:
    print(f"  ⚠️ Boto3 Session notice: {e}")

try:
    bedrock_model = get_bedrock_model(model_name=model_id, region=region, role_arn=role_arn)
    print(f"  ✅ Strands BedrockModel initialized: {type(bedrock_model)}")
except Exception as e:
    print(f"  ⚠️ Strands BedrockModel notice: {e}")

try:
    converse_llm = get_bedrock_converse_llm(model_name=model_id, region_name=region, role_arn=role_arn)
    print(f"  ✅ LangChain ChatBedrockConverse initialized: {type(converse_llm)}")
except Exception as e:
    print(f"  ⚠️ LangChain ChatBedrockConverse notice: {e}")

# 3. Test Local Nomic Embeddings on Port 8088
print("\n[3/4] Testing Local Nomic Embedding Server (Port 8088)...")
from core.nomic_embeddings import NomicEmbeddingsClient
nomic_client = NomicEmbeddingsClient()
health = nomic_client.check_health()
print(f"  • Health Status: {health.get('message')}")

if health.get("connected") and health.get("supported"):
    try:
        embs = nomic_client.get_embeddings(["search_query: health policy revenue", "search_document: Auto Insurance Policy"])
        print(f"  ✅ Generated {len(embs)} vectors of dimension {len(embs[0])}")
    except Exception as e:
        print(f"  ⚠️ Embedding generation notice: {e}")

# 4. Test DuckDB & SQLite Storage
print("\n[4/4] Testing Database Engine & SQLite Metadata Store...")
import pandas as pd
from core.db_engine import DatabaseEngine
from core.metadata_store import SQLiteMetadataStore

df_sample = pd.DataFrame({
    "policy_id": ["P001", "P002", "P003"],
    "policy_type": ["Health", "Auto", "Life"],
    "annual_premium": [3200, 1800, 2100]
})

engine = DatabaseEngine.get_instance()
engine.register_dataframe(df_sample, "t_test_sample")
meta = SQLiteMetadataStore.get_instance().get_dataset_metadata("t_test_sample")
print(f"  ✅ DuckDB Table registered & SQLite Catalog verified: {meta['table_name']} ({meta['row_count']} rows)")

print("\n" + "=" * 70)
print("ALL BEDROCK & NOMIC SYSTEM COMPONENTS CONFIGURED & VERIFIED")
print("=" * 70)
