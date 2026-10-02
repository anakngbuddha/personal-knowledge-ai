"""Intelligent Ask mention and slash-command handlers.

Supports:
- Mentions (@): notes, websites, connectors, products
- Slash commands (/): /goal, /connections, /plan, /graphify-sync, /briefing, /faq, /compare, /help
"""

from __future__ import annotations

import re
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import String, case, cast, func, literal, or_, select, union_all
from sqlalchemy.orm import Session

from app.catalog.service import CatalogService
from app.db.models import Document, EdgeStatus, Note, Product, ProductEdge, VendorSource
from app.documents.injection import wrap_untrusted
from app.generation.schemas import (
    ConnectionNodeOut,
    MentionTargetOut,
    ProductConnectionsOut,
)
from app.llm.base import SourceMetadata
from app.retrieval.permissions import predicates_for
from app.retrieval.sql import compile_predicate
from app.security.principal import Principal


def _literal_pattern(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _sync_code_graph(principal: Principal) -> str:
    """Run the fixed AST-only sync for administrators in a source checkout."""
    if not principal.is_admin or not principal.has_scope("mcp:write"):
        return "Code graph synchronization requires an administrator; catalog status is available below."
    root = Path(__file__).resolve().parents[3]
    if not (root / "graphify-out" / "graph.json").is_file():
        return "Code graph synchronization is unavailable in this deployment."
    try:
        result = subprocess.run([sys.executable, "-m", "graphify", "update", "."],
            cwd=root, capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return "Code graph synchronization is unavailable; catalog status is available below."
    return "Code knowledge graph synchronized." if result.returncode == 0 else "Code graph synchronization is unavailable; catalog status is available below."

KNOWN_CONNECTORS = [
    {
        "id": "brave",
        "ref": "connector:brave",
        "name": "Brave Search",
        "desc": "Live web search & fresh external documentation",
        "icon": "search",
    },
    {
        "id": "playwright",
        "ref": "connector:playwright",
        "name": "Playwright Browser",
        "desc": "Live web automation, dynamic JS pages & docs",
        "icon": "browser",
    },
    {
        "id": "ms365",
        "ref": "connector:ms365",
        "name": "Microsoft 365",
        "desc": "Outlook emails, calendar, contacts, OneDrive files",
        "icon": "mail",
    },
    {
        "id": "exa",
        "ref": "connector:exa",
        "name": "Exa AI Search",
        "desc": "Neural & semantic search for technical concepts",
        "icon": "search",
    },
    {
        "id": "firecrawl",
        "ref": "connector:firecrawl",
        "name": "Firecrawl",
        "desc": "Deep web scraping & clean markdown extraction",
        "icon": "globe",
    },
    {
        "id": "google_sheets",
        "ref": "connector:google_sheets",
        "name": "Google Sheets",
        "desc": "Live spreadsheets & tabular sales/quote data",
        "icon": "table",
    },
    {
        "id": "custom_mcp",
        "ref": "connector:custom_mcp",
        "name": "Custom MCP Studio",
        "desc": "Workspace tools exposed by the custom MCP server",
        "icon": "tool",
    },
]


@dataclass
class ResolvedMentions:
    note_chunks: list[dict]
    product_chunks: list[dict]
    note_sources: list[SourceMetadata]
    product_sources: list[SourceMetadata]
    prioritized_connectors: list[str]
    target_web_urls: list[str]
    relationships_lines: list[str]


@dataclass
class SlashCommandResult:
    handled: bool
    text: str | None = None
    connections_result: ProductConnectionsOut | None = None
    active_goal: str | None = None
    rewritten_question: str | None = None


def get_mention_targets(
    db: Session,
    workspace_id: uuid.UUID,
    org_id: uuid.UUID,
    q: str = "",
    category: str | None = None,
    limit: int = 20,
    principal: Principal | None = None,
) -> list[MentionTargetOut]:
    """Fetch bounded, permission-scoped autocomplete rows in one database query."""
    if not 1 <= limit <= 50:
        raise ValueError("limit must be between 1 and 50")
    if category not in (None, "note", "product", "website", "connector"):
        raise ValueError("Unknown mention category")
    pattern = f"%{_literal_pattern(q.strip())}%"
    queries = []

    def add(model, kind, ref, name, subtitle, filters, search_fields):
        statement = select(
            cast(model.id, String).label("id"), ref.label("ref"), name.label("name"),
            literal(kind).label("category"), subtitle.label("subtitle")
        ).where(*filters)
        if q.strip():
            statement = statement.where(or_(*(col.ilike(pattern, escape="\\") for col in search_fields)))
        # Rank each category so an All search returns a mix rather than only notes.
        rows = statement.subquery()
        queries.append(select(*rows.c, func.row_number().over(order_by=(rows.c.name, rows.c.id)).label("rank")))

    if category in (None, "note"):
        add(Note, "note", literal("note:") + Note.slug, Note.title, literal("Workspace Note"),
            [Note.workspace_id == workspace_id, Note.org_id == org_id], [Note.title, Note.slug])
    if category in (None, "product"):
        add(Product, "product", literal("product:") + Product.slug, Product.name,
            Product.vendor + literal(" · ") + Product.category,
            [Product.workspace_id == workspace_id, Product.org_id == org_id],
            [Product.name, Product.slug, Product.vendor, Product.category])
    if category in (None, "website"):
        add(VendorSource, "website", literal("web:") + VendorSource.url, VendorSource.label, VendorSource.url,
            [VendorSource.workspace_id == workspace_id, VendorSource.org_id == org_id],
            [VendorSource.label, VendorSource.url])
        from app.security.principal import owner_principal
        reader = principal or owner_principal(org_id)
        add(Document, "website", literal("web:") + Document.source_url,
            func.coalesce(Document.title, Document.original_filename), Document.source_url,
            [Document.workspace_id == workspace_id, Document.org_id == org_id,
             Document.source_type == "url", Document.is_current.is_(True), Document.source_url.isnot(None),
             *(compile_predicate(p) for p in predicates_for(reader))], [Document.title, Document.source_url])
        raw = q.strip()
        if raw and (raw.lower().startswith(("http://", "https://")) or ("." in raw and " " not in raw)):
            url = raw if raw.lower().startswith(("http://", "https://")) else f"https://{raw}"
            queries.append(select(literal(f"custom-web-{raw}").label("id"), literal(f"web:{url}").label("ref"),
                literal(f"Web: {raw}").label("name"), literal("website").label("category"),
                literal("Read this website").label("subtitle"), literal(0).label("rank")))
    if category in (None, "connector"):
        for conn in KNOWN_CONNECTORS:
            if not q.strip() or any(q.strip().lower() in conn[key].lower() for key in ("id", "name", "desc")):
                queries.append(select(literal(conn["id"]).label("id"), literal(conn["ref"]).label("ref"),
                    literal(conn["name"]).label("name"), literal("connector").label("category"),
                    literal(conn["desc"]).label("subtitle"), literal(1).label("rank")))
    if not queries:
        return []
    rows = union_all(*queries).subquery()
    # DISTINCT removes repeated saved URLs while the final limit bounds the response.
    targets = select(rows.c.ref, func.min(rows.c.id).label("id"), func.min(rows.c.name).label("name"),
        rows.c.category, func.min(rows.c.subtitle).label("subtitle"), func.min(rows.c.rank).label("rank")
    ).group_by(rows.c.ref, rows.c.category).subquery()
    found = db.execute(select(targets).order_by(targets.c.rank, targets.c.category, targets.c.name).limit(limit)).mappings()
    icons = {"note": "note", "product": "product", "connector": "tool", "website": "globe"}
    return [MentionTargetOut(id=row["id"], ref=row["ref"], name=row["name"], category=row["category"],
        subtitle=row["subtitle"], icon=icons[row["category"]]) for row in found]


def get_product_connections_data(
    db: Session, workspace_id: uuid.UUID, product_query: str
) -> ProductConnectionsOut | None:
    """Retrieve detailed dependency connections for a product."""
    clean = product_query.strip().strip('"\'')
    if not clean:
        return None

    # Find product by id, slug, or name
    product: Product | None = None
    try:
        pid = uuid.UUID(clean)
        product = db.scalars(
            select(Product).where(Product.id == pid, Product.workspace_id == workspace_id)
        ).first()
    except (ValueError, TypeError):
        pass

    if not product:
        product = db.scalars(
            select(Product).where(
                Product.workspace_id == workspace_id,
                or_(
                    Product.slug.ilike(_literal_pattern(clean), escape="\\"),
                    Product.name.ilike(_literal_pattern(clean), escape="\\"),
                    Product.name.ilike(f"%{_literal_pattern(clean)}%", escape="\\"),
                ),
            ).order_by(case((func.lower(Product.slug) == clean.lower(), 0), (func.lower(Product.name) == clean.lower(), 1), else_=2), Product.name, Product.id).limit(1)
        ).first()

    if not product:
        return None

    service = CatalogService(db)
    impact = service.query_impact(product.id, workspace_id)
    prereqs = [
        ConnectionNodeOut(
            id=str(item.product_id),
            name=item.name,
            relation_type="requires",
            evidence=item.evidence or (f"Path: {' -> '.join(item.path)}" if item.path else None),
        )
        for item in impact.all_prerequisites
    ]
    conflicts = [
        ConnectionNodeOut(
            id=str(item.conflicted_product_id),
            name=item.conflicted_product_name,
            relation_type="conflicts_with",
            evidence=item.evidence or item.reason,
        )
        for item in impact.all_incompatibilities
    ]
    integrations = [
        ConnectionNodeOut(
            id=str(item.product_id),
            name=item.name,
            relation_type="integrates_with",
            evidence=item.evidence or (f"Path: {' -> '.join(item.path)}" if item.path else None),
        )
        for item in impact.direct_integrations
    ]
    alternatives = [
        ConnectionNodeOut(
            id=str(item.product_id),
            name=item.name,
            relation_type="alternative_to",
            evidence=item.evidence or (f"Path: {' -> '.join(item.path)}" if item.path else None),
        )
        for item in impact.alternatives
    ]

    collateral_count = len(product.collateral_document_ids or [])

    return ProductConnectionsOut(
        product_id=str(product.id),
        product_name=product.name,
        vendor=product.vendor,
        category=product.category,
        prerequisites=prereqs,
        conflicts=conflicts,
        integrations=integrations,
        alternatives=alternatives,
        collateral_count=collateral_count,
    )


def resolve_mentions(
    db: Session,
    workspace_id: uuid.UUID | None,
    org_id: str,
    question: str,
) -> ResolvedMentions:
    """Parse @ mentions in the question and synthesize dedicated context chunks and relationships."""
    note_chunks: list[dict] = []
    product_chunks: list[dict] = []
    note_sources: list[SourceMetadata] = []
    product_sources: list[SourceMetadata] = []
    connectors: list[str] = []
    web_urls: list[str] = []
    relationship_lines: list[str] = []

    # 1. Notes: @note:<ref> or @note:"<title>"
    if db is not None and workspace_id is not None:
        note_refs = re.findall(r'(?<!\S)@note:(?:"([^"]+)"|([^\s,;!?]+))', question)
        seen_notes = set()
        for group in list(dict.fromkeys(note_refs))[:12]:
            ref = (group[0] or group[1]).strip()
            if not ref:
                continue
            note = db.scalars(
                select(Note).where(
                    Note.workspace_id == workspace_id,
                    Note.org_id == org_id,
                    or_(
                        Note.slug.ilike(_literal_pattern(ref), escape="\\"),
                        Note.title.ilike(_literal_pattern(ref), escape="\\"),
                    ),
                ).order_by(Note.id).limit(1)
            ).first()
            if note and note.id not in seen_notes:
                seen_notes.add(note.id)
                citation = f"note:{note.title}"
                fenced = wrap_untrusted(note.body, source=citation)
                metadata = {
                    "chunk_id": f"note-{note.id}",
                    "document_id": str(note.id),
                    "document_title": f"Note: {note.title}",
                    "page_number": None,
                    "slide_number": None,
                    "sheet_name": None,
                    "cell_range": None,
                    "heading_path": ["Tribal Notes", note.title],
                    "vendor": "Workspace Note",
                    "ownership": "Internal",
                    "approval_state": None,
                    "sensitivity": "internal",
                    "valid_until": None,
                    "is_stale": False,
                    "origin": "note",
                }
                note_chunks.append({
                    "index": 0,
                    "fenced_text": fenced,
                    "citation": citation,
                    "metadata": metadata,
                })
                note_sources.append(
                    SourceMetadata(
                        chunk_id=metadata["chunk_id"],
                        document_id=str(note.id),
                        document_title=metadata["document_title"],
                        citation=citation,
                        vendor="Workspace Note",
                        ownership="Internal",
                        sensitivity="internal",
                        origin="note",
                    )
                )

    # 2. Products: @product:<ref> or @product:"<name>"
    if db is not None and workspace_id is not None:
        product_refs = re.findall(r'(?<!\S)@product:(?:"([^"]+)"|([^\s,;!?]+))', question)
        seen_products = set()
        for group in list(dict.fromkeys(product_refs))[:12]:
            ref = (group[0] or group[1]).strip()
            if not ref:
                continue
            connections_data = get_product_connections_data(db, workspace_id, ref)
            if connections_data and connections_data.product_id not in seen_products:
                seen_products.add(connections_data.product_id)
                p_name = connections_data.product_name
                citation = f"product:{p_name}"

                lines_data = [
                    f"PRODUCT CATALOG ENTRY: {p_name}",
                    f"Vendor: {connections_data.vendor or 'N/A'}",
                    f"Category: {connections_data.category or 'N/A'}",
                ]
                product = db.scalars(select(Product).where(
                    Product.id == uuid.UUID(connections_data.product_id),
                    Product.workspace_id == workspace_id, Product.org_id == org_id,
                ).limit(1)).first()
                if product:
                    for key in ("description", "deployment_model", "licensing_model", "lifecycle_status", "prerequisites", "support_path"):
                        value = getattr(product, key, None)
                        if value:
                            lines_data.append(f"{key.replace('_', ' ').title()}: {value}")
                if connections_data.prerequisites:
                    lines_data.append("Prerequisites (Required): " + ", ".join(f"{x.name}" for x in connections_data.prerequisites))
                    for item in connections_data.prerequisites:
                        relationship_lines.append(f"{p_name} requires {item.name}")
                if connections_data.conflicts:
                    lines_data.append("Conflicts (Incompatible): " + ", ".join(f"{x.name}" for x in connections_data.conflicts))
                    for item in connections_data.conflicts:
                        relationship_lines.append(f"{p_name} conflicts with {item.name}")
                if connections_data.integrations:
                    lines_data.append("Integrations (Supported): " + ", ".join(f"{x.name}" for x in connections_data.integrations))
                    for item in connections_data.integrations:
                        relationship_lines.append(f"{p_name} integrates with {item.name}")
                if connections_data.alternatives:
                    lines_data.append("Alternatives: " + ", ".join(f"{x.name}" for x in connections_data.alternatives))

                fenced = wrap_untrusted("\n".join(lines_data), source=citation)
                metadata = {
                    "chunk_id": f"product-{connections_data.product_id}",
                    "document_id": str(connections_data.product_id),
                    "document_title": f"Product: {p_name}",
                    "page_number": None,
                    "slide_number": None,
                    "sheet_name": None,
                    "cell_range": None,
                    "heading_path": ["Product Catalog", p_name],
                    "vendor": connections_data.vendor or "Catalog",
                    "ownership": "Internal",
                    "approval_state": None,
                    "sensitivity": "public",
                    "valid_until": None,
                    "is_stale": False,
                    "origin": "catalog",
                }
                product_chunks.append({
                    "index": 0,
                    "fenced_text": fenced,
                    "citation": citation,
                    "metadata": metadata,
                })
                product_sources.append(
                    SourceMetadata(
                        chunk_id=metadata["chunk_id"],
                        document_id=str(connections_data.product_id),
                        document_title=metadata["document_title"],
                        citation=citation,
                        vendor=connections_data.vendor or "Catalog",
                        origin="catalog",
                    )
                )

    # 3. Connectors: @connector:<slug>
    connector_refs = re.findall(r"(?<!\S)@connector:([a-zA-Z0-9_\-]+)", question)
    for c_slug in connector_refs:
        if c_slug in [c["id"] for c in KNOWN_CONNECTORS]:
            connectors.append(c_slug)

    # 4. Websites: @web:<url> or @website:<url>
    web_refs = re.findall(r'(?<!\S)@(?:web|website):(?:"([^"]+)"|([^\s]+))', question)
    for w_url in web_refs:
        clean_url = (w_url[0] or w_url[1]).strip().rstrip(",;!?)")
        if clean_url and "://" not in clean_url:
            clean_url = f"https://{clean_url}"
        if clean_url:
            web_urls.append(clean_url)

    return ResolvedMentions(
        note_chunks=note_chunks,
        product_chunks=product_chunks,
        note_sources=note_sources,
        product_sources=product_sources,
        prioritized_connectors=list(dict.fromkeys(connectors)),
        target_web_urls=list(dict.fromkeys(web_urls))[:5],
        relationships_lines=relationship_lines,
    )


def handle_slash_command(
    db: Session,
    workspace_id: uuid.UUID | None,
    principal: Principal,
    question: str,
    goal: str | None = None,
) -> SlashCommandResult | None:
    """Evaluate and handle slash commands (/goal, /connections, /plan, /graphify-sync, /help, etc.)."""
    q_trimmed = question.strip()
    if not q_trimmed.startswith("/"):
        return None

    parts = q_trimmed.split(maxsplit=1)
    command = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    # ── /connections <product> ─────────────────────────────────────────
    if command == "/connections":
        if not workspace_id:
            return SlashCommandResult(
                handled=True,
                text="A workspace is required to inspect product connections.",
            )
        if not arg:
            return SlashCommandResult(
                handled=True,
                text="Please specify a product name or slug, for example: `/connections Atlas-Core`",
            )
        conn_data = get_product_connections_data(db, workspace_id, arg)
        if not conn_data:
            return SlashCommandResult(
                handled=True,
                text=f"Product **{arg}** was not found in the workspace catalog. Check `/catalog/products` or explore the Map.",
            )

        # Formulate rich Markdown representation
        md_lines = [
            f"### Product Connections & Graph Analysis: {conn_data.product_name}",
            f"- **Vendor**: {conn_data.vendor or 'N/A'}",
            f"- **Category**: {conn_data.category or 'N/A'}",
            f"- **Collateral Documents**: {conn_data.collateral_count} document(s)",
            "",
        ]

        if conn_data.prerequisites:
            md_lines.append(f"#### Prerequisites ({len(conn_data.prerequisites)})")
            for req in conn_data.prerequisites:
                ev = f" — *{req.evidence}*" if req.evidence else ""
                md_lines.append(f"- **{req.name}** (required){ev}")
            md_lines.append("")
        else:
            md_lines.append("#### Prerequisites\n- No mapped prerequisites\n")

        if conn_data.conflicts:
            md_lines.append(f"#### Incompatibilities & Conflicts ({len(conn_data.conflicts)})")
            for conf in conn_data.conflicts:
                ev = f" — *{conf.evidence}*" if conf.evidence else ""
                md_lines.append(f"- **{conf.name}** (conflict){ev}")
            md_lines.append("")

        if conn_data.integrations:
            md_lines.append(f"#### Direct Integrations ({len(conn_data.integrations)})")
            for itg in conn_data.integrations:
                ev = f" — *{itg.evidence}*" if itg.evidence else ""
                md_lines.append(f"- **{itg.name}** (supported integration){ev}")
            md_lines.append("")

        if conn_data.alternatives:
            md_lines.append(f"#### Alternative Products ({len(conn_data.alternatives)})")
            for alt in conn_data.alternatives:
                ev = f" — *{alt.evidence}*" if alt.evidence else ""
                md_lines.append(f"- **{alt.name}** (alternative){ev}")
            md_lines.append("")

        md_lines.append("Use the **Map Explorer** tab to visually navigate the graph.")

        return SlashCommandResult(
            handled=True,
            text="\n".join(md_lines),
            connections_result=conn_data,
        )

    # ── /goal or /set-goal <description> ──────────────────────────────
    if command in ("/goal", "/set-goal"):
        if arg.lower() in ("clear", "done", "achieved"):
            return SlashCommandResult(handled=True, text="Session goal achieved." if arg.lower() != "clear" else "Session goal cleared.", active_goal=None)
        if len(arg) > 1000:
            return SlashCommandResult(handled=True, text="Keep the session goal under 1,000 characters.", active_goal=goal)
        if not arg:
            current_status = f"Current active goal: **{goal}**" if goal else "No active goal set for this session."
            return SlashCommandResult(
                handled=True,
                text=f"{current_status}\n\nTo set or change the session goal, type: `/goal <your objective>` (e.g. `/goal Plan cloud migration architecture`).",
                active_goal=goal,
            )
        return SlashCommandResult(
            handled=True,
            text=f"Active Session Goal set to: **{arg}**\n\nAll subsequent questions, recommendations, and solution analyses in this session will be framed to help fulfill this objective.",
            active_goal=arg,
        )

    # ── /plan <task> ──────────────────────────────────────────────────
    if command == "/plan":
        if not arg:
            return SlashCommandResult(
                handled=True,
                text="Please provide a task or project to formulate a plan for, e.g. `/plan Deploy enterprise single sign-on with Azure AD`",
            )
        rewritten = (
            f"Generate a comprehensive, step-by-step implementation and execution plan for: {arg}. "
            f"Structure your response with: 1. Goal & Architectural Overview, 2. Technical Prerequisites & Dependencies (from product map), "
            f"3. Phased Implementation Milestones, 4. Verification & Testing Strategy, 5. Risk Assessment & Mitigations. "
            f"Ground all product references and prerequisites strictly in workspace documents and catalog graph."
        )
        return SlashCommandResult(
            handled=False,
            rewritten_question=rewritten,
            active_goal=goal,
        )

    # ── /graphify-sync ────────────────────────────────────────────────
    if command in ("/graphify-sync", "/sync-graph"):
        if not workspace_id:
            return SlashCommandResult(
                handled=True,
                text="A workspace is required to audit graph synchronization.",
            )
        sync_status = _sync_code_graph(principal)
        service = CatalogService(db)
        integrity = service.audit_integrity(workspace_id)
        prod_count = len(service.list_products(workspace_id, limit=500))
        note_count = db.scalar(select(func.count()).select_from(Note).where(Note.workspace_id == workspace_id, Note.org_id == principal.org_id)) or 0
        pending = db.scalar(select(func.count()).select_from(ProductEdge).where(ProductEdge.workspace_id == workspace_id, ProductEdge.status == EdgeStatus.PENDING_REVIEW)) or 0
        coverage = service.audit_coverage(workspace_id, principal.org_id)

        report_lines = [
            "### Knowledge Graph Synchronization & Integrity Report",
            sync_status,
            f"- **Products in Catalog**: {prod_count}",
            f"- **Tribal Notes**: {note_count}",
            f"- **Contradictions Found**: {len(integrity.contradictions)}",
            f"- **Unmapped Products**: {len(coverage.uncovered_products)}",
            f"- **Relationships Awaiting Review**: {pending}",
            f"- **Prerequisite Cycles**: {len(integrity.cycles)}",
            "",
            "Catalog status refreshed. Open the Map to review suggested relationships and missing coverage.",
        ]
        return SlashCommandResult(
            handled=True,
            text="\n".join(report_lines),
            active_goal=goal,
        )

    # ── /help ─────────────────────────────────────────────────────────
    if command == "/help":
        help_text = """### Intelligent Ask Cheatsheet

#### Mentions (`@`)
Mention workspace entities directly in your prompt to inject their full content into the answer context:
- `@note:<title>` — Injects workspace tribal notes (e.g. `@note:Architecture`)
- `@product:<name>` — Injects catalog specs and dependencies (e.g. `@product:Atlas-Core`)
- `@connector:<slug>` — Targets MCP connectors (e.g. `@connector:brave`, `@connector:ms365`)
- `@web:<url>` — Pulls live web context from specified URLs or saved web sources

#### Slash Commands (`/`)
Automate workflows and explore workspace connections:
- `/goal <description>` — Set or review the active conversational goal; `/goal clear` clears it and `/goal done` marks it achieved
- `/connections <product>` — Inspect product dependencies, prerequisites, and conflicts
- `/plan <task>` — Formulate a structured, grounded implementation plan
- `/graphify-sync` — Check knowledge graph health and synchronization status
- `/briefing` — Generate an executive briefing from your sources
- `/faq` — Generate an FAQ from workspace knowledge
- `/compare <items>` — Run comparative analysis across documents or products
- `/help` — Display this reference guide
"""
        return SlashCommandResult(
            handled=True,
            text=help_text,
            active_goal=goal,
        )

    # ── /briefing ─────────────────────────────────────────────────────
    if command == "/briefing":
        rewritten = f"Prepare an executive briefing summarizing key capabilities, architectural highlights, and strategic value propositions based on workspace collateral: {arg or 'across all active sources'}."
        return SlashCommandResult(handled=False, rewritten_question=rewritten, active_goal=goal)

    # ── /faq ──────────────────────────────────────────────────────────
    if command == "/faq":
        rewritten = f"Generate a comprehensive FAQ (Frequently Asked Questions with grounded answers) addressing common technical, architectural, and operational questions for: {arg or 'our workspace products and sources'}."
        return SlashCommandResult(handled=False, rewritten_question=rewritten, active_goal=goal)

    # ── /compare ──────────────────────────────────────────────────────
    if command == "/compare":
        rewritten = f"Perform a detailed comparative analysis between: {arg or 'the key products and documents in this workspace'}. Highlight specifications, requirements, advantages, and tradeoffs."
        return SlashCommandResult(handled=False, rewritten_question=rewritten, active_goal=goal)

    return SlashCommandResult(handled=True, text=f"Unknown command `{command}`. Type `/help` to see available commands.", active_goal=goal)
