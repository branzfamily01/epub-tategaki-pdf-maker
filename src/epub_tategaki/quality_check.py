from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
import json

from pypdf import PdfReader, PdfWriter


@dataclass
class QualityIssue:
    severity: str
    code: str
    message: str
    page: int | None = None


@dataclass
class QualityReport:
    pdf_path: Path
    page_count: int
    file_size: int
    status: str
    sampled_pages: list[int] = field(default_factory=list)
    issues: list[QualityIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == "OK"


def _sample_indices(page_count: int) -> list[int]:
    if page_count <= 0:
        return []
    raw = [0, 1, round((page_count - 1) * 0.25), round((page_count - 1) * 0.50),
           round((page_count - 1) * 0.75), page_count - 1]
    return sorted({max(0, min(page_count - 1, i)) for i in raw})


def inspect_pdf(pdf_path: str | Path, expected_min_pages: int = 1) -> QualityReport:
    path = Path(pdf_path)
    issues: list[QualityIssue] = []
    if not path.exists():
        return QualityReport(path, 0, 0, "ERROR", issues=[QualityIssue("error", "missing_file", "PDFファイルが見つかりません。")])

    file_size = path.stat().st_size
    if file_size < 2048:
        issues.append(QualityIssue("error", "too_small", "PDFファイルサイズが異常に小さいです。"))

    try:
        reader = PdfReader(str(path))
        page_count = len(reader.pages)
    except Exception as e:
        return QualityReport(path, 0, file_size, "ERROR", issues=[QualityIssue("error", "unreadable", f"PDFを開けません: {e}")])

    if page_count < expected_min_pages:
        issues.append(QualityIssue("error", "too_few_pages", f"ページ数が少なすぎます（{page_count}ページ）。"))

    samples = _sample_indices(page_count)
    blank_content_pages: list[int] = []
    for i, page in enumerate(reader.pages):
        try:
            box = page.mediabox
            if float(box.width) <= 0 or float(box.height) <= 0:
                issues.append(QualityIssue("error", "invalid_page_size", "ページサイズが不正です。", i + 1))
            contents = page.get_contents()
            if contents is None:
                blank_content_pages.append(i + 1)
            else:
                try:
                    data = contents.get_data()
                    if not data or len(data.strip()) < 8:
                        blank_content_pages.append(i + 1)
                except Exception:
                    pass
        except Exception as e:
            issues.append(QualityIssue("warning", "page_check_failed", f"ページ構造の確認に失敗しました: {e}", i + 1))

    if blank_content_pages:
        run: list[int] = []
        for p in blank_content_pages + [-999]:
            if not run or p == run[-1] + 1:
                run.append(p)
            else:
                if len(run) >= 3:
                    issues.append(QualityIssue("warning", "consecutive_blank_pages", f"内容がほぼ空のページが{len(run)}ページ連続しています（{run[0]}〜{run[-1]}ページ）。", run[0]))
                run = [p]

    textless_samples = 0
    for idx in samples:
        if idx == 0:
            continue
        try:
            text = reader.pages[idx].extract_text() or ""
            visible = "".join(text.split())
            if len(visible) < 5:
                textless_samples += 1
        except Exception:
            issues.append(QualityIssue("warning", "text_extract_failed", "代表ページの文字情報を確認できませんでした。", idx + 1))
    if len(samples) >= 4 and textless_samples >= max(2, len(samples) - 2):
        issues.append(QualityIssue("warning", "textless_samples", "代表ページの多くで文字情報を確認できません。画像化PDFまたは本文欠落の可能性があります。"))

    status = "ERROR" if any(i.severity == "error" for i in issues) else ("CHECK" if issues else "OK")
    return QualityReport(path, page_count, file_size, status, sampled_pages=[i + 1 for i in samples], issues=issues)


def create_sample_pdf(pdf_path: str | Path, output_path: str | Path, sampled_pages: Iterable[int] | None = None) -> Path:
    src = Path(pdf_path)
    out = Path(output_path)
    reader = PdfReader(str(src))
    pages = list(sampled_pages or [i + 1 for i in _sample_indices(len(reader.pages))])
    writer = PdfWriter()
    for page_no in pages:
        idx = page_no - 1
        if 0 <= idx < len(reader.pages):
            writer.add_page(reader.pages[idx])
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("wb") as f:
        writer.write(f)
    return out


def write_quality_report(report: QualityReport, output_path: str | Path) -> Path:
    out = Path(output_path)
    payload = {
        "status": report.status,
        "pdf": report.pdf_path.name,
        "pageCount": report.page_count,
        "fileSize": report.file_size,
        "sampledPages": report.sampled_pages,
        "issues": [{"severity": i.severity, "code": i.code, "message": i.message, "page": i.page} for i in report.issues],
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out
