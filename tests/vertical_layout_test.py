from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from epub_tategaki.epub_parser import EpubBook, Token
from epub_tategaki.renderer import RenderOptions, render_book


class VerticalLayoutTest(unittest.TestCase):
    def test_special_vertical_text_renders(self):
        with TemporaryDirectory() as td:
            root = Path(td)
            book = EpubBook(source=root / "dummy.epub", workdir=root, title="試験", author="著者")
            book.tokens = [
                Token("text", text="全角１２３ 半角123\t項目\n『かぎかっこ』\n\n次の段落"),
            ]
            out = root / "out.pdf"
            pages = render_book(book, out, RenderOptions(include_cover=False))
            self.assertGreaterEqual(pages, 1)
            self.assertTrue(out.exists())
            self.assertGreater(out.stat().st_size, 1024)


if __name__ == "__main__":
    unittest.main()
