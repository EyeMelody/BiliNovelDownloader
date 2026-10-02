import os
import re
import sys
import time
import json
import tempfile
import ctypes
import shutil
import logging
import threading
import subprocess
import webbrowser
import tkinter as tk
import socket as _socket
from pathlib import Path
from enum import Enum, auto
from datetime import datetime
from typing import List, Tuple
from tkinter import font as tkfont
from tkinter import ttk, messagebox

from PIL import ImageTk

from core import (DIR_DOWNLOADS, DIR_TRAD, VALID_URL_PATTERN,
                  DOWNLOAD_TIMEOUT_SECONDS, STALL_TIMEOUT_SECONDS,
                  get_resource_path, get_base_path, APP_VERSION, sanitize_filename, normalize_novel_url)
from scraper import NovelScraper, NovelInfo, classify_error, packer_log_is_network_error
from epub_tools import T2S_CONVERTER, process_downloaded_folder
from packer import find_downloader_exe, write_packer_pid, clear_packer_pid, cleanup_orphaned_packer
from network import load_settings, save_settings, validate_proxy, make_session
from download_job import run_job, DownloadError, parse_volumes
from updater import APP_REPO, PACKER_REPO, get_local_packer_version, check_target


_SINGLE_INSTANCE_PORT = 19877
_lock_socket = None

def _listen_for_reactivation(app: 'Application'):
    """第一个实例在背景监听，收到 show 讯号就把视窗带到前景"""
    def _server():
        while True:
            try:
                conn, _ = _lock_socket.accept()
                msg = conn.recv(16).decode(errors='ignore').strip()
                conn.close()
                if msg == "show":
                    app.after(0, _bring_to_front, app)
            except Exception:
                break
    threading.Thread(target=_server, daemon=True).start()

def _bring_to_front(app: 'Application'):
    """把视窗带到最前面"""
    app.deiconify()
    app.lift()
    app.focus_force()
    try:
        ctypes.windll.user32.FlashWindow(int(app.wm_frame()), True)
    except Exception:
        pass

def ensure_single_instance() -> bool:
    """
    回传 True  : 这是第一个实例，可以继续启动
    回传 False : 已有实例在跑，已发送 show 讯号，应静默退出
    """
    global _lock_socket
    sock = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    sock.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 0)
    try:
        sock.bind(('127.0.0.1', _SINGLE_INSTANCE_PORT))
        sock.listen(5)
        _lock_socket = sock
        return True
    except OSError:
        sock.close()
        try:
            s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
            s.connect(('127.0.0.1', _SINGLE_INSTANCE_PORT))
            s.sendall(b"show")
            s.close()
        except Exception:
            pass
        return False

class AppState(Enum):
    IDLE = auto()
    CHECKING = auto()
    DOWNLOADING = auto()

class LogHandler(logging.Handler):
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget
        self.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))

    def emit(self, record):
        msg = self.format(record)
        def append():
            self.text_widget.configure(state="normal")
            self.text_widget.insert("end", msg + "\n", record.levelname)
            self.text_widget.see("end")
            self.text_widget.configure(state="disabled")
        self.text_widget.after(0, append)

