"""Non-interactive core protocol, bounded process lifetime and validated outputs."""
import json
import os
import queue
import re
import subprocess
import threading
import time
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

from network import validate_proxy


class DownloadError(RuntimeError):
    def __init__(self, message, reason='error'):
        super().__init__(message)
        self.reason = reason


def parse_volumes(text):
    if text.strip() == '0':
        return None
    if not re.fullmatch(r'\s*\d+(?:\s*-\s*\d+)?(?:\s*[,，]\s*\d+(?:\s*-\s*\d+)?)*\s*', text):
        raise ValueError('分卷范围格式错误，请输入 1 或 1,3-5。')
    result = set()
    for item in text.replace('，', ',').split(','):
        ends = [int(n.strip()) for n in item.split('-')]
        start, end = ends[0], ends[-1]
        if start < 1 or end < start or end > 10000:
            raise ValueError('分卷编号必须为正整数，且范围起点不能大于终点。')
        result.update(range(start, end + 1))
    return sorted(result)


def validate_epub(path):
    with zipfile.ZipFile(path) as z:
        if z.testzip() or z.read('mimetype') != b'application/epub+zip':
            raise DownloadError('EPUB 完整性检查失败。')
        root = ET.fromstring(z.read('META-INF/container.xml'))
        opf = root.find('.//{*}rootfile').get('full-path')
        package = ET.fromstring(z.read(opf))
        if not package.findall('.//{*}spine/{*}itemref'):
            raise DownloadError('EPUB 没有正文目录。')


def run_job(command, cwd, job, cancel, on_start=lambda p: None,
            on_line=lambda line: None, on_tick=lambda elapsed: None,
            stall_seconds=900, timeout_seconds=21600):
    cwd = Path(cwd)
    # Caller creates a fresh task directory; never accept a leftover EPUB as success.
    if list(cwd.rglob('*.epub')):
        raise DownloadError('任务目录必须为空，不能混入历史 EPUB。')
    if job.get('proxy'):
        job = dict(job, proxy=validate_proxy(job['proxy']))
    flags = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
    capability = subprocess.run([*command, '--capabilities'], capture_output=True,
                                timeout=10, encoding='utf-8', errors='replace', **flags)
    try:
        supports = json.loads(capability.stdout)
    except (ValueError, TypeError):
        supports = {}
    if capability.returncode or supports.get('protocol') != 1 or supports.get('http_proxy') is not True:
        raise DownloadError('下载核心不兼容，请使用本分支附带的 gui 核心。')
    job_path = cwd / 'job.json'
    job_path.write_text(json.dumps(job, ensure_ascii=False), encoding='utf-8')
    process = subprocess.Popen([*command, '--gui-job', str(job_path.resolve())],
                               cwd=cwd, stdin=subprocess.DEVNULL,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               encoding='utf-8', errors='replace', **flags)
    on_start(process)
    messages = queue.Queue()
    def consume():
        try:
            for line in process.stdout:
                messages.put(line.rstrip())
        finally:
            messages.put(None)
    reader = threading.Thread(target=consume, daemon=True)
    reader.start()
    started = activity = time.monotonic()
    log_offset = 0
    done = eof = False
    tail = []
    try:
        while True:
            now = time.monotonic()
            if cancel.is_set():
                raise DownloadError('下载已取消。', 'cancelled')
            if now - started > timeout_seconds:
                raise DownloadError('下载超过总时间上限。', 'timeout')
            try:
                while True:
                    line = messages.get_nowait()
                    if line is None:
                        eof = True
                    elif line == 'BILI_GUI_JOB_DONE':
                        done = True
                        activity = now
                    else:
                        activity = now
                        tail.append(line)
                        tail = tail[-20:]
                        on_line(line)
            except queue.Empty:
                pass
            log = cwd / 'bili_novel.log'
            if log.exists():
                with log.open('r', encoding='utf-8', errors='replace') as stream:
                    stream.seek(log_offset)
                    lines = stream.readlines()
                    log_offset = stream.tell()
                if lines:
                    activity = now
                    for line in lines:
                        if line.strip(): on_line(line.strip())
            if process.poll() is not None and eof:
                break
            if now - activity > stall_seconds:
                raise DownloadError('下载停滞：长时间没有新日志。', 'stall')
            on_tick(int(now - started))
            time.sleep(0.1)
        if process.returncode != 0 or not done:
            raise DownloadError('核心没有成功完成任务。\n' + '\n'.join(tail[-5:]))
        epubs = sorted(cwd.rglob('*.epub'))
        if not epubs:
            raise DownloadError('核心未生成 EPUB 文件。')
        if job.get('volumes'):
            expected = 1 if job.get('merge') else len(job['volumes'])
            if len(epubs) != expected:
                raise DownloadError(f'应生成 {expected} 卷，实际只有 {len(epubs)} 卷。')
        for path in epubs:
            validate_epub(path)
        return epubs
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)
        reader.join(timeout=3)
        process.stdout.close()
