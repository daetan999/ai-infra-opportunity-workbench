from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EvidenceTypeValue = Literal[
    "verified_fact",
    "user_provided",
    "hypothesis",
    "generated_suggestion",
]


class InputModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)


class AccountCreate(InputModel):
    name: str = Field(min_length=2, max_length=200)
    industry: str = Field(min_length=2, max_length=120)
    geography: str = Field(min_length=2, max_length=120)
    segment: str = Field(min_length=2, max_length=120)
    fictional: bool = False


class SignalCreate(InputModel):
    summary: str = Field(min_length=3, max_length=2000)
    source: str = Field(min_length=2, max_length=1000)
    source_url: str | None = Field(default=None, max_length=2000)
    source_date: date
    evidence_type: EvidenceTypeValue
    confidence: float = Field(ge=0, le=1)
    notes: str = Field(default="", max_length=4000)


class WorkloadCreate(InputModel):
    name: str = Field(min_length=3, max_length=240)
    workload_type: str = Field(min_length=2, max_length=80)
    description: str = Field(min_length=3, max_length=4000)
    business_metric: str = Field(min_length=2, max_length=240)
    success_metrics: str = Field(min_length=3, max_length=2000)
    technical_requirements: str = Field(min_length=3, max_length=2000)
    confidence: float = Field(ge=0, le=1)
    deployment_pattern: str | None = Field(default=None, max_length=120)


class StakeholderCreate(InputModel):
    name: str = Field(min_length=2, max_length=200)
    title: str = Field(min_length=2, max_length=200)
    role: Literal[
        "champion",
        "economic_buyer",
        "executive_sponsor",
        "technical_buyer",
        "procurement",
        "security",
        "operations",
    ]
    engagement_status: Literal["unknown", "identified", "engaged", "confirmed"]
    confidence: float = Field(ge=0, le=1)


class DiscoveryCreate(InputModel):
    category: Literal[
        "measurable_pain",
        "business_impact",
        "technical_fit",
        "urgency",
        "executive_sponsorship",
        "champion_strength",
        "buying_process",
        "procurement_friction",
        "competitive_position",
        "access_to_technical_evidence",
        "poc_success",
        "poc_timeline",
        "general",
    ]
    question: str = Field(min_length=3, max_length=2000)
    answer: str = Field(min_length=1, max_length=5000)
    source: str = Field(min_length=2, max_length=1000)
    source_url: str | None = Field(default=None, max_length=2000)
    source_date: date
    evidence_type: EvidenceTypeValue
    confidence: float = Field(ge=0, le=1)
    notes: str = Field(default="", max_length=4000)
