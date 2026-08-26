from __future__ import annotations

import csv
import os
import queue
import shutil
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

from .epub_parser import open_epub
from .renderer import RenderOptions, render_book
from .presets import PRESETS, DEFAULT_PRESET
from .quality_check import inspect_pdf, create_sample_pdf, write_quality_report

APP_NAME = "EPUB 縦書き PDF Maker v2.1"
SUPPORTED = {".epub"}


def resource_path(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    candidate = base / name
    if candidate.exists():
        return candidate
    return Path(__file__).resolve().parents[2] / name


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("980x760")
        self.minsize(840, 660)
        self.items = []
        self.q = queue.Queue()
        self.running = False
        self.output_dir = Path.home() / "Documents" / "EPUB縦書きPDF"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._build_ui()
        self.after(100, self._poll)

    def _build_ui(self):
        root = ttk.Frame(self, padding=18)
        root.pack(fill="both", expand=True)
        header = ttk.Frame(root)
        header.pack(fill="x")
        ttk.Label(header, text=APP_NAME, font=("Yu Gothic UI", 20, "bold")).pack(side="left")
        ttk.Button(header, text="？ 使い方", command=self.open_manual).pack(side="right")
        ttk.Label(root, text="EPUBを追加すると、日本語書籍らしい縦書きPDFへ一括変換し、完成後に品質チェックまで行います。").pack(anchor="w", pady=(3, 12))

        toolbar = ttk.Frame(root)
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="EPUBを追加", command=self.choose_files).pack(side="left")
        ttk.Button(toolbar, text="フォルダーから一括追加", command=self.choose_folder).pack(side="left", padx=6)
        ttk.Button(toolbar, text="選択を削除", command=self.remove_selected).pack(side="left")
        ttk.Button(toolbar, text="一覧をクリア", command=self.clear_files).pack(side="left", padx=6)
        ttk.Button(toolbar, text="メタデータ編集", command=self.edit_metadata).pack(side="right")

        cols = ("title", "author", "file", "status")
        self.tree = ttk.Treeview(root, columns=cols, show="headings", height=11, selectmode="extended")
        for key, label in [("title", "書名"), ("author", "著者"), ("file", "ファイル"), ("status", "状態")]:
            self.tree.heading(key, text=label)
        self.tree.column("title", width=230)
        self.tree.column("author", width=150)
        self.tree.column("file", width=330)
        self.tree.column("status", width=150)
        self.tree.pack(fill="both", expand=True, pady=(10, 12))

        opts = ttk.LabelFrame(root, text="変換設定（通常はこのままでOK）", padding=12)
        opts.pack(fill="x")
        row1 = ttk.Frame(opts)
        row1.pack(fill="x")
        ttk.Label(row1, text="プリセット").pack(side="left")
        self.preset_var = tk.StringVar(value=DEFAULT_PRESET)
        preset = ttk.Combobox(row1, textvariable=self.preset_var, values=list(PRESETS), state="readonly", width=20)
        preset.pack(side="left", padx=(8, 16))
        preset.bind("<<ComboboxSelected>>", self.apply_preset)
        ttk.Label(row1, text="用紙").pack(side="left")
        self.size_var = tk.StringVar(value="B6")
        ttk.Combobox(row1, textvariable=self.size_var, values=["B6", "A5", "A4"], width=7, state="readonly").pack(side="left", padx=(8, 16))
        ttk.Label(row1, text="本文サイズ").pack(side="left")
        self.font_var = tk.DoubleVar(value=10.0)
        ttk.Spinbox(row1, from_=8.0, to=16.0, increment=.5, textvariable=self.font_var, width=6).pack(side="left", padx=(8, 16))
        self.cover_var = tk.BooleanVar(value=True)
        self.page_var = tk.BooleanVar(value=True)
        self.quality_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(row1, text="表紙", variable=self.cover_var).pack(side="left")
        ttk.Checkbutton(row1, text="ページ番号", variable=self.page_var).pack(side="left", padx=10)
        ttk.Checkbutton(row1, text="品質チェック", variable=self.quality_var).pack(side="left")

        row2 = ttk.Frame(opts)
        row2.pack(fill="x", pady=(10, 0))
        ttk.Label(row2, text="出力名").pack(side="left")
        self.name_var = tk.StringVar(value="{title}_縦書き.pdf")
        ttk.Entry(row2, textvariable=self.name_var, width=34).pack(side="left", padx=(8, 12))
        ttk.Button(row2, text="保存先を変更", command=self.choose_output).pack(side="left")
        self.out_label = ttk.Label(row2, text=str(self.output_dir), wraplength=430)
        self.out_label.pack(side="left", padx=10)

        action = ttk.LabelFrame(root, text="変換", padding=12)
        action.pack(fill="x", pady=(12, 0))
        self.start_btn = ttk.Button(action, text="キューをまとめて縦書きPDF化", command=self.start)
        self.start_btn.pack(fill="x", ipady=7)
        self.progress = ttk.Progressbar(action, maximum=100)
        self.progress.pack(fill="x", pady=(10, 4))
        self.status = ttk.Label(action, text="準備完了")
        self.status.pack(anchor="w")

        ttk.Label(root, text="品質チェックではPDFの破損・ページ数・異常な空ページを確認し、代表6ページの確認用PDFも自動生成します。", foreground="#555").pack(anchor="w", pady=(8, 0))
        bottom = ttk.Frame(root)
        bottom.pack(fill="x", pady=(10, 0))
        ttk.Button(bottom, text="保存先を開く", command=self.open_output).pack(side="right")
        ttk.Label(bottom, text="DRM・暗号化解除は行いません。書籍データはPC内だけで処理します。", foreground="#666").pack(side="left")

    def apply_preset(self, *_):
        p = PRESETS[self.preset_var.get()]
        self.size_var.set(p["page_size"])
        self.font_var.set(p["font_size"])

    def choose_files(self):
        paths = filedialog.askopenfilenames(title="EPUBを選択", filetypes=[("EPUB files", "*.epub")])
        self._add_paths([Path(p) for p in paths])

    def choose_folder(self):
        d = filedialog.askdirectory(title="EPUBを含むフォルダーを選択")
        if not d:
            return
        self._add_paths(sorted(p for p in Path(d).rglob("*") if p.suffix.lower() in SUPPORTED))

    def _add_paths(self, paths):
        existing = {x["path"].resolve() for x in self.items}
        for path in paths:
            if path.resolve() in existing:
                continue
            meta = {"path": path, "title": path.stem, "author": "", "status": "待機"}
            try:
                book = open_epub(path)
                meta["title"] = book.title or path.stem
                meta["author"] = book.author or ""
                shutil.rmtree(book.workdir, ignore_errors=True)
            except Exception as e:
                meta["status"] = "要確認"
                meta["error"] = str(e)
            self.items.append(meta)
            existing.add(path.resolve())
        self._refresh_tree()

    def _refresh_tree(self):
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        for i, item in enumerate(self.items):
            self.tree.insert("", "end", iid=str(i), values=(item["title"], item["author"], item["path"].name, item["status"]))

    def remove_selected(self):
        for i in sorted((int(x) for x in self.tree.selection()), reverse=True):
            if 0 <= i < len(self.items):
                self.items.pop(i)
        self._refresh_tree()

    def clear_files(self):
        if not self.running:
            self.items.clear()
            self._refresh_tree()

    def edit_metadata(self):
        sel = self.tree.selection()
        if len(sel) != 1:
            messagebox.showinfo(APP_NAME, "1冊だけ選択してからメタデータ編集を押してください。")
            return
        item = self.items[int(sel[0])]
        title = simpledialog.askstring("書名", "PDFに使う書名", initialvalue=item["title"], parent=self)
        if title is None:
            return
        author = simpledialog.askstring("著者", "PDFに使う著者名", initialvalue=item["author"], parent=self)
        if author is None:
            return
        item["title"] = title.strip() or item["path"].stem
        item["author"] = author.strip()
        self._refresh_tree()

    def choose_output(self):
        d = filedialog.askdirectory(initialdir=self.output_dir)
        if d:
            self.output_dir = Path(d)
            self.out_label.config(text=str(self.output_dir))

    def _safe_name(self, text):
        for c in '<>:"/\\|?*':
            text = text.replace(c, "_")
        return text.strip().rstrip(".") or "book"

    def start(self):
        if self.running:
            return
        if not self.items:
            messagebox.showinfo(APP_NAME, "EPUBを追加してください。")
            return
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.running = True
        self.start_btn.config(state="disabled")
        self.progress["value"] = 0
        self.run_options = {"page_size": self.size_var.get(), "font_size": float(self.font_var.get()), "include_cover": bool(self.cover_var.get()), "page_numbers": bool(self.page_var.get())}
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        report = []
        try:
            total = len(self.items)
            for bi, item in enumerate(self.items, start=1):
                path = item["path"]
                self.q.put(("item", (bi - 1, "変換中")))
                self.q.put(("status", f"解析中 {bi}/{total}: {path.name}"))
                book = open_epub(path)
                book.title = item["title"]
                book.author = item["author"]
                template = self.name_var.get() or "{title}_縦書き.pdf"
                filename = template.replace("{title}", self._safe_name(book.title)).replace("{author}", self._safe_name(book.author))
                if not filename.lower().endswith(".pdf"):
                    filename += ".pdf"
                out = self.output_dir / filename
                options = RenderOptions(**self.run_options)

                def progress(pct, msg):
                    self.q.put(("progress", ((bi - 1) + pct / 100) / total * 100))
                    self.q.put(("status", f"{bi}/{total} {msg}"))

                try:
                    pages = render_book(book, out, options, progress=progress)
                    quality_status = "未実施"
                    quality_json = ""
                    preview_pdf = ""
                    if self.quality_var.get():
                        self.q.put(("status", f"{bi}/{total} 品質チェック中: {out.name}"))
                        qr = inspect_pdf(out)
                        quality_status = qr.status
                        qdir = self.output_dir / "quality"
                        qdir.mkdir(parents=True, exist_ok=True)
                        quality_json_path = qdir / f"{out.stem}_quality.json"
                        preview_path = qdir / f"{out.stem}_sample-pages.pdf"
                        write_quality_report(qr, quality_json_path)
                        create_sample_pdf(out, preview_path, qr.sampled_pages)
                        quality_json = quality_json_path.name
                        preview_pdf = preview_path.name
                        state = f"完成 {pages}p / " + ("品質OK" if qr.status == "OK" else "要確認" if qr.status == "CHECK" else "品質エラー")
                    else:
                        state = f"完成 {pages}p"
                    self.q.put(("item", (bi - 1, state)))
                    report.append([path.name, book.title, book.author, out.name, pages, "OK", quality_status, quality_json, preview_pdf, ""])
                except Exception as e:
                    self.q.put(("item", (bi - 1, "エラー")))
                    report.append([path.name, book.title, book.author, "", 0, "ERROR", "ERROR", "", "", str(e)])
                finally:
                    shutil.rmtree(book.workdir, ignore_errors=True)

            report_path = self.output_dir / "conversion-report.csv"
            with report_path.open("w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(["source", "title", "author", "output", "pages", "status", "quality", "quality_report", "sample_pdf", "message"])
                w.writerows(report)
            self.q.put(("done", f"変換と品質チェックが完了しました。レポート: {report_path.name}"))
        except Exception as e:
            self.q.put(("error", str(e)))

    def _poll(self):
        try:
            while True:
                kind, value = self.q.get_nowait()
                if kind == "status":
                    self.status.config(text=value)
                elif kind == "progress":
                    self.progress["value"] = value
                elif kind == "item":
                    idx, status = value
                    if 0 <= idx < len(self.items):
                        self.items[idx]["status"] = status
                        self._refresh_tree()
                elif kind == "done":
                    self.running = False
                    self.start_btn.config(state="normal")
                    self.progress["value"] = 100
                    self.status.config(text=value)
                    messagebox.showinfo(APP_NAME, value)
                elif kind == "error":
                    self.running = False
                    self.start_btn.config(state="normal")
                    self.status.config(text="エラー")
                    messagebox.showerror(APP_NAME, value)
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def open_output(self):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        if sys.platform.startswith("win"):
            os.startfile(self.output_dir)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(self.output_dir)])
        else:
            subprocess.Popen(["xdg-open", str(self.output_dir)])

    def open_manual(self):
        manual = resource_path("manual.html")
        if manual.exists():
            webbrowser.open(manual.resolve().as_uri())
        else:
            webbrowser.open("https://branzfamily01.github.io/epub-tategaki-pdf-maker/manual.html")


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
