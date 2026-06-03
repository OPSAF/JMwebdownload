"""文件管理 blueprint — 浏览已下载文件、在线查看、导出 PDF/ZIP/长图."""

import os
import shutil
import zipfile
from pathlib import Path
from datetime import datetime

from flask import (
    Blueprint, render_template, request, jsonify,
    send_file, send_from_directory, current_app, abort, url_for,
)

from ..services.jm_client import get_download_dir, get_option
from jmcomic import Feature

bp = Blueprint("files", __name__, url_prefix="/files")


def _safe_path(relative_path: str) -> Path:
    """将相对路径解析为绝对路径，并验证在下载目录内（防目录穿越）."""
    base = Path(get_download_dir()).resolve()
    target = (base / relative_path).resolve()
    if not str(target).startswith(str(base)):
        raise ValueError("非法路径")
    return target


# ============================================================
# 页面
# ============================================================

@bp.route("/")
def index():
    """文件浏览器主页."""
    return render_template("files.html")


# ============================================================
# HTMX partial — 文件树
# ============================================================

@bp.route("/browse")
@bp.route("/browse/<path:subpath>")
def browse(subpath: str = ""):
    """浏览下载目录（HTMX partial）."""
    try:
        target = _safe_path(subpath) if subpath else Path(get_download_dir())
        target = target.resolve()
    except ValueError:
        return '<div class="alert alert-danger">非法路径</div>'

    if not target.exists():
        return '<div class="alert alert-warning">目录不存在</div>'

    # 面包屑
    breadcrumbs = _build_breadcrumbs(subpath)

    if target.is_file():
        return _render_file_view(target, breadcrumbs)

    # 目录：列出文件/文件夹
    entries = []
    try:
        for entry in sorted(target.iterdir(), key=lambda e: (e.is_file(), e.name.lower())):
            rel_path = str(entry.relative_to(Path(get_download_dir()).resolve()))
            stat = entry.stat()
            entries.append({
                "name": entry.name,
                "path": rel_path.replace("\\", "/"),
                "is_dir": entry.is_dir(),
                "size": stat.st_size,
                "size_human": _human_size(stat.st_size),
                "mtime": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                # 图片类型判断
                "is_image": entry.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"),
                "is_pdf": entry.suffix.lower() == ".pdf",
                "is_zip": entry.suffix.lower() in (".zip", ".7z"),
            })
    except PermissionError:
        return '<div class="alert alert-danger">权限不足</div>'

    return render_template(
        "partials/file_list.html",
        current_path=subpath,
        entries=entries,
        breadcrumbs=breadcrumbs,
        parent_path=str(Path(subpath).parent) if subpath else None,
    )


# ============================================================
# 文件预览（图片 / PDF / ZIP 内容列表）
# ============================================================

@bp.route("/view/<path:filepath>")
def view_file(filepath: str):
    """文件预览页面."""
    try:
        target = _safe_path(filepath)
    except ValueError:
        abort(400)

    if not target.exists() or not target.is_file():
        abort(404)

    ext = target.suffix.lower()
    if ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"):
        return render_template("viewer.html", filepath=filepath, file_type="image")
    elif ext == ".pdf":
        return render_template("viewer.html", filepath=filepath, file_type="pdf")
    elif ext in (".zip", ".7z"):
        # 列出 zip 内容
        try:
            with zipfile.ZipFile(target) as zf:
                files = zf.namelist()[:200]  # 只显示前200个
            return render_template("viewer.html", filepath=filepath, file_type="zip", zip_files=files)
        except Exception as e:
            return f'<div class="alert alert-danger">无法读取压缩包: {e}</div>'
    else:
        abort(415)


# ============================================================
# 文件下载
# ============================================================

@bp.route("/serve/<path:filepath>")
def serve_file(filepath: str):
    """直接提供文件下载/内联显示."""
    try:
        target = _safe_path(filepath)
    except ValueError:
        abort(400)

    if not target.exists() or not target.is_file():
        abort(404)

    # 图片和 PDF 内联显示，其他下载
    ext = target.suffix.lower()
    inline_exts = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".pdf"}
    if ext in inline_exts:
        return send_file(target)
    return send_file(target, as_attachment=True)


# ============================================================
# 导出 PDF / ZIP / 长图
# ============================================================

