"""Shared explicit HTTP proxy settings; disabled means direct, not OS fallback."""
import json
from pathlib import Path
from urllib.parse import urlsplit

import requests
from core import get_base_path

DEFAULT_PROXY = 'http://127.0.0.1:7890'


def validate_proxy(value: str) -> str:
    value = value.strip()
    if '://' not in value:
        value = 'http://' + value
    try:
        url = urlsplit(value)
        port = url.port
    except ValueError as e:
        raise ValueError('代理端口必须是 1–65535 之间的数字。') from e
    if (url.scheme != 'http' or not url.hostname or port is None or port < 1
            or url.username is not None or url.password is not None
            or url.path not in ('', '/') or url.query or url.fragment
            or any(c.isspace() for c in value)):
        raise ValueError('请输入 HTTP/混合代理地址，例如 http://127.0.0.1:7890（暂不支持 SOCKS 和账号密码）。')
    host = f'[{url.hostname}]' if ':' in url.hostname else url.hostname
    return f'http://{host}:{port}'


def load_settings(path: Path = None) -> dict:
    path = path or get_base_path() / 'settings.json'
    defaults = {'proxy_enabled': False, 'proxy_url': DEFAULT_PROXY}
    if not path.exists():
        return defaults
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data.get('proxy_enabled', False), bool):
        raise ValueError('代理设置格式错误。')
    return {'proxy_enabled': data.get('proxy_enabled', False),
            'proxy_url': validate_proxy(data.get('proxy_url', DEFAULT_PROXY))}


def save_settings(settings: dict, path: Path = None):
    path = path or get_base_path() / 'settings.json'
    settings = {'proxy_enabled': bool(settings['proxy_enabled']),
                'proxy_url': validate_proxy(settings['proxy_url'])}
    path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding='utf-8')


def make_session(settings: dict = None) -> requests.Session:
    settings = load_settings() if settings is None else settings
    session = requests.Session()
    session.trust_env = False
    if settings['proxy_enabled']:
        proxy = validate_proxy(settings['proxy_url'])
        session.proxies = {'http': proxy, 'https': proxy}
    return session


def request_get(url: str, **kwargs):
    with make_session() as session:
        return session.get(url, **kwargs)
