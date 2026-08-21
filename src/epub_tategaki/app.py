from __future__ import annotations
import os, queue, subprocess, sys, threading, shutil
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from .epub_parser import open_epub, EpubError
from .renderer import RenderOptions, render_book
APP_NAME="EPUB 縦書き PDF Maker"
class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title(APP_NAME); self.geometry("760x610"); self.minsize(680,560); self.files=[]; self.q=queue.Queue(); self.running=False
        self.output_dir=Path.home()/"Documents"/"EPUB縦書きPDF"; self.output_dir.mkdir(parents=True,exist_ok=True); self._build_ui(); self.after(100,self._poll)
    def _build_ui(self):
        root=ttk.Frame(self,padding=20); root.pack(fill="both",expand=True)
        ttk.Label(root,text=APP_NAME,font=("Yu Gothic UI",20,"bold")).pack(anchor="w")
        ttk.Label(root,text="EPUBを日本語書籍らしい右開き・縦書きPDFに変換します。処理はPC内だけで完結します。",wraplength=700).pack(anchor="w",pady=(4,16))
        box=ttk.LabelFrame(root,text="1. EPUBを選ぶ",padding=14); box.pack(fill="x")
        ttk.Button(box,text="EPUBファイルを選択",command=self.choose_files).pack(side="left"); ttk.Button(box,text="一覧をクリア",command=self.clear_files).pack(side="left",padx=8)
        self.file_label=ttk.Label(box,text="まだ選択されていません"); self.file_label.pack(side="left",padx=10)
        opts=ttk.LabelFrame(root,text="2. 組版設定（通常はこのままでOK）",padding=14); opts.pack(fill="x",pady=14)
        r=ttk.Frame(opts); r.pack(fill="x",pady=4); ttk.Label(r,text="用紙").pack(side="left"); self.size_var=tk.StringVar(value="B6"); ttk.Combobox(r,textvariable=self.size_var,values=["B6","A5","A4"],width=7,state="readonly").pack(side="left",padx=(8,20))
        ttk.Label(r,text="本文サイズ").pack(side="left"); self.font_var=tk.DoubleVar(value=10.0); ttk.Spinbox(r,from_=8.0,to=15.0,increment=.5,textvariable=self.font_var,width=6).pack(side="left",padx=(8,20))
        self.cover_var=tk.BooleanVar(value=True); ttk.Checkbutton(r,text="表紙を入れる",variable=self.cover_var).pack(side="left"); self.page_var=tk.BooleanVar(value=True); ttk.Checkbutton(r,text="ページ番号",variable=self.page_var).pack(side="left",padx=14)
        r2=ttk.Frame(opts); r2.pack(fill="x",pady=(8,2)); ttk.Button(r2,text="保存先を変更",command=self.choose_output).pack(side="left"); self.out_label=ttk.Label(r2,text=str(self.output_dir),wraplength=560); self.out_label.pack(side="left",padx=10)
        action=ttk.LabelFrame(root,text="3. PDFを作成",padding=14); action.pack(fill="x"); self.start_btn=ttk.Button(action,text="きれいな縦書きPDFを作成",command=self.start); self.start_btn.pack(fill="x",ipady=8)
        self.progress=ttk.Progressbar(action,maximum=100); self.progress.pack(fill="x",pady=(12,4)); self.status=ttk.Label(action,text="準備完了"); self.status.pack(anchor="w")
        logbox=ttk.LabelFrame(root,text="処理ログ",padding=8); logbox.pack(fill="both",expand=True,pady=(14,0)); self.log=tk.Text(logbox,height=9,state="disabled",wrap="word"); self.log.pack(fill="both",expand=True)
        bottom=ttk.Frame(root); bottom.pack(fill="x",pady=(10,0)); ttk.Button(bottom,text="保存先を開く",command=self.open_output).pack(side="right"); ttk.Label(bottom,text="※ DRM・暗号化されたEPUBの解除には対応しません。",foreground="#666").pack(side="left")
    def choose_files(self):
        paths=filedialog.askopenfilenames(title="EPUBを選択",filetypes=[("EPUB files","*.epub")])
        if paths:
            self.files=[Path(p) for p in paths]; self.file_label.config(text=f"{len(self.files)}冊を選択")
            for p in self.files:self._log(f"選択: {p.name}")
    def clear_files(self): self.files=[]; self.file_label.config(text="まだ選択されていません")
    def choose_output(self):
        d=filedialog.askdirectory(initialdir=self.output_dir)
        if d:self.output_dir=Path(d); self.out_label.config(text=str(self.output_dir))
    def start(self):
        if self.running:return
        if not self.files:messagebox.showinfo(APP_NAME,"EPUBファイルを選択してください。"); return
        self.output_dir.mkdir(parents=True,exist_ok=True); self.running=True; self.start_btn.config(state="disabled"); self.progress["value"]=0
        self.run_options={"page_size":self.size_var.get(),"font_size":float(self.font_var.get()),"include_cover":bool(self.cover_var.get()),"page_numbers":bool(self.page_var.get())}; threading.Thread(target=self._worker,daemon=True).start()
    def _worker(self):
        try:
            total=len(self.files)
            for bi,path in enumerate(self.files,start=1):
                self.q.put(("log",f"\n[{bi}/{total}] {path.name}")); self.q.put(("status",f"EPUBを解析しています：{path.name}")); book=open_epub(path); self.q.put(("log",f"書名: {book.title}"))
                if book.author:self.q.put(("log",f"著者: {book.author}"))
                self.q.put(("log",f"本文ファイル: {len(book.spine_files)} / 組版要素: {len(book.tokens):,}")); out=self.output_dir/f"{path.stem}_縦書き.pdf"; options=RenderOptions(**self.run_options)
                def progress(pct,msg): self.q.put(("progress",((bi-1)+pct/100)/total*100)); self.q.put(("status",msg))
                try: pages=render_book(book,out,options,progress=progress); self.q.put(("log",f"完成: {out.name}（{pages}ページ）"))
                finally: shutil.rmtree(book.workdir,ignore_errors=True)
            self.q.put(("done","すべてのPDFが完成しました。"))
        except Exception as e:self.q.put(("error",str(e)))
    def _poll(self):
        try:
            while True:
                kind,value=self.q.get_nowait()
                if kind=="log":self._log(value)
                elif kind=="status":self.status.config(text=value)
                elif kind=="progress":self.progress["value"]=value
                elif kind=="done":self.running=False; self.start_btn.config(state="normal"); self.progress["value"]=100; self.status.config(text=value); messagebox.showinfo(APP_NAME,value)
                elif kind=="error":self.running=False; self.start_btn.config(state="normal"); self.status.config(text="エラー"); self._log("エラー: "+value); messagebox.showerror(APP_NAME,value)
        except queue.Empty:pass
        self.after(100,self._poll)
    def _log(self,text): self.log.config(state="normal"); self.log.insert("end",text+"\n"); self.log.see("end"); self.log.config(state="disabled")
    def open_output(self):
        self.output_dir.mkdir(parents=True,exist_ok=True)
        if sys.platform.startswith("win"):os.startfile(self.output_dir)
        elif sys.platform=="darwin":subprocess.Popen(["open",str(self.output_dir)])
        else:subprocess.Popen(["xdg-open",str(self.output_dir)])
def main():App().mainloop()
if __name__=="__main__":main()
