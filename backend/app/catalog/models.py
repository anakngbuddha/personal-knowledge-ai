from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models import (
    DeploymentModel,
    EdgeStatus,
    LifecycleStatus,
    Ownership,
    RelationType,
)


def slugify(text: str) -> str:
    s = text.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_-]+", "-", s)
    return s.strip("-")


# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------


class CapabilityIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    slug: str | None = Field(None, max_length=128)
    category: str = Field(..., min_length=2, max_length=128)
    description: str | None = None

    @field_validator("slug", mode="before")
    @classmethod
    def default_slug(cls, v: str | None, values: Any) -> str:
        if v:
            return slugify(v)
        # fallback will be set during creation if None
        return ""


class CapabilityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    slug: str
    category: str
    description: str | None = None
    created_at: datetime
    product_count: int = 0


class ProductCapabilityIn(BaseModel):
    capability_id: uuid.UUID
    proficiency: str = Field("native", max_length=32)
    notes: str | None = None

    @field_validator("proficiency")
    @classmethod
    def validate_proficiency(cls, v: str) -> str:
        valid = {"native", "supported", "via_integration"}
        if v.lower() not in valid:
            raise ValueError(f"proficiency must be one of: {sorted(valid)}")
        return v.lower()


class ProductCapabilityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    capability_id: uuid.UUID
    name: str
    slug: str
    category: str
    description: str | None = None
    proficiency: str
    notes: str | None = None


# ---------------------------------------------------------------------------
# Products
# ---------------------------------------------------------------------------


class ProductIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=512)
    slug: str | None = Field(None, max_length=128)
    vendor: str = Field(..., min_length=1, max_length=255)
    ownership: str = Field(Ownership.OWN, max_length=16)
    category: str = Field(..., min_length=2, max_length=128)
    tier: str = Field("Core", max_length=64)
    deployment_model: str = Field(DeploymentModel.CLOUD, max_length=32)
    licensing_model: str = Field("subscription", max_length=64)
    target_segment: str = Field("Enterprise", max_length=64)
    lifecycle_status: str = Field(LifecycleStatus.GA, max_length=32)
    prerequisites: str | None = None
    support_path: str | None = None
    description: str | None = None
    collateral_document_ids: list[uuid.UUID] = Field(default_factory=list)

    # Resold-specific governance fields
    partner_tier: str | None = None
    margin_band: str | None = None
    support_owner: str | None = None  # vendor | reseller | joint
    contract_constraints: str | None = None
    source_of_truth_url: str | None = None

    @field_validator("ownership")
    @classmethod
    def validate_ownership(cls, v: str) -> str:
        v_clean = v.lower()
        if v_clean not in {Ownership.OWN, Ownership.RESOLD}:
            raise ValueError(f"ownership must be '{Ownership.OWN}' or '{Ownership.RESOLD}'")
        return v_clean

    @field_validator("deployment_model")
    @classmethod
    def validate_deployment_model(cls, v: str) -> str:
        v_clean = v.lower()
        if v_clean not in DeploymentModel.ALL:
            raise ValueError(f"deployment_model must be one of: {sorted(DeploymentModel.ALL)}")
        return v_clean

    @field_validator("lifecycle_status")
    @classmethod
    def validate_lifecycle_status(cls, v: str) -> str:
        if v not in LifecycleStatus.ALL:
            raise ValueError(f"lifecycle_status must be one of: {sorted(LifecycleStatus.ALL)}")
        return v


class ProductUpdate(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=512)
    slug: str | None = Field(None, max_length=128)
    vendor: str | None = Field(None, min_length=1, max_length=255)
    ownership: str | None = None
    category: str | None = None
    tier: str | None = None
    deployment_model: str | None = None
    licensing_model: str | None = None
    target_segment: str | None = None
    lifecycle_status: str | None = None
    prerequisites: str | None = None
    support_path: str | None = None
    description: str | None = None
    collateral_document_ids: list[uuid.UUID] | None = None
    partner_tier: str | None = None
    margin_band: str | None = None
    support_owner: str | None = None
    contract_constraints: str | None = None
    source_of_truth_url: str | None = None


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    slug: str
    vendor: str
    ownership: str
    category: str
    tier: str
    deployment_model: str
    licensing_model: str
    target_segment: str
    lifecycle_status: str
    prerequisites: str | None = None
    support_path: str | None = None
    description: str | None = None
    collateral_document_ids: list[uuid.UUID] | None = None

    partner_tier: str | None = None
    margin_band: str | None = None
    support_owner: str | None = None
    contract_constraints: str | None = None
    source_of_truth_url: str | None = None

    created_at: datetime
    updated_at: datetime
    capabilities: list[ProductCapabilityOut] = Field(default_factory=list)
    edge_count: int = 0


# ---------------------------------------------------------------------------
# Product Edges
# ---------------------------------------------------------------------------


class ProductEdgeIn(BaseModel):
    source_product_id: uuid.UUID
    target_product_id: uuid.UUID
    relation_type: str
    evidence: str = Field(..., min_length=3)
    confidence: float = Field(1.0, ge=0.0, le=1.0)
    document_id: uuid.UUID | None = None
    is_ai_suggested: bool = False
    status: str = EdgeStatus.APPROVED

    @field_validator("relation_type")
    @classmethod
    def validate_relation(cls, v: str) -> str:
        v_clean = v.lower()
        if v_clean not in RelationType.ALL:
            raise ValueError(f"relation_type must be one of: {sorted(RelationType.ALL)}")
        return v_clean

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        v_clean = v.lower()
        if v_clean not in EdgeStatus.ALL:
            raise ValueError(f"status must be one of: {sorted(EdgeStatus.ALL)}")
        return v_clean


