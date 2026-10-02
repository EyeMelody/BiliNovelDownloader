import io
import re
import html
import time
import logging
from typing import Optional, List, Tuple
from dataclasses import dataclass, field

import requests
from bs4 import BeautifulSoup
from PIL import Image

from core import USER_AGENT, get_base_path
from epub_tools import T2S_CONVERTER
from network import request_get
from core import normalize_novel_url


# 下载器 log 出现这些字串时，视为网路／DNS 连线失败
PACKER_NETWORK_MARKERS = (
    "Failed host lookup",   # DNS 解析不到网域
    "SocketException",      # 连线层失败，含 DNS、逾时、被拒
    "ClientException",      # Dart http 连线异常
    "HandshakeException",   # TLS 交握失败，常见于连线被中间阻断
)


def packer_log_is_network_error(log_text: str) -> bool:
    """判断下载器 log 是否为网路／DNS 连线失败。"""
    return any(marker in log_text for marker in PACKER_NETWORK_MARKERS)


def classify_error(e: Exception) -> tuple[str, str]:
    """回传 (错误标题, 使用者友善讯息)"""
    import requests as req_module

    if isinstance(e, FileNotFoundError):
        return ("找不到下载器",
                "在 tools 资料夹中找不到 bili_novel_packer 执行档。\n\n"
                "请确认 tools 资料夹与主程式在同一层目录，并且包含下载器 .exe 档案。")

    if isinstance(e, req_module.ConnectionError):
        return ("网路连线失败",
                "无法连接至哔哩轻小说伺服器。\n\n请确认网路连线是否正常。")

    if isinstance(e, req_module.Timeout):
        return ("连线逾时",
                "伺服器回应超时，可能是网路不稳定或伺服器忙碌。\n\n请稍后再试。")

    msg = str(e)
    if "404" in msg or "找不到" in msg:
        return ("小说不存在",
                "找不到对应的小说页面。\n\n请确认输入的网址或 ID 是否正确。")

    if "未侦测到下载档案" in msg or "下载失败" in msg:
        return ("下载失败",
                f"{msg}\n\n请查阅程式目录下 log 资料夹内的日志档案以取得详细资讯。")

    return ("发生未预期错误", f"错误讯息：{msg}\n\n请截图此讯息并回报给开发者。")

@dataclass
class NovelInfo:
    url: str
    title: str = "未知书名"
    cover_url: Optional[str] = None
    author: str = "未知"
    status: str = "未知"
    tags: str = "未知"
    latest: str = "未知"
    update_time: str = "未知"
    desc: str = "无简介"
    rating: str = "未知"
    volumes: List[Tuple[str, str]] = field(default_factory=list)

