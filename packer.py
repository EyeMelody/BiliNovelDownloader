import logging
from pathlib import Path
from typing import Optional

import psutil


def find_downloader_exe(base_path: Path) -> Optional[Path]:
    """动态寻找 tools 目录下的下载器执行档"""
    tools_dir = base_path / 'tools'
    exe_paths = list(tools_dir.glob('bili_novel_packer*-gui.exe'))
    if exe_paths:
        return exe_paths[0]
    return None

def _packer_pid_file(temp_dir: Path) -> Path:
    return temp_dir / 'packer.pid'

def write_packer_pid(temp_dir: Path, pid: int):
    """记录本程式启动的下载器 PID，供下次启动时清理异常残留。"""
    try:
        temp_dir.mkdir(parents=True, exist_ok=True)
        _packer_pid_file(temp_dir).write_text(str(pid), encoding='utf-8')
    except Exception as e:
        logging.warning(f"写入下载器 PID 档失败: {e}")

def clear_packer_pid(temp_dir: Path):
    """清除 PID 档（下载正常结束或清理完毕后呼叫）。"""
    try:
        _packer_pid_file(temp_dir).unlink(missing_ok=True)
    except Exception as e:
        logging.warning(f"删除下载器 PID 档失败: {e}")

def cleanup_orphaned_packer(temp_dir: Path, exe_path: Path):
    """清理上次因异常残留的下载器进程"""
    pid_file = _packer_pid_file(temp_dir)
    try:
        if not pid_file.exists():
            return
        pid = int(pid_file.read_text(encoding='utf-8').strip())
    except (ValueError, OSError):
        clear_packer_pid(temp_dir)
        return

    try:
        proc = psutil.Process(pid)
        if Path(proc.exe()).resolve() == exe_path.resolve():
            proc.kill()
            proc.wait(timeout=5)
            logging.info(f"已清理上次残留的下载器进程 (PID {pid})。")
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, psutil.TimeoutExpired):
        pass
    except Exception as e:
        logging.warning(f"清理残留下载器时发生错误: {e}")
    finally:
        clear_packer_pid(temp_dir)