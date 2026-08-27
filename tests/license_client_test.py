import json
import os
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from epub_tategaki.license_client import LicenseClient, LicenseConfig


class LicenseClientTest(unittest.TestCase):
    def _client(self, root):
        cfg = LicenseConfig("https://example.invalid", "public-key", "product", "1.0")
        with patch.dict(os.environ, {"APPDATA": str(root)}):
            return LicenseClient(cfg, app_folder="test-license-app")

    def test_install_id_is_persistent(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            c1 = self._client(root)
            first = c1.install_id
            c2 = self._client(root)
            self.assertEqual(first, c2.install_id)

    def test_offline_grace_requires_recent_verified_license(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            c = self._client(root)
            c.state["license"] = {"ok": True, "expiresAt": None}
            c.state["last_verified_at"] = time.time()
            c._save_state()
            self.assertTrue(c.offline_grace_ok(7))
            c.state["last_verified_at"] = time.time() - 8 * 86400
            c._save_state()
            self.assertFalse(c.offline_grace_ok(7))


if __name__ == "__main__":
    unittest.main()
