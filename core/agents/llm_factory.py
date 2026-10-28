import os
from typing import Optional, Dict, Any, List
import boto3
from dotenv import load_dotenv
from config import (
    AWS_REGION,
    AWS_ROLE_ARN,
    BEDROCK_MODEL_ID,
    AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY,
    AWS_SESSION_TOKEN,
    OPENROUTER_API_KEY,
    OPENROUTER_BASE_URL,
    OPENROUTER_MODEL,
    LLM_PROVIDER,
    logger
)

# Load environment variables cleanly from .env file
load_dotenv()

try:
    from strands.models.bedrock import BedrockModel
except ImportError:
    try:
        from strands.models import BedrockModel
    except ImportError:
        BedrockModel = None

try:
    from strands.models.openai import OpenAIModel
except ImportError:
    try:
        from strands.models import OpenAIModel
    except ImportError:
        OpenAIModel = None

try:
    from langchain_aws import ChatBedrockConverse
except ImportError:
    ChatBedrockConverse = None

from dataclasses import dataclass

@dataclass
class ModelCapability:
    """Capability contract describing model features, token limits, and orchestration parameters."""
    model_id: str
    provider: str
    context_window: int
    supports_tools: bool
    supports_streaming: bool
    supports_system_prompt: bool
    recommended_temperature: float = 0.0

# Supported Model Capability Registry
MODEL_REGISTRY: Dict[str, ModelCapability] = {
    # Amazon Bedrock Primary Models
    "anthropic.claude-3-5-haiku-20241022-v1:0": ModelCapability(
        model_id="anthropic.claude-3-5-haiku-20241022-v1:0",
        provider="bedrock",
        context_window=200_000,
        supports_tools=True,
        supports_streaming=True,
        supports_system_prompt=True,
        recommended_temperature=0.0
    ),
    "anthropic.claude-haiku-4-5": ModelCapability(
        model_id="anthropic.claude-haiku-4-5",
        provider="bedrock",
        context_window=200_000,
        supports_tools=True,
        supports_streaming=True,
        supports_system_prompt=True,
        recommended_temperature=0.0
    ),
    "bedrock.gpt-5-6-luna": ModelCapability(
        model_id="bedrock.gpt-5-6-luna",
        provider="bedrock",
        context_window=128_000,
        supports_tools=True,
        supports_streaming=True,
        supports_system_prompt=True,
        recommended_temperature=0.0
    ),
    "bedrock.moonshot-kimi-k3": ModelCapability(
        model_id="bedrock.moonshot-kimi-k3",
        provider="bedrock",
        context_window=128_000,
        supports_tools=True,
        supports_streaming=True,
        supports_system_prompt=True,
        recommended_temperature=0.0
    ),
    # OpenRouter Configurable Secondary Models
    "openai/gpt-4o-mini": ModelCapability(
        model_id="openai/gpt-4o-mini",
        provider="openrouter",
        context_window=128_000,
        supports_tools=True,
        supports_streaming=True,
        supports_system_prompt=True,
        recommended_temperature=0.0
    ),
    "anthropic/claude-3.5-haiku": ModelCapability(
        model_id="anthropic/claude-3.5-haiku",
        provider="openrouter",
        context_window=200_000,
        supports_tools=True,
        supports_streaming=True,
        supports_system_prompt=True,
        recommended_temperature=0.0
    ),
}

def get_bedrock_session(
    region_name: Optional[str] = None,
    role_arn: Optional[str] = None
) -> boto3.Session:
    """
    Creates an authenticated boto3 Session for AWS Bedrock.
    If a Role ARN is configured, assumes the IAM role via AWS Security Token Service (STS).
    Otherwise, uses environment-configured AWS credentials or default credential chain.
    """
    region = (region_name or AWS_REGION or os.getenv("REGION", "ap-south-1")).strip()
    target_role_arn = (role_arn or AWS_ROLE_ARN or os.getenv("ROLE_ARN", "")).strip()

    # 1. Assume IAM Role via STS if ROLE_ARN is provided
    if target_role_arn:
        try:
            logger.info(f"Assuming Bedrock IAM role: '{target_role_arn}' in region '{region}'...")
            sts = boto3.client("sts", region_name=region)
            assume_role_response = sts.assume_role(
                RoleArn=target_role_arn,
                RoleSessionName="session_for_llm"
            )
            creds = assume_role_response["Credentials"]
            return boto3.Session(
                aws_access_key_id=creds["AccessKeyId"],
                aws_secret_access_key=creds["SecretAccessKey"],
                aws_session_token=creds["SessionToken"],
                region_name=region
            )
        except Exception as e:
            logger.warning(f"STS AssumeRole for '{target_role_arn}' failed ({e}). Falling back to direct credentials/session.")

    # 2. Fallback to direct credentials if configured
    access_key = (AWS_ACCESS_KEY_ID or os.getenv("AWS_ACCESS_KEY_ID", "")).strip()
    secret_key = (AWS_SECRET_ACCESS_KEY or os.getenv("AWS_SECRET_ACCESS_KEY", "")).strip()
    session_token = (AWS_SESSION_TOKEN or os.getenv("AWS_SESSION_TOKEN", "")).strip() or None

    if access_key and secret_key:
        return boto3.Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            aws_session_token=session_token,
            region_name=region
        )

    # 3. Default environment / instance profile session
    return boto3.Session(region_name=region)

