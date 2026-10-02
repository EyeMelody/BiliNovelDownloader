import re
import sys
from pathlib import Path

# ================= 全域常数 =================
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
DIR_DOWNLOADS = 'downloads'
DIR_SIMP = '简体'
DIR_TRAD = '繁体'

VALID_URL_PATTERN = re.compile(
    r'^https?://(?:(?:www|tw|m)\.)?(?:linovelib\.com|bilinovel\.(?:com|net))/novel/\d+(?:\.html)?(?:/.*)?$'
)

DOWNLOAD_TIMEOUT_SECONDS = 21600  # 下载超时上限（秒），预设 6 小时
STALL_TIMEOUT_SECONDS = 900       # 停滞侦测：连续无 log 活动上限（秒），预设 15 分钟

# ================= 核心工具函式 =================

def get_resource_path(relative_path: str) -> Path:
    """获取资源档案的绝对路径"""
    if hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS) / relative_path
    return Path(__file__).resolve().parent / relative_path

def get_base_path() -> Path:
    """获取程式执行的根目录"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    else:
        return Path(__file__).resolve().parent

def _read_version() -> str:
    version_file = get_resource_path('version.txt')
    if version_file.exists():
        return version_file.read_text(encoding='utf-8-sig').strip()
    return 'v0.0.0-dev'

APP_VERSION = _read_version()

def sanitize_filename(name: str) -> str:
    """清理档案/资料夹名称中的不合法字元"""
    return re.sub(r'[\\/*?:"<>|]', "", name)

def normalize_novel_url(value: str) -> str:
    value = value.strip()
    if value.isdigit():
        ident = value
    elif VALID_URL_PATTERN.fullmatch(value):
        ident = re.search(r'/novel/(\d+)', value).group(1)
    else:
        raise ValueError('请输入哔哩轻小说网址或数字 ID。')
    return f'https://www.bilinovel.com/novel/{ident}.html'
