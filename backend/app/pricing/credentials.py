"""Tenant pricing credentials; no host credentials or model-supplied tokens."""

from __future__ import annotations

import asyncio

from pydantic import BaseModel, ConfigDict, Field

from app.mcp.credentials import decrypt_secret
from app.mcp.store import get_integration
from app.pricing.providers.aws import AwsPricingProvider
from app.pricing.providers.azure import AzurePricingProvider, PricingUnavailable, UnsupportedPrice
from app.pricing.providers.gcp import GoogleCloudPricingProvider
from app.pricing.providers.huawei import HuaweiPricingProvider, HuaweiRateSpec
from app.sales.sheets import validate_service_account_config


class AwsCredential(BaseModel):
    model_config = ConfigDict(extra="forbid")
    access_key_id: str = Field(min_length=16, max_length=128)
    secret_access_key: str = Field(min_length=16, max_length=256)
    session_token: str | None = Field(default=None, max_length=8192)


def validate_pricing_secret(provider: str, secret: str) -> None:
    if provider == "aws":
        AwsCredential.model_validate_json(secret)
    elif provider == "gcp":
        validate_service_account_config(secret)
    elif provider == "huawei":
        if not secret.strip() or len(secret) > 8192 or any(char.isspace() for char in secret):
            raise ValueError("invalid Huawei IAM token")
    else:
        raise ValueError("provider does not require tenant credentials")


def _gcp_token(secret: str) -> str:
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account
    credentials = service_account.Credentials.from_service_account_info(
        validate_service_account_config(secret),
        scopes=["https://www.googleapis.com/auth/cloud-platform.read-only"],
    )
    request = Request()

    def bounded_request(**kwargs):
        kwargs["timeout"] = 15.0
        return request(**kwargs)

    credentials.refresh(bounded_request)
    if not credentials.token:
        raise PricingUnavailable("Google Cloud did not issue a pricing token")
    return str(credentials.token)


async def provider_for_mapping(db, principal, mapping, huawei_spec: HuaweiRateSpec | None = None):
    if mapping.provider == "azure":
        if not mapping.meter:
            raise UnsupportedPrice("Azure live capture needs an exact reviewed meter")
        return AzurePricingProvider()
    row = get_integration(db, principal.org_id, f"pricing_{mapping.provider}")
    if row is None or not row.enabled or not row.secret_ciphertext:
        raise UnsupportedPrice("tenant pricing credentials are not configured")
    try:
        secret = decrypt_secret(row.secret_ciphertext)
        validate_pricing_secret(mapping.provider, secret)
        if mapping.provider == "aws":
            import boto3
            from botocore.config import Config
            credential = AwsCredential.model_validate_json(secret)
            client = boto3.client(
                "pricing", region_name="us-east-1",
                aws_access_key_id=credential.access_key_id,
                aws_secret_access_key=credential.secret_access_key,
                aws_session_token=credential.session_token,
                config=Config(connect_timeout=5, read_timeout=15,
                              retries={"max_attempts": 2, "mode": "standard"}),
            )
            return AwsPricingProvider(service_code=mapping.service, client=client)
        if mapping.provider == "gcp":
            return GoogleCloudPricingProvider(service_id=mapping.service,
                                             bearer_token=await asyncio.to_thread(_gcp_token, secret))
        if mapping.provider == "huawei":
            if huawei_spec is None:
                raise UnsupportedPrice("Huawei requires explicit reviewed rate dimensions")
            if (huawei_spec.region, huawei_spec.resource_spec, huawei_spec.resource_type,
                huawei_spec.cloud_service_type) != (mapping.region, mapping.sku, mapping.meter, mapping.service):
                raise UnsupportedPrice("Huawei dimensions differ from the approved mapping")
            return HuaweiPricingProvider(spec=huawei_spec, auth_token=secret)
    except UnsupportedPrice:
        raise
    except Exception as exc:
        raise PricingUnavailable("tenant pricing authorization failed") from exc
    raise UnsupportedPrice("unknown pricing provider")
