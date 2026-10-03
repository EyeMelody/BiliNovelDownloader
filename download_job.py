"""GUI adapter for the unmodified upstream interactive downloader."""
import os
import queue
import re
import subprocess
import threading
import time
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET



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
    """Drive the unmodified upstream interactive core, keeping stdin open."""
    cwd = Path(cwd)
    if list(cwd.rglob('*.epub')):
        raise DownloadError('任务目录必须为空，不能混入历史 EPUB。')
    flags = {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}
    process = subprocess.Popen(command, cwd=cwd, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               encoding='utf-8', errors='replace', bufsize=1, **flags)
    on_start(process)
    messages = queue.Queue()
    def consume():
        try:
            # Core prompts have no trailing newline. read(1) also handles UTF-8
            # characters split across pipe writes via TextIOWrapper's decoder.
            while True:
                char = process.stdout.read(1)
                if not char:
                    break
                messages.put(char)
        finally:
            messages.put(None)
    reader = threading.Thread(target=consume, daemon=True)
    reader.start()
    started = activity = time.monotonic()
    log_offset = 0
    buffer = ''
    state = 'url'
    completed = 0
    selected_count = None
    epubs = None
    tail = []
    prompts = ('请输入链接(多个链接使用空格隔开):', '请选择要下载的分卷: ',
               '是否合并选择的分卷为一个文件? ', '是否在每章开头添加章节标题? ')
    def send(value):
        process.stdin.write(value + '\n')
        process.stdin.flush()
    def report(line):
        nonlocal completed
        line = line.strip()
        if not line:
            return
        tail.append(line)
        del tail[:-20]
        on_line(line)
        if line.startswith('打包完成: '):
            completed += 1
        if '运行出错.' in line:
            raise DownloadError('原版核心报告下载失败。\n' + '\n'.join(tail[-5:]))
    try:
        while epubs is None:
            now = time.monotonic()
            if cancel.is_set():
                raise DownloadError('下载已取消。', 'cancelled')
            if now - started > timeout_seconds:
                raise DownloadError('下载超过总时间上限。', 'timeout')
            eof = False
            # Bound each drain so a noisy child cannot starve cancellation.
            for _ in range(32768):
                try:
                    char = messages.get_nowait()
                except queue.Empty:
                    break
                if char is None:
                    eof = True
                    break
                activity = now
                buffer += char
                matched = next((p for p in prompts if buffer.endswith(p)), None)
                if matched:
                    if matched == prompts[0]:
                        if state == 'url':
                            send(job['url'])
                            state = 'volumes'
                        elif state == 'downloading':
                            expected = 1 if job.get('merge') else selected_count
                            epubs = sorted(cwd.rglob('*.epub'))
                            if not expected or completed != expected or len(epubs) != expected:
                                raise DownloadError(f'下载结果不完整：应生成 {expected} 卷，完成提示 {completed} 次，文件 {len(epubs)} 个。')
                            for path in epubs:
                                validate_epub(path)
                        else:
                            raise DownloadError('核心提前返回输入状态，任务未完成。')
                    elif matched == prompts[1] and state == 'volumes':
                        # Selection menu includes [0] for all. Its maximum
                        # positive index gives the actual catalog count.
                        numbers = [int(n) for n in re.findall(r'\[(\d+)\]', '\n'.join(tail))]
                        total = max(numbers, default=0)
                        volumes = job.get('volumes')
                        if not total or (volumes and (min(volumes) < 1 or max(volumes) > total)):
                            raise DownloadError('分卷编号超出核心目录范围。')
                        selected_count = len(volumes) if volumes else total
                        send(','.join(map(str, volumes)) if volumes else '0')
                        state = 'options'
                    elif matched == prompts[2] and state == 'options':
                        send('1' if job.get('merge') else '2')
                        state = 'titles'
                    elif matched == prompts[3] and state in ('options', 'titles'):
                        send('1' if job.get('add_titles') else '2')
                        state = 'downloading'
                    else:
                        raise DownloadError('核心交互提示与预期不符，请检查核心版本。')
                    buffer = ''
                elif char == '\n':
                    report(buffer)
                    buffer = ''
                if len(buffer) > 65536:
                    raise DownloadError('核心输出异常：未识别的超长提示。')
            log = cwd / 'bili_novel.log'
            if log.exists():
                with log.open('r', encoding='utf-8', errors='replace') as stream:
                    stream.seek(log_offset)
                    lines = stream.readlines()
                    log_offset = stream.tell()
                if lines:
                    activity = now
                    for line in lines:
                        if line.strip():
                            on_line(line.strip())
            if epubs is not None:
                break
            if eof:
                raise DownloadError('核心在任务完成前退出。\n' + '\n'.join(tail[-5:]))
            if now - activity > stall_seconds:
                raise DownloadError('下载停滞：长时间没有新日志。', 'stall')
            on_tick(int(now - started))
            time.sleep(0.1)
        return epubs
    finally:
        # The stock core deliberately loops forever. End only our own child
        # after its next-URL prompt and validated outputs (or failure/cancel).
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)
        reader.join(timeout=3)
        process.stdin.close()
        process.stdout.close()
