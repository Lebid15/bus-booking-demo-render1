from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings
from django.utils.module_loading import import_string

from securityops.models import StoredFile


@dataclass(frozen=True)
class ScanResult:
    clean: bool
    detected_mime: str
    size_bytes: int
    sha256: str
    engine: str
    malware_name: str | None = None


def _local_scanner(file: StoredFile, expected_sha256: str) -> ScanResult:
    result = str(getattr(settings, "FILE_SCAN_MOCK_RESULT", "clean")).lower()
    return ScanResult(
        clean=result == "clean",
        detected_mime=file.mime_type,
        size_bytes=file.size_bytes,
        sha256=expected_sha256,
        engine="local-contract-scanner",
        malware_name=None if result == "clean" else "test-malware-signature",
    )


def scan_stored_file(file: StoredFile, expected_sha256: str) -> ScanResult:
    backend = str(getattr(settings, "FILE_SCANNER_BACKEND", "")).strip()
    if not backend:
        return _local_scanner(file, expected_sha256)
    scanner = import_string(backend)
    result = scanner(file, expected_sha256)
    if not isinstance(result, ScanResult):
        raise TypeError("FILE_SCANNER_BACKEND must return ScanResult")
    return result
