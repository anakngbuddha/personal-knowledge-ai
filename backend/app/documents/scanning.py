"""Malware scanning before parsing.

Three backends behind one interface:

* `none`      - explicit opt-out. Recorded on the document so it is auditable.
* `heuristic` - default. Not an antivirus, and does not pretend to be. It refuses
                the categories that matter for a collateral pipeline: Office macros,
                embedded executables, PDFs carrying JavaScript or launch actions,
                and OOXML packages with external-target relationships.
* `clamav`    - a real scanner over clamd's INSTREAM protocol when one is available.

`clamav` fails **closed**: if the scanner is configured and unreachable, the upload
is rejected. A silently skipped scanner is worse than no scanner, because the
document still ends up labelled as scanned.
"""

from __future__ import annotations

import io
import re
import socket
import struct
import zipfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from functools import lru_cache

from app.core.config import settings
from app.core.errors import MalwareDetected, ScannerUnavailable
from app.core.logging import get_logger

logger = get_logger(__name__)

_MACRO_PARTS = ("vbaproject.bin", "vbadata.xml", "macros/")
_PDF_DANGEROUS = (
    (rb"/JavaScript", "PDF contains JavaScript"),
    (rb"/JS", "PDF contains JavaScript"),
    (rb"/Launch", "PDF contains a Launch action"),
    (rb"/EmbeddedFile", "PDF contains an embedded file"),
    (rb"/OpenAction\s*<<[^>]*\/JS", "PDF auto-runs JavaScript on open"),
)
_EMBEDDED_EXECUTABLE = (
    (b"\x4d\x5a\x90\x00\x03", "embedded Windows executable"),
    (b"\x7fELF\x02\x01\x01", "embedded ELF executable"),
)
_EXTERNAL_TARGET_RE = re.compile(rb'TargetMode\s*=\s*"External"', re.IGNORECASE)


@dataclass
class ScanResult:
    backend: str
    clean: bool
    findings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"backend": self.backend, "clean": self.clean, "findings": self.findings}


class Scanner(ABC):
    name: str = "scanner"

    @abstractmethod
    def scan(self, data: bytes, file_type: str) -> ScanResult: ...


class NullScanner(Scanner):
    name = "none"

    def scan(self, data: bytes, file_type: str) -> ScanResult:
        return ScanResult(backend=self.name, clean=True, findings=["scanning disabled"])


class HeuristicScanner(Scanner):
    """Structural refusal rules. Cheap, deterministic, and testable."""

    name = "heuristic"

    def scan(self, data: bytes, file_type: str) -> ScanResult:
        findings: list[str] = []

        for magic, label in _EMBEDDED_EXECUTABLE:
            if magic in data:
                findings.append(label)

        if file_type == "pdf":
            findings.extend(self._scan_pdf(data))
        elif file_type in {"docx", "pptx", "xlsx"}:
            findings.extend(self._scan_ooxml(data))

        findings = sorted(set(findings))
        return ScanResult(backend=self.name, clean=not findings, findings=findings)

    def _scan_pdf(self, data: bytes) -> list[str]:
        return [label for pattern, label in _PDF_DANGEROUS if re.search(pattern, data)]

    def _scan_ooxml(self, data: bytes) -> list[str]:
        findings: list[str] = []
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                names = [n.lower() for n in archive.namelist()]
                if any(part in name for name in names for part in _MACRO_PARTS):
                    findings.append("Office document contains a VBA macro project")
                for name in archive.namelist():
                    if not name.lower().endswith(".rels"):
                        continue
                    with archive.open(name) as handle:
                        if _EXTERNAL_TARGET_RE.search(handle.read(65536)):
                            findings.append(
                                "OOXML package references an external relationship target"
                            )
                            break
        except zipfile.BadZipFile:
            findings.append("OOXML package is unreadable")
        return findings


class ClamAvScanner(Scanner):
    """clamd INSTREAM client. No third-party dependency, no shell out."""

    name = "clamav"

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self._host, self._port, self._timeout = host, port, timeout

    def scan(self, data: bytes, file_type: str) -> ScanResult:
        try:
            with socket.create_connection((self._host, self._port), timeout=self._timeout) as sock:
                sock.settimeout(self._timeout)
                sock.sendall(b"zINSTREAM\x00")
                for start in range(0, len(data), 65536):
                    chunk = data[start : start + 65536]
                    sock.sendall(struct.pack("!L", len(chunk)) + chunk)
                sock.sendall(struct.pack("!L", 0))
                response = b""
                while b"\x00" not in response:
                    received = sock.recv(4096)
                    if not received:
                        break
                    if len(response) + len(received) > 65536:
                        raise ScannerUnavailable("clamd response size limit exceeded")
                    response += received
        except OSError as exc:
            raise ScannerUnavailable(f"clamd at {self._host}:{self._port} unreachable: {exc}") from exc

        text = response.decode("utf-8", "replace").strip("\x00\n ")
        if text.endswith("OK"):
            return ScanResult(backend=self.name, clean=True)
        if "FOUND" in text:
            return ScanResult(backend=self.name, clean=False, findings=[text])
        raise ScannerUnavailable(f"clamd returned an unexpected reply: {text[:200]}")


@lru_cache
def get_scanner() -> Scanner:
    backend = settings.malware_scanner.lower()
    if backend == "none":
        logger.warning("malware scanning is disabled (MALWARE_SCANNER=none)")
        return NullScanner()
    if backend == "clamav":
        if not settings.clamav_host:
            raise ScannerUnavailable("MALWARE_SCANNER=clamav but CLAMAV_HOST is not set")
        return ClamAvScanner(
            settings.clamav_host, settings.clamav_port, settings.clamav_timeout_seconds
        )
    return HeuristicScanner()


def scan_or_raise(data: bytes, file_type: str, scanner: Scanner | None = None) -> ScanResult:
    scanner = scanner or get_scanner()
    result = scanner.scan(data, file_type)
    if not result.clean:
        raise MalwareDetected("; ".join(result.findings) or "scanner reported the file as unsafe")
    return result
