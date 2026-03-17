import json
from pydantic import EmailStr, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Dict, List
from pydantic import field_validator


class EmailForwarderConfig(BaseSettings):
    from_email: EmailStr = Field(
        ..., validation_alias="FROM_EMAIL", description="Email address to send from"
    )
    subject_prefix: str | None = Field(
        default=None,
        validation_alias="SUBJECT_PREFIX",
        description="Prefix to add to forwarded email subjects",
    )
    email_bucket: str = Field(
        ..., validation_alias="EMAIL_BUCKET", description="S3 bucket name for storing emails"
    )
    email_key_prefix: str = Field(
        default="received/",
        validation_alias="EMAIL_KEY_PREFIX",
        description="S3 key prefix for stored emails",
    )
    forward_mapping: Dict[EmailStr, List[EmailStr]] = Field(
        ..., validation_alias="FORWARD_MAPPING", description="Mapping of recipient to forward addresses"
    )

    @field_validator("subject_prefix", mode="before")
    @classmethod
    def normalize_subject_prefix(cls, value):
        if isinstance(value, str):
            value = value.strip().strip("\"'")
        return value or None

    @field_validator("forward_mapping", mode="before")
    @classmethod
    def validate_forward_mapping(cls, value):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError as exc:
                raise ValueError("FORWARD_MAPPING must be valid JSON") from exc
        if not isinstance(value, dict):
            raise TypeError("FORWARD_MAPPING must be a JSON object")
        return value

    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")


CONFIG = EmailForwarderConfig()
