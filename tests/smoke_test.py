from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from epub_tategaki.epub_parser import open_epub
from epub_tategaki.renderer import RenderOptions, render_book


def convert(epub, out):
    book = open_epub(epub)
    return render_book(book, out, RenderOptions(page_size="B6", font_size=10.0))

if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python tests/smoke_test.py input.epub output.pdf")
    pages = convert(sys.argv[1], sys.argv[2])
    print("OK", pages, "pages")
