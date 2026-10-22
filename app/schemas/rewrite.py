"""Pydantic schemas for structured LLM output."""
from __future__ import annotations

from pydantic import BaseModel, Field


class Alternative(BaseModel):
    style: str = "neutral"
    text: str


class RewriteResponse(BaseModel):
    intent: str = "other"
    language: str = "ru"
    tone: str = "neutral"
    meaning: str = ""
    rewritten_text: str = ""
    alternatives: list[Alternative] = Field(default_factory=list)
    suggestion: str = ""
