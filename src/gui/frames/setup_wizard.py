"""Meta API setup wizard."""

import customtkinter as ctk


class SetupWizard(ctk.CTkToplevel):
    """Six-step guide for Meta API setup."""

    _PERMISSIONS = [
        "pages_read_engagement",
        "pages_manage_posts",
        "instagram_basic",
        "instagram_manage_comments",
        "threads_basic",
        "threads_manage_replies",
    ]

    _STEPS = [
        ("建立 Meta Developer 帳號", "前往 Meta for Developers，使用企業或管理者帳號完成開通流程。"),
        ("建立應用程式", "建立一個 Business 類型應用程式，並加入 Facebook、Instagram 與 Threads 相關產品。"),
        ("設定權限", "在 App Review 與角色設定中加入測試人員，並準備申請必要權限。"),
        ("取得 Access Token", "透過 Graph API Explorer 或系統使用者產生長效 Access Token。"),
        ("設定 Webhook", "為 Facebook/Instagram Webhook 設定回呼網址、驗證字串與訂閱欄位。"),
        ("測試連線", "使用測試貼文與留言驗證讀取、偵測與回覆流程是否正常。"),
    ]

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.title("Meta API 設定精靈")
        self.geometry("760x520")
        self.resizable(False, False)

        self._step_index = 0

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            self,
            text="Meta API 設定精靈",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=24, pady=(20, 10))

        self._content = ctk.CTkFrame(self)
        self._content.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 16))
        self._content.grid_columnconfigure(0, weight=1)
        self._content.grid_rowconfigure(2, weight=1)

        nav = ctk.CTkFrame(self, fg_color="transparent")
        nav.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 20))
        nav.grid_columnconfigure(1, weight=1)

        self._prev_btn = ctk.CTkButton(nav, text="Previous", width=100, command=self._previous_step)
        self._prev_btn.grid(row=0, column=0, sticky="w")

        self._next_btn = ctk.CTkButton(nav, text="Next", width=100, command=self._next_step)
        self._next_btn.grid(row=0, column=2, sticky="e")

        self._finish_btn = ctk.CTkButton(nav, text="Finish", width=100, command=self.destroy)
        self._finish_btn.grid(row=0, column=3, sticky="e", padx=(10, 0))

        self._render_step()

    def _render_step(self):
        for child in self._content.winfo_children():
            child.destroy()

        step_title, step_body = self._STEPS[self._step_index]

        ctk.CTkLabel(
            self._content,
            text=f"Step {self._step_index + 1} / {len(self._STEPS)}",
            text_color="gray60",
            font=ctk.CTkFont(size=12),
        ).grid(row=0, column=0, sticky="w", padx=18, pady=(18, 6))

        ctk.CTkLabel(
            self._content,
            text=step_title,
            font=ctk.CTkFont(size=18, weight="bold"),
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", padx=18)

        body = ctk.CTkTextbox(self._content, wrap="word", height=260)
        body.grid(row=2, column=0, sticky="nsew", padx=18, pady=(12, 12))
        body.insert("1.0", step_body + "\n\n")
        body.insert("end", "必要權限:\n")
        for permission in self._PERMISSIONS:
            body.insert("end", f"- {permission}\n")
        body.configure(state="disabled")

        self._prev_btn.configure(state="normal" if self._step_index > 0 else "disabled")
        self._next_btn.configure(state="normal" if self._step_index < len(self._STEPS) - 1 else "disabled")
        self._finish_btn.configure(state="normal" if self._step_index == len(self._STEPS) - 1 else "disabled")

    def _previous_step(self):
        if self._step_index > 0:
            self._step_index -= 1
            self._render_step()

    def _next_step(self):
        if self._step_index < len(self._STEPS) - 1:
            self._step_index += 1
            self._render_step()
