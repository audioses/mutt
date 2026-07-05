"""Shared zip-bomb guard for Office document handlers.

Office formats (.docx/.xlsx/.pptx) are ZIP archives. A malicious file can
ship a tiny outer archive that decompresses to gigabytes of XML and exhaust
memory during parsing. We cheaply inspect the central directory and raise
before handing the file to python-docx / openpyxl / python-pptx.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

# Conservative upper bound for total uncompressed size across all entries.
# A real Office document virtually never exceeds a few hundred MiB even with
# embedded media; anything bigger is almost certainly adversarial.
MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024  # 512 MiB
# Maximum per-entry compression ratio; classic zip-bomb indicator.
MAX_COMPRESSION_RATIO = 250


class OfficeZipBombError(Exception):
    """Raised when an Office file's ZIP container looks like a bomb."""


def assert_safe_office_zip(file_path: Path) -> None:
    """Raise :class:`OfficeZipBombError` if the ZIP looks adversarial.

    The check is deliberately lightweight: it only reads the central
    directory, never the entry payloads. Safe files fall through in a few
    milliseconds.
    """
    try:
        with zipfile.ZipFile(str(file_path)) as zf:
            total = 0
            for info in zf.infolist():
                total += info.file_size
                if info.file_size and info.compress_size:
                    ratio = info.file_size / max(info.compress_size, 1)
                    if ratio > MAX_COMPRESSION_RATIO:
                        raise OfficeZipBombError(
                            f"Entry {info.filename!r} has compression ratio "
                            f"{ratio:.0f}x — refusing to parse."
                        )
                if total > MAX_UNCOMPRESSED_BYTES:
                    raise OfficeZipBombError(
                        f"Uncompressed size exceeds {MAX_UNCOMPRESSED_BYTES} "
                        f"bytes — refusing to parse."
                    )
    except zipfile.BadZipFile as exc:
        raise OfficeZipBombError(f"Not a valid Office container: {exc}") from exc
