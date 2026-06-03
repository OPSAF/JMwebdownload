"""下载任务管理器 — 后台线程池 + 目录快照追踪 + 导出."""

import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

import jmcomic
from jmcomic import (
    JmOption,
    create_option_by_file,
    download_album,
    download_photo,
    MissingAlbumPhotoException,
    RequestRetryAllFailException,
    PartialDownloadFailedException,
    JmcomicException,
)

from .jm_client import get_option, get_download_dir

# ============================================================
# 数据模型
# ============================================================

@dataclass
class TaskProgress:
    task_id: str
    album_id: str
    title: str = ""
    status: str = "pending"  # pending|running|processing|exporting|completed|failed|cancelled
    total_photos: int = 0
    current_photo: int = 0
    current_photo_title: str = ""
    total_images: int = 0
    current_image: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    finished_at: str = ""
    message: str = ""
    error: str = ""
    export_formats: list = field(default_factory=list)
    download_path: str = ""
    _cancelled: bool = field(default=False, repr=False)


# ============================================================
# 全局状态
# ============================================================

_tasks: dict[str, TaskProgress] = {}
_tasks_lock = threading.Lock()
_listeners: dict[str, list[Callable]] = {}

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}


def get_task(task_id: str) -> TaskProgress | None:
    with _tasks_lock:
        return _tasks.get(task_id)


def get_all_tasks() -> list[TaskProgress]:
    with _tasks_lock:
        return list(_tasks.values())


def subscribe_progress(task_id: str, cb: Callable):
    with _tasks_lock:
        _listeners.setdefault(task_id, []).append(cb)


def unsubscribe_progress(task_id: str, cb: Callable):
    with _tasks_lock:
        lst = _listeners.get(task_id, [])
        if cb in lst:
            lst.remove(cb)


def _notify(task: TaskProgress):
    with _tasks_lock:
        cbs = _listeners.get(task.task_id, [])[:]
    data = task_to_dict(task)
    for cb in cbs:
        try:
            cb(data)
        except Exception:
            pass


def _update(task_id: str, **kw):
    with _tasks_lock:
        t = _tasks.get(task_id)
        if t is None:
            return
        for k, v in kw.items():
            if hasattr(t, k):
                setattr(t, k, v)
    _notify(t)


def task_to_dict(t: TaskProgress) -> dict:
    ip = round(t.current_image / t.total_images * 100, 1) if t.total_images > 0 else 0
    pp = round(t.current_photo / t.total_photos * 100, 1) if t.total_photos > 0 else 0
    return {
        "task_id": t.task_id, "album_id": t.album_id, "title": t.title,
        "status": t.status, "total_photos": t.total_photos,
        "current_photo": t.current_photo, "current_photo_title": t.current_photo_title,
        "total_images": t.total_images, "current_image": t.current_image,
        "created_at": t.created_at, "finished_at": t.finished_at,
        "message": t.message, "error": t.error,
        "export_formats": t.export_formats, "download_path": t.download_path,
        "image_percent": ip, "photo_percent": pp,
    }


# ============================================================
# 目录工具
# ============================================================

def _dir_snapshot(base: Path) -> set[str]:
    """返回 base 下所有子目录的相对路径集合."""
    if not base.exists():
        return set()
    return {str(d.relative_to(base)) for d in base.iterdir() if d.is_dir()}


def _count_images(dirs: list[Path]) -> int:
    """统计多个目录下的图片总数."""
    c = 0
    for d in dirs:
        if not d.exists():
            continue
        try:
            for root, _, files in os.walk(d):
                c += sum(1 for f in files if Path(f).suffix.lower() in IMAGE_EXTS)
        except PermissionError:
            pass
    return c


def _collect_images(dirs: list[Path]) -> list[Path]:
    """按章节排序收集所有图片路径."""
    result = []
    for d in sorted(dirs, key=lambda x: x.name):
        imgs = sorted(
            [p for p in d.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTS],
            key=lambda p: p.name,
        )
        result.extend(imgs)
    return result


# ============================================================
# 进度监控
# ============================================================

