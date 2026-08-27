from __future__ import annotations

import json
import os
import platform
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path


@dataclass
class LicenseConfig:
    supabase_url: str
    publishable_key: str
    product_slug: str
    app_version: str


class LicenseError(RuntimeError):
    pass


class LicenseClient:
    """Common desktop license client.

    The service-role key is never stored in the desktop app. The app uses a
    Supabase publishable key plus the signed-in user's access token, while all
    privileged license checks are handled by authenticated Edge Functions.
    """

    def __init__(self, config: LicenseConfig, app_folder: str = "EPUB-Tategaki-PDF-Maker"):
        self.cfg = config
        base = Path(os.environ.get("APPDATA") or (Path.home() / ".config")) / app_folder
        base.mkdir(parents=True, exist_ok=True)
        self.state_path = base / "license-state.json"
        self.state = self._load_state()
        if not self.state.get("install_id"):
            self.state["install_id"] = str(uuid.uuid4())
            self._save_state()

    def _load_state(self):
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_state(self):
        self.state_path.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")

    def _request(self, url: str, payload: dict, token: str | None = None):
        headers = {"Content-Type": "application/json", "apikey": self.cfg.publishable_key}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode("utf-8"))
            except Exception:
                detail = {"error": str(exc)}
            raise LicenseError(detail.get("error", str(exc))) from exc

    def sign_up(self, email: str, password: str):
        return self._request(
            f"{self.cfg.supabase_url}/auth/v1/signup",
            {"email": email, "password": password},
        )

    def sign_in(self, email: str, password: str):
        data = self._request(
            f"{self.cfg.supabase_url}/auth/v1/token?grant_type=password",
            {"email": email, "password": password},
        )
        self.state["access_token"] = data.get("access_token")
        self.state["refresh_token"] = data.get("refresh_token")
        self.state["email"] = email
        self._save_state()
        return data

    @property
    def token(self):
        return self.state.get("access_token")

    @property
    def install_id(self):
        return self.state["install_id"]

    def activate(self, license_key: str):
        if not self.token:
            raise LicenseError("AUTH_REQUIRED")
        data = self._request(
            f"{self.cfg.supabase_url}/functions/v1/license-activate",
            {
                "licenseKey": license_key,
                "productSlug": self.cfg.product_slug,
                "installId": self.install_id,
                "deviceLabel": platform.node() or platform.system(),
                "appVersion": self.cfg.app_version,
            },
            self.token,
        )
        self.state["license"] = data
        self._save_state()
        return data

    def check(self):
        if not self.token:
            raise LicenseError("AUTH_REQUIRED")
        data = self._request(
            f"{self.cfg.supabase_url}/functions/v1/license-check",
            {
                "productSlug": self.cfg.product_slug,
                "installId": self.install_id,
                "appVersion": self.cfg.app_version,
            },
            self.token,
        )
        self.state["license"] = data
        self._save_state()
        return data

    def deactivate_this_device(self):
        if not self.token:
            raise LicenseError("AUTH_REQUIRED")
        return self._request(
            f"{self.cfg.supabase_url}/functions/v1/license-deactivate",
            {"productSlug": self.cfg.product_slug, "installId": self.install_id},
            self.token,
        )

    def latest_release(self, channel: str = "stable"):
        if not self.token:
            raise LicenseError("AUTH_REQUIRED")
        return self._request(
            f"{self.cfg.supabase_url}/functions/v1/latest-release",
            {"productSlug": self.cfg.product_slug, "channel": channel},
            self.token,
        )
