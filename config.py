"""
Configuration loader for DDP-API.

Loads organization credentials from:
1. AWS Secrets Manager (production)
2. Local JSON file (development fallback)
"""

import json
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# AWS Secrets Manager settings
AWS_SECRET_NAME = os.getenv("AWS_SECRET_NAME", "ddp-api/org-credentials")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# Local fallback config path
LOCAL_CONFIG_PATH = os.getenv("LOCAL_CONFIG_PATH", "config.local.json")

# Dedicated API key-store secret — decoupled from org-credentials (the Voatz
# org/credentials blob). The key store reads/writes ONLY this secret so a writer
# managing the Voatz side can never clobber issued keys, and so the key store has
# no dependency on get_config()'s required `organizations` field. The secret holds
# a single top-level `api_keys` array.
API_KEYS_SECRET_NAME = os.getenv("API_KEYS_SECRET_NAME", "ddp-api/api-keys")
API_KEYS_LOCAL_PATH = os.getenv("API_KEYS_LOCAL_PATH", "api-keys.local.json")


def load_from_secrets_manager() -> Optional[dict]:
    """Load configuration from AWS Secrets Manager."""
    try:
        import boto3
        from botocore.exceptions import ClientError, NoCredentialsError

        client = boto3.client("secretsmanager", region_name=AWS_REGION)
        response = client.get_secret_value(SecretId=AWS_SECRET_NAME)
        secret_string = response.get("SecretString")

        if secret_string:
            logger.info(f"Loaded configuration from Secrets Manager: {AWS_SECRET_NAME}")
            return json.loads(secret_string)

    except NoCredentialsError:
        logger.warning("No AWS credentials found, falling back to local config")
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        if error_code == "ResourceNotFoundException":
            logger.warning(f"Secret '{AWS_SECRET_NAME}' not found, falling back to local config")
        else:
            logger.error(f"Error loading from Secrets Manager: {e}")
    except Exception as e:
        logger.error(f"Unexpected error loading from Secrets Manager: {e}")

    return None


def load_from_local_file() -> Optional[dict]:
    """Load configuration from local JSON file."""
    if not os.path.exists(LOCAL_CONFIG_PATH):
        logger.warning(f"Local config file not found: {LOCAL_CONFIG_PATH}")
        return None

    try:
        with open(LOCAL_CONFIG_PATH, "r") as f:
            config = json.load(f)
            logger.info(f"Loaded configuration from local file: {LOCAL_CONFIG_PATH}")
            return config
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {LOCAL_CONFIG_PATH}: {e}")
    except Exception as e:
        logger.error(f"Error loading local config: {e}")

    return None


def load_config() -> dict:
    """
    Load configuration from Secrets Manager or local file.

    Returns:
        dict with keys:
            - organizations: list of org configs
            - zapier_webhook_url: webhook URL for push notifications
            - sync_interval_minutes: how often to check (default 30)
    """
    # Try Secrets Manager first (production)
    config = load_from_secrets_manager()

    # Fall back to local file (development)
    if config is None:
        config = load_from_local_file()

    # Validate config
    if config is None:
        raise RuntimeError(
            "No configuration found. Set up AWS Secrets Manager or create config.local.json"
        )

    if "organizations" not in config or not config["organizations"]:
        raise RuntimeError("Configuration must include 'organizations' list")

    # Set defaults
    config.setdefault("zapier_webhook_url", os.getenv("ZAPIER_WEBHOOK_URL"))
    config.setdefault("sync_interval_minutes", int(os.getenv("SYNC_INTERVAL_MINUTES", "30")))

    return config


# Singleton config instance (loaded once at startup)
_config = None


def get_config() -> dict:
    """Get the loaded configuration (cached)."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def reload_config() -> dict:
    """Force reload configuration from source."""
    global _config
    _config = load_config()
    return _config
