"""Tenant-scoped catalog mapping, price capture, and immutable quote versions."""

from __future__ import annotations

import asyncio
import hashlib
import re
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.routes.opportunities import _visible_opportunity
from app.db.models import (
    CommercialPolicyRecord, OpportunityRequirement, Product, ProviderSkuMap,
    SalesQuote, SalesQuoteExport, SalesQuoteVersion, StoredPriceObservation,
)
from app.db.session import get_db
from app.pricing.calculator import (
    CommercialPolicy, QuoteComponentInput, QuoteResult, calculate_quote,
)
from app.pricing.schemas import PriceObservation
from app.pricing.providers.azure import AmbiguousPrice, PricingUnavailable, UnsupportedPrice
from app.mcp.credentials import decrypt_secret, encrypt_secret
from app.mcp.store import upsert_integration
from app.pricing.credentials import provider_for_mapping, validate_pricing_secret
from app.pricing.providers.huawei import HuaweiRateSpec
from app.mcp.servers import GOOGLE_SHEETS
from app.mcp.store import get_integration
from app.sales.sheets import GoogleSheetsExporter, SheetExportError, customer_sheet_rows, service_account_access_token
from app.security.audit import record_audit
from app.security.deps import resolve_principal
from app.security.labels import Role, role_has_access
from app.security.principal import Principal

router = APIRouter(prefix="/api/sales", tags=["sales-quotes"])


@router.get("/opportunities/{opportunity_id}/signals")
def opportunity_signals(opportunity_id: uuid.UUID, limit: int = Query(50, ge=1, le=100),
                       offset: int = Query(0, ge=0, le=10000), db: Session = Depends(get_db),
                       principal: Principal = Depends(resolve_principal)):
    """Evidence from stored sales records, with no inferred renewals or notifications."""
    _write(principal)
    _visible_opportunity(db, principal, opportunity_id)
    unresolved = db.scalar(select(func.count()).select_from(OpportunityRequirement).where(
        OpportunityRequirement.org_id == principal.org_id,
        OpportunityRequirement.opportunity_id == opportunity_id,
        OpportunityRequirement.priority == "must", OpportunityRequirement.coverage_state != "covered",
    )) or 0
    versions = db.scalars(select(SalesQuoteVersion).join(SalesQuote).where(
        SalesQuote.org_id == principal.org_id, SalesQuote.opportunity_id == opportunity_id,
        SalesQuoteVersion.org_id == principal.org_id,
    ).order_by(SalesQuoteVersion.created_at.desc(), SalesQuoteVersion.id).limit(limit).offset(offset)).all()
    now = datetime.now(timezone.utc)
    signals = []
    if unresolved:
        signals.append({"kind": "missing_requirements", "count": unresolved,
                        "message": f"{unresolved} mandatory requirements need coverage review"})
    for version in versions:
        _view(version)  # Verify the snapshot before deriving any customer signal.
        if version.status == "review":
            signals.append({"kind": "awaiting_approval", "quote_version_id": str(version.id),
                            "message": f"Quote version {version.number} awaits approval"})
        for observation in version.snapshot.get("observations", []):
            value = PriceObservation.model_validate(observation)
            if value.expires_at <= now + timedelta(hours=24):
                kind = "expired_price" if value.expires_at <= now else "expiring_price"
                signals.append({"kind": kind, "quote_version_id": str(version.id),
                                "sku": value.sku, "expires_at": value.expires_at.isoformat(),
                                "source_ref": value.source_ref,
                                "message": f"Price for {value.sku} {'expired' if kind == 'expired_price' else 'expires within 24 hours'}"})
    record_audit(db, principal, "read_signals", "opportunity", str(opportunity_id),
                 {"quote_versions_checked": len(versions)})
    return {"items": signals, "limit": limit, "offset": offset,
            "quote_versions_checked": len(versions), "generated_at": now.isoformat()}


def _admin(principal: Principal) -> None:
    if not principal.is_admin or principal.user_id is None:
        raise HTTPException(403, "commercial administrator required")


def _write(principal: Principal) -> None:
    if not role_has_access(principal.role, Role.SALES) or principal.user_id is None:
        raise HTTPException(403, "sales role required")


