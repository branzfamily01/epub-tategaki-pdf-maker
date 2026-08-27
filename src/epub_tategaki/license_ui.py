from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox

from .license_client import LicenseClient, LicenseError
from .license_config import OFFLINE_GRACE_DAYS


ERROR_MESSAGES = {
    "AUTH_REQUIRED": "ログインが必要です。",
    "INVALID_LICENSE": "ライセンスキーが正しくありません。",
    "LICENSE_OWNED_BY_OTHER_USER": "このライセンスは別のユーザーに登録されています。",
    "DEVICE_LIMIT_REACHED": "利用できる端末数の上限に達しています。",
    "DEVICE_REVOKED": "この端末のライセンスは解除されています。",
    "DEVICE_NOT_ACTIVE": "この端末はまだライセンス認証されていません。",
    "NO_LICENSE": "このアカウントには、このアプリのライセンスがありません。",
    "EXPIRED": "ライセンスの有効期限が切れています。",
    "LICENSE_DISABLED": "このライセンスは現在利用できません。",
    "NETWORK_ERROR": "インターネットに接続できません。",
}


def friendly_error(exc: Exception) -> str:
    code = str(exc)
    return ERROR_MESSAGES.get(code, code)


class LicenseDialog(tk.Toplevel):
    def __init__(self, parent, client: LicenseClient):
        super().__init__(parent)
        self.client = client
        self.result = False
        self.title("ライセンス管理")
        self.geometry("520x470")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._build()
        self._refresh_status()

    def _build(self):
        root = ttk.Frame(self, padding=18)
        root.pack(fill="both", expand=True)

        ttk.Label(root, text="EPUB 縦書き PDF Maker", font=("Yu Gothic UI", 16, "bold")).pack(anchor="w")
        ttk.Label(root, text="購入・試用ライセンスを、このアカウントと端末に登録します。", wraplength=470).pack(anchor="w", pady=(4, 12))

        account = ttk.LabelFrame(root, text="1. アカウント", padding=12)
        account.pack(fill="x")
        row = ttk.Frame(account); row.pack(fill="x", pady=4)
        ttk.Label(row, text="メール", width=10).pack(side="left")
        self.email_var = tk.StringVar(value=self.client.email)
        ttk.Entry(row, textvariable=self.email_var, width=38).pack(side="left", fill="x", expand=True)
        row2 = ttk.Frame(account); row2.pack(fill="x", pady=4)
        ttk.Label(row2, text="パスワード", width=10).pack(side="left")
        self.password_var = tk.StringVar()
        ttk.Entry(row2, textvariable=self.password_var, show="●", width=38).pack(side="left", fill="x", expand=True)
        buttons = ttk.Frame(account); buttons.pack(fill="x", pady=(6, 0))
        ttk.Button(buttons, text="アカウント作成", command=self._signup).pack(side="left")
        ttk.Button(buttons, text="ログイン", command=self._signin).pack(side="left", padx=8)
        ttk.Button(buttons, text="ログアウト", command=self._logout).pack(side="right")

        activation = ttk.LabelFrame(root, text="2. ライセンスキー", padding=12)
        activation.pack(fill="x", pady=12)
        self.key_var = tk.StringVar()
        ttk.Entry(activation, textvariable=self.key_var, width=48).pack(fill="x")
        ttk.Button(activation, text="この端末をライセンス認証", command=self._activate).pack(fill="x", pady=(8, 0), ipady=4)

        statusbox = ttk.LabelFrame(root, text="状態", padding=12)
        statusbox.pack(fill="both", expand=True)
        self.status_var = tk.StringVar(value="未確認")
        ttk.Label(statusbox, textvariable=self.status_var, wraplength=450, justify="left").pack(anchor="w")

        bottom = ttk.Frame(root); bottom.pack(fill="x", pady=(12, 0))
        ttk.Button(bottom, text="この端末の認証を解除", command=self._deactivate).pack(side="left")
        ttk.Button(bottom, text="閉じる", command=self._close).pack(side="right")

    def _signup(self):
        email = self.email_var.get().strip()
        password = self.password_var.get()
        if not email or len(password) < 6:
            messagebox.showinfo("アカウント作成", "メールアドレスと6文字以上のパスワードを入力してください。", parent=self)
            return
        try:
            data = self.client.sign_up(email, password)
            if data.get("access_token"):
                self.status_var.set("アカウントを作成し、ログインしました。次にライセンスキーを認証してください。")
            else:
                self.status_var.set("アカウントを作成しました。確認メールが届いた場合は、メール内のリンクを開いてからログインしてください。")
        except Exception as exc:
            messagebox.showerror("アカウント作成", friendly_error(exc), parent=self)

    def _signin(self):
        email = self.email_var.get().strip()
        password = self.password_var.get()
        try:
            self.client.sign_in(email, password)
            self.status_var.set(f"ログイン済み：{email}\nライセンスキーを認証してください。")
            self._refresh_status()
        except Exception as exc:
            messagebox.showerror("ログイン", friendly_error(exc), parent=self)

    def _logout(self):
        self.client.sign_out_local()
        self.status_var.set("ログアウトしました。")

    def _activate(self):
        key = self.key_var.get().strip()
        if not key:
            messagebox.showinfo("ライセンス", "ライセンスキーを入力してください。", parent=self)
            return
        try:
            data = self.client.activate(key)
            self.result = True
            self._show_license(data, prefix="ライセンス認証が完了しました。")
        except Exception as exc:
            messagebox.showerror("ライセンス認証", friendly_error(exc), parent=self)

    def _deactivate(self):
        if not self.client.token:
            messagebox.showinfo("ライセンス", "先にログインしてください。", parent=self)
            return
        if not messagebox.askyesno("認証解除", "このパソコンのライセンス認証を解除しますか？", parent=self):
            return
        try:
            self.client.deactivate_this_device()
            self.result = False
            self.status_var.set("この端末の認証を解除しました。別の端末で利用枠を使えます。")
        except Exception as exc:
            messagebox.showerror("認証解除", friendly_error(exc), parent=self)

    def _show_license(self, data: dict, prefix: str = "ライセンスは有効です。"):
        lines = [prefix]
        if data.get("plan"):
            lines.append(f"プラン：{data['plan']}")
        if data.get("customerCode"):
            lines.append(f"顧客コード：{data['customerCode']}")
        if data.get("expiresAt"):
            lines.append(f"有効期限：{data['expiresAt']}")
        else:
            lines.append("有効期限：なし")
        lines.append(f"端末ID：{self.client.install_id[:8]}…")
        self.status_var.set("\n".join(lines))

    def _refresh_status(self):
        if not self.client.token:
            self.status_var.set("未ログインです。アカウントを作成するか、ログインしてください。")
            return
        try:
            data = self.client.check()
            self.result = True
            self._show_license(data)
        except LicenseError as exc:
            if str(exc) == "NETWORK_ERROR" and self.client.offline_grace_ok(OFFLINE_GRACE_DAYS):
                self.result = True
                self.status_var.set(f"オフライン利用中です。最後の正常確認から{OFFLINE_GRACE_DAYS}日以内は利用できます。")
            else:
                self.status_var.set(friendly_error(exc))

    def _close(self):
        self.destroy()


def ensure_license(parent, client: LicenseClient) -> tuple[bool, str]:
    """Return (allowed, status_text)."""
    if client.token:
        try:
            data = client.check()
            customer = data.get("customerCode") or data.get("plan") or "有効"
            return True, f"ライセンス：{customer}"
        except LicenseError as exc:
            if str(exc) == "NETWORK_ERROR" and client.offline_grace_ok(OFFLINE_GRACE_DAYS):
                return True, f"ライセンス：オフライン利用（{OFFLINE_GRACE_DAYS}日猶予）"

    dialog = LicenseDialog(parent, client)
    parent.wait_window(dialog)
    if dialog.result:
        lic = client.cached_license
        customer = lic.get("customerCode") or lic.get("plan") or "有効"
        return True, f"ライセンス：{customer}"
    return False, "ライセンス：未認証"
