"""Custom MCP Server Engine for Personal Knowledge AI.

Implements the Model Context Protocol (v2024-11-05 JSON-RPC specification)
allowing external AI tools (such as Claude Desktop, Cursor, Antigravity) to
execute read and write commands against the knowledge base and catalog graph.

Authorization (audit finding 2): every tool that loads documents goes through
`app.retrieval.access`, the same predicate set search uses (tenant, sensitivity,
account grants, approval state, corpus rules). Write tools additionally require an
SE-or-higher role and, for scoped MCP tokens, the `mcp:write` scope.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.catalog.graph import query_product_impact
from app.catalog.models import ProductEdgeIn, ProductIn
from app.catalog.service import CatalogService
from app.core.logging import get_logger
from app.documents.metadata import DocumentMetadataIn
from app.documents.service import create_document, enqueue_ingestion
from app.generation.service import ask as generation_ask
from app.notes import service as notes_service
from app.retrieval.access import get_readable_document, readable_documents
from app.retrieval.search import search as run_search
from app.retrieval.spec import RetrievalFilters
from app.retrieval.web import gather_web_fallback
from app.security.labels import SourceType
from app.security.principal import MCP_WRITE_SCOPE, Principal

logger = get_logger(__name__)

MCP_PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "personal-knowledge-ai"
SERVER_VERSION = "1.1.0"

# ── Tool Definitions ──────────────────────────────────────────────────────────

MCP_TOOLS: list[dict[str, Any]] = [
    # ── Read Tools ────────────────────────────────────────────────────────────
    {
        "name": "search_knowledge",
        "description": "Hybrid search (keyword BM25 + dense vector embeddings) across all uploaded collateral, documents, and notes.",
        "category": "read",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query or natural language question",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Maximum number of relevant passages to return (default: 5)",
                    "default": 5,
                },
                "products": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional list of product names to filter by",
                },
                "vendor": {
                    "type": "string",
                    "description": "Optional vendor name to filter by",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "read_document",
        "description": "Retrieve document metadata and text chunks by document ID (only documents you are allowed to read).",
        "category": "read",
        "inputSchema": {
            "type": "object",
            "properties": {
                "document_id": {
                    "type": "string",
                    "description": "UUID of the document to inspect",
                }
            },
            "required": ["document_id"],
        },
    },
    {
        "name": "list_documents",
        "description": "List indexed collateral and documents you are allowed to read, with titles and approval state.",
        "category": "read",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Number of documents to return (default: 20)",
                    "default": 20,
                },
                "offset": {
                    "type": "integer",
                    "description": "Offset for pagination (default: 0)",
                    "default": 0,
                },
            },
        },
    },
    {
        "name": "ask_intelligence",
        "description": "Ask the Grounded Knowledge AI engine a question. Strict (cited sources only) by default; set strict_mode=false for expert mode, which labels unsourced guidance separately.",
        "category": "read",
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "Question to answer from the knowledge base and web fallback",
                },
                "enable_web_search": {
                    "type": "boolean",
                    "description": "Whether to allow live web search if question is not answered by internal docs (default: true)",
                    "default": True,
                },
                "strict_mode": {
                    "type": "boolean",
                    "description": "True (default) = only cited sources. False = expert mode; general guidance is returned in a separately labeled section.",
                    "default": True,
                },
            },
            "required": ["question"],
        },
    },
    {
        "name": "read_note",
        "description": "Read the full markdown body, wikilinks, and backlinks of a saved note.",
        "category": "read",
        "inputSchema": {
            "type": "object",
            "properties": {
                "note_id": {
                    "type": "string",
                    "description": "UUID of the note to retrieve",
                }
            },
            "required": ["note_id"],
        },
    },
    {
        "name": "list_notes",
        "description": "List user notes, briefing outputs, and research records.",
        "category": "read",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Number of notes to return (default: 20)",
                    "default": 20,
                },
                "offset": {
                    "type": "integer",
                    "description": "Offset for pagination (default: 0)",
                    "default": 0,
                },
            },
        },
    },
    {
        "name": "get_catalog_impact",
        "description": "Query the product graph for prerequisites, conflicts, integrations, and alternatives for a given product.",
        "category": "read",
        "inputSchema": {
            "type": "object",
            "properties": {
                "product": {
                    "type": "string",
                    "description": "Exact product name to analyze in the catalog graph",
                }
            },
            "required": ["product"],
        },
    },
    {
        "name": "web_search",
        "description": "Perform live web search via DuckDuckGo / Brave and return clean passage text.",
        "category": "read",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Web search query",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Number of results to return (default: 5)",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    # ── Write Tools ───────────────────────────────────────────────────────────
    {
        "name": "create_note",
        "description": "Create and persist a new note with markdown content in the knowledge base.",
        "category": "write",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Title of the note",
                },
                "body": {
                    "type": "string",
                    "description": "Markdown body of the note (supports [[wikilinks]])",
                },
            },
            "required": ["title", "body"],
        },
    },
    {
        "name": "upload_text_document",
        "description": "Ingest a new text or markdown document into the knowledge base, triggering automatic chunking and vector indexing.",
        "category": "write",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Filename (e.g. 'architecture-overview.md', 'spec.txt')",
                },
                "content": {
                    "type": "string",
                    "description": "Raw text or markdown content of the document",
                },
                "title": {
                    "type": "string",
                    "description": "Optional title for the document",
                },
                "vendor": {
                    "type": "string",
                    "description": "Optional vendor or author name",
                },
            },
            "required": ["filename", "content"],
        },
    },
    {
        "name": "add_catalog_product",
        "description": "Register a new product or service in the solution catalog graph.",
        "category": "write",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Product name (e.g. 'PostgreSQL 16', 'Redis Cluster')",
                },
                "vendor": {
                    "type": "string",
                    "description": "Vendor or publisher name",
                },
                "description": {
                    "type": "string",
                    "description": "Optional product description",
                },
                "category": {
                    "type": "string",
                    "description": "Optional category (e.g. 'Database', 'Cache', 'Security')",
                },
            },
            "required": ["name", "vendor"],
        },
    },
    {
        "name": "link_catalog_products",
        "description": "Create a relationship edge between two products in the catalog graph (e.g. requires, conflicts, integrates_with).",
        "category": "write",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_product": {
                    "type": "string",
                    "description": "Name of the source product",
                },
                "target_product": {
                    "type": "string",
                    "description": "Name of the target product",
                },
                "relation": {
                    "type": "string",
                    "enum": ["requires", "conflicts", "integrates_with", "replaces", "bundles"],
                    "description": "Relationship type",
                },
                "reason": {
                    "type": "string",
                    "description": "Optional reason or citation for this relationship",
                },
            },
            "required": ["source_product", "target_product", "relation"],
        },
    },
    {
        "name": "delete_note",
        "description": "Delete a note from the knowledge base by ID.",
        "category": "write",
        "inputSchema": {
            "type": "object",
            "properties": {
                "note_id": {
                    "type": "string",
                    "description": "UUID of the note to delete",
                }
            },
            "required": ["note_id"],
        },
    },
]

WRITE_TOOLS: frozenset[str] = frozenset(t["name"] for t in MCP_TOOLS if t.get("category") == "write")


def may_run_write_tools(principal: Principal) -> bool:
    """SE-or-higher role, and the token (if scoped) must carry mcp:write."""
    return bool(principal.can_write_catalog and principal.has_scope(MCP_WRITE_SCOPE))


def _get_workspace_id(db: Session, principal: Principal) -> uuid.UUID:
    """Resolve default workspace ID for principal's org."""
    from app.db.models import Workspace
    from sqlalchemy import select

    workspace = db.scalars(
        select(Workspace).where(Workspace.org_id == principal.org_id).limit(1)
    ).first()
    if workspace:
        return workspace.id
    workspace = Workspace(org_id=principal.org_id, name="Default Workspace")
    db.add(workspace)
    db.commit()
    db.refresh(workspace)
    return workspace.id


