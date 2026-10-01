"""Killable parser processes with Linux CPU/address-space limits and bounded JSON output."""
import json
import math
import multiprocessing
import os
from dataclasses import asdict
from app.core.config import settings
from app.core.errors import ExtractionError, ExtractionTimeout


def _parse(connection, data, file_type, limits):
    try:
        if os.name == "posix":
            import resource
            memory = 384 * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
            seconds = max(1, math.ceil(limits.timeout_seconds))
            resource.setrlimit(resource.RLIMIT_CPU, (seconds, seconds+1))
        from app.documents.extraction import extract
        result = asdict(extract(data, file_type, limits=limits))
        payload = json.dumps({"result": result}).encode()
        if len(payload) > limits.max_extracted_chars * 6 + 1048576:
            raise ExtractionError("parser output size limit exceeded")
        connection.send_bytes(payload)
    except Exception:
        connection.send_bytes(b'{"error":"document extraction failed"}')
    finally:
        connection.close()


def extract_isolated(data, file_type, limits=None, on_progress=None):
    from app.documents.extraction import Block, ExtractionResult
    from app.documents.limits import ParseLimits, guard_extracted_size
    limits = limits or ParseLimits()
    if len(data) > settings.max_upload_bytes:
        raise ExtractionError("parser input size limit exceeded")
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(target=_parse, args=(child, data, file_type, limits), daemon=True)
    try:
        process.start()
        child.close()
        if not parent.poll(limits.timeout_seconds):
            raise ExtractionTimeout("document parsing deadline exceeded")
        try:
            payload = json.loads(parent.recv_bytes(maxlength=limits.max_extracted_chars * 6 + 1048576))
        except (EOFError, OSError, ValueError) as exc:
            raise ExtractionError("parser terminated without a valid result") from exc
        if "error" in payload:
            raise ExtractionError("document extraction failed")
        output = payload["result"]
        output["blocks"] = [Block(**row) for row in output["blocks"]]
        result = ExtractionResult(**output)
        guard_extracted_size(result.total_chars, limits)
        return result
    finally:
        if process.pid:
            if process.is_alive():
                process.terminate()
            process.join(timeout=1)
            if process.is_alive():
                process.kill()
                process.join(timeout=1)
        parent.close()
        child.close()
