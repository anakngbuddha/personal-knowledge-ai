"""Hard call deadlines must terminate resistant workers and their descendants."""
import json
import os
import subprocess
import sys
import threading
import time
import psutil
import pytest
from app.mcp import process_calls
from app.core.errors import AppError


def _echo(value):
    return {"pid": os.getpid(), "value": value}


def _resists_deadline(marker):
    from pathlib import Path
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    Path(marker).write_text(json.dumps([os.getpid(), child.pid]))
    while True:
        time.sleep(0.01)


def test_sdk_worker_result_and_reaping():
    result = process_calls.call_isolated(_echo, ("fixture",), timeout=10)
    assert result["value"] == "fixture" and result["pid"] != os.getpid()
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and psutil.pid_exists(result["pid"]):
        time.sleep(0.05)
    assert not psutil.pid_exists(result["pid"])


def test_hard_deadline_terminates_resistant_worker_tree(tmp_path):
    marker = tmp_path / "worker-pids.json"
    started = time.monotonic()
    with pytest.raises(TimeoutError):
        process_calls.call_isolated(_resists_deadline, (str(marker),), timeout=5)
    assert time.monotonic()-started < 10
    assert marker.exists()
    for pid in json.loads(marker.read_text()):
        if psutil.pid_exists(pid):
            assert psutil.Process(pid).status() == psutil.STATUS_ZOMBIE


def test_worker_output_budget_and_admission_limit(monkeypatch):
    with pytest.raises(AppError):
        process_calls.call_isolated(_echo, ("x"*10000,), timeout=10, max_bytes=100)
    semaphore = threading.BoundedSemaphore(1)
    semaphore.acquire()
    monkeypatch.setattr(process_calls, "_SLOTS", semaphore)
    with pytest.raises(AppError) as exc:
        process_calls.call_isolated(_echo, ("fixture",), timeout=10)
    assert exc.value.status_code == 429