class _ProgressMonitor:
    """轮询新下载目录中的图片数，更新任务进度."""
    def __init__(self, task_id: str, base_dir: Path, snapshot_before: set[str]):
        self.task_id = task_id
        self.base_dir = base_dir
        self.snapshot_before = snapshot_before
        self.stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _get_new_dirs(self) -> list[Path]:
        if not self.base_dir.exists():
            return []
        return [
            self.base_dir / d for d in _dir_snapshot(self.base_dir)
            if d not in self.snapshot_before
        ]

    def _run(self):
        time.sleep(0.5)  # 等下载开始创建目录
        while not self.stop.is_set():
            t = get_task(self.task_id)
            if t is None or t.status in ("completed", "failed", "cancelled"):
                break
            new_dirs = self._get_new_dirs()
            count = _count_images(new_dirs)
            if count > 0:
                _update(self.task_id, current_image=count)
            time.sleep(0.5)

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def join(self, timeout=None):
        self.stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)


# ============================================================
# 导出
# ============================================================

def _do_exports(task_id: str, photo_dirs: list[Path], title: str, formats: list[str]):
    """对下载的目执行导出操作."""
    export_dir = Path(get_download_dir()) / "_exports"
    export_dir.mkdir(parents=True, exist_ok=True)

    for fmt in formats:
        try:
            if fmt == "pdf":
                _export_pdf(photo_dirs, export_dir, title, task_id)
            elif fmt == "zip":
                _export_zip(photo_dirs, export_dir, title, task_id)
            elif fmt == "long_img":
                _export_longimg(photo_dirs, export_dir, title, task_id)
        except Exception as e:
            _update(task_id, message=f"导出 {fmt} 失败: {e}")


def _export_pdf(photo_dirs: list[Path], out_dir: Path, title: str, task_id: str):
    import img2pdf
    imgs = _collect_images(photo_dirs)
    if not imgs:
        return
    safe_title = "".join(c for c in title if c not in r'\/:*?"<>|')
    pdf_path = out_dir / f"{safe_title}.pdf"
    with open(pdf_path, "wb") as f:
        f.write(img2pdf.convert([str(p) for p in imgs]))
    _update(task_id, message=f"PDF 已导出: {pdf_path.name}")
    print(f"[export] PDF done: {pdf_path}")


def _export_zip(photo_dirs: list[Path], out_dir: Path, title: str, task_id: str):
    import zipfile
    safe_title = "".join(c for c in title if c not in r'\/:*?"<>|')
    zip_path = out_dir / f"{safe_title}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for d in sorted(photo_dirs, key=lambda x: x.name):
            for root, _, files in os.walk(d):
                for f in files:
                    fp = Path(root) / f
                    zf.write(fp, arcname=str(fp.relative_to(d.parent)))
    _update(task_id, message=f"ZIP 已导出: {zip_path.name}")
    print(f"[export] ZIP done: {zip_path}")


def _export_longimg(photo_dirs: list[Path], out_dir: Path, title: str, task_id: str):
    from PIL import Image
    imgs = _collect_images(photo_dirs)
    if not imgs:
        return

    pil_imgs, max_w = [], 0
    for p in imgs:
        img = Image.open(p).convert("RGB")
        pil_imgs.append(img)
        max_w = max(max_w, img.width)

    total_h, resized = 0, []
    for img in pil_imgs:
        nh = int(img.height * max_w / img.width) if img.width > 0 else img.height
        resized.append(img.resize((max_w, nh), Image.LANCZOS))
        total_h += nh

    merged = Image.new("RGB", (max_w, total_h))
    y = 0
    for img in resized:
        merged.paste(img, (0, y))
        y += img.height

    safe_title = "".join(c for c in title if c not in r'\/:*?"<>|')
    out_path = out_dir / f"{safe_title}.png"
    merged.save(str(out_path), "PNG")
    _update(task_id, message=f"长图已导出: {out_path.name}")
    print(f"[export] long_img done: {out_path}")


# ============================================================
# 下载 Worker
# ============================================================

