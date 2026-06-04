"""书签管理服务 — 本地JSON文件存储，支持导入导出."""

import json
import os
import threading
from pathlib import Path
from typing import Optional, List, Dict

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BOOKMARKS_FILE = PROJECT_ROOT / "bookmarks.json"

# 线程锁
_lock = threading.Lock()


class BookmarkItem:
    """书签项."""
    def __init__(self, album_id: str, title: str = "", tags: List[str] = None, added_at: int = 0):
        self.album_id = album_id
        self.title = title
        self.tags = tags or []
        if added_at:
            self.added_at = added_at
        else:
            self.added_at = os.path.getctime(str(BOOKMARKS_FILE)) if BOOKMARKS_FILE.exists() else 0

    def to_dict(self):
        return {
            "album_id": self.album_id,
            "title": self.title,
            "tags": self.tags,
            "added_at": self.added_at,
        }


def _load_bookmarks() -> List[Dict]:
    """从文件加载书签."""
    if not BOOKMARKS_FILE.exists():
        return []
    try:
        with open(BOOKMARKS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_bookmarks(items: List[Dict]):
    """保存书签到文件."""
    with open(BOOKMARKS_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def get_all_bookmarks() -> List[BookmarkItem]:
    """获取所有书签."""
    with _lock:
        items = _load_bookmarks()
        return [BookmarkItem(**item) for item in items]


def get_bookmark(album_id: str) -> Optional[BookmarkItem]:
    """获取单个书签."""
    with _lock:
        items = _load_bookmarks()
        for item in items:
            if item["album_id"] == album_id:
                return BookmarkItem(**item)
        return None


def add_bookmark(album_id: str, title: str = "", tags: List[str] = None) -> bool:
    """添加书签，已存在则更新."""
    with _lock:
        items = _load_bookmarks()
        for item in items:
            if item["album_id"] == album_id:
                item["title"] = title or item["title"]
                item["tags"] = tags or item["tags"]
                _save_bookmarks(items)
                return True
        
        items.append({
            "album_id": album_id,
            "title": title,
            "tags": tags or [],
            "added_at": os.path.getctime(str(BOOKMARKS_FILE)) if BOOKMARKS_FILE.exists() else 0,
        })
        _save_bookmarks(items)
        return True


def remove_bookmark(album_id: str) -> bool:
    """删除书签."""
    with _lock:
        items = _load_bookmarks()
        new_items = [item for item in items if item["album_id"] != album_id]
        if len(new_items) != len(items):
            _save_bookmarks(new_items)
            return True
        return False


def update_bookmark(album_id: str, title: str = None, tags: List[str] = None) -> bool:
    """更新书签信息."""
    with _lock:
        items = _load_bookmarks()
        for item in items:
            if item["album_id"] == album_id:
                if title is not None:
                    item["title"] = title
                if tags is not None:
                    item["tags"] = tags
                _save_bookmarks(items)
                return True
        return False


def get_all_tags() -> List[str]:
    """获取所有标签."""
    with _lock:
        items = _load_bookmarks()
        tags = set()
        for item in items:
            tags.update(item.get("tags", []))
        return sorted(list(tags))


def filter_by_tag(tag: str) -> List[BookmarkItem]:
    """按标签筛选书签."""
    with _lock:
        items = _load_bookmarks()
        result = []
        for item in items:
            if tag in item.get("tags", []):
                result.append(BookmarkItem(**item))
        return result


def export_bookmarks() -> str:
    """导出书签为JSON字符串."""
    with _lock:
        items = _load_bookmarks()
        return json.dumps(items, ensure_ascii=False, indent=2)


def import_bookmarks(json_str: str) -> int:
    """导入书签（合并模式）."""
    with _lock:
        try:
            new_items = json.loads(json_str)
            if not isinstance(new_items, list):
                return 0
            
            existing = _load_bookmarks()
            existing_ids = {item["album_id"] for item in existing}
            
            added = 0
            for item in new_items:
                if isinstance(item, dict) and "album_id" in item:
                    if item["album_id"] not in existing_ids:
                        existing.append(item)
                        added += 1
            
            _save_bookmarks(existing)
            return added
        except Exception:
            return 0


def clear_all_bookmarks() -> int:
    """清空所有书签."""
    with _lock:
        items = _load_bookmarks()
        count = len(items)
        _save_bookmarks([])
        return count
