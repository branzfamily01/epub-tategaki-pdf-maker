from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from reportlab.pdfgen.canvas import Canvas
from epub_tategaki.quality_check import inspect_pdf, create_sample_pdf, write_quality_report


class QualityCheckTest(unittest.TestCase):
    def test_valid_pdf_is_checked_and_sample_created(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            src = root / "book.pdf"
            canvas = Canvas(str(src), pagesize=(300, 420))
            for i in range(8):
                canvas.drawString(30, 320, f"page {i + 1} sample text for quality check")
                canvas.drawString(30, 290, "EPUB Tategaki PDF Maker test document")
                canvas.showPage()
            canvas.save()

            report = inspect_pdf(src)
            self.assertEqual(report.page_count, 8)
            self.assertEqual(report.status, "OK")
            sample = create_sample_pdf(src, root / "sample.pdf", report.sampled_pages)
            self.assertTrue(sample.exists())
            out = write_quality_report(report, root / "quality.json")
            self.assertTrue(out.exists())

    def test_missing_pdf_is_error(self):
        report = inspect_pdf("definitely-missing.pdf")
        self.assertEqual(report.status, "ERROR")


if __name__ == "__main__":
    unittest.main()
