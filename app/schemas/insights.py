"""Pydantic v2 schemas for Insights API endpoints."""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class TrendData(BaseModel):
    current: int = 0
    previous: int = 0
    delta: int = 0
    direction: str = "flat"  # "up", "down", "flat"
    basis: Optional[str] = None


class LiveCpmResponse(BaseModel):
    calls_per_minute: int
    window_minutes: int = 1
    minute_start: Optional[str] = None
    minute_end: Optional[str] = None
    trend: Optional[TrendData] = None


class AttachedEventInfo(BaseModel):
    id: int
    event_id: str
    status: str
    event_type: Optional[str] = None


class TransmissionEntities(BaseModel):
    units: List[str] = Field(default_factory=list)
    locations: List[str] = Field(default_factory=list)
    call_types: List[str] = Field(default_factory=list)
    status: List[str] = Field(default_factory=list)


class SearchResultItem(BaseModel):
    id: int
    timestamp: Optional[str] = None
    talkgroup: Optional[str] = None
    transcript: str
    duration: float = 0.0
    file_size: int = 0
    confidence: Optional[float] = None
    audio_path: Optional[str] = None
    attached_events: List[AttachedEventInfo] = Field(default_factory=list)
    entities: TransmissionEntities = Field(default_factory=TransmissionEntities)


class SearchTranscriptionsResponse(BaseModel):
    total: int
    results: List[SearchResultItem]


class HourActivityItem(BaseModel):
    hour: int
    count: int


class SummaryHoursResponse(BaseModel):
    date: str
    hours: List[HourActivityItem]


class HourSummaryItem(BaseModel):
    id: int
    date: str
    hour: int
    text: str
    format: str = "markdown"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    created_by: Optional[str] = None


class ListHourSummariesResponse(BaseModel):
    date: str
    format: str = "markdown"
    summaries: List[HourSummaryItem]


class GenerateHourSummaryResponse(BaseModel):
    created: bool
    format: str = "markdown"
    summary: HourSummaryItem


class DeleteHourSummaryResponse(BaseModel):
    success: bool


# Insights /stats schemas
class InsightsSummaryTrends(BaseModel):
    total_transcriptions: Optional[TrendData] = None
    calls_last_minute: Optional[TrendData] = None
    unique_talkgroups: Optional[TrendData] = None


class InsightsSummary(BaseModel):
    total: int
    unique_talkgroups: int
    avg_duration: float
    total_airtime: Optional[float] = None
    peak_hour: Optional[str] = None
    calls_per_minute: float
    calls_last_minute: Optional[int] = None
    calls_per_minute_window: Optional[int] = 1
    is_multi_day: Optional[bool] = None
    range_days: Optional[int] = None
    trends: Optional[InsightsSummaryTrends] = None


class ActivityPoint(BaseModel):
    label: str
    count: int
    events_count: int = 0
    hour: Optional[int] = None
    date: Optional[str] = None


class TalkgroupEntry(BaseModel):
    talkgroup: str
    count: int
    duration: Optional[float] = None
    avg_duration: Optional[float] = None
    percentage: Optional[float] = None


class HeatmapHourCell(BaseModel):
    hour: int
    label: str
    count: int
    duration: float


class HeatmapDayRow(BaseModel):
    day: int  # 0=Sun .. 6=Sat
    day_label: str
    hours: List[HeatmapHourCell]
    day_total: int


class DiurnalHeatmapData(BaseModel):
    matrix: List[HeatmapDayRow]
    max_count: int
    total_calls: int
    total_airtime: float
    peak_day: str
    peak_hour: str
    range_start: str
    range_end: str


class RtfHourlyPoint(BaseModel):
    hour: int
    label: str
    count: int
    audio_s: float
    proc_s: float
    rtf: float


class RtfTelemetry(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    rtf: float
    speedup: float
    total_audio_s: float
    total_proc_s: float
    avg_latency_ms: float
    avg_duration_s: float
    avg_confidence: float
    model_used: str
    status: str
    insufficient_data: bool = False
    timeline: List[RtfHourlyPoint] = Field(default_factory=list)


class TacticalEntityItem(BaseModel):
    canonical: str
    label: str
    freq: int
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    sample_tx_id: Optional[int] = None


class TacticalNerSummary(BaseModel):
    all: List[TacticalEntityItem] = Field(default_factory=list)
    units: List[TacticalEntityItem] = Field(default_factory=list)
    call_types: List[TacticalEntityItem] = Field(default_factory=list)
    locations: List[TacticalEntityItem] = Field(default_factory=list)
    status: List[TacticalEntityItem] = Field(default_factory=list)
    total_entities_detected: int = 0
    insufficient_data: bool = False


class AnomalyDriver(BaseModel):
    talkgroup: str
    count: int
    percentage: float


class AnomalyIncidentRecord(BaseModel):
    date: Optional[str] = None
    hour: int
    time_window: str
    z_score: float
    observed: int
    baseline: int
    primary_driver: str
    likely_incident: Optional[str] = None


class AnomalyTimelinePoint(BaseModel):
    hour: int
    label: str
    observed: int
    baseline: int
    upper_bound: float
    z_score: float
    is_anomaly: bool


class TrafficAnomalyTelemetry(BaseModel):
    current_hour_label: str
    observed: int
    baseline: int
    surge_percentage: float
    z_score: float
    severity: str
    status_label: str
    primary_driver: str
    drivers: List[AnomalyDriver] = Field(default_factory=list)
    timeline: List[AnomalyTimelinePoint] = Field(default_factory=list)
    recent_anomalies: List[AnomalyIncidentRecord] = Field(default_factory=list)
    insufficient_data: bool = False
    is_multi_day: bool = False
    range_days: Optional[int] = None


class AsrQualitySpectrum(BaseModel):
    high_count: int
    high_percentage: float
    moderate_count: int
    moderate_percentage: float
    low_count: int
    low_percentage: float
    mean_confidence: float
    total_evaluated: int
    insufficient_data: bool = False


class RecentTranscriptionItem(BaseModel):
    id: int
    timestamp: Optional[str] = None
    talkgroup: Optional[str] = None
    transcript: str
    duration: float = 0.0
    attached_events: List[Dict[str, Any]] = Field(default_factory=list)


class InsightsStatsResponse(BaseModel):
    summary: InsightsSummary
    activity: List[ActivityPoint]
    talkgroups: List[TalkgroupEntry]
    talkgroups_all: List[TalkgroupEntry]
    recent: List[RecentTranscriptionItem]
    heatmap: DiurnalHeatmapData
    rtf: RtfTelemetry
    ner: TacticalNerSummary
    anomaly: TrafficAnomalyTelemetry
    asr_quality: AsrQualitySpectrum
