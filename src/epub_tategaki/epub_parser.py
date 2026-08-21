from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Iterable
import os
import re
import tempfile
import zipfile
import xml.etree.ElementTree as ET

from bs4 import BeautifulSoup, NavigableString, Tag
from PIL import Image


@dataclass
class Token:
    kind: str
    text: str = ""
    ruby: str = ""
    src: str = ""
    level: int = 0


@dataclass
class EpubBook:
    source: Path
    workdir: Path
    title: str = ""
    author: str = ""
    language: str = "ja"
    spine_files: list[Path] = field(default_factory=list)
    cover_image: Path | None = None
    tokens: list[Token] = field(default_factory=list)


class EpubError(RuntimeError):
    pass


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find_text(root: ET.Element, name: str) -> str:
    for el in root.iter():
        if _local(el.tag) == name and el.text:
            return el.text.strip()
    return ""


def _safe_extract(zf: zipfile.ZipFile, dest: Path) -> None:
    root = dest.resolve()
    for member in zf.infolist():
        target = (dest / member.filename).resolve()
        if not str(target).startswith(str(root) + os.sep) and target != root:
            raise EpubError("EPUB内に不正なパスが含まれています。")
    zf.extractall(dest)


def open_epub(path: str | Path) -> EpubBook:
    path = Path(path)
    if path.suffix.lower() != ".epub":
        raise EpubError("EPUBファイルを選択してください。")
    if not zipfile.is_zipfile(path):
        raise EpubError("EPUBとして読み込めないファイルです。")

    workdir = Path(tempfile.mkdtemp(prefix="epub_tategaki_"))
    with zipfile.ZipFile(path) as zf:
        if "META-INF/encryption.xml" in zf.namelist():
            enc = zf.read("META-INF/encryption.xml")
            # Font obfuscation is common and does not necessarily protect text, but
            # this MVP avoids any encrypted/obfuscated resources rather than bypassing protection.
            if b"EncryptedData" in enc:
                raise EpubError("暗号化されたリソースを含むEPUBには対応していません。DRMのないEPUBを使用してください。")
        _safe_extract(zf, workdir)

    container = workdir / "META-INF" / "container.xml"
    if not container.exists():
        raise EpubError("EPUBのcontainer.xmlが見つかりません。")
    croot = ET.parse(container).getroot()
    opf_rel = None
    for el in croot.iter():
        if _local(el.tag) == "rootfile":
            opf_rel = el.attrib.get("full-path")
            if opf_rel:
                break
    if not opf_rel:
        raise EpubError("EPUBのパッケージ情報を特定できません。")

    opf = workdir / PurePosixPath(opf_rel)
    oroot = ET.parse(opf).getroot()
    base = opf.parent

    book = EpubBook(source=path, workdir=workdir)
    book.title = _find_text(oroot, "title") or path.stem
    book.author = _find_text(oroot, "creator")
    book.language = _find_text(oroot, "language") or "ja"

    manifest: dict[str, dict] = {}
    cover_id = None
    for el in oroot.iter():
        ln = _local(el.tag)
        if ln == "item":
            item_id = el.attrib.get("id", "")
            manifest[item_id] = {
                "href": el.attrib.get("href", ""),
                "media": el.attrib.get("media-type", ""),
                "properties": el.attrib.get("properties", ""),
            }
            if "cover-image" in el.attrib.get("properties", "").split():
                cover_id = item_id
        elif ln == "meta" and el.attrib.get("name") == "cover":
            cover_id = el.attrib.get("content")

    spine_ids = []
    for el in oroot.iter():
        if _local(el.tag) == "itemref":
            iid = el.attrib.get("idref")
            if iid:
                spine_ids.append(iid)

    for iid in spine_ids:
        info = manifest.get(iid)
        if not info:
            continue
        if "html" in info["media"] or "xhtml" in info["media"]:
            p = base / PurePosixPath(info["href"])
            if p.exists():
                book.spine_files.append(p)

    if cover_id and cover_id in manifest:
        p = base / PurePosixPath(manifest[cover_id]["href"])
        if p.exists() and _is_booklike_cover(p):
            book.cover_image = p

    book.tokens = list(_tokens_from_spine(book.spine_files))
    return book


def _is_booklike_cover(path: Path) -> bool:
    try:
        with Image.open(path) as im:
            w, h = im.size
        if min(w, h) < 300:
            return False
        ratio = w / h if h else 99
        return 0.45 <= ratio <= 0.9
    except Exception:
        return False


def _tokens_from_spine(files: Iterable[Path]) -> Iterable[Token]:
    for idx, path in enumerate(files):
        raw = path.read_bytes()
        # BeautifulSoup handles encoding declarations in XHTML better than manual decoding.
        soup = BeautifulSoup(raw, "lxml")
        body = soup.body or soup
        if idx:
            yield Token("chapter_break")
        yield from _walk(body, path.parent)


def _walk(node, base: Path) -> Iterable[Token]:
    if isinstance(node, NavigableString):
        text = str(node)
        text = re.sub(r"[\t\r\n]+", "", text)
        if text:
            yield Token("text", text=text)
        return
    if not isinstance(node, Tag):
        return

    name = node.name.lower()
    if name in {"script", "style", "head", "rt", "rp"}:
        return
    if name == "br":
        yield Token("line_break")
        return
    if name == "img":
        src = node.get("src", "")
        if src:
            p = (base / PurePosixPath(src)).resolve()
            if p.exists():
                yield Token("image", src=str(p))
        return
    if name == "ruby":
        base_parts = []
        ruby_parts = []
        for child in node.children:
            if isinstance(child, Tag) and child.name and child.name.lower() == "rt":
                ruby_parts.append(child.get_text("", strip=False))
            elif isinstance(child, Tag) and child.name and child.name.lower() == "rp":
                continue
            else:
                base_parts.append(child.get_text("", strip=False) if isinstance(child, Tag) else str(child))
        b = re.sub(r"\s+", "", "".join(base_parts))
        r = re.sub(r"\s+", "", "".join(ruby_parts))
        if b:
            yield Token("ruby", text=b, ruby=r)
        return

    block = name in {"p", "div", "li", "blockquote", "section", "article"}
    heading = name in {"h1", "h2", "h3", "h4", "h5", "h6"}
    if heading:
        level = int(name[1])
        text = node.get_text("", strip=True)
        if text:
            yield Token("heading", text=text, level=level)
        yield Token("paragraph_break")
        return

    for child in node.children:
        yield from _walk(child, base)
    if block:
        yield Token("paragraph_break")