@bp.route("/api/export", methods=["POST"])
def export_files():
    """对已下载的目录执行导出操作.

    JSON body:
        path: str — 相对于下载目录的路径（目录或文件所在目录）
        format: str — "pdf" | "zip" | "long_img"
    """
    data = request.get_json() or {}
    rel_path = data.get("path", "").strip()
    fmt = data.get("format", "pdf")

    if not rel_path:
        return jsonify({"error": "path 必填"}), 400
    if fmt not in ("pdf", "zip", "long_img"):
        return jsonify({"error": f"不支持的格式: {fmt}"}), 400

    try:
        target = _safe_path(rel_path)
    except ValueError:
        return jsonify({"error": "非法路径"}), 400

    if not target.exists():
        return jsonify({"error": "路径不存在"}), 404

    # 如果传的是文件，导出它所在的目录
    if target.is_file():
        target = target.parent

    export_dir = Path(get_download_dir()) / "_exports"
    export_dir.mkdir(parents=True, exist_ok=True)

    try:
        if fmt == "pdf":
            _export_to_pdf(target, export_dir)
        elif fmt == "zip":
            _export_to_zip(target, export_dir)
        elif fmt == "long_img":
            _export_to_long_img(target, export_dir)

        return jsonify({"message": f"导出 {fmt} 成功", "export_dir": str(export_dir)})
    except Exception as e:
        return jsonify({"error": f"导出失败: {e}"}), 500


def _export_to_pdf(img_dir: Path, output_dir: Path):
    """将目录中的图片合并为 PDF."""
    import img2pdf

    images = sorted(
        [p for p in img_dir.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")],
        key=lambda p: p.name,
    )
    if not images:
        raise ValueError("没有找到图片文件")

    pdf_name = f"{img_dir.name}.pdf"
    pdf_path = output_dir / pdf_name

    with open(pdf_path, "wb") as f:
        f.write(img2pdf.convert([str(p) for p in images]))

    return str(pdf_path)


def _export_to_zip(img_dir: Path, output_dir: Path):
    """将目录打包为 ZIP."""
    zip_name = f"{img_dir.name}.zip"
    zip_path = output_dir / zip_name

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(img_dir.iterdir()):
            if p.is_file():
                zf.write(p, arcname=p.name)
            elif p.is_dir():
                for root, _, files in os.walk(p):
                    for f in files:
                        fp = Path(root) / f
                        zf.write(fp, arcname=str(fp.relative_to(img_dir)))

    return str(zip_path)


def _export_to_long_img(img_dir: Path, output_dir: Path):
    """将目录中的图片拼接为长图 PNG."""
    from PIL import Image

    images = sorted(
        [p for p in img_dir.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")],
        key=lambda p: p.name,
    )
    if not images:
        raise ValueError("没有找到图片文件")

    pil_images = []
    max_width = 0

    for p in images:
        img = Image.open(p).convert("RGB")
        pil_images.append(img)
        max_width = max(max_width, img.width)

    # 统一宽度，垂直拼接
    total_height = sum(int(img.height * max_width / img.width) for img in pil_images)
    merged = Image.new("RGB", (max_width, total_height))

    y_offset = 0
    for img in pil_images:
        new_h = int(img.height * max_width / img.width)
        resized = img.resize((max_width, new_h), Image.LANCZOS)
        merged.paste(resized, (0, y_offset))
        y_offset += new_h

    output_name = f"{img_dir.name}.png"
    output_path = output_dir / output_name
    merged.save(str(output_path), "PNG")

    return str(output_path)


# ============================================================
# 删除
# ============================================================

@bp.route("/api/delete", methods=["POST"])
def delete_path():
    """删除文件或目录."""
    data = request.get_json() or {}
    rel_path = data.get("path", "").strip()
    if not rel_path:
        return jsonify({"error": "path 必填"}), 400
    try:
        target = _safe_path(rel_path)
    except ValueError:
        return jsonify({"error": "非法路径"}), 400

    if not target.exists():
        return jsonify({"error": "路径不存在"}), 404

    try:
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        return jsonify({"message": f"已删除: {rel_path}"})
    except Exception as e:
        return jsonify({"error": f"删除失败: {e}"}), 500


# ============================================================
# 工具函数
# ============================================================

def _human_size(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _build_breadcrumbs(subpath: str) -> list[dict]:
    if not subpath:
        return [{"name": "📁 下载目录", "path": ""}]
    parts = subpath.replace("\\", "/").split("/")
    crumbs = [{"name": "📁 下载目录", "path": ""}]
    accumulated = ""
    for part in parts:
        accumulated = f"{accumulated}/{part}" if accumulated else part
        crumbs.append({"name": part, "path": accumulated})
    return crumbs


def _render_file_view(target: Path, breadcrumbs: list[dict]):
    """渲染文件预览视图."""
    ext = target.suffix.lower()
    rel_path = str(target.relative_to(Path(get_download_dir()).resolve())).replace("\\", "/")

    if ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"):
        return render_template(
            "partials/file_view.html",
            file_type="image",
            filepath=rel_path,
            filename=target.name,
            breadcrumbs=breadcrumbs,
            size_human=_human_size(target.stat().st_size),
        )
    elif ext == ".pdf":
        return render_template(
            "partials/file_view.html",
            file_type="pdf",
            filepath=rel_path,
            filename=target.name,
            breadcrumbs=breadcrumbs,
            size_human=_human_size(target.stat().st_size),
        )
    else:
        return f'<div class="alert alert-info">无法预览此文件类型: {ext}</div>'
