"""书签管理 blueprint — 本地书签管理、批量下载、导入导出."""

import csv
import io

from flask import Blueprint, render_template, request, jsonify, Response

from ..services.bookmarks import (
    get_all_bookmarks,
    add_bookmark,
    remove_bookmark,
    update_bookmark,
    get_all_tags,
    filter_by_tag,
    export_bookmarks,
    import_bookmarks,
)

bp = Blueprint("favorites", __name__, url_prefix="/favorites")


@bp.route("/")
def index():
    """书签管理页面 → 重定向到 SPA."""
    return redirect("/app#favorites", code=302)


# ============================================================
# API 端点
# ============================================================

@bp.route("/api/list")
def api_bookmarks_list():
    """获取书签列表."""
    tag_filter = request.args.get("tag", "")
    
    if tag_filter:
        items = filter_by_tag(tag_filter)
    else:
        items = get_all_bookmarks()
    
    return jsonify({
        "items": [item.to_dict() for item in items],
        "total": len(items),
    })


@bp.route("/api/add", methods=["POST"])
def api_add_bookmark():
    """添加书签."""
    data = request.get_json() or {}
    album_id = data.get("album_id", "").strip()
    
    if not album_id:
        return jsonify({"error": "album_id 必填"}), 400
    
    success = add_bookmark(
        album_id=album_id,
        title=data.get("title", ""),
        tags=data.get("tags", []),
    )
    
    if success:
        return jsonify({"message": "添加成功"})
    return jsonify({"error": "添加失败"}), 500


@bp.route("/api/remove", methods=["POST"])
def api_remove_bookmark():
    """删除书签."""
    data = request.get_json() or {}
    album_id = data.get("album_id", "").strip()
    
    if not album_id:
        return jsonify({"error": "album_id 必填"}), 400
    
    success = remove_bookmark(album_id)
    
    if success:
        return jsonify({"message": "删除成功"})
    return jsonify({"error": "书签不存在"}), 404


@bp.route("/api/update", methods=["POST"])
def api_update_bookmark():
    """更新书签."""
    data = request.get_json() or {}
    album_id = data.get("album_id", "").strip()
    
    if not album_id:
        return jsonify({"error": "album_id 必填"}), 400
    
    success = update_bookmark(
        album_id=album_id,
        title=data.get("title"),
        tags=data.get("tags"),
    )
    
    if success:
        return jsonify({"message": "更新成功"})
    return jsonify({"error": "书签不存在"}), 404


@bp.route("/api/tags")
def api_get_tags():
    """获取所有标签."""
    tags = get_all_tags()
    return jsonify({"tags": tags})


@bp.route("/api/export/json")
def api_export_json():
    """导出书签为 JSON."""
    content = export_bookmarks()
    return Response(
        content,
        mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=bookmarks.json"},
    )


@bp.route("/api/export/csv")
def api_export_csv():
    """导出书签为 CSV."""
    items = get_all_bookmarks()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["album_id", "title", "tags"])
    
    for item in items:
        writer.writerow([item.album_id, item.title, ",".join(item.tags)])
    
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=bookmarks.csv"},
    )


@bp.route("/api/import", methods=["POST"])
def api_import_bookmarks():
    """导入书签."""
    data = request.get_json() or {}
    json_str = data.get("data", "")
    
    if not json_str:
        return jsonify({"error": "导入数据不能为空"}), 400
    
    count = import_bookmarks(json_str)
    return jsonify({"message": f"成功导入 {count} 个书签"})


@bp.route("/api/batch/download", methods=["POST"])
def api_batch_download():
    """批量下载书签中的本子."""
    data = request.get_json() or {}
    album_ids = data.get("album_ids", [])
    
    if not album_ids:
        return jsonify({"error": "请选择要下载的本子"}), 400
    
    from ..services.downloader import start_download
    
    task_ids = []
    for aid in album_ids:
        task_id = start_download(album_id=str(aid).strip())
        task_ids.append(task_id)
    
    return jsonify({"task_ids": task_ids, "count": len(task_ids)})