def download_worker(
    task_id: str, album_id: str, *,
    config_path: str | None = None,
    image_suffix: str | None = None,
    thread_count: int | None = None,
    export_formats: list[str] | None = None,
    login_username: str | None = None,
    login_password: str | None = None,
    proxy: str | None = None,
):
    """后台下载线程 — 核心逻辑."""
    t = get_task(task_id)
    if t is None:
        return

    _update(task_id, status="running", message="初始化配置...")

    try:
        # ==== 构建 option ====
        option = get_option(config_path)

        if image_suffix:
            option.download['image']['suffix'] = image_suffix
        if thread_count and thread_count > 0:
            option.download['threading']['image'] = min(thread_count, 30)
            option.download['threading']['photo'] = max(1, min(thread_count // 2, 8))
        if proxy:
            option.client.postman.meta_data['proxies'] = proxy

        # 登录
        if login_username and login_password:
            cl = option.new_jm_client()
            cl.login(login_username, login_password)

        # ==== 获取元数据 ====
        _update(task_id, message="获取本子信息...")
        cl = option.new_jm_client()
        try:
            album = cl.get_album_detail(album_id)
            title = album.title or album_id
            photos = list(album)
        except Exception:
            title = album_id
            photos = []

        total_photos = len(photos)
        total_images = 0
        for p in photos:
            try:
                pd = cl.get_photo_detail(p.photo_id, False)
                total_images += len(list(pd))
            except Exception:
                pass

        _update(task_id, title=title, total_photos=total_photos,
                total_images=total_images, status="processing",
                message=f"下载 [{title}]，{total_photos}章 {total_images}图")

        # ==== 目录快照 ====
        base = Path(get_download_dir())
        base.mkdir(parents=True, exist_ok=True)
        snapshot = _dir_snapshot(base)

        # ==== 启动进度监控 ====
        monitor = _ProgressMonitor(task_id, base, snapshot)
        monitor.start()

        # ==== 执行下载 ====
        _update(task_id, status="processing", message="正在下载...")
        try:
            download_album(album_id, option, check_exception=False)
        finally:
            monitor.join(timeout=3)

        # ==== 找出新创建的目录 ====
        new_dirs = [
            base / d for d in _dir_snapshot(base)
            if d not in snapshot
        ]
        if not new_dirs:
            # 回退：用所有子目录（排除 _exports）
            new_dirs = [
                d for d in base.iterdir()
                if d.is_dir() and d.name != "_exports"
            ]

        actual_count = _count_images(new_dirs)
        _update(task_id, total_images=max(total_images, actual_count),
                current_image=actual_count, download_path=str(base))

        # ==== 导出 ====
        if export_formats and actual_count > 0:
            _update(task_id, status="exporting", message="导出中...")
            _do_exports(task_id, new_dirs, title, export_formats)

        # ==== 完成 ====
        _update(task_id, status="completed",
                message=f"下载完成 [{title}]，{actual_count}张图",
                finished_at=datetime.now().isoformat())

    except MissingAlbumPhotoException as e:
        _update(task_id, status="failed", error=f"本子不存在: {e.error_jmid}")
    except RequestRetryAllFailException:
        _update(task_id, status="failed", error="网络请求全部失败，请检查代理或域名")
    except PartialDownloadFailedException as e:
        _update(task_id, status="completed",
                message="部分章节/图片下载失败", error=str(e)[:300])
    except JmcomicException as e:
        _update(task_id, status="failed", error=f"jmcomic 异常: {str(e)[:300]}")
    except Exception as e:
        _update(task_id, status="failed", error=f"未知错误: {str(e)[:300]}")


# ============================================================
# 公开 API
# ============================================================

def start_download(album_id: str, **kw) -> str:
    task_id = str(uuid.uuid4())[:8]
    t = TaskProgress(task_id=task_id, album_id=album_id,
                     export_formats=kw.get("export_formats") or [])
    with _tasks_lock:
        _tasks[task_id] = t
    th = threading.Thread(target=download_worker, args=(task_id, album_id),
                          kwargs=kw, daemon=True)
    th.start()
    return task_id


def cancel_task(task_id: str) -> bool:
    t = get_task(task_id)
    if t and t.status in ("pending", "running", "processing"):
        t._cancelled = True
        _update(task_id, status="cancelled", message="已取消")
        return True
    return False


def delete_task(task_id: str) -> bool:
    with _tasks_lock:
        t = _tasks.get(task_id)
        if t and t.status in ("completed", "failed", "cancelled"):
            del _tasks[task_id]
            _listeners.pop(task_id, None)
            return True
    return False
