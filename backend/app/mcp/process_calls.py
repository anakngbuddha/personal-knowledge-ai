"""Hard deadlines for SDK calls, including cancellation-resistant Python workers."""
import asyncio
import json
import multiprocessing
import threading
import psutil
from app.core.errors import AppError

_SLOTS = threading.BoundedSemaphore(2)


def _worker(connection, function, arguments, budget):
    try:
        result = function(*arguments)
        payload = json.dumps({"result": result}, allow_nan=False).encode()
        if len(payload) > budget:
            raise ValueError("MCP output budget")
        connection.send_bytes(payload)
    except BaseException:
        try:
            connection.send_bytes(b'{"error":"MCP operation failed"}')
        except (OSError, BrokenPipeError):
            pass
    finally:
        connection.close()


def _stop_tree(process):
    try:
        descendants = psutil.Process(process.pid).children(recursive=True)
    except psutil.NoSuchProcess:
        descendants = []
    # Stop new SDK launches before killing the previously enumerated descendants.
    if process.is_alive():
        process.kill()
    for child in reversed(descendants):
        try:
            child.kill()
        except psutil.NoSuchProcess:
            pass
    psutil.wait_procs(descendants, timeout=1)
    process.join(timeout=1)


def call_isolated(function, arguments, *, timeout, max_bytes=32768):
    if not _SLOTS.acquire(blocking=False):
        raise AppError("MCP capacity exceeded", status_code=429)
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(target=_worker, args=(child, function, arguments, max_bytes), daemon=True)
    try:
        process.start()
        child.close()
        if not parent.poll(timeout):
            raise TimeoutError("MCP deadline exceeded")
        try:
            payload = json.loads(parent.recv_bytes(maxlength=max_bytes))
        except (EOFError, OSError, ValueError) as exc:
            raise AppError("MCP worker failed", status_code=502) from exc
        if "error" in payload:
            raise AppError("MCP operation failed", status_code=502)
        return payload["result"]
    finally:
        try:
            if process.pid:
                _stop_tree(process)
        finally:
            parent.close()
            child.close()
            _SLOTS.release()


def _sdk_request(spec, method, name, arguments):
    from app.mcp.client import SdkMcpClient
    client = SdkMcpClient()
    coroutine = client._alist_tools(spec) if method == "list" else client._acall_tool(spec, name, arguments)
    return asyncio.run(coroutine)


def sdk_request(spec, method, *, name=None, arguments=None, timeout, max_bytes):
    return call_isolated(_sdk_request, (spec, method, name, arguments or {}), timeout=timeout, max_bytes=max_bytes)