class ProductEdgeUpdate(BaseModel):
    relation_type: str | None = None
    evidence: str | None = None
    confidence: float | None = None
    status: str | None = None
    rejection_reason: str | None = None


class ProductEdgeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    workspace_id: uuid.UUID
    source_product_id: uuid.UUID
    source_product_name: str
    target_product_id: uuid.UUID
    target_product_name: str
    relation_type: str
    evidence: str
    confidence: float
    document_id: uuid.UUID | None = None
    is_ai_suggested: bool = False
    status: str
    rejection_reason: str | None = None
    created_at: datetime


class EdgeSuggestionOut(BaseModel):
    id: uuid.UUID
    source_product_id: uuid.UUID
    source_product_name: str
    target_product_id: uuid.UUID
    target_product_name: str
    relation_type: str
    evidence: str
    confidence: float
    document_id: uuid.UUID | None = None
    document_filename: str | None = None
    status: str


class EdgeActionIn(BaseModel):
    reason: str | None = None


class ContextLinkOut(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    context_id: uuid.UUID
    context_name: str
    context_kind: str
    relation_type: str
    evidence: str
    confidence: float
    status: str
    is_ai_suggested: bool = True


class AutoGraphOut(BaseModel):
    edges: list[EdgeSuggestionOut] = Field(default_factory=list)
    context_links: list[ContextLinkOut] = Field(default_factory=list)
    proposed: int = 0


# ---------------------------------------------------------------------------
# Reference Architecture
# ---------------------------------------------------------------------------


class ReferenceArchitectureProductItem(BaseModel):
    product_id: uuid.UUID
    role: str = "Component"
    notes: str | None = None


class ReferenceArchitectureIn(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    slug: str | None = Field(None, max_length=128)
    description: str | None = None
    architecture_overview: str | None = None
    target_segment: str | None = None
    products: list[ReferenceArchitectureProductItem] = Field(default_factory=list)


class ReferenceArchitectureProductOut(BaseModel):
    product_id: uuid.UUID
    product_name: str
    vendor: str
    ownership: str
    category: str
    role: str
    notes: str | None = None


class ReferenceArchitectureOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    org_id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    slug: str
    description: str | None = None
    architecture_overview: str | None = None
    target_segment: str | None = None
    created_at: datetime
    products: list[ReferenceArchitectureProductOut] = Field(default_factory=list)


class ProductDetailOut(ProductOut):
    outgoing_edges: list[ProductEdgeOut] = Field(default_factory=list)
    incoming_edges: list[ProductEdgeOut] = Field(default_factory=list)
    reference_architectures: list[ReferenceArchitectureOut] = Field(default_factory=list)
    collateral_documents: list[dict[str, Any]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Visual Graph, Queries & Reports
# ---------------------------------------------------------------------------


class GraphNode(BaseModel):
    id: str
    name: str
    slug: str
    vendor: str
    ownership: str
    category: str
    tier: str
    deployment_model: str
    lifecycle_status: str
    capability_count: int
    collateral_count: int


class GraphLink(BaseModel):
    id: str
    source: str
    target: str
    relation_type: str
    evidence: str
    confidence: float
    status: str
    is_ai_suggested: bool


class PortfolioGraphOut(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphLink]
    categories: list[str]
    vendors: list[str]
    relation_types: list[str]


class NeighborhoodOut(BaseModel):
    center_product: ProductOut
    upstream_requires: list[ProductEdgeOut] = Field(default_factory=list)
    downstream_required_by: list[ProductEdgeOut] = Field(default_factory=list)
    conflicts: list[ProductEdgeOut] = Field(default_factory=list)
    integrations: list[ProductEdgeOut] = Field(default_factory=list)
    alternatives: list[ProductEdgeOut] = Field(default_factory=list)
    bundles: list[ProductEdgeOut] = Field(default_factory=list)
    replaces: list[ProductEdgeOut] = Field(default_factory=list)
    migrates_to: list[ProductEdgeOut] = Field(default_factory=list)
    reference_architectures: list[ReferenceArchitectureOut] = Field(default_factory=list)


class ImpactItem(BaseModel):
    product_id: uuid.UUID
    name: str
    vendor: str
    ownership: str
    depth: int
    path: list[str] = Field(default_factory=list)
    evidence: str | None = None


class ConflictItem(BaseModel):
    conflicted_product_id: uuid.UUID
    conflicted_product_name: str
    conflicted_product_vendor: str
    reason: str
    conflict_path: list[str] = Field(default_factory=list)
    evidence: str | None = None


class GraphQueryOut(BaseModel):
    product_id: uuid.UUID
    product_name: str
    vendor: str
    ownership: str
    all_prerequisites: list[ImpactItem] = Field(default_factory=list)
    all_incompatibilities: list[ConflictItem] = Field(default_factory=list)
    direct_integrations: list[ImpactItem] = Field(default_factory=list)
    alternatives: list[ImpactItem] = Field(default_factory=list)
    reference_architectures: list[ReferenceArchitectureOut] = Field(default_factory=list)


class IntegrityReportOut(BaseModel):
    is_valid: bool
    cycle_detected: bool
    cycles: list[list[str]] = Field(default_factory=list)
    contradictions_detected: bool
    contradictions: list[dict[str, Any]] = Field(default_factory=list)


class ProductCoverageDetail(BaseModel):
    id: uuid.UUID
    name: str
    vendor: str
    ownership: str
    missing: list[str]


class CoverageReportOut(BaseModel):
    total_products: int
    products_with_capability: int
    products_with_document: int
    products_with_edge: int
    fully_covered_products: int
    coverage_percentage: float
    orphan_capabilities: list[dict[str, Any]] = Field(default_factory=list)
    uncovered_products: list[ProductCoverageDetail] = Field(default_factory=list)
    exit_criteria_met: bool
