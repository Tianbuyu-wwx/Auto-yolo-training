"""AYT 安装向导（tkinter）。

四个页面：① 环境扫描（只读）→ ② 选项（目录/模式/GPU/镜像）→
③ 执行（实时日志）→ ④ 完成（启动入口）。

线程模型：扫描与安装在后台线程跑，UI 线程通过 queue + after() 轮询刷新。
"""

from __future__ import annotations

import queue
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

from .execute import InstallOptions, build_actions, run_actions, shortcut_target
from .plan import build_plan
from .scan import default_install_dir, scan

FONT = "Microsoft YaHei UI"


class Wizard(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("AYT 安装向导")
        self.geometry("780x580")
        self.minsize(720, 540)
        try:  # 高分屏清晰度（失败不影响功能）
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:  # noqa: BLE001
            pass

        self.report: dict | None = None
        self.plan: dict | None = None
        self.events: queue.Queue = queue.Queue()
        self.busy = False

        self._build()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._scan_async()
        self.after(120, self._poll)

    # ---------------- UI ----------------

    def _build(self) -> None:
        header = tk.Frame(self)
        header.pack(fill="x", padx=16, pady=(12, 4))
        tk.Label(header, text="AYT 安装向导", font=(FONT, 15, "bold")).pack(anchor="w")
        self.step_label = tk.Label(header, text="步骤 1/3 · 正在扫描本机环境…", fg="#666", font=(FONT, 9))
        self.step_label.pack(anchor="w")
        ttk.Separator(self).pack(fill="x")

        self.body = tk.Frame(self)
        self.body.pack(fill="both", expand=True, padx=16, pady=8)

        foot = tk.Frame(self)
        foot.pack(fill="x", padx=16, pady=10)
        self.btn_back = ttk.Button(foot, text="返回", command=self._go_back, state="disabled")
        self.btn_next = ttk.Button(foot, text="下一步", command=self._go_next, state="disabled")
        self.btn_back.pack(side="left")
        self.btn_next.pack(side="right")

        self.pages: dict[str, tk.Frame] = {}
        for name, builder in (
            ("scan", self._page_scan),
            ("options", self._page_options),
            ("run", self._page_run),
            ("done", self._page_done),
        ):
            frame = tk.Frame(self.body)
            builder(frame)
            self.pages[name] = frame
        self._show("scan")

    def _show(self, name: str) -> None:
        for f in self.pages.values():
            f.pack_forget()
        self.pages[name].pack(fill="both", expand=True)
        self.current = name
        caps = {"scan": "步骤 1/3 · 环境扫描", "options": "步骤 2/3 · 安装选项", "run": "步骤 3/3 · 执行", "done": "完成"}
        self.step_label.config(text=caps.get(name, ""))
        self.btn_back.config(state="normal" if name == "options" else "disabled")
        if name == "scan":
            self.btn_next.config(text="下一步", state="disabled" if self.report is None else "normal")
        elif name == "options":
            self.btn_next.config(text="开始安装", state="normal")
        elif name == "run":
            self.btn_next.config(text="关闭", state="normal")
        else:
            self.btn_next.config(text="完成", state="normal")

    # ---------------- 页面 ----------------

    def _page_scan(self, frame: tk.Frame) -> None:
        tk.Label(frame, text="本机环境检查结果（只读扫描，不会改动任何东西）：", font=(FONT, 9)).pack(anchor="w")
        wrap = tk.Frame(frame)
        wrap.pack(fill="both", expand=True, pady=(6, 0))
        self.scan_text = tk.Text(wrap, height=16, font=("Consolas", 9), relief="solid", borderwidth=1)
        sb = ttk.Scrollbar(wrap, command=self.scan_text.yview)
        self.scan_text.configure(yscrollcommand=sb.set)
        self.scan_text.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.scan_text.insert("1.0", "正在扫描…")
        self.scan_text.configure(state="disabled")
        self.plan_summary = tk.Label(frame, text="", font=(FONT, 9), fg="#0a6", justify="left")
        self.plan_summary.pack(anchor="w", pady=(6, 0))

    def _page_options(self, frame: tk.Frame) -> None:
        pad = {"padx": 8, "pady": 4}
        row0 = tk.Frame(frame)
        row0.pack(fill="x", **pad)
        tk.Label(row0, text="安装目录：", font=(FONT, 9), width=12, anchor="w").pack(side="left")
        self.opt_dir = tk.StringVar(value=str(default_install_dir()))
        tk.Entry(row0, textvariable=self.opt_dir, font=("Consolas", 9)).pack(side="left", fill="x", expand=True)
        ttk.Button(row0, text="浏览…", command=self._pick_dir).pack(side="left", padx=(6, 0))

        row1 = tk.Frame(frame)
        row1.pack(fill="x", **pad)
        tk.Label(row1, text="安装模式：", font=(FONT, 9), width=12, anchor="w").pack(side="left")
        self.opt_mode = tk.StringVar(value="venv")
        ttk.Radiobutton(row1, text="隔离安装（推荐：独立 venv，干净可卸载）", variable=self.opt_mode, value="venv").pack(anchor="w")
        self.rb_reuse = ttk.Radiobutton(row1, text="复用现有环境（跳过安装，最快）", variable=self.opt_mode, value="reuse")
        self.rb_reuse.pack(anchor="w")

        row2 = tk.Frame(frame)
        row2.pack(fill="x", **pad)
        tk.Label(row2, text="PyTorch：", font=(FONT, 9), width=12, anchor="w").pack(side="left")
        self.opt_gpu = tk.StringVar(value="gpu")
        self.rb_gpu = ttk.Radiobutton(row2, text="CUDA 12.8（GPU 训练）", variable=self.opt_gpu, value="gpu")
        self.rb_gpu.pack(side="left")
        self.rb_cpu = ttk.Radiobutton(row2, text="CPU 版", variable=self.opt_gpu, value="cpu")
        self.rb_cpu.pack(side="left", padx=(10, 0))

        row3 = tk.Frame(frame)
        row3.pack(fill="x", **pad)
        tk.Label(row3, text="下载源：", font=(FONT, 9), width=12, anchor="w").pack(side="left")
        self.opt_mirror = tk.BooleanVar(value=False)
        ttk.Checkbutton(row3, text="使用清华镜像（PyPI 直连慢时勾选）", variable=self.opt_mirror).pack(side="left")

        row4 = tk.Frame(frame)
        row4.pack(fill="x", **pad)
        tk.Label(row4, text="AYT 安装包：", font=(FONT, 9), width=12, anchor="w").pack(side="left")
        self.opt_wheel = tk.StringVar(value="")
        tk.Entry(row4, textvariable=self.opt_wheel, font=("Consolas", 9)).pack(side="left", fill="x", expand=True)
        ttk.Button(row4, text="选择 wheel…", command=self._pick_wheel).pack(side="left", padx=(6, 0))
        tk.Label(frame, text="（留空 = 从 PyPI 安装 auto-yolo-training[launcher]）", fg="#888", font=(FONT, 8)).pack(anchor="w", padx=8)

        row5 = tk.Frame(frame)
        row5.pack(fill="x", **pad)
        self.opt_shortcut = tk.BooleanVar(value=True)
        ttk.Checkbutton(row5, text="创建桌面快捷方式", variable=self.opt_shortcut).pack(anchor="w")

    def _page_run(self, frame: tk.Frame) -> None:
        self.run_status = tk.Label(frame, text="准备中…", font=(FONT, 9, "bold"))
        self.run_status.pack(anchor="w")
        self.progress = ttk.Progressbar(frame, mode="indeterminate")
        self.progress.pack(fill="x", pady=6)
        wrap = tk.Frame(frame)
        wrap.pack(fill="both", expand=True)
        self.run_text = tk.Text(wrap, height=16, font=("Consolas", 8), relief="solid", borderwidth=1)
        sb = ttk.Scrollbar(wrap, command=self.run_text.yview)
        self.run_text.configure(yscrollcommand=sb.set)
        self.run_text.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    def _page_done(self, frame: tk.Frame) -> None:
        self.done_label = tk.Label(frame, text="", font=(FONT, 11, "bold"), justify="left")
        self.done_label.pack(anchor="w", pady=(20, 8))
        self.done_detail = tk.Label(frame, text="", font=(FONT, 9), fg="#555", justify="left")
        self.done_detail.pack(anchor="w")
        btns = tk.Frame(frame)
        btns.pack(anchor="w", pady=16)
        self.btn_open = ttk.Button(btns, text="打开安装目录", command=self._open_install_dir)
        self.btn_open.pack(side="left")
        self.btn_launch = ttk.Button(btns, text="启动 AYT 启动器", command=self._launch)
        self.btn_launch.pack(side="left", padx=(8, 0))

    # ---------------- 交互 ----------------

    def _pick_dir(self) -> None:
        d = filedialog.askdirectory(initialdir=self.opt_dir.get())
        if d:
            self.opt_dir.set(d)

    def _pick_wheel(self) -> None:
        f = filedialog.askopenfilename(filetypes=[("Wheel", "*.whl"), ("全部文件", "*.*")])
        if f:
            self.opt_wheel.set(f)

    def _go_back(self) -> None:
        if self.current == "options":
            self._show("scan")

    def _go_next(self) -> None:
        if self.current == "scan":
            self._apply_scan_to_options()
            self._show("options")
        elif self.current == "options":
            self._show("run")
            self._run_async()
        else:
            self.destroy()

    def _apply_scan_to_options(self) -> None:
        """用扫描结果预置选项（GPU 有→默认 GPU；PyPI 不通→默认镜像；全满足→提示可复用）。"""
        rep = self.report or {}
        gpu = bool((rep.get("gpu") or {}).get("present"))
        if not gpu:
            self.opt_gpu.set("cpu")
        pypi_ok = bool(((rep.get("network") or {}).get("pypi") or {}).get("ok"))
        if not pypi_ok:
            self.opt_mirror.set(True)
        can_reuse = bool(rep.get("selected_python")) and not (rep.get("deps_note") or "")
        self.rb_reuse.config(state="normal" if can_reuse else "disabled")

    def _on_close(self) -> None:
        if self.busy:
            from tkinter import messagebox

            if not messagebox.askyesno("安装进行中", "安装仍在进行，确定要关闭吗？"):
                return
        self.destroy()

    # ---------------- 线程与轮询 ----------------

    def _scan_async(self) -> None:
        def work() -> None:
            try:
                rep = scan(str(self.opt_dir.get()) if hasattr(self, "opt_dir") else None)
                plan = build_plan(rep)
                self.events.put(("scan_done", rep, plan))
            except Exception as exc:  # noqa: BLE001
                self.events.put(("error", str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def _run_async(self) -> None:
        rep = self.report or {}
        opt = InstallOptions(
            install_dir=Path(self.opt_dir.get()),
            mode=self.opt_mode.get(),
            gpu=(self.opt_gpu.get() == "gpu"),
            mirror=bool(self.opt_mirror.get()),
            ayt_source=self.opt_wheel.get().strip(),
            make_shortcut=bool(self.opt_shortcut.get()),
        )
        actions = build_actions(rep, opt)
        self.busy = True
        self.progress.start(12)

        def work() -> None:
            try:
                results = run_actions(
                    actions,
                    install_dir=opt.install_dir,
                    on_line=lambda s: self.events.put(("line", s)),
                    on_step=lambda i, a: self.events.put(("step", i, a)),
                )
                self.events.put(("run_done", results, opt))
            except Exception as exc:  # noqa: BLE001
                self.events.put(("error", str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def _poll(self) -> None:
        try:
            while True:
                ev = self.events.get_nowait()
                kind = ev[0]
                if kind == "scan_done":
                    self._on_scan_done(ev[1], ev[2])
                elif kind == "line":
                    self.run_text.insert("end", ev[1] + "\n")
                    self.run_text.see("end")
                elif kind == "step":
                    self.run_status.config(text=f"执行中：{ev[2]['title']} …")
                    self.run_text.insert("end", f"\n=== {ev[2]['title']} ===\n")
                    self.run_text.see("end")
                elif kind == "run_done":
                    self._on_run_done(ev[1], ev[2])
                elif kind == "error":
                    self.run_status.config(text=f"出错：{ev[1]}")
                    self.progress.stop()
                    self.busy = False
        except queue.Empty:
            pass
        self.after(120, self._poll)

    # ---------------- 状态回调 ----------------

    def _on_scan_done(self, rep: dict, plan: dict) -> None:
        self.report = rep
        self.plan = plan
        from . import __main__ as cli

        self.scan_text.configure(state="normal")
        self.scan_text.delete("1.0", "end")
        self.scan_text.insert("1.0", cli._fmt_scan(rep) + "\n\n" + cli._fmt_plan(plan))
        self.scan_text.configure(state="disabled")
        s = plan["summary"]
        self.plan_summary.config(text=("✓ " if s["ready_now"] else "→ ") + s["note"])
        self._show("scan")
        self.btn_next.config(state="normal")

    def _on_run_done(self, results: list[dict], opt: InstallOptions) -> None:
        self.progress.stop()
        self.busy = False
        ok = all(r.get("ok") for r in results)
        self.results = results
        self.install_opt = opt
        if ok:
            self.done_label.config(text="✓ 安装完成", fg="#0a6")
            self.done_detail.config(
                text=f"安装目录：{opt.install_dir}\n桌面已创建「AYT 启动器」快捷方式。\n"
                "双击即可打开启动器，选择数据集开始训练。"
            )
        else:
            bad = next((r for r in results if not r.get("ok")), None)
            self.done_label.config(text="× 安装未完成", fg="#c33")
            self.done_detail.config(
                text=f"在步骤「{bad.get('title') if bad else '?'}」失败（{bad.get('detail') if bad else ''}）。\n"
                "可返回重试；完整日志见上一步骤窗口。"
            )
        self._show("done")

    def _open_install_dir(self) -> None:
        d = self.install_opt.install_dir if getattr(self, "install_opt", None) else Path(self.opt_dir.get())
        subprocess.Popen(["explorer", str(d)])  # noqa: S603,S607

    def _launch(self) -> None:
        opt = getattr(self, "install_opt", None)
        if opt is None:
            return
        exe = shortcut_target(opt.install_dir)
        try:
            subprocess.Popen([exe], cwd=str(opt.install_dir))  # noqa: S603
        except OSError:
            self._open_install_dir()


def main(install_dir: str | None = None) -> int:
    app = Wizard()
    if install_dir:
        app.opt_dir.set(install_dir)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