def _digest(payload: dict) -> str:
    import json
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class SkuMapIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: uuid.UUID
    provider: str = Field(pattern=r"^(huawei|aws|azure|gcp)$")
    service: str = Field(min_length=1, max_length=128)
    sku: str = Field(min_length=1, max_length=255)
    meter: str | None = Field(default=None, max_length=255)
    region: str = Field(min_length=1, max_length=128)
    billing_mode: str = Field(min_length=1, max_length=64)


class SkuMapOut(SkuMapIn):
    id: uuid.UUID
    status: str


@router.post("/sku-maps", response_model=SkuMapOut, status_code=201)
def create_sku_map(payload: SkuMapIn, db: Session = Depends(get_db), principal: Principal = Depends(resolve_principal)):
    _admin(principal)
    product = db.scalars(select(Product).where(Product.id == payload.product_id, Product.org_id == principal.org_id)).first()
    if product is None:
        raise HTTPException(404, "product not found")
    row = ProviderSkuMap(org_id=principal.org_id, **payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    record_audit(db, principal, "create", "provider_sku_map", str(row.id))
    return SkuMapOut.model_validate({**payload.model_dump(), "id": row.id, "status": row.status})


@router.get("/sku-maps")
def list_sku_maps(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0, le=10000),
                  db: Session = Depends(get_db), principal: Principal = Depends(resolve_principal)):
    _write(principal)
    rows = db.scalars(select(ProviderSkuMap).where(
        ProviderSkuMap.org_id == principal.org_id,
        ProviderSkuMap.status == "approved",
    ).order_by(ProviderSkuMap.created_at.desc(), ProviderSkuMap.id).limit(limit).offset(offset)).all()
    return {"items": [SkuMapOut.model_validate({field: getattr(row, field)
                                                 for field in SkuMapOut.model_fields}) for row in rows],
            "limit": limit, "offset": offset}


@router.post("/sku-maps/{map_id}/approve", response_model=SkuMapOut)
def approve_sku_map(map_id: uuid.UUID, db: Session = Depends(get_db), principal: Principal = Depends(resolve_principal)):
    _admin(principal)
    row = db.scalars(select(ProviderSkuMap).where(ProviderSkuMap.id == map_id, ProviderSkuMap.org_id == principal.org_id)).first()
    if row is None:
        raise HTTPException(404, "SKU map not found")
    if row.status != "draft":
        raise HTTPException(409, "only draft SKU maps can be approved")
    row.status = "approved"
    row.reviewer_id = principal.user_id
    db.commit()
    record_audit(db, principal, "approve", "provider_sku_map", str(row.id))
    return SkuMapOut.model_validate({field: getattr(row, field) for field in SkuMapOut.model_fields})


class ObservationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku_map_id: uuid.UUID
    observation: PriceObservation
    commercial_cost_per_unit: Decimal = Field(default=Decimal(0), ge=0)


class ObservationOut(BaseModel):
    id: uuid.UUID
    sku_map_id: uuid.UUID
    payload_sha256: str


@router.get("/price-observations")
def list_price_observations(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0, le=10000),
                            sku_map_id: uuid.UUID | None = None,
                            db: Session = Depends(get_db), principal: Principal = Depends(resolve_principal)):
    _write(principal)
    statement = select(StoredPriceObservation).join(
        ProviderSkuMap, StoredPriceObservation.sku_map_id == ProviderSkuMap.id
    ).where(StoredPriceObservation.org_id == principal.org_id,
            ProviderSkuMap.org_id == principal.org_id,
            ProviderSkuMap.status == "approved")
    if sku_map_id:
        statement = statement.where(StoredPriceObservation.sku_map_id == sku_map_id)
    rows = db.scalars(statement.order_by(StoredPriceObservation.created_at.desc(),
                                         StoredPriceObservation.id).limit(limit).offset(offset)).all()
    return {"items": [{"id": str(row.id), "sku_map_id": str(row.sku_map_id),
                       "observation": row.payload, "source_kind": row.source_kind}
                      for row in rows], "limit": limit, "offset": offset}


