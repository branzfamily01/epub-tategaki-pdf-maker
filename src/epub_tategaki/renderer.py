from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import math
import os
import re

from PIL import Image
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.pagesizes import B6, A5, A4
from reportlab.lib.utils import ImageReader
from pypdf import PdfReader

from .epub_parser import EpubBook

ROTATE_VERTICAL = set("（）［］【】「」『』〈〉《》ー―〜…‥—–-=<>[]{}()")
ROTATE_SWAP = {
    "（": "）", "）": "（", "［": "］", "］": "［", "【": "】", "】": "【",
    "「": "」", "」": "「", "『": "』", "』": "『", "〈": "〉", "〉": "〈",
    "《": "》", "》": "《", "(": ")", ")": "(", "[": "]", "]": "[",
    "{": "}", "}": "{", "<": ">", ">": "<",
}
SMALL_PUNCT = set("、。，．")
FULLWIDTH_DIGITS = set("０１２３４５６７８９")
HALFWIDTH_DIGIT_RE = re.compile(r"[0-9]+")
PAGE_SIZES = {"B6": B6, "A5": A5, "A4": A4}


@dataclass
class RenderOptions:
    page_size: str = "B6"
    font_size: float = 10.0
    line_gap: float = 6.2
    margin_top_mm: float = 14.0
    margin_bottom_mm: float = 14.0
    margin_inside_mm: float = 18.0
    margin_outside_mm: float = 14.0
    ruby_scale: float = 0.46
    page_numbers: bool = True
    include_cover: bool = True
    chapter_new_page: bool = True


def mm(v):
    return v * 72.0 / 25.4


