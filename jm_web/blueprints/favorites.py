"""收藏夹 blueprint — 登录、查看收藏夹、导出."""

import csv
import io
import math

from flask import Blueprint, render_template, request, jsonify, Response

from ..services.jm_client import get_client, get_option

bp = Blueprint("favorites", __name__, url_prefix="/favorites")


@bp.route("/")
def index():
    """收藏夹页面."""
    return render_template("favorites.html")


@bp.route("/api/login", methods=["POST"])
def api_login():
    """登录禁漫账号."""
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()

    if not username or not password:
        return jsonify({"error": "用户名和密码必填"}), 400

    try:
        client = get_client()
        client.login(username, password)
        return jsonify({"message": "登录成功"})
    except Exception as e:
        return jsonify({"error": f"登录失败: {e}"}), 401


@bp.route("/api/list")
def api_favorites_list():
    """获取收藏夹列表."""
    page = request.args.get("page", 1, type=int)
    folder_id = request.args.get("folder_id", "0")

    try:
        client = get_client()
        result = client.favorite_folder(page=page, folder_id=folder_id)

        items = []
        for aid, atitle in result.iter_id_title():
            items.append({"id": aid, "title": atitle})

        total = getattr(result, "total", len(items))
        page_size = getattr(result, "page_size", 20)
        total_pages = math.ceil(total / page_size) if page_size else 1

        return jsonify({
            "items": items,
            "total": total,
            "page": page,
            "total_pages": total_pages,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/export")
def api_export_csv():
    """导出收藏夹为 CSV."""
    try:
        client = get_client()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["album_id", "title"])

        for page_data in client.favorite_folder_gen():
            for aid, atitle in page_data.iter_id_title():
                writer.writerow([aid, atitle])

        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=favorites.csv"},
        )
    except Exception as e:
        return jsonify({"error": f"导出失败（请确认已登录）: {e}"}), 500
