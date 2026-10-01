"""Validated timestamp/UUID cursors; callers retain tenant predicates."""
import base64
import json
import uuid
from datetime import datetime, timezone
from sqlalchemy import tuple_
from app.core.errors import AppError


def encode_cursor(timestamp, row_id):
    timestamp = timestamp.replace(tzinfo=timezone.utc) if timestamp.tzinfo is None else timestamp
    return base64.urlsafe_b64encode(json.dumps({"timestamp": timestamp.isoformat(), "id": str(row_id)}).encode()).decode().rstrip("=")


def seek_before(statement, timestamp_column, id_column, cursor):
    if not cursor:
        return statement
    try:
        if len(cursor) > 512:
            raise ValueError()
        decoded = json.loads(base64.b64decode(cursor + "=" * (-len(cursor) % 4), altchars=b"-_", validate=True))
        if not isinstance(decoded, dict) or set(decoded) != {"timestamp", "id"}:
            raise ValueError()
        timestamp = datetime.fromisoformat(decoded["timestamp"].replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError()
        row_id = uuid.UUID(decoded["id"])
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        raise AppError("invalid pagination cursor", status_code=422) from exc
    return statement.where(tuple_(timestamp_column, id_column) < tuple_(timestamp, row_id))