def find_japanese_font() -> Path:
    candidates = [
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "YuMincho.ttc",
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "YuMincho.ttf",
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "msmincho.ttc",
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "msgothic.ttc",
        Path("/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for p in candidates:
        if p.exists():
            return p
    raise RuntimeError("日本語フォントが見つかりません。Windows標準の游明朝/ＭＳ明朝が必要です。")


def _register_font():
    name = "EpubTategakiJP"
    if name in pdfmetrics.getRegisteredFontNames():
        return name
    path = find_japanese_font()
    try:
        try:
            pdfmetrics.registerFont(TTFont(name, str(path), subfontIndex=0))
        except TypeError:
            pdfmetrics.registerFont(TTFont(name, str(path)))
        return name
    except Exception:
        cid = "HeiseiMin-W3"
        if cid not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(UnicodeCIDFont(cid))
        return cid


class VerticalRenderer:
    def __init__(self, book: EpubBook, out_path: Path, options: RenderOptions, progress=None):
        self.book = book
        self.out_path = Path(out_path)
        self.opt = options
        self.progress = progress or (lambda pct, msg: None)
        self.font = _register_font()
        self.page_w, self.page_h = PAGE_SIZES.get(options.page_size, B6)
        self.canvas = Canvas(str(self.out_path), pagesize=(self.page_w, self.page_h), pageCompression=1)
        self.page_no = 0
        self.usable_top = self.page_h - mm(options.margin_top_mm)
        self.usable_bottom = mm(options.margin_bottom_mm)
        self.cell = options.font_size * 1.22
        self.col_pitch = options.font_size + options.line_gap
        self.columns_per_page = max(5, int((self.page_w - mm(options.margin_inside_mm + options.margin_outside_mm)) / self.col_pitch))
        self._new_page(start=True)

    def _margins(self):
        odd = self.page_no % 2 == 1
        return ((mm(self.opt.margin_inside_mm), mm(self.opt.margin_outside_mm)) if odd else (mm(self.opt.margin_outside_mm), mm(self.opt.margin_inside_mm)))

    def _new_page(self, start=False):
        if not start:
            self._draw_page_number()
            self.canvas.showPage()
        self.page_no += 1
        _left, right = self._margins()
        self.col_idx = 0
        self.col_x = self.page_w - right - self.opt.font_size
        self.y = self.usable_top
        self.canvas.setFont(self.font, self.opt.font_size)

    def _draw_page_number(self):
        if not self.opt.page_numbers or self.page_no <= 1:
            return
        self.canvas.saveState()
        self.canvas.setFont(self.font, max(7, self.opt.font_size * .72))
        self.canvas.drawCentredString(self.page_w / 2, mm(6), str(self.page_no))
        self.canvas.restoreState()

    def _advance_cell(self, n=1):
        self.y -= self.cell * n
        if self.y < self.usable_bottom + self.cell * .2:
            self._next_column()

    def _next_column(self):
        self.col_idx += 1
        if self.col_idx >= self.columns_per_page:
            self._new_page()
            return
        self.col_x -= self.col_pitch
        self.y = self.usable_top

    def _paragraph_break(self):
        if self.y < self.usable_top - self.cell * .5:
            self._advance_cell(1)
        else:
            self._next_column()

    def _line_break(self):
        self._next_column()

    def _draw_char(self, ch, size=None):
        size = size or self.opt.font_size
        if ch in {"　", " "}:
            self._advance_cell()
            return
        self.canvas.setFont(self.font, size)
        cx = self.col_x + size * .5
        cy = self.y - self.cell * .5
        if ch in SMALL_PUNCT:
            self.canvas.drawString(self.col_x + size * .52, self.y - size * .58, ch)
        elif ch in FULLWIDTH_DIGITS:
            # Full-width numerals stay upright and stack vertically, one per cell.
            self.canvas.drawCentredString(cx, self.y - size, ch)
        elif ch in ROTATE_VERTICAL:
            # Horizontal bracket glyphs need open/close substitution before rotation.
            draw_ch = ROTATE_SWAP.get(ch, ch)
            self.canvas.saveState()
            self.canvas.translate(cx, cy)
            self.canvas.rotate(90)
            self.canvas.drawCentredString(0, -size * .34, draw_ch)
            self.canvas.restoreState()
        elif ord(ch) < 128 and ch.isprintable() and not ch.isspace():
            self.canvas.saveState()
            self.canvas.translate(cx, cy)
            self.canvas.rotate(90)
            self.canvas.drawCentredString(0, -size * .34, ch)
            self.canvas.restoreState()
        else:
            self.canvas.drawCentredString(cx, self.y - size, ch)
        self._advance_cell()

    def _draw_halfwidth_run(self, run: str, size=None):
        """Draw half-width digits horizontally with the logical head on the right.

        The first digit is placed at the right edge and later digits extend left.
        This matches the requested Japanese vertical-table convention and keeps
        full-width digits distinct from half-width numeric runs.
        """
        size = size or self.opt.font_size
        self.canvas.setFont(self.font, size)
        step = size * .62
        max_width = max(self.col_pitch * 2.4, size * 1.2)
        draw_size = size
        if len(run) * step > max_width:
            draw_size = max(size * .62, size * max_width / (len(run) * step))
            step = draw_size * .62
            self.canvas.setFont(self.font, draw_size)
        right_x = self.col_x + size * .72
        baseline_y = self.y - self.cell * .78
        for i, ch in enumerate(run):
            x = right_x - i * step
            self.canvas.drawCentredString(x, baseline_y, ch)
        self._advance_cell(1)

    def _draw_text(self, text, size=None):
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        i = 0
        while i < len(text):
            ch = text[i]
            if ch == "\t":
                # One EPUB tab is treated as a two-character vertical indent.
                self._advance_cell(2)
                i += 1
                continue
            if ch == "\n":
                j = i
                while j < len(text) and text[j] == "\n":
                    j += 1
                if j - i >= 2:
                    self._paragraph_break()
                else:
                    self._line_break()
                i = j
                continue
            m = HALFWIDTH_DIGIT_RE.match(text, i)
            if m:
                self._draw_halfwidth_run(m.group(0), size=size)
                i = m.end()
                continue
            self._draw_char(ch, size)
            i += 1

    def _draw_ruby(self, base, ruby):
        sx, sy = self.col_x, self.y
        for ch in base:
            self._draw_char(ch)
        if ruby:
            rs = max(4.2, self.opt.font_size * self.opt.ruby_scale)
            self.canvas.saveState()
            self.canvas.setFont(self.font, rs)
            rc = rs * 1.05
            total = len(ruby) * rc
            bt = max(self.cell, len(base) * self.cell)
            ry = sy - (bt - total) / 2
            rx = sx + self.opt.font_size * 1.12
            for ch in ruby:
                self.canvas.drawCentredString(rx, ry - rs, ch)
                ry -= rc
            self.canvas.restoreState()

    def _draw_heading(self, text, level):
        if self.y < self.usable_top - self.cell * 3:
            self._next_column()
        self._draw_text(text, self.opt.font_size * (1.5 if level <= 2 else 1.22))
        self._paragraph_break()

    def _draw_image(self, src):
        try:
            with Image.open(src) as im:
                iw, ih = im.size
            if self.y < self.usable_top - self.cell:
                self._new_page()
            maxw = self.page_w - mm(self.opt.margin_inside_mm + self.opt.margin_outside_mm)
            maxh = self.page_h - mm(self.opt.margin_top_mm + self.opt.margin_bottom_mm)
            scale = min(maxw / iw, maxh / ih)
            w, h = iw * scale, ih * scale
            self.canvas.drawImage(ImageReader(src), (self.page_w - w) / 2, (self.page_h - h) / 2, width=w, height=h, preserveAspectRatio=True, mask='auto')
            self._new_page()
        except Exception:
            pass

    def draw_cover(self):
        if self.opt.include_cover and self.book.cover_image:
            try:
                with Image.open(self.book.cover_image) as im:
                    iw, ih = im.size
                scale = min(self.page_w / iw, self.page_h / ih)
                w, h = iw * scale, ih * scale
                self.canvas.drawImage(ImageReader(str(self.book.cover_image)), (self.page_w - w) / 2, (self.page_h - h) / 2, width=w, height=h, preserveAspectRatio=True, mask='auto')
                self._new_page()
                return
            except Exception:
                pass
        self.canvas.saveState()
        ts = min(18, self.opt.font_size * 1.8)
        x = self.page_w * .66
        y = self.page_h * .78
        self.canvas.setFont(self.font, ts)
        for ch in self.book.title:
            self.canvas.drawCentredString(x, y - ts, ch)
            y -= ts * 1.35
            if y < self.page_h * .22:
                x -= ts * 1.6
                y = self.page_h * .78
        if self.book.author:
            s = self.opt.font_size
            x2, y2 = self.page_w * .34, self.page_h * .68
            self.canvas.setFont(self.font, s)
            for ch in self.book.author:
                self.canvas.drawCentredString(x2, y2 - s, ch)
                y2 -= s * 1.35
        self.canvas.restoreState()
        self._new_page()

    def render(self):
        self.progress(1, "表紙を準備しています")
        self.draw_cover()
        total = max(1, len(self.book.tokens))
        for i, tok in enumerate(self.book.tokens):
            if i % 80 == 0:
                self.progress(5 + int(i / total * 88), f"本文を組版しています {i:,}/{total:,}")
            if tok.kind == "text":
                self._draw_text(tok.text)
            elif tok.kind == "ruby":
                self._draw_ruby(tok.text, tok.ruby)
            elif tok.kind == "paragraph_break":
                self._paragraph_break()
            elif tok.kind == "line_break":
                self._line_break()
            elif tok.kind == "heading":
                self._draw_heading(tok.text, tok.level)
            elif tok.kind == "image":
                self._draw_image(tok.src)
            elif tok.kind == "chapter_break" and self.opt.chapter_new_page and self.y < self.usable_top - self.cell * .5:
                self._new_page()
        self._draw_page_number()
        self.canvas.save()
        self.progress(95, "PDFを検査しています")
        pages = validate_pdf(self.out_path)
        self.progress(100, f"完了：{pages}ページ")
        return pages


def validate_pdf(path):
    path = Path(path)
    if not path.exists() or path.stat().st_size < 1024:
        raise RuntimeError("PDFの生成に失敗しました。")
    pages = len(PdfReader(str(path)).pages)
    if pages < 1:
        raise RuntimeError("PDFにページがありません。")
    return pages


def render_book(book, out_path, options=None, progress=None):
    return VerticalRenderer(book, Path(out_path), options or RenderOptions(), progress).render()
