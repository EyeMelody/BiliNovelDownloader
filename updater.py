import re
import time
import xml.etree.ElementTree as ET
from urllib.parse import unquote
from typing import Optional

import requests
from network import request_get

from core import USER_AGENT

APP_REPO = 'EyeMelody/BiliNovelDownloader'
PACKER_REPO = 'Montaro2017/bili_novel_packer'
_release_cache = {}

_PACKER_VERSION_PATTERN = re.compile(r'bili_novel_packer-(\d+(?:\.\d+)+)', re.IGNORECASE)


def parse_version(text) -> Optional[tuple]:
    """把 'v1.4.0' 这类版号字串转成数字 tuple，解析失败回 None"""
    if not text:
        return None
    m = re.fullmatch(r'v?(\d+(?:\.\d+)*)', text.strip(), re.IGNORECASE)
    if not m:
        return None
    return tuple(int(p) for p in m.group(1).split('.'))


def is_newer(remote: Optional[str], local: Optional[str]) -> bool:
    """远端版号是否比本地新，任一边解析不出一律视为否"""
    r, l = parse_version(remote), parse_version(local)
    if r is None or l is None:
        return False
    n = max(len(r), len(l))
    return r + (0,) * (n - len(r)) > l + (0,) * (n - len(l))


def get_local_packer_version(exe_path) -> Optional[str]:
    """从下载器 exe 档名解析版号"""
    if not exe_path:
        return None
    m = _PACKER_VERSION_PATTERN.search(exe_path.name)
    return m.group(1) if m else None


def check_target(repo: str, local: Optional[str]) -> dict:
    """查一个 repo 的最新 release 并与本地版本比对

    回传 dict：
      local   本地版号（可能为 None）
      latest  最新 release 的 tag（查询失败为 None）
      url     该 release 的页面网址
      status  'update' 有新版 / 'latest' 已是最新 / 'no_local' 本地版本无法判定
              / 'ratelimit' API 限额 / 'network' 其他网路或解析错误
    """
    cached = _release_cache.get(repo)
    if cached and time.monotonic() - cached[0] < 300:
        data = dict(cached[1])
    else:
        data = _fetch_release(repo)
        # 缓存成功结果；失败只缓存 30 秒，避免反复点击增加请求。
        ttl = 300 if data.get('latest') or data.get('status') == 'no_release' else 30
        _release_cache[repo] = (time.monotonic() - (300 - ttl), dict(data))
    result = dict(data, local=local)
    if not result.get('latest'):
        return result
    elif parse_version(local) is None:
        result['status'] = 'no_local'
    elif is_newer(result['latest'], local):
        result['status'] = 'update'
    else:
        result['status'] = 'latest'
    return result


def _fetch_release(repo):
    result = {'latest': None, 'url': f'https://github.com/{repo}/releases', 'status': 'network'}
    headers = {'User-Agent': USER_AGENT, 'Accept': 'application/vnd.github+json'}
    try:
        resp = request_get(f'https://api.github.com/repos/{repo}/releases/latest', headers=headers, timeout=10)
        listing = resp.status_code == 404
        if listing:
            resp = request_get(f'https://api.github.com/repos/{repo}/releases?per_page=10', headers=headers, timeout=10)
        if resp.status_code in (403, 429):
            limited = (resp.status_code == 429 or resp.headers.get('X-RateLimit-Remaining') == '0'
                       or resp.headers.get('Retry-After') is not None
                       or 'rate limit' in resp.text.lower())
            result['status'] = 'ratelimit' if limited else 'forbidden'
        else:
            resp.raise_for_status()
            data = next((x for x in resp.json() if not x.get('draft')), {}) if listing else resp.json()
            if not data:
                return dict(result, status='no_release')
            if data.get('tag_name'):
                return dict(result, latest=data['tag_name'], url=data.get('html_url') or result['url'])
    except (requests.RequestException, ValueError, TypeError, AttributeError):
        pass
    # 公开发布订阅不使用 REST API 配额；包含上游预发布版本。
    try:
        resp = request_get(f'https://github.com/{repo}/releases.atom', headers={'User-Agent': USER_AGENT}, timeout=10)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        ns = {'a': 'http://www.w3.org/2005/Atom'}
        if root.tag != '{http://www.w3.org/2005/Atom}feed':
            return result
        entries = root.findall('a:entry', ns)
        if not entries:
            return dict(result, status='no_release')
        prefix = f'https://github.com/{repo}/releases/tag/'
        for entry in entries:
            for link in entry.findall('a:link', ns):
                url = link.get('href', '')
                if url.lower().startswith(prefix.lower()):
                    return dict(result, latest=unquote(url[len(prefix):]), url=url, source='feed')
    except (requests.RequestException, ET.ParseError, ValueError):
        pass
    return result
