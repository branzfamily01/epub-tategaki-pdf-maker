import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from epub_tategaki import app as app_module
from epub_tategaki.pdf_identity import stamp_cached_identity
from epub_tategaki.renderer import validate_pdf


_original_render_book = app_module.render_book


def _licensed_render_book(book, out_path, options=None, progress=None):
    pages = _original_render_book(book, out_path, options, progress)
    stamp_cached_identity(out_path)
    # Re-open after metadata stamping so a failed rewrite is never reported as success.
    return validate_pdf(out_path)


app_module.render_book = _licensed_render_book


if __name__ == "__main__":
    app_module.main()
