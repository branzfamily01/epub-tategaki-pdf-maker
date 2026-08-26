from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from pypdf import PdfWriter
from epub_tategaki.quality_check import inspect_pdf, create_sample_pdf, write_quality_report


class QualityCheckTest(unittest.TestCase):
    def test_valid_pdf_is_checked_and_sample_created(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            src = root / "book.pdf"
            writer = PdfWriter()
            for _ in range(8):
                writer.add_blank_page(width=300, height=420)
            with src.open("wb") as f:
                writer.write(f)
            report = inspect_pdf(src)
            self.assertEqual(report.page_count, 8)
            self.assertIn(report.status, {"OK", "CHECK"})
            sample = create_sample_pdf(src, root / "sample.pdf", report.sampled_pages)
            self.assertTrue(sample.exists())
            out = write_quality_report(report, root / "quality.json")
            self.assertTrue(out.exists())

    def test_missing_pdf_is_error(self):
        report = inspect_pdf("definitely-missing.pdf")
        self.assertEqual(report.status, "ERROR")


if __name__ == "__main__":
    unittest.main()
