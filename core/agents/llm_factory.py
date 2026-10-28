import os
from typing import Optional, Dict, Any
import boto3
from dotenv import load_dotenv
from config import (
    AWS_REGION,
    AWS_ROLE_ARN,
    BEDROCK_MODEL_ID,
    AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY,
    AWS_SESSION_TOKEN,
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
    from langchain_aws import ChatBedrockConverse
except ImportError:
    ChatBedrockConverse = None

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

# Alias for backwards-compatibility across agent factories
get_openrouter_model = get_bedrock_model
