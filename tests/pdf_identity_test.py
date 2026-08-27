from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from pypdf import PdfReader, PdfWriter

from epub_tategaki.pdf_identity import stamp_license_metadata


class PdfIdentityTest(unittest.TestCase):
    def test_non_personal_identity_is_embedded(self):
        with TemporaryDirectory() as td:
            path = Path(td) / "book.pdf"
            writer = PdfWriter()
            writer.add_blank_page(width=300, height=420)
            with path.open("wb") as f:
                writer.write(f)

            stamp_license_metadata(
                path,
                {"licenseId": "LIC-TEST", "customerCode": "CUST-001"},
                "INSTALL-XYZ",
                "2.2",
                "BUILD-CUSTOMER",
                "education",
            )
            meta = PdfReader(str(path)).metadata
            self.assertEqual(meta.get("/TategakiLicenseId"), "LIC-TEST")
            self.assertEqual(meta.get("/TategakiCustomerCode"), "CUST-001")
            self.assertEqual(meta.get("/TategakiInstallId"), "INSTALL-XYZ")
            self.assertEqual(meta.get("/TategakiAppVersion"), "2.2")
            self.assertEqual(meta.get("/TategakiEdition"), "education")


if __name__ == "__main__":
    unittest.main()
