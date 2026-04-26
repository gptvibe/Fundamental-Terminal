from __future__ import annotations

from pydantic import BaseModel, Field


class FormulaMetadataPayload(BaseModel):
    formula_id: str
    formula_version: str
    human_readable_formula: str
    input_fields: list[str] = Field(default_factory=list)
    source_periods: list[str] = Field(default_factory=list)
    proxy_fallback_flags: list[str] = Field(default_factory=list)
    missing_input_behavior: str | None = None


class FormulaSummaryPayload(BaseModel):
    formula_id: str
    formula_version: str
    human_readable_formula: str


class FormulaListResponse(BaseModel):
    schema_version: str
    include_details: bool = False
    formulas: list[FormulaSummaryPayload | FormulaMetadataPayload] = Field(default_factory=list)
