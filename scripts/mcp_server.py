#!/usr/bin/env python3
"""Personal Knowledge AI - Model Context Protocol (MCP) Stdio Server.

This script runs as a subprocess launched by Claude Desktop, Cursor, Antigravity,
or other MCP-compatible clients. It listens for JSON-RPC 2.0 requests on stdin,
forwards tool execution and queries to the Personal Knowledge AI backend API,
and writes JSON-RPC responses to stdout.

Zero external dependencies: uses only Python standard library.

Environment variables:
    PERSONAL_KNOWLEDGE_API_URL: Base URL of backend (default: http://localhost:8000)
    PERSONAL_KNOWLEDGE_API_KEY: Bearer access token generated from the website
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

API_URL = os.environ.get("PERSONAL_KNOWLEDGE_API_URL", "http://localhost:8000").rstrip("/")
API_KEY = os.environ.get("PERSONAL_KNOWLEDGE_API_KEY", "").strip()

PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "personal-knowledge-ai"
SERVER_VERSION = "1.0.0"

# Fallback tool definitions if backend is booting or warming up
FALLBACK_TOOLS = [
    {
        "name": "search_knowledge",
        "description": "Hybrid search (keyword BM25 + vector) across collateral and documents.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query or question"},
                "top_k": {"type": "integer", "description": "Number of hits", "default": 5},
            },
            "required": ["query"],
        },
    },
    {
        "name": "ask_intelligence",
        "description": "Ask Grounded Knowledge AI with live web search fallback.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "Question to answer"},
                "strict_mode": {"type": "boolean", "default": False},
            },
            "required": ["question"],
        },
    },
    {
        "name": "list_documents",
        "description": "List documents in knowledge base.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 20},
            },
        },
    },
    {
        "name": "read_document",
        "description": "Read document chunks and text by document ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "document_id": {"type": "string", "description": "Document UUID"},
            },
            "required": ["document_id"],
        },
    },
    {
        "name": "create_note",
        "description": "Create and persist a new markdown note in the knowledge base.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Note title"},
                "body": {"type": "string", "description": "Markdown body"},
            },
            "required": ["title", "body"],
        },
    },
    {
        "name": "upload_text_document",
        "description": "Ingest text or markdown document directly into knowledge base.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "Filename with extension"},
                "content": {"type": "string", "description": "Raw text content"},
            },
            "required": ["filename", "content"],
        },
    },
    {
        "name": "get_catalog_impact",
        "description": "Query product graph for prerequisites, conflicts, and integrations.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "product": {"type": "string", "description": "Product name"},
            },
            "required": ["product"],
        },
    },
    {
        "name": "web_search",
        "description": "Perform live web search and extract page contents.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
            },
            "required": ["query"],
        },
    },
]


def log_err(msg: str) -> None:
    sys.stderr.write(f"[{SERVER_NAME}] {msg}\n")
    sys.stderr.flush()


def send_json(data: dict[str, Any]) -> None:
    out = json.dumps(data)
    sys.stdout.write(out + "\n")
    sys.stdout.flush()


def forward_to_backend(payload: dict[str, Any]) -> dict[str, Any] | None:
    """Forward a JSON-RPC request to the Personal Knowledge AI backend API."""
    url = f"{API_URL}/api/mcp/custom-server/rpc"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    data_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data_bytes, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        log_err(f"HTTP {exc.code} from backend: {err_body}")
        return None
    except Exception as exc:
        log_err(f"Failed to reach backend at {url}: {exc}")
        return None


def handle_request(req: dict[str, Any]) -> None:
    req_id = req.get("id")
    method = req.get("method", "")

    # For initialize, we can return directly or query backend
    if method == "initialize":
        send_json({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "serverInfo": {
                    "name": SERVER_NAME,
                    "version": SERVER_VERSION,
                },
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {"subscribe": False, "listChanged": False},
                    "prompts": {"listChanged": False},
                },
            },
        })
        return

    if method == "notifications/initialized":
        return

    # Try forwarding to the backend API first
    backend_reply = forward_to_backend(req)
    if backend_reply is not None:
        send_json(backend_reply)
        return

    # Fallback if backend is unavailable or not authenticated
    if method == "tools/list":
        send_json({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": FALLBACK_TOOLS},
        })
        return

    if method == "tools/call":
        send_json({
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"Error: Unable to connect to Personal Knowledge AI at {API_URL}. "
                            "Please ensure the backend server is running and PERSONAL_KNOWLEDGE_API_KEY is configured."
                        ),
                    }
                ],
                "isError": True,
            },
        })
        return

    send_json({
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {
            "code": -32601,
            "message": f"Method not found or backend unreachable: {method}",
        },
    })


def main() -> None:
    log_err(f"Server starting. API_URL={API_URL}, API_KEY={'[configured]' if API_KEY else '[not set]'}")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            if isinstance(req, dict):
                handle_request(req)
        except json.JSONDecodeError:
            send_json({
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error: Invalid JSON"},
            })
        except Exception as exc:
            log_err(f"Error handling request: {exc}")


if __name__ == "__main__":
    main()