@router.post("/price-observations/import", response_model=ObservationOut, status_code=201)
def import_observation(payload: ObservationIn, db: Session = Depends(get_db), principal: Principal = Depends(resolve_principal)):
    """Controlled commercial import; only an administrator can attest source data."""
    _admin(principal)
    mapping = db.scalars(select(ProviderSkuMap).where(
        ProviderSkuMap.id == payload.sku_map_id, ProviderSkuMap.org_id == principal.org_id,
        ProviderSkuMap.status == "approved",
    )).first()
    if mapping is None:
        raise HTTPException(404, "approved SKU map not found")
    value = payload.observation
    if (mapping.provider, mapping.service, mapping.sku, mapping.meter, mapping.region, mapping.billing_mode) != (
        value.provider, value.service, value.sku, value.meter, value.region, value.billing_mode
    ):
        raise HTTPException(422, "price dimensions do not match approved SKU map")
    if value.rate_type != "public" and value.entitlement_org_id != principal.org_id:
        raise HTTPException(422, "contract price entitlement belongs to another tenant")
    data = value.model_dump(mode="json")
    row = StoredPriceObservation(
        org_id=principal.org_id, sku_map_id=mapping.id, payload=data,
        payload_sha256=_digest(data), source_kind="controlled_import",
        commercial_cost_per_unit=str(payload.commercial_cost_per_unit),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    record_audit(db, principal, "import", "price_observation", str(row.id), {"sku_map_id": str(mapping.id)})
    return ObservationOut(id=row.id, sku_map_id=row.sku_map_id, payload_sha256=row.payload_sha256)


class CapturePriceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    commercial_cost_per_unit: Decimal = Field(default=Decimal(0), ge=0)
    huawei_spec: HuaweiRateSpec | None = None


class PricingCredentialIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = True
    secret: str | None = Field(default=None, min_length=1, max_length=16384)


@router.put("/pricing-credentials/{provider}")
def configure_pricing_credentials(provider: str, payload: PricingCredentialIn,
                                  db: Session = Depends(get_db), principal: Principal = Depends(resolve_principal)):
    _admin(principal)
    if provider not in {"aws", "gcp", "huawei"}:
        raise HTTPException(404, "credentialed provider not found")
    row = get_integration(db, principal.org_id, f"pricing_{provider}")
    if payload.secret:
        try:
            validate_pricing_secret(provider, payload.secret)
        except ValueError as exc:
            raise HTTPException(422, "invalid provider credentials") from exc
        encrypted = encrypt_secret(payload.secret)
    else:
        encrypted = row.secret_ciphertext if row else None
    if payload.enabled and not encrypted:
        raise HTTPException(422, "tenant provider credentials required")
    row = upsert_integration(db, org_id=principal.org_id, slug=f"pricing_{provider}",
                             enabled=payload.enabled, config={}, secret_ciphertext=encrypted,
                             status="disconnected" if payload.enabled else "disabled")
    record_audit(db, principal, "configure", "pricing_credentials", provider,
                 {"enabled": payload.enabled, "rotated": bool(payload.secret)})
    return {"provider": provider, "enabled": row.enabled, "has_secret": bool(row.secret_ciphertext)}


@router.post("/sku-maps/{map_id}/capture-price", response_model=ObservationOut, status_code=201)
async def capture_public_price(map_id: uuid.UUID, payload: CapturePriceIn,
                               db: Session = Depends(get_db), principal: Principal = Depends(resolve_principal)):
    _admin(principal)
    mapping = db.scalars(select(ProviderSkuMap).where(
        ProviderSkuMap.id == map_id, ProviderSkuMap.org_id == principal.org_id,
        ProviderSkuMap.status == "approved",
    )).first()
    if mapping is None:
        raise HTTPException(404, "approved SKU map not found")
    try:
        provider = await provider_for_mapping(db, principal, mapping, payload.huawei_spec)
        value = await provider.get_price(
            sku=mapping.sku, region=mapping.region, billing_mode=mapping.billing_mode,
            entitlement_org_id=None, meter=mapping.meter,
        )
    except AmbiguousPrice as exc:
        raise HTTPException(409, str(exc)) from exc
    except UnsupportedPrice as exc:
        raise HTTPException(422, str(exc)) from exc
    except PricingUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    if (value.provider, value.service, value.sku, value.meter, value.region, value.billing_mode) != (
        mapping.provider, mapping.service, mapping.sku, mapping.meter, mapping.region, mapping.billing_mode
    ):
        raise HTTPException(409, "provider response differs from the approved mapping")
    data = value.model_dump(mode="json")
    row = StoredPriceObservation(
        org_id=principal.org_id, sku_map_id=mapping.id, payload=data,
        payload_sha256=_digest(data), source_kind=f"{mapping.provider}_api",
        commercial_cost_per_unit=str(payload.commercial_cost_per_unit),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    record_audit(db, principal, "capture", "price_observation", str(row.id), {"sku_map_id": str(mapping.id)})
    return ObservationOut(id=row.id, sku_map_id=row.sku_map_id, payload_sha256=row.payload_sha256)


class ListPricePolicy(CommercialPolicy):
    tax_percent: Decimal = Field(default=Decimal(0), ge=0, le=0)
    max_discount_percent: Decimal = Field(default=Decimal(0), ge=0, le=0)
    min_margin_percent: Decimal = Field(default=Decimal(0), ge=0, le=0)


@router.post("/policies", status_code=201)
def create_policy(policy: ListPricePolicy, db: Session = Depends(get_db), principal: Principal = Depends(resolve_principal)):
    _admin(principal)
    exists = db.scalars(select(CommercialPolicyRecord).where(
        CommercialPolicyRecord.org_id == principal.org_id,
        CommercialPolicyRecord.version == policy.version,
    )).first()
    if exists is not None:
        raise HTTPException(409, "policy version already exists")
    row = CommercialPolicyRecord(
        org_id=principal.org_id, version=policy.version,
        payload=policy.model_dump(mode="json"), created_by=principal.user_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    record_audit(db, principal, "create", "commercial_policy", str(row.id))
    return {"id": row.id, "version": row.version}


@router.get("/policies")
def list_policies(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0, le=10000),
                  db: Session = Depends(get_db), principal: Principal = Depends(resolve_principal)):
    _write(principal)
    rows = db.scalars(select(CommercialPolicyRecord).where(
        CommercialPolicyRecord.org_id == principal.org_id,
    ).order_by(CommercialPolicyRecord.created_at.desc(), CommercialPolicyRecord.id).limit(limit).offset(offset)).all()
    return {"items": [{"id": str(row.id), **row.payload} for row in rows],
            "limit": limit, "offset": offset}


class QuoteLineIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    observation_id: uuid.UUID
    resource_quantity: Decimal = Field(gt=0)
    usage_per_resource: Decimal = Field(gt=0)
    discount_percent: Decimal = Field(default=Decimal(0), ge=0, le=0)
    assumption: str = Field(min_length=1, max_length=1000)


class QuoteDraftIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    policy_id: uuid.UUID
    lines: list[QuoteLineIn] = Field(min_length=1, max_length=100)


class QuoteVersionOut(BaseModel):
    id: uuid.UUID
    quote_id: uuid.UUID
    number: int
    status: str
    snapshot_sha256: str
    result: QuoteResult


def _coverage_gate(db: Session, principal: Principal, opportunity_id: uuid.UUID) -> None:
    rows = db.scalars(select(OpportunityRequirement).where(
        OpportunityRequirement.org_id == principal.org_id,
        OpportunityRequirement.opportunity_id == opportunity_id,
    )).all()
    if not rows or any(row.priority == "must" and row.coverage_state != "covered" for row in rows):
        raise HTTPException(409, "mandatory requirement coverage is incomplete")


def _build_snapshot(db: Session, principal: Principal, opportunity_id: uuid.UUID, payload: QuoteDraftIn) -> tuple[dict, QuoteResult]:
    policy_row = db.scalars(select(CommercialPolicyRecord).where(
        CommercialPolicyRecord.id == payload.policy_id, CommercialPolicyRecord.org_id == principal.org_id,
    )).first()
    if policy_row is None:
        raise HTTPException(404, "commercial policy not found")
    policy = CommercialPolicy.model_validate(policy_row.payload)
    if policy.tax_percent != 0 or policy.max_discount_percent != 0 or policy.min_margin_percent != 0:
        raise HTTPException(422, "a zero-tax, zero-discount list-price policy is required")
    opportunity = _visible_opportunity(db, principal, opportunity_id, write=True)
    if policy.currency != opportunity.currency:
        raise HTTPException(422, "policy currency does not match opportunity")
    components: list[QuoteComponentInput] = []
    line_refs: list[dict] = []
    for line in payload.lines:
        observed = db.scalars(select(StoredPriceObservation).where(
            StoredPriceObservation.id == line.observation_id,
            StoredPriceObservation.org_id == principal.org_id,
        )).first()
        if observed is None:
            raise HTTPException(404, "price observation not found")
        mapping = db.scalars(select(ProviderSkuMap).where(
            ProviderSkuMap.id == observed.sku_map_id,
            ProviderSkuMap.org_id == principal.org_id,
            ProviderSkuMap.status == "approved",
        )).first()
        if mapping is None:
            raise HTTPException(409, "approved SKU mapping is unavailable")
        product = db.scalars(select(Product).where(Product.id == mapping.product_id, Product.org_id == principal.org_id)).first()
        if product is None or product.lifecycle_status.lower() not in {"ga", "general availability"} or product.curation_status != "confirmed":
            raise HTTPException(409, "mapped product is not approved for sale")
        observation = PriceObservation.model_validate(observed.payload)
        if observation.rate_type != "public":
            raise HTTPException(422, "raw list-price quotations require public price observations")
        if observation.currency != policy.currency:
            raise HTTPException(422, "price currency needs an approved FX record")
        if observation.rate_type != "public" and observation.entitlement_org_id != principal.org_id:
            raise HTTPException(403, "price observation is not entitled to this tenant")
        if observed.payload_sha256 != _digest(observed.payload):
            raise HTTPException(409, "price observation integrity check failed")
        values = line.model_dump(exclude={"observation_id"})
        components.append(QuoteComponentInput(
            observation=observation, cost_per_unit=None,
            tax_percent=policy.tax_percent, **values,
        ))
        line_refs.append({"observation_id": str(observed.id), "sku_map_id": str(mapping.id),
                          "product_id": str(product.id), "cost_per_unit": observed.commercial_cost_per_unit,
                          "input": line.model_dump(mode="json")})
    result = calculate_quote(components, policy, list_price_only=True)
    snapshot = {
        "opportunity_id": str(opportunity_id), "policy_id": str(policy_row.id),
        "policy": policy.model_dump(mode="json"), "lines": line_refs,
        "observations": [component.observation.model_dump(mode="json") for component in components],
        "result": result.model_dump(mode="json"),
        "pricing_mode": "public_list_price",
    }
    return snapshot, result


def _view(row: SalesQuoteVersion) -> QuoteVersionOut:
    if row.snapshot_sha256 != _digest(row.snapshot):
        raise HTTPException(409, "quote snapshot integrity check failed")
    return QuoteVersionOut(
        id=row.id, quote_id=row.quote_id, number=row.number, status=row.status,
        snapshot_sha256=row.snapshot_sha256, result=QuoteResult.model_validate(row.snapshot["result"]),
    )


@router.post("/opportunities/{opportunity_id}/quotes", response_model=QuoteVersionOut, status_code=201)
def create_quote(opportunity_id: uuid.UUID, payload: QuoteDraftIn,
                 db: Session = Depends(get_db), principal: Principal = Depends(resolve_principal)):
    _write(principal)
    _visible_opportunity(db, principal, opportunity_id, write=True)
    _coverage_gate(db, principal, opportunity_id)
    snapshot, _ = _build_snapshot(db, principal, opportunity_id, payload)
    quote = SalesQuote(org_id=principal.org_id, opportunity_id=opportunity_id)
    db.add(quote)
    db.flush()
    version = SalesQuoteVersion(
        org_id=principal.org_id, quote_id=quote.id, number=1, policy_id=payload.policy_id,
        snapshot=snapshot, snapshot_sha256=_digest(snapshot), created_by=principal.user_id,
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    record_audit(db, principal, "create", "sales_quote_version", str(version.id))
    return _view(version)


@router.post("/quotes/{quote_id}/versions", response_model=QuoteVersionOut, status_code=201)
def reprice_quote(quote_id: uuid.UUID, payload: QuoteDraftIn,
                  db: Session = Depends(get_db), principal: Principal = Depends(resolve_principal)):
    """Create a new immutable version; never mutate the prior commercial snapshot."""
    _write(principal)
    quote = db.scalars(select(SalesQuote).where(
        SalesQuote.id == quote_id, SalesQuote.org_id == principal.org_id,
    ).with_for_update()).first()
    if quote is None:
        raise HTTPException(404, "quote not found")
    _visible_opportunity(db, principal, quote.opportunity_id, write=True)
    _coverage_gate(db, principal, quote.opportunity_id)
    snapshot, _ = _build_snapshot(db, principal, quote.opportunity_id, payload)
    number = db.scalar(select(func.max(SalesQuoteVersion.number)).where(
        SalesQuoteVersion.quote_id == quote.id, SalesQuoteVersion.org_id == principal.org_id,
    )) or 0
    version = SalesQuoteVersion(
        org_id=principal.org_id, quote_id=quote.id, number=number + 1,
        policy_id=payload.policy_id, snapshot=snapshot, snapshot_sha256=_digest(snapshot),
        created_by=principal.user_id,
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    record_audit(db, principal, "reprice", "sales_quote_version", str(version.id),
                 {"prior_version_number": number})
    return _view(version)


def _visible_version(db: Session, principal: Principal, version_id: uuid.UUID, *, write: bool = False) -> SalesQuoteVersion:
    version = db.scalars(select(SalesQuoteVersion).where(
        SalesQuoteVersion.id == version_id, SalesQuoteVersion.org_id == principal.org_id,
    )).first()
    if version is None:
        raise HTTPException(404, "quote version not found")
    quote = db.scalars(select(SalesQuote).where(
        SalesQuote.id == version.quote_id, SalesQuote.org_id == principal.org_id,
    )).first()
    if quote is None:
        raise HTTPException(404, "quote not found")
    _visible_opportunity(db, principal, quote.opportunity_id, write=write)
    return version


@router.get("/quote-versions/{version_id}", response_model=QuoteVersionOut)
def get_quote_version(version_id: uuid.UUID, db: Session = Depends(get_db), principal: Principal = Depends(resolve_principal)):
    return _view(_visible_version(db, principal, version_id))


@router.get("/quote-versions/{version_id}/customer-export")
def customer_quote_export(version_id: uuid.UUID, db: Session = Depends(get_db),
                          principal: Principal = Depends(resolve_principal)):
    _write(principal)
    row = _visible_version(db, principal, version_id)
    result = _view(row).result
    if row.status != "issued":
        raise HTTPException(409, "only issued quote versions can be exported")
    public_lines = [{
        "sku": line.sku, "provider": line.provider, "currency": line.currency,
        "sell_amount": str(line.sell_amount), "tax_amount": str(line.tax_amount),
        "total_amount": str(line.total_amount), "assumption": line.assumption,
        "source_ref": line.source_ref, "price_expires_at": line.expires_at.isoformat(),
    } for line in result.lines]
    record_audit(db, principal, "export", "sales_quote_version", str(row.id))
    return {
        "quote_id": str(row.quote_id), "version": row.number, "currency": result.currency,
        "lines": public_lines, "subtotal": str(result.subtotal),
        "tax_total": str(result.tax_total), "total": str(result.total),
        "issued_at": row.issued_at.isoformat() if row.issued_at else None,
    }


@router.post("/quote-versions/{version_id}/export/google-sheets")
async def export_quote_to_google_sheets(
    version_id: uuid.UUID, db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
):
    _write(principal)
    version = _visible_version(db, principal, version_id)
    _view(version)
    if version.status != "issued" or version.issued_at is None:
        raise HTTPException(409, "only issued quote versions can be exported")
    previous = db.scalars(select(SalesQuoteExport).where(
        SalesQuoteExport.org_id == principal.org_id,
        SalesQuoteExport.quote_version_id == version_id,
        SalesQuoteExport.destination == GOOGLE_SHEETS,
    ).with_for_update()).first()
    if previous is not None:
        if previous.status == "completed" and previous.external_id:
            return {"export_id": str(previous.id), "spreadsheet_id": previous.external_id,
                    "url": f"https://docs.google.com/spreadsheets/d/{previous.external_id}/edit"}
        if previous.status != "retry_authorized":
            raise HTTPException(409, "export requires reconciliation before retry")
    integration = get_integration(db, principal.org_id, GOOGLE_SHEETS)
    if integration is None or not integration.enabled or not integration.secret_ciphertext:
        raise HTTPException(409, "tenant Google Sheets integration is not configured")
    try:
        secret = decrypt_secret(integration.secret_ciphertext)
    except Exception as exc:
        raise HTTPException(503, "tenant Google Sheets credentials are unavailable") from exc
    rows = customer_sheet_rows(version.snapshot, quote_id=str(version.quote_id),
                               version=version.number, issued_at=version.issued_at)
    if previous is not None:
        attempt = previous
        attempt.status = "pending"
    else:
        attempt = SalesQuoteExport(
            org_id=principal.org_id, quote_version_id=version_id,
            destination=GOOGLE_SHEETS, status="pending", created_by=principal.user_id,
        )
        db.add(attempt)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "export already started; refresh its status") from exc
    try:
        token = await asyncio.to_thread(service_account_access_token, secret)
        spreadsheet_id = await GoogleSheetsExporter(token).export(
            rows, title=f"Quote {str(version.quote_id)[:8]} v{version.number}"
        )
    except SheetExportError as exc:
        attempt.status = "needs_reconciliation"
        db.commit()
        record_audit(db, principal, "export_failed", "sales_quote_version", str(version_id),
                     {"destination": GOOGLE_SHEETS, "export_id": str(attempt.id)})
        raise HTTPException(502, "Google Sheets export failed; reconciliation is required") from exc
    attempt.external_id = spreadsheet_id
    attempt.status = "completed"
    attempt.completed_at = datetime.now(timezone.utc)
    db.commit()
    record_audit(db, principal, "export", "sales_quote_version", str(version_id),
                 {"destination": GOOGLE_SHEETS, "export_id": str(attempt.id)})
    return {"export_id": str(attempt.id), "spreadsheet_id": spreadsheet_id,
            "url": f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"}


class SheetReconcileIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome: str = Field(pattern=r"^(completed|not_created)$")
    spreadsheet_id: str | None = Field(default=None, max_length=255)
    rationale: str = Field(min_length=10, max_length=1000)


@router.get("/quote-versions/{version_id}/export/google-sheets")
def get_google_sheets_export(version_id: uuid.UUID, db: Session = Depends(get_db),
                             principal: Principal = Depends(resolve_principal)):
    _write(principal)
    _visible_version(db, principal, version_id)
    row = db.scalars(select(SalesQuoteExport).where(
        SalesQuoteExport.org_id == principal.org_id,
        SalesQuoteExport.quote_version_id == version_id,
        SalesQuoteExport.destination == GOOGLE_SHEETS,
    )).first()
    if row is None:
        raise HTTPException(404, "Google Sheets export not found")
    return {"export_id": str(row.id), "status": row.status,
            "spreadsheet_id": row.external_id,
            "url": f"https://docs.google.com/spreadsheets/d/{row.external_id}/edit" if row.external_id else None}


@router.post("/quote-versions/{version_id}/export/google-sheets/reconcile")
def reconcile_google_sheets_export(version_id: uuid.UUID, payload: SheetReconcileIn,
                                   db: Session = Depends(get_db),
                                   principal: Principal = Depends(resolve_principal)):
    _admin(principal)
    _visible_version(db, principal, version_id)
    row = db.scalars(select(SalesQuoteExport).where(
        SalesQuoteExport.org_id == principal.org_id,
        SalesQuoteExport.quote_version_id == version_id,
        SalesQuoteExport.destination == GOOGLE_SHEETS,
    ).with_for_update()).first()
    if row is None:
        raise HTTPException(404, "Google Sheets export not found")
    if row.status != "needs_reconciliation":
        raise HTTPException(409, "export does not need reconciliation")
    if payload.outcome == "completed":
        if not payload.spreadsheet_id or not re.fullmatch(r"[A-Za-z0-9_-]{10,255}", payload.spreadsheet_id):
            raise HTTPException(422, "a valid spreadsheet ID is required")
        row.external_id = payload.spreadsheet_id
        row.status = "completed"
        row.completed_at = datetime.now(timezone.utc)
    elif payload.spreadsheet_id is not None:
        raise HTTPException(422, "spreadsheet ID must be omitted when no sheet was created")
    else:
        row.status = "retry_authorized"
    db.commit()
    record_audit(db, principal, "reconcile", "sales_quote_export", str(row.id),
                 {"outcome": payload.outcome, "rationale": payload.rationale,
                  "spreadsheet_id": row.external_id})
    return {"export_id": str(row.id), "status": row.status, "spreadsheet_id": row.external_id}


@router.get("/opportunities/{opportunity_id}/quotes")
def list_quotes(opportunity_id: uuid.UUID, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0, le=10000),
                db: Session = Depends(get_db), principal: Principal = Depends(resolve_principal)):
    _visible_opportunity(db, principal, opportunity_id)
    rows = db.scalars(select(SalesQuoteVersion).join(SalesQuote, SalesQuoteVersion.quote_id == SalesQuote.id).where(
        SalesQuote.org_id == principal.org_id, SalesQuote.opportunity_id == opportunity_id,
        SalesQuoteVersion.org_id == principal.org_id,
    ).order_by(SalesQuoteVersion.created_at.desc(), SalesQuoteVersion.id).limit(limit).offset(offset)).all()
    return {"items": [_view(row) for row in rows], "limit": limit, "offset": offset}


@router.post("/quote-versions/{version_id}/submit", response_model=QuoteVersionOut)
def submit_quote(version_id: uuid.UUID, db: Session = Depends(get_db), principal: Principal = Depends(resolve_principal)):
    _write(principal)
    row = _visible_version(db, principal, version_id, write=True)
    if row.status != "draft":
        raise HTTPException(409, "only a draft quote can be submitted")
    if not _view(row).result.issueable:
        raise HTTPException(409, "quote has commercial blockers")
    _coverage_gate(db, principal, uuid.UUID(row.snapshot["opportunity_id"]))
    row.status = "review"
    db.commit()
    record_audit(db, principal, "submit", "sales_quote_version", str(row.id))
    return _view(row)


@router.post("/quote-versions/{version_id}/approve", response_model=QuoteVersionOut)
def approve_quote(version_id: uuid.UUID, db: Session = Depends(get_db), principal: Principal = Depends(resolve_principal)):
    _admin(principal)
    row = _visible_version(db, principal, version_id)
    if row.status != "review":
        raise HTTPException(409, "quote is not awaiting review")
    if row.created_by == principal.user_id:
        raise HTTPException(403, "quote author cannot approve their own quote")
    if not _view(row).result.issueable:
        raise HTTPException(409, "quote has commercial blockers")
    _coverage_gate(db, principal, uuid.UUID(row.snapshot["opportunity_id"]))
    if any(datetime.fromisoformat(value["expires_at"]) <= datetime.now(timezone.utc)
           for value in row.snapshot["observations"]):
        raise HTTPException(409, "a price observation expired")
    row.status = "approved"
    row.approved_by = principal.user_id
    row.approved_at = datetime.now(timezone.utc)
    db.commit()
    record_audit(db, principal, "approve", "sales_quote_version", str(row.id))
    return _view(row)


@router.post("/quote-versions/{version_id}/issue", response_model=QuoteVersionOut)
def issue_quote(version_id: uuid.UUID, db: Session = Depends(get_db), principal: Principal = Depends(resolve_principal)):
    _write(principal)
    row = _visible_version(db, principal, version_id, write=True)
    if row.status != "approved":
        raise HTTPException(409, "quote needs commercial approval")
    _view(row)
    _coverage_gate(db, principal, uuid.UUID(row.snapshot["opportunity_id"]))
    if any(datetime.fromisoformat(value["expires_at"]) <= datetime.now(timezone.utc)
           for value in row.snapshot["observations"]):
        raise HTTPException(409, "a price observation expired; create a new version")
    row.status = "issued"
    row.issued_at = datetime.now(timezone.utc)
    db.commit()
    record_audit(db, principal, "issue", "sales_quote_version", str(row.id))
    return _view(row)
