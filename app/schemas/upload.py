"""Pydantic v2 schemas for file upload endpoints."""
from typing import List
from pydantic import BaseModel, ConfigDict


class UploadAudioResponse(BaseModel):
    """Response returned upon successful audio upload."""
    model_config = ConfigDict(from_attributes=True)

    message: str
    filename: str
    size_mb: float
    path: str


class UploadStatusResponse(BaseModel):
    """Response returned by upload diagnostic status endpoint."""
    model_config = ConfigDict(from_attributes=True)

    online: bool
    ingest_directory: str
    allowed_extensions: List[str]
    server_version: str

