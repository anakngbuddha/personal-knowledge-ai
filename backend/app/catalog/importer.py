"""3.3 Put an imported product list on the map.

The list a person imports is theirs, so unlike the read step this writes ``confirmed``
rows straight away. Two rules keep an import from destroying work:

* a product we already know is matched on the same normalised name / alias / slug key
  the map read uses, so importing twice does not double the map;
* on a match we only fill blanks. A person's own correction is never overwritten unless
  they explicitly ask for it.

An imported product is also proof the product is real, so a row that arrived as a
suggestion from a datasheet is promoted to confirmed, and anything the sample catalog
left behind stops being sample material.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog import product_list
from app.core.logging import get_logger
from app.db.models import CurationStatus, Product

logger = get_logger(__name__)

#: Product columns an imported list is allowed to set.
WRITABLE_FIELDS = tuple(
    item.key for item in product_list.FIELDS if item.key not in {"name", "aliases"}
)


@dataclass
class ImportResult:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    problems: list[dict] = field(default_factory=list)
    truncated: bool = False

    @property
    def total(self) -> int:
        return self.created + self.updated + self.unchanged

    def as_dict(self) -> dict:
        return {
            "created": self.created,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "total": self.total,
            "problems": list(self.problems),
            "truncated": self.truncated,
        }


class ProductListImporter:
    def __init__(self, db: Session):
        self.db = db

    def apply(
        self,
        *,
        org_id: uuid.UUID,
        workspace_id: uuid.UUID,
        plan: product_list.ImportPlan,
        overwrite: bool = False,
        dry_run: bool = False,
    ) -> ImportResult:
        result = ImportResult(
            problems=[problem.as_dict() for problem in plan.problems],
            truncated=plan.truncated,
        )
        index = self._index(workspace_id)
        taken = self._taken_slugs(workspace_id)

        for draft in plan.drafts:
            existing = index.get(draft.key)
            if existing is None:
                if not dry_run:
                    product = self._create(org_id, workspace_id, draft, taken)
                    for key in self._keys(product):
                        index.setdefault(key, product)
                result.created += 1
                continue
            changed = self._merge(existing, draft, overwrite=overwrite, dry_run=dry_run)
            if changed:
                result.updated += 1
            else:
                result.unchanged += 1

        if dry_run:
            self.db.rollback()
        else:
            self.db.commit()
            logger.info(
                "product list import for workspace %s: %s new, %s filled in",
                workspace_id,
                result.created,
                result.updated,
            )
        return result

    # -- writing -----------------------------------------------------------

    def _create(
        self,
        org_id: uuid.UUID,
        workspace_id: uuid.UUID,
        draft: product_list.ProductDraft,
        taken: set[str],
    ) -> Product:
        values = dict(draft.values)
        aliases = values.pop("aliases", None)
        product = Product(
            org_id=org_id,
            workspace_id=workspace_id,
            name=draft.name,
            slug=self._unique_slug(draft.name, taken),
            vendor=values.pop("vendor", None) or "Unspecified",
            category=values.pop("category", None) or "other",
            aliases=aliases or None,
            curation_status=CurationStatus.CONFIRMED,
            is_ai_suggested=False,
            is_demo=False,
        )
        for key in WRITABLE_FIELDS:
            if key in values and values[key] not in (None, ""):
                setattr(product, key, values[key])
        self.db.add(product)
        self.db.flush()
        return product

    def _merge(
        self,
        product: Product,
        draft: product_list.ProductDraft,
        *,
        overwrite: bool,
        dry_run: bool,
    ) -> bool:
        values = dict(draft.values)
        aliases = values.pop("aliases", None) or []
        changed = False

        for key in WRITABLE_FIELDS:
            if key not in values:
                continue
            incoming = values[key]
            if incoming in (None, ""):
                continue
            current = getattr(product, key, None)
            blank = current in (None, "") or (
                key == "vendor" and str(current) == "Unspecified"
            )
            if not (blank or overwrite):
                continue
            if str(current) == str(incoming):
                continue
            if not dry_run:
                setattr(product, key, incoming)
            changed = True

        if aliases:
            current_aliases = list(product.aliases or [])
            lowered = {str(item).lower() for item in current_aliases}
            added = [alias for alias in aliases if alias.lower() not in lowered]
            if added:
                if not dry_run:
                    product.aliases = current_aliases + added
                changed = True

        # Being on someone's own list is what makes a product real.
        if product.curation_status != CurationStatus.CONFIRMED:
            if not dry_run:
                product.curation_status = CurationStatus.CONFIRMED
            changed = True
        if getattr(product, "is_demo", False):
            if not dry_run:
                product.is_demo = False
            changed = True

        return changed

    # -- matching ----------------------------------------------------------

    def _index(self, workspace_id: uuid.UUID) -> dict[str, Product]:
        index: dict[str, Product] = {}
        for product in self.db.scalars(
            select(Product).where(Product.workspace_id == workspace_id)
        ).all():
            for key in self._keys(product):
                index.setdefault(key, product)
        return index

    @staticmethod
    def _keys(product: Product) -> list[str]:
        keys = [product_list.normalize_name(product.name)]
        if product.slug:
            keys.append(product_list.normalize_name(product.slug.replace("-", " ")))
        for alias in product.aliases or []:
            keys.append(product_list.normalize_name(str(alias)))
        return [key for key in keys if key]

    def _taken_slugs(self, workspace_id: uuid.UUID) -> set[str]:
        return set(
            self.db.scalars(
                select(Product.slug).where(Product.workspace_id == workspace_id)
            ).all()
        )

    @staticmethod
    def _unique_slug(name: str, taken: set[str]) -> str:
        from app.catalog.extraction import slugify

        base = slugify(name)
        slug = base
        counter = 2
        while slug in taken:
            slug = f"{base}-{counter}"[:128]
            counter += 1
        taken.add(slug)
        return slug
