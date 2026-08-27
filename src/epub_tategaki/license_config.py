from __future__ import annotations

from .license_client import LicenseConfig

LICENSE_REQUIRED = True
OFFLINE_GRACE_DAYS = 7

LICENSE_CONFIG = LicenseConfig(
    supabase_url="https://wktwfbocbwyqcdebwcgh.supabase.co",
    publishable_key="sb_publishable_K8r3_LrlVhDgdu9QihplcA_WpD61aP7",
    product_slug="epub-tategaki-pdf-maker",
    app_version="2.2",
)
