from __future__ import annotations

import json
import os
import platform
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
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
    """Reusable desktop license client.

    Only the public Supabase publishable key is stored in the desktop app.
    Privileged license decisions are performed by authenticated Edge Functions.
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
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise LicenseError("NETWORK_ERROR") from exc

    def _store_session(self, data: dict, email: str | None = None):
        access = data.get("access_token")
        refresh = data.get("refresh_token")
        if access:
            self.state["access_token"] = access
        if refresh:
            self.state["refresh_token"] = refresh
        if email:
            self.state["email"] = email
        self._save_state()

    def sign_up(self, email: str, password: str):
        data = self._request(
            f"{self.cfg.supabase_url}/auth/v1/signup",
            {"email": email, "password": password},
        )
        self._store_session(data, email)
        return data

    def sign_in(self, email: str, password: str):
        data = self._request(
            f"{self.cfg.supabase_url}/auth/v1/token?grant_type=password",
            {"email": email, "password": password},
        )
        self._store_session(data, email)
        return data

    def refresh(self):
        token = self.state.get("refresh_token")
        if not token:
            raise LicenseError("AUTH_REQUIRED")
        data = self._request(
            f"{self.cfg.supabase_url}/auth/v1/token?grant_type=refresh_token",
            {"refresh_token": token},
        )
        self._store_session(data)
        return data

    def sign_out_local(self):
        install_id = self.state.get("install_id")
        self.state = {"install_id": install_id} if install_id else {}
        self._save_state()

    @property
    def token(self):
        return self.state.get("access_token")

    @property
    def email(self):
        return self.state.get("email", "")

    @property
    def install_id(self):
        return self.state["install_id"]

    @property
    def cached_license(self):
        return self.state.get("license") or {}

    def _edge_request(self, function_name: str, payload: dict):
        if not self.token:
            raise LicenseError("AUTH_REQUIRED")
        try:
            return self._request(
                f"{self.cfg.supabase_url}/functions/v1/{function_name}",
                payload,
                self.token,
            )
        except LicenseError as exc:
            if str(exc) in {"AUTH_REQUIRED", "Invalid JWT", "JWT expired"} and self.state.get("refresh_token"):
                self.refresh()
                return self._request(
                    f"{self.cfg.supabase_url}/functions/v1/{function_name}",
                    payload,
                    self.token,
                )
            raise

    def _mark_verified(self, data: dict):
        self.state["license"] = data
        self.state["last_verified_at"] = time.time()
        self._save_state()

    def activate(self, license_key: str):
        data = self._edge_request(
            "license-activate",
            {
                "licenseKey": license_key.strip(),
                "productSlug": self.cfg.product_slug,
                "installId": self.install_id,
                "deviceLabel": platform.node() or platform.system(),
                "appVersion": self.cfg.app_version,
            },
        )
        self._mark_verified(data)
        return data

    def check(self):
        data = self._edge_request(
            "license-check",
            {
                "productSlug": self.cfg.product_slug,
                "installId": self.install_id,
                "appVersion": self.cfg.app_version,
            },
        )
        self._mark_verified(data)
        return data

    def offline_grace_ok(self, days: int = 7) -> bool:
        verified = self.state.get("last_verified_at")
        lic = self.cached_license
        if not verified or not lic.get("ok"):
            return False
        if time.time() - float(verified) > days * 86400:
            return False
        expires = lic.get("expiresAt")
        if expires:
            try:
                dt = datetime.fromisoformat(expires.replace("Z", "+00:00"))
                if dt.astimezone(timezone.utc) < datetime.now(timezone.utc):
                    return False
            except Exception:
                return False
        return True

    def deactivate_this_device(self):
        data = self._edge_request(
            "license-deactivate",
            {"productSlug": self.cfg.product_slug, "installId": self.install_id},
        )
        self.state.pop("license", None)
        self.state.pop("last_verified_at", None)
        self._save_state()
        return data

    def latest_release(self, channel: str = "stable"):
        return self._edge_request(
            "latest-release",
            {"productSlug": self.cfg.product_slug, "channel": channel},
        )