def get_bedrock_model(
    model_name: Optional[str] = None,
    region: Optional[str] = None,
    role_arn: Optional[str] = None,
    api_key: Optional[str] = None
) -> Any:
    """
    Initializes a Strands BedrockModel for autonomous multi-agent tool execution using Claude 3.5 Haiku.
    """
    active_model_id = (model_name or BEDROCK_MODEL_ID or os.getenv("MODEL_ID", "anthropic.claude-3-5-haiku-20241022-v1:0")).strip()
    boto_sess = get_bedrock_session(region_name=region, role_arn=role_arn)

    logger.info(f"Initializing AWS Bedrock model: '{active_model_id}' (Region: {boto_sess.region_name})")

    if BedrockModel is not None:
        return BedrockModel(
            model_id=active_model_id,
            boto_session=boto_sess,
            temperature=0.0,
            max_tokens=4000
        )
    else:
        raise ImportError("strands-agents BedrockModel is required for Bedrock agent orchestration.")

def get_bedrock_converse_llm(
    model_name: Optional[str] = None,
    region_name: Optional[str] = None,
    role_arn: Optional[str] = None
) -> Any:
    """
    Initializes ChatBedrockConverse (LangChain-AWS) with STS assume-role credentials for streaming inference.
    """
    if ChatBedrockConverse is None:
        raise ImportError("langchain-aws is required. Run `pip install langchain-aws`.")

    region = (region_name or AWS_REGION or os.getenv("REGION", "ap-south-1")).strip()
    target_role_arn = (role_arn or AWS_ROLE_ARN or os.getenv("ROLE_ARN", "")).strip()
    active_model_id = (model_name or BEDROCK_MODEL_ID or os.getenv("MODEL_ID", "anthropic.claude-3-5-haiku-20241022-v1:0")).strip()

    # If Role ARN provided, assume role
    if target_role_arn:
        try:
            sts = boto3.client("sts", region_name=region)
            response = sts.assume_role(
                RoleArn=target_role_arn,
                RoleSessionName="session_for_llm"
            )
            credentials = response["Credentials"]
            return ChatBedrockConverse(
                model_id=active_model_id,
                region_name=region,
                aws_access_key_id=credentials["AccessKeyId"],
                aws_secret_access_key=credentials["SecretAccessKey"],
                aws_session_token=credentials["SessionToken"],
                temperature=0.0,
                max_tokens=4000
            )
        except Exception as e:
            logger.warning(f"ChatBedrockConverse STS assume role failed ({e}). Trying direct credentials.")

    access_key = (AWS_ACCESS_KEY_ID or os.getenv("AWS_ACCESS_KEY_ID", "")).strip()
    secret_key = (AWS_SECRET_ACCESS_KEY or os.getenv("AWS_SECRET_ACCESS_KEY", "")).strip()
    session_token = (AWS_SESSION_TOKEN or os.getenv("AWS_SESSION_TOKEN", "")).strip() or None

    return ChatBedrockConverse(
        model_id=active_model_id,
        region_name=region,
        aws_access_key_id=access_key if access_key else None,
        aws_secret_access_key=secret_key if secret_key else None,
        aws_session_token=session_token,
        temperature=0.0,
        max_tokens=4000
    )

def get_openrouter_model(
    model_name: Optional[str] = None,
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    temperature: float = 0.0,
    max_tokens: int = 4000,
    **kwargs
) -> Any:
    """
    Initializes a Strands OpenAIModel configured for OpenRouter OpenAI-compatible API execution.
    """
    if OpenAIModel is None:
        raise ImportError(
            "strands-agents OpenAI provider is required for OpenRouter integration. "
            "Run `pip install 'strands-agents[openai]'`."
        )

    active_api_key = (api_key or OPENROUTER_API_KEY or os.getenv("OPENROUTER_API_KEY", "")).strip()
    if not active_api_key:
        raise ValueError(
            "OpenRouter API key is missing. Set OPENROUTER_API_KEY in .env or pass api_key explicitly."
        )

    active_model = (model_name or OPENROUTER_MODEL or os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")).strip()
    active_base_url = (base_url or OPENROUTER_BASE_URL or os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")).strip()

    logger.info(f"Initializing OpenRouter model: '{active_model}' via {active_base_url}")

    return OpenAIModel(
        model_id=active_model,
        client_args={
            "api_key": active_api_key,
            "base_url": active_base_url,
        },
        params={
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
    )

def get_model_capability(model_id: str) -> Optional[ModelCapability]:
    """Retrieves capability contract for a designated model ID."""
    return MODEL_REGISTRY.get(model_id)

def list_supported_models() -> List[str]:
    """Lists all registered models across primary (Bedrock) and secondary (OpenRouter) providers."""
    return list(MODEL_REGISTRY.keys())

def get_model(
    model_name: Optional[str] = None,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    region: Optional[str] = None,
    role_arn: Optional[str] = None,
    **kwargs
) -> Any:
    """
    Unified model factory supporting configurable providers:
    - "openrouter" -> OpenRouter (default for local evaluation)
    - "bedrock"    -> Amazon Bedrock (existing supported provider)
    """
    resolved_provider = (provider or LLM_PROVIDER or "bedrock").lower().strip()

    # Route based on model naming if provider not explicitly specified
    if provider is None and model_name:
        if "/" in model_name or model_name.startswith(("gpt-", "deepseek", "claude-3-5", "claude-3-7")):
            resolved_provider = "openrouter"
        elif "anthropic." in model_name or "amazon." in model_name or "meta." in model_name:
            resolved_provider = "bedrock"

    if resolved_provider == "openrouter":
        return get_openrouter_model(model_name=model_name, api_key=api_key, **kwargs)
    elif resolved_provider == "bedrock":
        return get_bedrock_model(model_name=model_name, region=region, role_arn=role_arn, api_key=api_key, **kwargs)
    else:
        raise ValueError(f"Unsupported LLM provider '{resolved_provider}'. Choose 'openrouter' or 'bedrock'.")
