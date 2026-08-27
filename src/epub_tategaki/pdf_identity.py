from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

from pypdf import PdfReader, PdfWriter

from .build_identity import BUILD_CUSTOMER_CODE, BUILD_EDITION
from .license_config import LICENSE_CONFIG


def stamp_license_metadata(
    pdf_path: str | Path,
    license_data: dict | None,
    install_id: str,
    app_version: str,
    build_customer_code: str = "",
    edition: str = "standard",
) -> None:
    """Embed traceable, non-personal license metadata in a generated PDF.

    No email address or name is embedded. The values are opaque license/customer/
    install identifiers used for support and unauthorized-redistribution tracing.
    """
    path = Path(pdf_path)
    if not path.exists():
        return
    license_data = license_data or {}
    reader = PdfReader(str(path))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)

    old = reader.metadata or {}
    metadata = {str(k): str(v) for k, v in old.items() if k and v is not None}
    metadata.update({
        "/TategakiAppVersion": str(app_version),
        "/TategakiLicenseId": str(license_data.get("licenseId") or ""),
        "/TategakiCustomerCode": str(license_data.get("customerCode") or build_customer_code or ""),
        "/TategakiInstallId": str(install_id or ""),
        "/TategakiEdition": str(edition or "standard"),
    })
    writer.add_metadata(metadata)

    with NamedTemporaryFile(prefix=path.stem + "_", suffix=".pdf", dir=path.parent, delete=False) as tmp:
        tmp_path = Path(tmp.name)
        writer.write(tmp)
    tmp_path.replace(path)


def stamp_cached_identity(pdf_path: str | Path) -> None:
    """Read only non-personal identifiers from the local license cache and stamp them.

    Authentication tokens and the account email are never copied into the PDF.
    """
    base = Path(os.environ.get("APPDATA") or (Path.home() / ".config")) / "EPUB-Tategaki-PDF-Maker"
    state_path = base / "license-state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        state = {}
    stamp_license_metadata(
        pdf_path,
        state.get("license") or {},
        str(state.get("install_id") or ""),
        LICENSE_CONFIG.app_version,
        BUILD_CUSTOMER_CODE,
        BUILD_EDITION,
    )