def _doc_title(doc) -> str:
    return getattr(doc, "title", None) or doc.original_filename


# ── Tool Execution Handlers ───────────────────────────────────────────────────

def execute_mcp_tool_call(
    db: Session,
    principal: Principal,
    name: str,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Execute a read or write MCP tool call with principal authorization."""
    if name in WRITE_TOOLS and not may_run_write_tools(principal):
        return {"error": "forbidden: your role or token scope does not allow write tools"}

    # 2. read_document (Read) - handled before workspace resolution: a read must not
    # create rows, and the authorization check is the whole point of this branch.
    if name == "read_document":
        doc_id_str = str(args.get("document_id", "")).strip()
        try:
            doc_uuid = uuid.UUID(doc_id_str)
        except ValueError:
            return {"error": f"Invalid document UUID: {doc_id_str}"}

        doc = get_readable_document(db, principal, doc_uuid)
        if not doc:
            # Same answer for "missing" and "not allowed", so ids cannot be probed.
            return {"error": f"Document {doc_id_str} not found"}

        from app.db.models import DocumentChunk
        from sqlalchemy import select

        chunks = db.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == doc.id)
            .order_by(DocumentChunk.chunk_index)
            .limit(50)
        ).all()

        return {
            "document_id": str(doc.id),
            "filename": doc.original_filename,
            "title": _doc_title(doc),
            "vendor": getattr(doc, "vendor", None),
            "approval_state": doc.approval_state,
            "sensitivity": getattr(doc, "sensitivity", None),
            "chunks_count": len(chunks),
            "passages": [
                {
                    "chunk_index": c.chunk_index,
                    "text": c.text,
                    "page_number": c.page_number,
                    "slide_number": c.slide_number,
                }
                for c in chunks
            ],
        }

    # 3. list_documents (Read)
    if name == "list_documents":
        limit = max(1, min(int(args.get("limit", 20) or 20), 100))
        offset = max(0, int(args.get("offset", 0) or 0))

        from app.db.models import Document

        docs = db.scalars(
            readable_documents(principal)
            .order_by(Document.created_at.desc())
            .offset(offset)
            .limit(limit)
        ).all()

        return {
            "count": len(docs),
            "offset": offset,
            "documents": [
                {
                    "id": str(d.id),
                    "filename": d.original_filename,
                    "title": _doc_title(d),
                    "vendor": getattr(d, "vendor", None),
                    "approval_state": d.approval_state,
                    "created_at": d.created_at.isoformat() if d.created_at else None,
                }
                for d in docs
            ],
        }

    workspace_id = _get_workspace_id(db, principal)

    # 1. search_knowledge (Read)
    if name == "search_knowledge":
        query = str(args.get("query", "")).strip()
        if not query:
            return {"error": "query is required"}
        top_k = int(args.get("top_k", 5) or 5)
        filters: dict[str, Any] = {}
        if args.get("products"):
            filters["products"] = args["products"]
        if args.get("vendor"):
            filters["vendor"] = args["vendor"]

        retrieval_filters = RetrievalFilters(**filters) if filters else None
        search_result = run_search(
            db,
            principal=principal,
            query=query,
            filters=retrieval_filters,
            mode="hybrid",
            top_k=max(1, min(top_k, 20)),
        )
        hits = [
            {
                "chunk_id": h.chunk_id,
                "document_id": h.document_id,
                "document_title": h.document_title,
                "citation": h.citation,
                "text": h.text,
                "score": float(getattr(h, "rrf_score", 0) or 0),
                "page_number": h.page_number,
                "vendor": h.vendor,
            }
            for h in search_result.hits
        ]
        return {
            "query": query,
            "total_hits": len(hits),
            "results": hits,
        }

    # 4. ask_intelligence (Read)
    if name == "ask_intelligence":
        question = str(args.get("question", "")).strip()
        if not question:
            return {"error": "question is required"}
        enable_web = bool(args.get("enable_web_search", True))
        strict_mode = bool(args.get("strict_mode", True))

        ans = generation_ask(
            db,
            principal=principal,
            question=question,
            workspace_id=workspace_id,
            strict_mode=strict_mode,
            web_search=enable_web,
            persist=False,
        )
        return {
            "answer": ans.text,
            "model": ans.model_id,
            "strict_mode": strict_mode,
            "citations": [
                {
                    "citation": c.citation,
                    "document_title": c.document_title,
                    "page_number": c.page_number,
                    "url": getattr(c, "source_url", None),
                    "support_score": getattr(c, "support_score", None),
                }
                for c in ans.citations
            ],
            "web_note": ans.web_note,
            "web_sources_count": len(ans.web_sources),
        }

    # 5. read_note (Read)
    if name == "read_note":
        note_id_str = str(args.get("note_id", "")).strip()
        try:
            note_uuid = uuid.UUID(note_id_str)
        except ValueError:
            return {"error": f"Invalid note UUID: {note_id_str}"}

        note = notes_service.get_note(db, org_id=principal.org_id, note_id=note_uuid)
        if not note:
            return {"error": f"Note {note_id_str} not found"}

        return {
            "id": str(note.id),
            "title": note.title,
            "body": note.body,
            "created_at": note.created_at.isoformat() if note.created_at else None,
            "updated_at": note.updated_at.isoformat() if note.updated_at else None,
        }

    # 6. list_notes (Read)
    if name == "list_notes":
        limit = max(1, min(int(args.get("limit", 20) or 20), 100))
        offset = max(0, int(args.get("offset", 0) or 0))

        listed = notes_service.list_notes(db, org_id=principal.org_id, limit=limit, offset=offset)
        return {
            "total": listed.total,
            "notes": [
                {
                    "id": str(n.id),
                    "title": n.title,
                    "body_snippet": n.body[:200] if n.body else "",
                    "created_at": n.created_at.isoformat() if n.created_at else None,
                }
                for n in listed.notes
            ],
        }

    # 7. get_catalog_impact (Read)
    if name == "get_catalog_impact":
        product = str(args.get("product", "")).strip()
        if not product:
            return {"error": "product is required"}

        try:
            impact = query_product_impact(db, workspace_id=workspace_id, product_name=product)
            return {
                "product": product,
                "prerequisites": impact.get("prerequisites", []),
                "conflicts": impact.get("conflicts", []),
                "integrations": impact.get("integrations", []),
                "alternatives": impact.get("alternatives", []),
            }
        except Exception as exc:
            return {"product": product, "error": str(exc)}

    # 8. web_search (Read)
    if name == "web_search":
        query = str(args.get("query", "")).strip()
        if not query:
            return {"error": "query is required"}
        max_res = max(1, min(int(args.get("max_results", 5) or 5), 10))
        fb = gather_web_fallback(query)
        return {
            "query": query,
            "note": fb.note,
            "results": [
                {"title": p.title, "url": p.url, "snippet": p.text[:500]}
                for p in fb.passages[:max_res]
            ],
        }

    # 9. create_note (Write)
    if name == "create_note":
        title = str(args.get("title", "")).strip()
        body = str(args.get("body", "")).strip()
        if not title or not body:
            return {"error": "title and body are required to create a note"}

        note = notes_service.create_note(
            db,
            principal=principal,
            workspace_id=workspace_id,
            title=title,
            body=body,
        )
        return {
            "success": True,
            "id": str(note.id),
            "title": note.title,
            "message": "Note successfully saved to knowledge base",
        }

    # 10. upload_text_document (Write)
    if name == "upload_text_document":
        filename = str(args.get("filename", "")).strip()
        content = str(args.get("content", ""))
        title = str(args.get("title", "")).strip() or filename
        vendor = str(args.get("vendor", "")).strip() or None

        if not filename or not content:
            return {"error": "filename and content are required"}

        meta = DocumentMetadataIn(
            title=title,
            source_type=str(SourceType.TEXT) if hasattr(SourceType, "TEXT") else str(SourceType.PASTE),
            vendor=vendor,
        )
        data = content.encode("utf-8")
        doc = create_document(
            db,
            principal=principal,
            original_filename=filename,
            data=data,
            mime_type="text/markdown" if filename.endswith((".md", ".markdown")) else "text/plain",
            metadata=meta,
        )
        enqueue_ingestion(db, doc)
        return {
            "success": True,
            "document_id": str(doc.id),
            "filename": filename,
            "title": title,
            "message": "Document ingested and queued for chunking and vector indexing",
        }

    # 11. add_catalog_product (Write)
    if name == "add_catalog_product":
        prod_name = str(args.get("name", "")).strip()
        vendor = str(args.get("vendor", "")).strip()
        desc = str(args.get("description", "")).strip() or None
        cat = str(args.get("category", "")).strip() or "General"

        if not prod_name or not vendor:
            return {"error": "name and vendor are required"}

        try:
            service = CatalogService(db)
            data = ProductIn(
                name=prod_name,
                vendor=vendor,
                description=desc,
                category=cat,
            )
            prod = service.create_product(
                org_id=principal.org_id,
                workspace_id=workspace_id,
                data=data,
            )
            return {
                "success": True,
                "product_id": str(prod.id),
                "name": prod.name,
                "vendor": prod.vendor,
                "message": f"Product '{prod.name}' registered in catalog graph",
            }
        except Exception as exc:
            return {"error": f"Failed to register product: {exc}"}

    # 12. link_catalog_products (Write)
    if name == "link_catalog_products":
        src = str(args.get("source_product", "")).strip()
        tgt = str(args.get("target_product", "")).strip()
        rel = str(args.get("relation", "")).strip()
        reason = str(args.get("reason", "")).strip() or None

        if not src or not tgt or not rel:
            return {"error": "source_product, target_product, and relation are required"}

        try:
            from app.db.models import Product
            from sqlalchemy import func, select

            src_prod = db.scalar(
                select(Product).where(
                    Product.workspace_id == workspace_id,
                    func.lower(Product.name) == func.lower(src),
                )
            )
            tgt_prod = db.scalar(
                select(Product).where(
                    Product.workspace_id == workspace_id,
                    func.lower(Product.name) == func.lower(tgt),
                )
            )
            if not src_prod:
                return {"error": f"Source product '{src}' not found in catalog"}
            if not tgt_prod:
                return {"error": f"Target product '{tgt}' not found in catalog"}

            service = CatalogService(db)
            edge_data = ProductEdgeIn(
                source_product_id=src_prod.id,
                target_product_id=tgt_prod.id,
                relation_type=rel,
                evidence=reason or f"Linked via MCP command between {src} and {tgt}",
            )
            edge = service.create_edge(
                org_id=principal.org_id,
                workspace_id=workspace_id,
                data=edge_data,
            )
            return {
                "success": True,
                "source": src,
                "target": tgt,
                "relation": rel,
                "edge_id": str(edge.id),
                "message": f"Linked '{src}' --[{rel}]--> '{tgt}' in catalog graph",
            }
        except Exception as exc:
            return {"error": f"Failed to link products: {exc}"}

    # 13. delete_note (Write)
    if name == "delete_note":
        note_id_str = str(args.get("note_id", "")).strip()
        try:
            note_uuid = uuid.UUID(note_id_str)
        except ValueError:
            return {"error": f"Invalid note UUID: {note_id_str}"}

        deleted = notes_service.delete_note(db, org_id=principal.org_id, note_id=note_uuid)
        return {
            "success": bool(deleted),
            "note_id": note_id_str,
            "message": "Note deleted" if deleted else "Note not found",
        }

    return {"error": f"Unknown MCP tool: {name}"}


# ── JSON-RPC 2.0 Dispatcher ──────────────────────────────────────────────────

def handle_mcp_jsonrpc_request(
    db: Session,
    principal: Principal,
    request: dict[str, Any],
) -> dict[str, Any]:
    """Handle a standard Model Context Protocol JSON-RPC request."""
    req_id = request.get("id")
    method = request.get("method", "")
    params = request.get("params") or {}

    # 1. initialize
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "serverInfo": {
                    "name": SERVER_NAME,
                    "version": SERVER_VERSION,
                },
                "capabilities": {
                    "tools": {
                        "listChanged": False,
                    },
                    "resources": {
                        "subscribe": False,
                        "listChanged": False,
                    },
                    "prompts": {
                        "listChanged": False,
                    },
                },
            },
        }

    # 2. notifications/initialized
    if method == "notifications/initialized":
        return {"jsonrpc": "2.0", "result": {}}

    # 3. tools/list
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": [
                    {
                        "name": t["name"],
                        "description": t["description"],
                        "inputSchema": t["inputSchema"],
                    }
                    for t in MCP_TOOLS
                ]
            },
        }

    # 4. tools/call
    if method == "tools/call":
        name = str(params.get("name", "")).strip()
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            arguments = {}

        try:
            tool_result = execute_mcp_tool_call(db, principal, name, arguments)
            is_error = "error" in tool_result
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(tool_result, indent=2, default=str),
                        }
                    ],
                    "isError": is_error,
                },
            }
        except Exception as exc:
            logger.error("MCP tool execution error on %s", name, exc_info=True)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps({"error": f"{type(exc).__name__}: {exc}"}),
                        }
                    ],
                    "isError": True,
                },
            }

    # 5. resources/list
    if method == "resources/list":
        docs = db.scalars(readable_documents(principal).limit(20)).all()

        resources = [
            {
                "uri": f"knowledge://document/{doc.id}",
                "name": _doc_title(doc),
                "mimeType": "text/markdown",
                "description": f"Indexed collateral: {doc.original_filename}",
            }
            for doc in docs
        ]
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"resources": resources},
        }

    # 6. prompts/list
    if method == "prompts/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "prompts": [
                    {
                        "name": "ask_knowledge_base",
                        "description": "Grounded question answering with citations from Personal Knowledge AI",
                        "arguments": [
                            {
                                "name": "question",
                                "description": "The question to investigate",
                                "required": True,
                            }
                        ],
                    },
                    {
                        "name": "catalog_impact_analysis",
                        "description": "Examine prerequisites, conflicts, and architecture recommendations for a product",
                        "arguments": [
                            {
                                "name": "product",
                                "description": "Name of the product",
                                "required": True,
                            }
                        ],
                    },
                ]
            },
        }

    # Unknown method
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {
            "code": -32601,
            "message": f"Method not found: {method}",
        },
    }
