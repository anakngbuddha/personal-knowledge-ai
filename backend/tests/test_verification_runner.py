"""Verification must fail closed for missing tooling or unexpected skips."""

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "verification_runner", Path(__file__).resolve().parents[2] / "scripts" / "verify_project.py"
)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def test_missing_frontend_dependencies_fail(tmp_path):
    (tmp_path / "frontend").mkdir()
    assert not runner.verify_frontend(tmp_path)


def test_missing_npm_fails(tmp_path, monkeypatch):
    (tmp_path / "frontend" / "node_modules").mkdir(parents=True)

    def missing(*args, **kwargs):
        raise FileNotFoundError("npm")

    monkeypatch.setattr(runner.subprocess, "run", missing)
    assert not runner.verify_frontend(tmp_path)


def test_only_necessary_database_skips_are_accepted(tmp_path):
    report = tmp_path / "report.xml"
    assert not runner.acceptable_backend_skips(report)
    report.write_text('<testsuites><testsuite><testcase><skipped message="not implemented"/></testcase></testsuite></testsuites>')
    assert not runner.acceptable_backend_skips(report)
    report.write_text('<testsuites><testsuite><testcase><skipped message="no reachable DATABASE_URL; set one to run the integration tests"/></testcase></testsuite></testsuites>')
    assert runner.acceptable_backend_skips(report)
    report.write_text('<testsuites><testsuite><testcase/></testsuite></testsuites>')
    assert runner.acceptable_backend_skips(report)
