from pydantic import BaseModel, EmailStr, Field
from typing import Dict, List
import json
from pathlib import Path


class EmailForwarderConfig(BaseModel):
    from_email: EmailStr = Field(..., description="Email address to send from")
    subject_prefix: str = Field(
        default="", description="Prefix to add to forwarded email subjects"
    )
    email_bucket: str = Field(..., description="S3 bucket name for storing emails")
    email_key_prefix: str = Field(
        default="received/", description="S3 key prefix for stored emails"
    )
    forward_mapping: Dict[EmailStr, List[EmailStr]] = Field(
        ..., description="Mapping of recipient to forward addresses"
    )

    @classmethod
    def from_json(cls, file_path: str):
        with open(file_path, "r") as f:
            data = json.load(f)
        return cls(**data)


# Load config
CONFIG = EmailForwarderConfig.from_json(str(Path(__file__).parent / "config.json"))