class Application(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"哔哩轻小说下载器 · 简体版 {APP_VERSION}")

        # 尝试载入视窗图示
        icon_path = get_resource_path('icon.ico')
        if icon_path.exists():
            try:
                self.iconbitmap(str(icon_path))
            except Exception as e:
                logging.warning(f"无法载入视窗图示: {e}")

        width, height = 950, 700
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width // 2) - (width // 2)
        y = (screen_height // 2) - (height // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")
        self.minsize(width, height)
        self.resizable(True, True)
        self.configure(padx=10, pady=5)

        self.scraper = NovelScraper()
        self.app_state = AppState.IDLE
        self.current_process = None
        self.cancel_event = threading.Event()
        self._abort_reason = None
        self.last_activity_time = 0
        self.last_checked_url = ""
        self._pg_reset()

        self._update_results = None       # 更新检查结果，主程式与核心下载器各一笔
        self._update_checking = False
        self._update_menu_added = False
        self._update_win = None

        self.create_widgets()
        self.setup_logging()
        self._start_update_check()

        # 绑定视窗关闭事件
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def _load_history(self) -> list:
        history_path = get_base_path() / 'history.json'
        if history_path.exists():
            try:
                return json.loads(history_path.read_text(encoding='utf-8'))
            except Exception as e:
                logging.warning(f"历史纪录档读取失败，已重置: {e}")
                return []
        return []

    def _save_to_history(self, url: str, title: str):
        history = self._load_history()
        history = [h for h in history if h.get('url') != url]
        history.insert(0, {'url': url, 'title': title, 'time': datetime.now().strftime('%Y-%m-%d %H:%M')})
        history = history[:15]
        history_path = get_base_path() / 'history.json'
        try:
            history_path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding='utf-8')
        except Exception as e:
            logging.warning(f"无法储存历史纪录: {e}")

    def _show_history_menu(self):
        history = self._load_history()
        if not history:
            messagebox.showinfo("下载历史", "目前尚无下载记录。")
            return

        menu = tk.Menu(self, tearoff=0)
        for item in history:
            label = f"{item['title']}  ({item.get('time', '')})"
            if len(label) > 40: label = label[:37] + "..."
            menu.add_command(
                label=label,
                command=lambda u=item['url']: self._fill_url_from_history(u)
            )

        x = self.history_btn.winfo_rootx()
        y = self.history_btn.winfo_rooty() + self.history_btn.winfo_height()
        try:
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def _fill_url_from_history(self, url: str):
        self.url_var.set(url)
        self.entry_url.configure(foreground="black")
        self.last_checked_url = ""
        self.check_novel_info()

    def on_closing(self):
        if self.app_state == AppState.DOWNLOADING:
            if messagebox.askokcancel("退出确认", "目前正在下载中，确定要强制退出吗？\n(这将终止所有下载与转换进程)"):
                self.cancel_download()
                self.destroy()
        else:
            self.destroy()

    def create_widgets(self):
        self._build_menu()
        self._build_url_frame()
        self._build_settings_frame()
        self._build_run_frame()
        self._build_bottom_frame()

    def _build_menu(self):
        self.menubar = tk.Menu(self)
        file_menu = tk.Menu(self.menubar, tearoff=0)
        file_menu.add_command(label="开启下载资料夹", command=self._open_downloads_folder)
        self.menubar.add_cascade(label="档案", menu=file_menu)
        help_menu = tk.Menu(self.menubar, tearoff=0)
        help_menu.add_command(label="检查更新", command=lambda: self._show_update_window(recheck=True))
        help_menu.add_command(label="关于", command=self._show_about)
        self.menubar.add_cascade(label="说明", menu=help_menu)
        self.menubar.add_command(label="代理设置", command=self._show_proxy_settings)
        self.config(menu=self.menubar)

    def _show_proxy_settings(self):
        if self.app_state != AppState.IDLE:
            messagebox.showinfo("代理设置", "请等待当前任务结束后再修改代理。")
            return
        win = tk.Toplevel(self)
        win.title("代理设置")
        win.transient(self)
        win.resizable(False, False)
        frm = ttk.Frame(win, padding=18)
        frm.pack(fill="both", expand=True)
        try:
            settings = load_settings()
        except (ValueError, OSError) as e:
            messagebox.showerror("设置读取失败", str(e))
            settings = {'proxy_enabled': False, 'proxy_url': 'http://127.0.0.1:7890'}
        enabled = tk.BooleanVar(value=settings['proxy_enabled'])
        address = tk.StringVar(value=settings['proxy_url'])
        ttk.Checkbutton(frm, text="启用代理", variable=enabled).pack(anchor="w")
        ttk.Label(frm, text="HTTP / 混合代理地址").pack(anchor="w", pady=(12, 4))
        ttk.Entry(frm, textvariable=address, width=48).pack(fill="x")
        ttk.Label(frm, text="例如 http://127.0.0.1:7890\n作用于书籍预览、正文、插图和更新检查。\n关闭时直接连接；暂不支持 SOCKS、账号密码代理。", wraplength=420).pack(anchor="w", pady=10)
        result = tk.StringVar()
        ttk.Label(frm, textvariable=result, wraplength=420).pack(anchor="w")
        buttons = ttk.Frame(frm)
        buttons.pack(fill="x", pady=(12, 0))
        def values():
            return {'proxy_enabled': enabled.get(), 'proxy_url': validate_proxy(address.get())}
        def save():
            try:
                save_settings(values())
                self.last_checked_url = ""
                self.status_label.config(text="代理设置已保存，下次请求生效", foreground="green")
                win.destroy()
            except (ValueError, OSError) as e:
                messagebox.showerror("无法保存代理", str(e), parent=win)
        def test():
            try:
                current = values()
            except ValueError as e:
                result.set(str(e)); return
            test_btn.config(state="disabled")
            result.set("正在测试网站连接…")
            def worker():
                try:
                    with make_session(current) as session:
                        response = session.get('https://www.bilinovel.com/novel/4836.html', headers=self.scraper.headers, timeout=15)
                        message = f"{'代理' if current['proxy_enabled'] else '直连'}测试：HTTP {response.status_code}"
                except Exception as e:
                    message = f"连接失败：{e}"
                def finish():
                    if win.winfo_exists():
                        result.set(message); test_btn.config(state="normal")
                self.after(0, finish)
            threading.Thread(target=worker, daemon=True).start()
        test_btn = ttk.Button(buttons, text="测试连接", command=test)
        test_btn.pack(side="left")
        ttk.Button(buttons, text="保存", command=save).pack(side="right")
        win.grab_set()

    def _show_about(self):
        win = tk.Toplevel(self)
        win.title("关于")
        win.resizable(False, False)
        win.transient(self)
        icon_path = get_resource_path('icon.ico')
        if icon_path.exists():
            try:
                win.iconbitmap(str(icon_path))
            except Exception:
                pass
        frm = ttk.Frame(win, padding=20)
        frm.pack(fill="both", expand=True)
        ttk.Label(frm, text=f"BiliNovelDownloader {APP_VERSION}",
                  font=("Microsoft YaHei", 12, "bold")).pack(anchor="w")
        ttk.Label(frm, text="哔哩轻小说下载器 · 简体版").pack(anchor="w", pady=(0, 10))

        def add_link(text, url):
            lbl = ttk.Label(frm, text=text, foreground="#0066CC", cursor="hand2")
            lbl.pack(anchor="w")
            lbl.bind("<Button-1>", lambda e: webbrowser.open(url))

        add_link("https://github.com/EyeMelody/BiliNovelDownloader",
                 "https://github.com/EyeMelody/BiliNovelDownloader")
        ttk.Label(frm, text="\n核心下载功能由 bili_novel_packer（Montaro2017）提供").pack(anchor="w")
        add_link("https://github.com/Montaro2017/bili_novel_packer",
                 "https://github.com/Montaro2017/bili_novel_packer")
        ttk.Label(frm, text="\nMIT License").pack(anchor="w")

        btnf = ttk.Frame(frm)
        btnf.pack(fill="x", pady=(15, 0))
        ttk.Button(btnf, text="第三方授权", command=self._open_third_party_licenses).pack(side="left")

        # 置中于主视窗
        win.grab_set()
        win.update_idletasks()
        w, h = win.winfo_width(), win.winfo_height()
        x = self.winfo_rootx() + (self.winfo_width() - w) // 2
        y = self.winfo_rooty() + (self.winfo_height() - h) // 2
        win.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def _open_third_party_licenses(self):
        path = get_base_path() / 'THIRD_PARTY_LICENSES.txt'
        if not path.exists():
            messagebox.showinfo("第三方授权", "找不到 THIRD_PARTY_LICENSES.txt。")
            return
        try:
            os.startfile(str(path))
        except Exception:
            webbrowser.open(path.as_uri())

    def _open_downloads_folder(self):
        folder = get_base_path() / DIR_DOWNLOADS
        try:
            folder.mkdir(parents=True, exist_ok=True)
            os.startfile(str(folder))
        except Exception as e:
            messagebox.showerror("错误", f"无法开启下载资料夹:\n{e}")

    def _start_update_check(self):
        """背景查一次更新，已在查则不重复启动"""
        if self._update_checking:
            return
        self._update_checking = True
        self._refresh_update_window()
        threading.Thread(target=self._thread_check_updates, daemon=True).start()

    def _thread_check_updates(self):
        packer_exe = find_downloader_exe(get_base_path())
        results = {
            'app': check_target(APP_REPO, APP_VERSION),
            'packer': {'status': 'no_local', 'latest': '随本分支应用整包更新',
                       'local': get_local_packer_version(packer_exe), 'url': None},
        }
        self._update_results = results
        self._update_checking = False
        self.after(0, self._apply_update_results)

    def _apply_update_results(self):
        results = self._update_results or {}
        if (not self._update_menu_added
                and any(r.get('status') == 'update' for r in results.values())):
            self.menubar.add_command(label="有可用更新",
                                     command=lambda: self._show_update_window(recheck=False))
            self._update_menu_added = True
        self._refresh_update_window()

    def _show_update_window(self, recheck=False):
        if self._update_win is not None and self._update_win.winfo_exists():
            self._update_win.lift()
            self._update_win.focus_force()
        else:
            self._build_update_window()
        if recheck or self._update_results is None:
            self._start_update_check()
        self._refresh_update_window()

    def _build_update_window(self):
        win = tk.Toplevel(self)
        win.title("检查更新")
        win.resizable(False, False)
        win.transient(self)
        icon_path = get_resource_path('icon.ico')
        if icon_path.exists():
            try:
                win.iconbitmap(str(icon_path))
            except Exception:
                pass
        frm = ttk.Frame(win, padding=20)
        frm.pack(fill="both", expand=True)

        local_packer = get_local_packer_version(find_downloader_exe(get_base_path()))
        self._upd_labels = {}
        rows = (('app', '主程式', APP_VERSION),
                ('packer', '核心下载器', f"v{local_packer}" if local_packer else "无法判定"))
        for i, (key, name, current) in enumerate(rows):
            base = i * 2
            pad_top = (0, 0) if i == 0 else (10, 0)
            ttk.Label(frm, text=name, font=("Microsoft YaHei", 10, "bold")).grid(
                row=base, column=0, sticky="w", pady=pad_top)
            ttk.Label(frm, text=current).grid(row=base, column=1, sticky="w", padx=(15, 0), pady=pad_top)
            ttk.Label(frm, text="最新版本").grid(row=base + 1, column=0, sticky="w")
            latest = ttk.Label(frm, text="检查中…", foreground="gray")
            latest.grid(row=base + 1, column=1, sticky="w", padx=(15, 0))
            link = ttk.Label(frm, text="前往下载", foreground="#0066CC", cursor="hand2")
            link.grid(row=base + 1, column=2, sticky="w", padx=(10, 0))
            link.grid_remove()
            self._upd_labels[key] = {'latest': latest, 'link': link}

        self._upd_warn = ttk.Label(frm, text="", foreground="#B25900", wraplength=320)
        self._upd_warn.grid(row=4, column=0, columnspan=3, sticky="w", pady=(12, 0))
        self._upd_warn.grid_remove()

        btnf = ttk.Frame(frm)
        btnf.grid(row=5, column=0, columnspan=3, sticky="e", pady=(15, 0))
        self._upd_recheck_btn = ttk.Button(btnf, text="重新检查",
                                           command=lambda: self._show_update_window(recheck=True))
        self._upd_recheck_btn.pack(side="left", padx=(0, 5))
        ttk.Button(btnf, text="关闭", command=win.destroy).pack(side="left")

        self._update_win = win
        win.grab_set()
        win.update_idletasks()
        w, h = win.winfo_width(), win.winfo_height()
        x = self.winfo_rootx() + (self.winfo_width() - w) // 2
        y = self.winfo_rooty() + (self.winfo_height() - h) // 2
        win.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def _refresh_update_window(self):
        """把目前的检查状态反映到检查更新视窗（未开启时不做事）"""
        if self._update_win is None or not self._update_win.winfo_exists():
            return
        results = self._update_results or {}
        checking = self._update_checking
        for key in ('app', 'packer'):
            widgets = self._upd_labels[key]
            r = results.get(key)
            if checking or not r:
                widgets['latest'].config(text="检查中…" if checking else "—", foreground="gray")
                widgets['link'].grid_remove()
                continue
            status = r['status']
            if status == 'update':
                widgets['latest'].config(text=r['latest'], foreground="#0066CC")
                widgets['link'].bind("<Button-1>", lambda e, u=r['url']: webbrowser.open(u))
                widgets['link'].grid()
            elif status == 'latest':
                widgets['latest'].config(text=f"{r['latest']}（已是最新）", foreground="green")
                widgets['link'].grid_remove()
            elif status == 'no_local':
                widgets['latest'].config(text=r['latest'] or "—", foreground="black")
                widgets['link'].grid_remove()
            else:
                widgets['latest'].config(text="—", foreground="gray")
                widgets['link'].grid_remove()

        statuses = [r.get('status') for r in results.values()]
        if checking:
            warn = ""
        elif 'ratelimit' in statuses:
            warn = "查询过于频繁，请稍后再试。"
        elif 'network' in statuses:
            warn = "无法取得更新资讯，请检查网路连线。"
        else:
            warn = ""
        if warn:
            self._upd_warn.config(text=warn)
            self._upd_warn.grid()
        else:
            self._upd_warn.grid_remove()
        self._upd_recheck_btn.config(state="disabled" if checking else "normal")

    def _build_url_frame(self):
        frame_url = ttk.LabelFrame(self, text="小说来源与资讯预览")
        frame_url.pack(fill="x", pady=5)

        url_input_frame = tk.Frame(frame_url)
        url_input_frame.pack(fill="x", padx=10, pady=5)

        ttk.Label(url_input_frame, text="输入网址或数字 ID:").pack(side="left")
        self.url_var = tk.StringVar()
        self.placeholder = "例如：https://www.bilinovel.com/novel/2.html 或 2"
        self.entry_url = ttk.Entry(url_input_frame, textvariable=self.url_var, font=("Consolas", 11), width=50)
        self.entry_url.pack(side="left", fill="x", expand=True, padx=5)
        self.entry_url.bind("<Return>", self.check_novel_info)

        def on_focus_in(event):
            if self.url_var.get() == self.placeholder:
                self.url_var.set("")
                self.entry_url.configure(foreground="black")

        def on_focus_out(event):
            if not self.url_var.get().strip():
                self.url_var.set(self.placeholder)
                self.entry_url.configure(foreground="gray")

        self.entry_url.bind("<FocusIn>", on_focus_in)
        self.entry_url.bind("<FocusOut>", on_focus_out)
        self.url_var.set(self.placeholder)
        self.entry_url.configure(foreground="gray")

        self.check_btn = ttk.Button(url_input_frame, text="检查并载入资讯", width=16, command=self.check_novel_info)
        self.check_btn.pack(side="left", padx=5)

        self.history_btn = ttk.Button(url_input_frame, text="历史纪录", command=self._show_history_menu)
        self.history_btn.pack(side="left", padx=5)

        self.go_url_btn = ttk.Button(url_input_frame, text="前往网址", command=self.open_url)
        self.go_url_btn.pack(side="left", padx=5)

        preview_frame = tk.Frame(frame_url)
        preview_frame.pack(fill="x", padx=10, pady=5)

        self.cover_container = tk.Frame(preview_frame, width=200, height=280, bg="lightgray")
        self.cover_container.pack(side="left", padx=(0, 10))
        self.cover_container.pack_propagate(False)

        self.cover_label = tk.Label(self.cover_container, text="封面缩图预览", bg="lightgray", wraplength=150)
        self.cover_label.pack(expand=True, fill="both")

        info_text_frame = tk.Frame(preview_frame)
        info_text_frame.pack(side="left", fill="both", expand=True)

        self.title_text = self._make_info_field(info_text_frame, ("Microsoft YaHei", 12, "bold"))
        self.title_text.pack(fill="x", pady=(0, 5))
        self.author_text = self._make_info_field(info_text_frame, ("Microsoft YaHei", 10))
        self.author_text.pack(fill="x", pady=2)
        self.meta_text = self._make_info_field(info_text_frame, ("Microsoft YaHei", 10))
        self.meta_text.pack(fill="x", pady=2)
        self.update_text = self._make_info_field(info_text_frame, ("Microsoft YaHei", 10))
        self.update_text.pack(fill="x", pady=2)

        self._set_info_field(self.title_text, "书名：尚未载入")
        self._set_info_field(self.author_text, "-")
        self._set_info_field(self.meta_text, "-")
        self._set_info_field(self.update_text, "-")

        ttk.Label(info_text_frame, text="简介：", font=("Microsoft YaHei", 10)).pack(anchor="nw", pady=(2, 0))

        desc_container = tk.Frame(info_text_frame)
        desc_container.pack(anchor="nw", fill="x", expand=True, pady=(0, 5))
        desc_container.columnconfigure(0, weight=1)

        desc_v_scroll = ttk.Scrollbar(desc_container, orient="vertical")
        self.desc_text = tk.Text(desc_container, height=7, font=("Microsoft YaHei", 10), foreground="black",
                                 wrap="word", borderwidth=0, highlightthickness=0, insertwidth=0)
        self.desc_text.bind("<Key>", self._readonly_text_key)  # 唯读但可选取

        def set_desc_sb(first, last):
            if float(first) <= 0.0 and float(last) >= 1.0:
                desc_v_scroll.grid_remove()
            else:
                desc_v_scroll.grid(row=0, column=1, sticky="ns")
            desc_v_scroll.set(first, last)

        self.desc_text.config(yscrollcommand=set_desc_sb)
        desc_v_scroll.config(command=self.desc_text.yview)

        self.desc_text.config(bg=self.cget("bg"))
        self.desc_text.grid(row=0, column=0, sticky="nsew")
        self._set_desc("-")

        self.status_label = ttk.Label(info_text_frame, text="", foreground="blue")
        self.status_label.pack(anchor="nw", pady=(5, 0))

    def _readonly_text_key(self, event):
        """让 Text 唯读但仍可选取, 复制"""
        if event.state & 0x0004 and event.keysym.lower() in ("c", "insert"):
            return  # Ctrl+C, Ctrl+Insert 复制
        if not (event.state & 0x0004) and event.keysym in (
            "Left", "Right", "Up", "Down", "Home", "End", "Prior", "Next",
            "Shift_L", "Shift_R", "Control_L", "Control_R",
        ):
            return  # 移动游标与选取用的键
        return "break"

    def _autosize_info_field(self, widget):
        """依实际换行后的显示行数调整 Text 高度，让长字串完整显示不被裁切"""
        try:
            res = widget.count("1.0", "end-1c", "displaylines")
            n = res[0] if isinstance(res, tuple) else res
        except Exception:
            n = 1
        n = max(int(n or 1), 1)
        if int(widget.cget("height")) != n:
            widget.configure(height=n)

    def _make_info_field(self, parent, font):
        """建立唯读、可选取、会自动换行并依内容调整高度的资讯栏位"""
        txt = tk.Text(parent, font=font, height=1, wrap="word", relief="flat",
                      borderwidth=0, highlightthickness=0, padx=0, pady=0,
                      insertwidth=0, bg=self.cget("bg"))
        txt.bind("<Key>", self._readonly_text_key)
        txt.bind("<Configure>", lambda e, w=txt: self._autosize_info_field(w))
        return txt

    def _set_info_field(self, widget, text):
        """更新资讯栏位内容并在版面就绪后重算高度"""
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.after_idle(lambda: self._autosize_info_field(widget))

    def _set_desc(self, text):
        """更新简介内容（唯读 Text，免切换 state）"""
        self.desc_text.delete("1.0", "end")
        self.desc_text.insert("1.0", text)

    def _build_settings_frame(self):
        # 设定区块_分卷下载与进阶选项
        settings_container = tk.Frame(self)
        settings_container.pack(fill="x", pady=2)

        # 2. 分卷下载设定
        frame_vol = ttk.LabelFrame(settings_container, text="分卷下载设定")
        frame_vol.pack(side="left", fill="both", expand=True, padx=(0, 5))

        self.vol_mode_var = tk.StringVar(value="all")
        ttk.Radiobutton(frame_vol, text="下载全部分卷", variable=self.vol_mode_var, value="all", command=self.on_vol_mode_change).grid(row=0, column=0, sticky="w", padx=10, pady=2)
        ttk.Radiobutton(frame_vol, text="下载指定范围：", variable=self.vol_mode_var, value="specific", command=self.on_vol_mode_change).grid(row=1, column=0, sticky="w", padx=10, pady=2)

        self.vol_specific_var = tk.StringVar()
        self.vol_entry = ttk.Entry(frame_vol, textvariable=self.vol_specific_var, state="disabled", width=15)
        self.vol_entry.grid(row=1, column=1, sticky="w", padx=5)
        ttk.Label(frame_vol, text="(例: 1,2-9,11，可参考分卷对照表)", foreground="gray", font=("Arial", 9)).grid(row=1, column=2, sticky="w")

        # 3. 进阶选项
        frame_opt = ttk.LabelFrame(settings_container, text="进阶选项")
        frame_opt.pack(side="left", fill="both", expand=True, padx=(5, 0))

        self.merge_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame_opt, text="合并选取的分卷为单一档案", variable=self.merge_var).pack(anchor="w", padx=10, pady=2)
        self.title_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(frame_opt, text="在每章开头添加章节标题", variable=self.title_var).pack(anchor="w", padx=10, pady=2)

    def _build_run_frame(self):
        # 4. 状态与执行
        frame_run = tk.Frame(self)
        frame_run.pack(fill="x", pady=5)

        self.start_btn = ttk.Button(frame_run, text="开始下载", command=self.start_process, width=20)
        self.start_btn.pack(pady=(0, 2))

        self.progress_var = tk.StringVar(value="")
        ttk.Label(frame_run, textvariable=self.progress_var, font=("Microsoft YaHei", 10), foreground="black").pack()

        self.progress_canvas = tk.Canvas(frame_run, width=500, height=14, bg='#E0E0E0', highlightthickness=0)
        self.progress_rect = self.progress_canvas.create_rectangle(-100, 0, 0, 14, fill='#06B025', width=0)

    def _build_bottom_frame(self):
        # 下方区块_分卷对照表与日志视窗
        bottom_container = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        bottom_container.pack(fill="both", expand=True, pady=5)

        # 2.5 分卷对照表
        frame_vol_ref = ttk.LabelFrame(bottom_container, text="分卷对照表")
        bottom_container.add(frame_vol_ref, weight=4)

        frame_vol_ref.columnconfigure(0, weight=0)
        frame_vol_ref.columnconfigure(1, weight=1)
        frame_vol_ref.rowconfigure(0, weight=0)
        frame_vol_ref.rowconfigure(1, weight=1)

        def sync_yview(*args):
            self.vol_tree_id.yview(*args)
            self.vol_tree_name.yview(*args)

        self.header_id = ttk.Label(frame_vol_ref, text="编号", relief="flat", anchor="center", font=("Microsoft YaHei", 9, "bold"), background="#E1E1E1")
        self.header_name = ttk.Label(frame_vol_ref, text="分卷名称", relief="flat", anchor="center", font=("Microsoft YaHei", 9, "bold"), background="#E1E1E1")
        self.header_id.grid(row=0, column=0, sticky="nsew")
        self.header_name.grid(row=0, column=1, sticky="nsew")

        self.vol_tree_id = ttk.Treeview(frame_vol_ref, columns=("id"), show="", selectmode="browse", height=1)
        self.vol_tree_id.column("#0", width=0, stretch=False)
        self.vol_tree_id.column("id", width=50, minwidth=50, stretch=False, anchor="center")

        def handle_id_click(event):
            if self.vol_tree_id.identify_region(event.x, event.y) == "separator": return "break"
        self.vol_tree_id.bind("<Button-1>", handle_id_click)
        self.vol_tree_id.bind("<B1-Motion>", handle_id_click)

        self.vol_tree_name = ttk.Treeview(frame_vol_ref, columns=("name"), show="", selectmode="browse", height=1)
        self.vol_tree_name.column("name", width=160, minwidth=100, stretch=True, anchor="w")

        vol_v_scroll = ttk.Scrollbar(frame_vol_ref, orient="vertical", command=sync_yview)
        vol_h_scroll = ttk.Scrollbar(frame_vol_ref, orient="horizontal", command=self.vol_tree_name.xview)

        def set_vol_v_sb(first, last):
            f, l = float(first), float(last)
            if (f <= 0.0 and l >= 0.999) or f == l: vol_v_scroll.grid_remove()
            else: vol_v_scroll.grid(row=1, column=2, sticky="ns")
            vol_v_scroll.set(first, last)

        def set_vol_h_sb(first, last):
            f, l = float(first), float(last)
            if (f <= 0.0 and l >= 0.999) or f == l: vol_h_scroll.grid_remove()
            else: vol_h_scroll.grid(row=2, column=1, sticky="ew")
            vol_h_scroll.set(first, last)

        self.vol_tree_id.config(yscrollcommand=set_vol_v_sb)
        self.vol_tree_name.config(yscrollcommand=set_vol_v_sb, xscrollcommand=set_vol_h_sb)

        def on_tree_mousewheel(event):
            delta = int(-1*(event.delta/120))
            self.vol_tree_id.yview_scroll(delta, "units")
            self.vol_tree_name.yview_scroll(delta, "units")
            return "break"

        self.vol_tree_id.bind("<MouseWheel>", on_tree_mousewheel)
        self.vol_tree_name.bind("<MouseWheel>", on_tree_mousewheel)
        self.vol_tree_id.grid(row=1, column=0, sticky="ns")
        self.vol_tree_name.grid(row=1, column=1, sticky="nsew")

        # 5. 日志视窗
        frame_log = ttk.LabelFrame(bottom_container, text="执行日志")
        bottom_container.add(frame_log, weight=6)
        frame_log.columnconfigure(0, weight=1)
        frame_log.rowconfigure(0, weight=1)

        log_v_scroll = ttk.Scrollbar(frame_log, orient="vertical")
        log_h_scroll = ttk.Scrollbar(frame_log, orient="horizontal")

        self.log_text = tk.Text(frame_log, state="disabled", font=("Consolas", 9), wrap="none", width=40)

        def set_log_sb(first, last, sb, orient):
            f, l = float(first), float(last)
            if (f <= 0.0 and l >= 0.999) or f == l: sb.grid_remove()
            else: sb.grid()
            sb.set(first, last)

        self.log_text.config(yscrollcommand=lambda f, l: set_log_sb(f, l, log_v_scroll, "v"), xscrollcommand=lambda f, l: set_log_sb(f, l, log_h_scroll, "h"))
        log_v_scroll.config(command=self.log_text.yview)
        log_h_scroll.config(command=self.log_text.xview)

        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_v_scroll.grid(row=0, column=1, sticky="ns")
        log_h_scroll.grid(row=1, column=0, sticky="ew")

        self.log_text.tag_config("INFO", foreground="black")
        self.log_text.tag_config("WARNING", foreground="#D2691E")
        self.log_text.tag_config("ERROR", foreground="red")

    def setup_logging(self):
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        if logger.hasHandlers():
            logger.handlers.clear()

        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

        # GUI 显示的 Log
        gui_handler = LogHandler(self.log_text)
        gui_handler.setFormatter(formatter)
        logger.addHandler(gui_handler)

        # 写入档案的 Log
        log_dir = get_base_path() / 'log'
        log_dir.mkdir(exist_ok=True)
        file_handler = logging.FileHandler(log_dir / 'app_runtime.log', encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    def open_url(self):
        url_input = self.url_var.get().strip()
        if not url_input or url_input == self.placeholder:
            messagebox.showwarning("警告", "请先输入网址 or ID！")
            return
        url = normalize_novel_url(url_input) if url_input.isdigit() or VALID_URL_PATTERN.fullmatch(url_input) else url_input
        try:
            webbrowser.open(url)
        except Exception as e:
            messagebox.showerror("错误", f"无法开启网址:\n{e}")

    def on_vol_mode_change(self):
        if self.vol_mode_var.get() == "all":
            self.vol_entry.config(state="disabled")
            self.vol_specific_var.set("")
        else:
            self.vol_entry.config(state="normal")
            self.vol_entry.focus()

    def set_app_state(self, state: AppState):
        self.app_state = state
        if state == AppState.IDLE:
            self.check_btn.config(state="normal", text="检查并载入资讯")
            self.start_btn.config(state="normal", text="开始下载", command=self.start_process)
            self.progress_canvas.pack_forget()
        elif state == AppState.CHECKING:
            self.check_btn.config(state="disabled", text="检查中...")
            self.status_label.config(text="正在获取小说资讯...", foreground="orange")
        elif state == AppState.DOWNLOADING:
            self._pg_reset()
            self.check_btn.config(state="disabled")
            self.start_btn.config(text="取消下载", command=self.cancel_download)
            self.progress_canvas.pack(pady=(2, 0))
            self.progress_canvas.coords(self.progress_rect, -100, 0, 0, 14)
            self._animate_progress_bar()

    def _animate_progress_bar(self):
        """进度条：有真实章节进度时显示填充，否则退回原滑动动画"""
        if self.app_state != AppState.DOWNLOADING:
            return
        coords = self.progress_canvas.coords(self.progress_rect)
        if not coords:
            return

        frac = self._real_progress_fraction()
        if frac is not None:
            # 真实进度：从左端填到对应比例
            self.progress_canvas.coords(self.progress_rect, 0, 0, frac * 500, 14)
            # 进度数字与进度条同一轮更新，避免数字比进度条慢
            if not self._pg_complete:
                text = self._build_progress_text(self._pg_elapsed_str)
                if text != self._pg_last_label:
                    self._pg_last_label = text
                    self.progress_var.set(text)
        else:
            # fallback：尚无可用进度标记时维持滑动动画
            x1, y1, x2, y2 = coords
            step, width = 6, 100
            x1 += step
            x2 += step
            if x1 > 500:
                x1, x2 = -width, 0
            self.progress_canvas.coords(self.progress_rect, x1, y1, x2, y2)

        self.after(20, self._animate_progress_bar)

    def _pg_reset(self):
        """重置真实进度追踪状态（每次下载开始时呼叫）"""
        self._pg_vols = None              # 卷名清单，来自 packer 的 PackArgument
        self._pg_total = []               # 每卷总章数（该卷列目录的 ==> 行数）
        self._pg_fetch = []               # 每卷已抓取的章节页数（GET {url} OK）
        self._pg_res = []                 # 每卷已解析／打包完成的章数（OK 书名 行）
        self._pg_cur = -1                 # 目前显示的卷索引（0 起算，尚未开始为 -1）
        self._pg_url_vol = {}             # 章节网址 → 卷索引，列目录时建立
        self._pg_fetched_urls = set()     # 已计入抓取的章节网址，避免重试重复计数
        self._pg_active = False           # 是否已有抓取／解析活动，决定显示真实进度或动画
        self._pg_complete = False         # 下载器成功结束，进度补满 100%
        self._pg_frac_hi = 0.0            # 已显示过的最高比例，用来钳制成只进不退
        self._pg_elapsed_str = "00:00"    # 由监看执行绪每秒更新，供进度标签显示耗时
        self._pg_last_label = None        # 已显示的标签文字，避免重复 set

    def _match_vol(self, body: str) -> int:
        """判断这行章节属于哪一卷，取最长相符的卷名以避免前缀撞名，找不到回 -1"""
        best, best_len = -1, -1
        for k, name in enumerate(self._pg_vols):
            if body.startswith(name) and len(name) > best_len:
                best, best_len = k, len(name)
        return best

    def _update_progress_from_line(self, raw_line: str):
        """从下载器 log 逐行解析进度讯号（在 tail 执行绪呼叫）

        下载一章要经两阶段：先「抓页面」(`GET {url} OK`)、再「解析＋图片＋打包」(`OK 书名`)
        列目录的 ==> 行同时带卷名与章节网址，用来建「网址→卷索引」表并累计总章数
        抓页面与解析各算半步，进度条到满代表两阶段都完成，避免页抓完就满进度条还在跑
        0.2.43 两阶段交错、0.2.44 先抓完再解析，皆适用
        """
        content = raw_line.lstrip('│ \t')
        if self._pg_vols is None:
            if content.startswith('PackArgument'):
                m = re.search(r'packVolumes:\s*\[(.*)\]', content)
                if m and m.group(1).strip():
                    vols = [v.strip() for v in m.group(1).split(', ') if v.strip()]
                    if vols:
                        self._pg_vols = vols
                        self._pg_total = [0] * len(vols)
                        self._pg_fetch = [0] * len(vols)
                        self._pg_res = [0] * len(vols)
            return
        if content.startswith('==> '):
            body = content[4:]
            k = self._match_vol(body)
            if k >= 0:
                self._pg_total[k] += 1
                self._pg_url_vol[body.rsplit(' ', 1)[-1]] = k  # 最后一个 token 是章节网址
        elif content.startswith('GET ') and content.endswith(' OK'):
            parts = content.split(' ')
            if len(parts) >= 2:
                url = parts[1]
                k = self._pg_url_vol.get(url)  # 只认章节页网址，图片等其他 GET 不在表中
                if k is not None and url not in self._pg_fetched_urls and self._pg_fetch[k] < self._pg_total[k]:
                    self._pg_fetched_urls.add(url)
                    self._pg_fetch[k] += 1
                    self._pg_cur = k
                    self._pg_active = True
        elif content.startswith('OK '):
            k = self._match_vol(content[3:])
            if k >= 0 and self._pg_res[k] < self._pg_total[k]:
                self._pg_res[k] += 1
                self._pg_cur = k
                self._pg_active = True

    def _real_progress_fraction(self):
        """回传整体进度比例 0.0~1.0；尚无可用资料时回 None（改用滑动动画）"""
        if self._pg_complete:
            return 1.0
        if not self._pg_active or not self._pg_vols or self._pg_cur < 0:
            return None
        # 每卷各占 1/N，卷内以（已抓页 + 已解析）/（2×总章）填充，两阶段各半步
        n = len(self._pg_vols)
        acc = 0.0
        for k in range(n):
            t = self._pg_total[k]
            if t > 0:
                acc += min((self._pg_fetch[k] + self._pg_res[k]) / (2 * t), 1.0)
        overall = min(max(acc / n, 0.0), 1.0)
        # 单调钳制：只前进不后退
        if overall < self._pg_frac_hi:
            overall = self._pg_frac_hi
        else:
            self._pg_frac_hi = overall
        return overall

    def _build_progress_text(self, time_str: str) -> str:
        """组合进度标签文字；显示章数由半步进度换算，与进度条同步"""
        if not self._pg_active or not self._pg_vols or self._pg_cur < 0:
            return f"状态: 下载中...   (已耗时 {time_str})  "
        k = self._pg_cur
        total = self._pg_total[k]
        if total <= 0:
            return f"状态: 下载中...   (已耗时 {time_str})  "
        done = min(int((self._pg_fetch[k] + self._pg_res[k]) / 2), total)
        if len(self._pg_vols) > 1:
            core = f"第 {k + 1}/{len(self._pg_vols)} 卷 · 本卷 {done}/{total} 章"
        else:
            core = f"{done}/{total} 章"
        return f"下载中… {core} · 已耗时 {time_str}"

    def reset_info_labels(self):
        self._set_info_field(self.title_text, "书名：尚未载入")
        self._set_info_field(self.author_text, "-")
        self._set_info_field(self.meta_text, "-")
        self._set_info_field(self.update_text, "-")
        self._set_desc("-")

        for item in self.vol_tree_id.get_children(): self.vol_tree_id.delete(item)
        for item in self.vol_tree_name.get_children(): self.vol_tree_name.delete(item)

        self.cover_label.config(image='', text="正在载入封面...", width=28, height=14)
        self.cover_label.image = None

    def check_novel_info(self, event=None, auto_start=False):
        if self.app_state == AppState.CHECKING:
            messagebox.showinfo("提示", "正在获取小说资讯中，请稍候...")
            return
        if self.app_state == AppState.DOWNLOADING:
            return

        url_input = self.url_var.get().strip()
        if not url_input or url_input == self.placeholder:
            messagebox.showwarning("警告", "请输入小说网址或数字 ID！")
            return

        url = normalize_novel_url(url_input) if url_input.isdigit() or VALID_URL_PATTERN.fullmatch(url_input) else url_input

        if not url_input.isdigit() and not VALID_URL_PATTERN.match(url_input):
            messagebox.showwarning(
                "网址格式错误",
                "请输入有效的哔哩轻小说网址或纯数字 ID。\n\n"
                "有效格式范例：\n"
                "  · https://www.bilinovel.com/novel/2.html\n"
                "  · 2"
            )
            return

        self.url_var.set(url)
        self.entry_url.icursor("end")
        self.entry_url.xview_moveto(1.0)
        self.entry_url.configure(foreground="black")

        if self.app_state != AppState.IDLE: return

        self.set_app_state(AppState.CHECKING)
        self.reset_info_labels()
        self._set_info_field(self.title_text, "书名：载入中...")

        thread = threading.Thread(target=self._thread_fetch_info, args=(url, auto_start), daemon=True)
        thread.start()

    def _thread_fetch_info(self, url: str, auto_start: bool):
        try:
            info = self.scraper.fetch_info(url)
            self.after(0, lambda: self._apply_info_to_ui(info))
            self.last_checked_url = url

            # 抓取封面
            if info.cover_url:
                try:
                    cover_img = self.scraper.download_cover(info.cover_url)
                    if cover_img:
                        photo = ImageTk.PhotoImage(cover_img)
                        self.after(0, lambda p=photo: self._apply_cover_to_ui(p))
                    else:
                        self.after(0, lambda: self.status_label.config(text="找不到封面图片", foreground="orange"))
                except Exception as e:
                    self.after(0, lambda err=e: self.status_label.config(text=f"封面下载失败: {err}", foreground="orange"))

            # 抓取目录
            try:
                vols = self.scraper.fetch_catalog(url)
                if vols:
                    self.after(0, lambda v=vols: self._apply_catalog_to_ui(v))
                    self.after(0, lambda: self.status_label.config(text="小说资讯与目录载入成功", foreground="green"))
                else:
                    self.after(0, lambda: self.status_label.config(text="资讯载入成功 (但找不到目录)", foreground="orange"))
            except Exception as e:
                self.after(0, lambda err=e: self.status_label.config(text=f"载入完成 (目录抓取失败: {err})", foreground="orange"))

            if auto_start:
                self.after(500, self.start_process)

        except Exception as e:
            self.after(0, lambda err=e: self._handle_fetch_error(err))
        finally:
            self.after(0, self._reset_state_after_check)

    def _reset_state_after_check(self):
        if self.app_state == AppState.CHECKING:
            self.set_app_state(AppState.IDLE)

    def _apply_info_to_ui(self, info: NovelInfo):
        self._set_info_field(self.title_text, f"书名：{info.title}")
        self._set_info_field(self.author_text, f"作者：{info.author}")
        self._set_info_field(self.meta_text, f"{info.status} | {info.tags} | {info.rating}")
        self._set_info_field(self.update_text, f"最新进度：{info.latest} (更新时间：{info.update_time})")

        # 修正微软正黑体会将 em-dash (— 或 ―) 显示为上横线的字体渲染 Bug
        # 改用制表符 (Box Drawing Light Horizontal U+2500) 让线条相连
        display_desc = info.desc.replace('—', '─').replace('―', '─')
        self._set_desc(display_desc)

        self._save_to_history(info.url, info.title)

    def _apply_cover_to_ui(self, photo):
        self.cover_label.config(image=photo, text="", width=200, height=280)
        self.cover_label.image = photo

    def _apply_catalog_to_ui(self, vols: List[Tuple[str, str]]):
        for item in self.vol_tree_id.get_children(): self.vol_tree_id.delete(item)
        for item in self.vol_tree_name.get_children(): self.vol_tree_name.delete(item)

        f = tkfont.Font(family="Microsoft YaHei", size=9)
        max_w = 330
        for v_id, v_name in vols:
            w = f.measure(v_name)
            if w > max_w: max_w = w

        self.vol_tree_name.column("name", width=(max_w + 20 if max_w > 330 else 330), stretch=(max_w <= 330))
        for v_id, v_name in vols:
            self.vol_tree_id.insert("", "end", values=(v_id,))
            self.vol_tree_name.insert("", "end", values=(v_name,))

    def _handle_fetch_error(self, error: Exception):
        self.reset_info_labels()
        self._set_info_field(self.title_text, "书名：载入失败")
        self.status_label.config(text=str(error), foreground="red")
        self.cover_label.config(image='', text="[ 图片载入失败 ]", width=28, height=14)

    def cancel_download(self):
        if messagebox.askyesno("取消确认", "确定要终止目前的下载与转换程序吗？"):
            self.cancel_event.set()
            logging.warning("使用者触发取消程序...")
            if self.current_process:
                try:
                    self.current_process.kill()
                    logging.info("已终止下载器进程。")
                except Exception as e:
                    logging.error(f"终止进程时发生错误: {e}")
            self.start_btn.config(state="disabled", text="正在取消...")

    def start_process(self):
        if self.app_state == AppState.CHECKING:
            messagebox.showinfo("提示", "正在获取小说资讯中，请稍候再点击下载。")
            return

        url_input = self.url_var.get().strip()
        if not url_input or url_input == self.placeholder:
            messagebox.showwarning("警告", "请输入小说网址或数字 ID！")
            return

        url = normalize_novel_url(url_input) if url_input.isdigit() or VALID_URL_PATTERN.fullmatch(url_input) else url_input

        if not url_input.isdigit() and not VALID_URL_PATTERN.match(url_input):
            messagebox.showwarning(
                "网址格式错误",
                "请输入有效的哔哩轻小说网址或纯数字 ID。\n\n"
                "有效格式范例：\n"
                "  · https://www.bilinovel.com/novel/2.html\n"
                "  · 2"
            )
            return

        self.url_var.set(url)
        self.entry_url.icursor("end")
        self.entry_url.xview_moveto(1.0)
        self.entry_url.configure(foreground="black")

        if not self.last_checked_url:
            logging.info("尚未载入资讯，自动执行资讯检查并下载...")
            self.check_novel_info(auto_start=True)
            return

        if self.last_checked_url != url:
            if not messagebox.askyesno("提示", "侦测到输入网址与目前预览资讯不符。\n\n建议先点击『检查并载入资讯』以确认小说内容。\n是否仍要直接开始下载？"):
                return
            logging.info("使用者选择直接下载，同步更新预览资讯...")
            self.check_novel_info(auto_start=False)

        o1 = '0' if self.vol_mode_var.get() == "all" else self.vol_specific_var.get().strip()
        if self.vol_mode_var.get() != "all" and not o1:
            messagebox.showwarning("警告", "您勾选了指定范围，请输入范围数字！")
            return

        try:
            parse_volumes(o1)
        except ValueError as e:
            messagebox.showwarning("分卷设置", str(e))
            return
        o2 = '1' if self.merge_var.get() else '2'
        o3 = '1' if self.title_var.get() else '2'

        self.set_app_state(AppState.DOWNLOADING)
        self.cancel_event.clear()

        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

        threading.Thread(target=self._thread_run_main_logic, args=(url, o1, o2, o3), daemon=True).start()

    def _thread_run_main_logic(self, url, o1, o2, o3):
        start_time = time.time()
        self._abort_reason = None
        try:
            summary = self._main_logic(url, o1, o2, o3)
            elapsed = int(time.time() - start_time)
            mins, secs = divmod(elapsed, 60)

            if self.cancel_event.is_set():
                self.after(0, lambda: self.progress_var.set("状态: 程序已由使用者取消"))
                self.after(0, lambda: messagebox.showwarning("已取消", "程序已终止。"))
            elif self._abort_reason == "stall":
                self.after(0, lambda: self.progress_var.set("状态: 下载停滞，已终止"))
                self.after(0, lambda: messagebox.showwarning("下载停滞",
                    f"下载已停滞（{STALL_TIMEOUT_SECONDS // 60} 分钟无回应），可能是网路中断或伺服器无回应。\n\n请检查网路后再试一次。"))
            elif self._abort_reason == "timeout":
                self.after(0, lambda: self.progress_var.set("状态: 下载超时，已终止"))
                self.after(0, lambda: messagebox.showwarning("下载超时",
                    f"下载超过 {DOWNLOAD_TIMEOUT_SECONDS // 3600} 小时上限，已强制终止。"))
            elif self._abort_reason == "network":
                self.after(0, lambda: self.progress_var.set("状态: 无法连线到伺服器"))
                self.after(0, lambda: messagebox.showerror("网路连线失败",
                    "无法连线到下载伺服器 www.bilinovel.com，下载已中止。\n\n"
                    "可能是你的网路或 DNS 连不到这个网域。可以尝试改公用 DNS 或开 VPN 后再试。\n\n"
                    "详细纪录见 log 资料夹。"))
            elif self._abort_reason == "error":
                self.after(0, lambda: self.progress_var.set("状态: 下载器异常结束"))
                self.after(0, lambda: messagebox.showerror("下载失败",
                    "下载器异常结束，请稍后再试。\n\n若持续发生，可查看 log 资料夹的纪录。"))
            else:
                self.after(0, lambda: self.progress_var.set("状态: 下载完成"))
                epub_info = f"共 {summary['epub_count']} 个 EPUB 档案" if summary and summary.get('epub_count') else "请查阅下载资料夹"
                time_info = f"{mins} 分 {secs} 秒" if mins > 0 else f"{secs} 秒"
                folder_name = summary.get('folder_name', '未知') if summary else '未知'
                self.after(0, lambda: messagebox.showinfo(
                    "完成",
                    f"小说下载与转换程序已全部完成！\n\n"
                    f"书名：{folder_name}\n"
                    f"结果：{epub_info}\n"
                    f"耗时：{time_info}"
                ))
        except Exception as e:
            if not self.cancel_event.is_set():
                logging.error(f"发生错误: {e}", exc_info=True)
                self.after(0, lambda: self.progress_var.set("状态: 发生错误"))
                title, msg = classify_error(e)
                self.after(0, lambda t=title, m=msg: messagebox.showerror(t, m))
        finally:
            self.current_process = None
            self.after(0, lambda: self.set_app_state(AppState.IDLE))

    def _run_downloader_process(self, exe_path: Path, url: str, o1: str, o2: str, o3: str, cwd: str) -> bool:
        try:
            settings = load_settings()
            job = {'url': normalize_novel_url(url), 'volumes': parse_volumes(o1),
                   'merge': o2 == '1', 'add_titles': o3 == '1',
                   'proxy': settings['proxy_url'] if settings['proxy_enabled'] else None}
            logging.info("正在启动单次下载任务（%s）", job['proxy'] or '直连')
            def started(process):
                self.current_process = process
            def line(text):
                self.last_activity_time = time.time()
                self._update_progress_from_line(text)
                logging.info("[下载器] %s", text)
            def tick(elapsed):
                mins, secs = divmod(elapsed, 60)
                self._pg_elapsed_str = f"{mins:02d}:{secs:02d}"
                self.after(0, lambda t=self._pg_elapsed_str: self.progress_var.set(f"状态: 下载中…（耗时 {t}）"))
            run_job([str(exe_path)], cwd, job, self.cancel_event, started, line, tick,
                    STALL_TIMEOUT_SECONDS, DOWNLOAD_TIMEOUT_SECONDS)
            self._pg_complete = True
            logging.info("核心正常退出，EPUB 检查通过，开始简繁转换。")
            return True
        except DownloadError as e:
            self._abort_reason = e.reason
            logging.error("%s", e)
            return False
        except Exception as e:
            self._abort_reason = 'error'
            logging.exception("下载失败：%s", e)
            return False
        finally:
            self.current_process = None

    def _main_logic(self, url, o1, o2, o3):
        base = get_base_path()
        exe = find_downloader_exe(base)
        if not exe:
            raise FileNotFoundError("找不到配套 gui 下载核心，请保留 tools 文件夹。")
        temp_root = base / 'temp'
        temp_root.mkdir(exist_ok=True)
        task = Path(tempfile.mkdtemp(prefix='job-', dir=temp_root))
        # Keep successful and failed sources; never erase earlier downloads.
        logging.info("本次任务目录：%s", task)
        if not self._run_downloader_process(exe, url, o1, o2, o3, str(task)):
            return {}
        if self.cancel_event.is_set():
            return {}
        folders = [p for p in task.iterdir() if p.is_dir() and list(p.glob('*.epub'))]
        total = 0
        for folder in folders:
            total += process_downloaded_folder(folder, base)
        if not total:
            raise RuntimeError("没有生成有效的 EPUB。")
        return {'epub_count': total, 'folder_name': '、'.join(T2S_CONVERTER.convert(p.name) for p in folders)}
