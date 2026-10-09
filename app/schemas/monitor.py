"""Pydantic schemas for Monitor management."""
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict


class MonitorBase(BaseModel):
    name: str = Field(..., min_length=1)
    talkgroup_ids: List[str] = Field(default_factory=list)
    start_event_labels: List[str] = Field(default_factory=lambda: ["EVT_TYPE"])
    geo_region: Optional[str] = None
    known_units: Optional[str] = None


class MonitorCreate(MonitorBase):
    pass


class MonitorUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1)
    enabled: Optional[bool] = None
    talkgroup_ids: Optional[List[str]] = None
    start_event_labels: Optional[List[str]] = None
    geo_region: Optional[str] = None
    known_units: Optional[str] = None


class MonitorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    enabled: bool
    talkgroup_ids: List[str]
    start_event_labels: List[str]
    geo_region: Optional[str] = None
    known_units: Optional[str] = None