class NovelScraper:
    def __init__(self):
        self.headers = {'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36', 'Referer': 'https://www.bilinovel.com/', 'Cookie': 'night=0'}

    def fetch_info(self, url: str) -> NovelInfo:
        url = normalize_novel_url(url)
        res = request_get(url, headers=self.headers, timeout=60)
        if res.status_code == 403:
            raise Exception("被网站防火墙阻挡 (HTTP 403)，请确认网址或稍后再试。")
        elif res.status_code != 200:
            raise Exception(f"无法存取网页 (HTTP {res.status_code})")

        res.encoding = 'utf-8'
        try:
            import lxml
            parser = 'lxml'
        except ImportError:
            parser = 'html.parser'
        soup = BeautifulSoup(res.text, parser)
        info = NovelInfo(url=url)

        # 标题
        meta_title = soup.find("meta", property="og:title")
        if meta_title:
            info.title = meta_title.get("content", "未知书名")
        else:
            title_div = soup.select_one(".book-title, #title")
            if title_div:
                info.title = title_div.get_text(strip=True)

        # 手机站不总是提供 OpenGraph 元数据。
        mobile_author = soup.select_one('.book-rand-a span')
        if mobile_author: info.author = mobile_author.get_text(strip=True)
        mobile_cover = soup.select_one('.book-layout img')
        if mobile_cover: info.cover_url = mobile_cover.get('data-src') or mobile_cover.get('src')

        # 评价
        score_div = soup.find("div", class_="score-num")
        if score_div:
            rating_text = score_div.get_text(strip=True)
            info.rating = f"{rating_text} 分"
            count_p = soup.find("p", class_="done-count")
            if count_p and count_p.find("em"):
                info.rating += f" ({count_p.find('em').get_text(strip=True)})"

        # 作者
        meta_author = soup.find("meta", property="og:novel:author")
        if meta_author: info.author = meta_author.get("content", "未知")

        # 状态与分类
        meta_status = soup.find("meta", property="og:novel:status")
        if meta_status: info.status = meta_status.get("content", "未知")
        meta_category = soup.find("meta", property="og:novel:category")
        if meta_category: info.tags = meta_category.get("content", "未知")

        # 最新章节与时间
        meta_latest = soup.find("meta", property="og:novel:latest_chapter_name")
        if meta_latest: info.latest = meta_latest.get("content", "未知")
        meta_update = soup.find("meta", property="og:novel:update_time")
        if meta_update:
            info.update_time = meta_update.get("content", "未知")
        else:
            update_div = soup.find("div", class_="book-meta-l")
            if update_div:
                m_update2 = re.search(r'(\d{4}-\d{2}-\d{2})', update_div.get_text())
                if m_update2: info.update_time = m_update2.group(1)

        # 简介
        info.desc = self._extract_description(soup, url)

        # 封面
        meta_image = soup.find("meta", property="og:image")
        if meta_image:
            info.cover_url = meta_image.get("content")
        else:
            img_tag = soup.find("img", border="0")
            if img_tag and img_tag.get("src"):
                info.cover_url = img_tag.get("src")

        if info.cover_url and not info.cover_url.startswith("http"):
            domain = "https://www.bilinovel.com/"
            info.cover_url = f"{domain}{info.cover_url.lstrip('/')}"

        self._convert_info_to_tw(info)
        return info

    def _extract_description(self, soup: BeautifulSoup, url: str) -> str:
        desc = "无简介"
        summary_tag = soup.select_one('#bookSummary, .book-summary')
        if summary_tag:
            content_tag = summary_tag.find("content") or summary_tag.find(class_="notice-body")
            desc = content_tag.get_text(separator=" ", strip=True) if content_tag else summary_tag.get_text(separator=" ", strip=True)

        if desc == "无简介" or len(desc) < 10:
            intro_tag = soup.find(class_="book-intro")
            if intro_tag:
                desc = intro_tag.get_text(strip=True)
            else:
                meta_desc = soup.find("meta", property="og:description")
                if meta_desc:
                    desc = meta_desc.get("content", "无简介")

        desc = re.sub(r'^(简介|内容简介|内容简介)[：:]\s*', '', desc)
        desc = re.sub(r'\s+', ' ', desc).strip()
        if len(desc) > 1000:
            desc = desc[:997] + "..."
        return desc

    def _convert_info_to_tw(self, info: NovelInfo):
        info.title = html.unescape(T2S_CONVERTER.convert(info.title))
        info.author = html.unescape(T2S_CONVERTER.convert(info.author))

        status_tw = T2S_CONVERTER.convert(info.status)
        info.status = "连载中" if status_tw == "连载" else ("已完结" if status_tw == "完结" else status_tw)
        info.tags = T2S_CONVERTER.convert(info.tags)
        info.latest = html.unescape(T2S_CONVERTER.convert(info.latest))
        info.desc = html.unescape(T2S_CONVERTER.convert(info.desc))

    def fetch_catalog(self, url: str) -> List[Tuple[str, str]]:
        cat_url = normalize_novel_url(url).replace('.html', '/catalog')
        res = request_get(cat_url, headers=self.headers, timeout=60)
        vols = []
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, 'html.parser')
            vol_tags = soup.select('.chapter-bar')
            for i, v in enumerate(vol_tags, 1):
                v_name = v.get_text(strip=True)
                vols.append((str(i), T2S_CONVERTER.convert(v_name)))
        return vols

    def download_cover(self, cover_url: str) -> Optional['Image.Image']:
        if not cover_url: return None
        import hashlib

        cache_dir = get_base_path() / 'temp' / 'covers'
        cache_dir.mkdir(parents=True, exist_ok=True)

        url_hash = hashlib.md5(cover_url.encode('utf-8')).hexdigest()
        cache_path = cache_dir / f"{url_hash}.jpg"

        # 检查快取是否存在且未过期 (24小时)
        if cache_path.exists():
            if time.time() - cache_path.stat().st_mtime < 86400:
                try:
                    img = Image.open(cache_path).copy()
                    img.thumbnail((200, 280), Image.LANCZOS)
                    return img
                except Exception:
                    cache_path.unlink(missing_ok=True)
            else:
                cache_path.unlink(missing_ok=True)

        # 快取未命中或已过期：下载并存入快取
        try:
            res = request_get(cover_url, headers=self.headers, timeout=15)
            if res.status_code == 200:
                img = Image.open(io.BytesIO(res.content))
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                img.save(cache_path, 'JPEG', quality=85)
                img.thumbnail((200, 280), Image.LANCZOS)
                return img
        except Exception as e:
            logging.warning(f"封面下载失败: {e}")
        return None