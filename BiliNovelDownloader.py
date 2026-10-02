import sys
import ctypes
import importlib
import tkinter as tk
from tkinter import messagebox

try:
    # 让 Windows 知道这个程式支援高解析度缩放，避免字体模糊
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    pass

# 启动前检查第三方套件，缺少时一次列出并友善退出
# lxml 为选用（fetch_info 已有 html.parser fallback）
def _check_dependencies():
    required = {
        'requests': 'requests', 'PIL': 'Pillow', 'psutil': 'psutil',
        'opencc': 'opencc', 'bs4': 'beautifulsoup4',
    }
    missing = []
    for mod, pkg in required.items():
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append(pkg)
    return missing

_missing_deps = _check_dependencies()
if _missing_deps:
    _root = tk.Tk()
    _root.withdraw()
    messagebox.showerror(
        "缺少必要套件",
        "无法启动，缺少以下套件：\n\n"
        + "\n".join(f"　• {p}" for p in _missing_deps)
        + "\n\n请在终端机安装后再开启：\npip install " + " ".join(_missing_deps)
    )
    sys.exit(1)

# 依赖齐备后才载入会汇入第三方套件的模组，确保上面的友善提示能先生效
from gui import Application, ensure_single_instance, _listen_for_reactivation

if __name__ == "__main__":
    if not ensure_single_instance():
        sys.exit(0)
    app = Application()
    _listen_for_reactivation(app)
    app.mainloop()