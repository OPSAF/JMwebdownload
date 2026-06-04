"""搜索 & 浏览 blueprint — 搜索、排行榜、分类、本子详情."""

import math

from flask import Blueprint, render_template, request, jsonify, current_app, redirect

from ..services.jm_client import get_client, get_option, get_magic_constants, extract_album_id

bp = Blueprint("search", __name__, url_prefix="/browse")


@bp.route("/")
def index():
    """搜索/浏览主页 → 重定向到 SPA."""
    return redirect("/app#browse", code=302)


# ============================================================
# HTMX partial 端点 — 返回 HTML 片段
# ============================================================

@bp.route("/search-results")
def search_results():
    """搜索本子（HTMX partial）."""
    q = request.args.get("q", "").strip()
    page = request.args.get("page", 1, type=int)
    category = request.args.get("category", "")
    order_by = request.args.get("order_by", "")

    if not q and not category:
        return render_template("partials/search_results.html", items=[], total=0, page=1, total_pages=0, q=q)

    try:
        client = get_client()

        # 构建搜索参数
        kwargs = {"search_query": q, "page": page}
        if category:
            kwargs["category"] = category
        if order_by:
            kwargs["order_by"] = order_by

        result = client.search_site(**kwargs)

        items = []
        for aid, atitle in result.iter_id_title():
            items.append({"id": aid, "title": atitle})

        # 兼容不同版本的 search page 对象
        total = getattr(result, "total", len(items))
        page_size = getattr(result, "page_size", 20)
        total_pages = math.ceil(total / page_size) if page_size else 1

        return render_template(
            "partials/search_results.html",
            items=items,
            total=total,
            page=page,
            total_pages=total_pages,
            q=q,
        )
    except Exception as e:
        return render_template(
            "partials/search_results.html",
            items=[],
            total=0,
            page=1,
            total_pages=0,
            q=q,
            error=str(e),
        )


@bp.route("/rankings")
def rankings():
    """排行榜/分类浏览."""
    page = request.args.get("page", 1, type=int)
    time_filter = request.args.get("time", "WEEK")
    category = request.args.get("category", "CATEGORY_ALL")
    order_by = request.args.get("order_by", "VIEW")

    magic = get_magic_constants()

    try:
        client = get_client()
        time_val = magic["time"].get(time_filter, magic["time"]["WEEK"])
        cat_val = magic["categories"].get(category, magic["categories"]["CATEGORY_ALL"])
        order_val = magic["order_by"].get(order_by, magic["order_by"]["VIEW"])

        result = client.categories_filter(
            page=page,
            time=time_val,
            category=cat_val,
            order_by=order_val,
        )

        items = []
        for aid, atitle in result.iter_id_title():
            items.append({"id": aid, "title": atitle})

        total = getattr(result, "total", len(items))
        page_size = getattr(result, "page_size", 20)
        total_pages = max(1, math.ceil(total / page_size))

        return render_template(
            "partials/rankings.html",
            items=items,
            total=total,
            page=page,
            total_pages=total_pages,
            current_time=time_filter,
            current_category=category,
            current_order=order_by,
            magic=magic,
        )
    except Exception as e:
        return render_template(
            "partials/rankings.html",
            items=[],
            total=0,
            page=1,
            total_pages=0,
            error=str(e),
            magic=magic,
        )


# ============================================================
# 热门排行榜 API
# ============================================================

@bp.route("/api/hot")
def api_hot_list():
    """获取热门排行榜（用于首页展示）."""
    limit = request.args.get("limit", 8, type=int)
    
    try:
        client = get_client()
        magic = get_magic_constants()
        result = client.categories_filter(
            page=1,
            time=magic["time"]["WEEK"],
            category=magic["categories"]["CATEGORY_ALL"],
            order_by=magic["order_by"]["VIEW"],
        )
        
        items = []
        count = 0
        for aid, atitle in result.iter_id_title():
            if count >= limit:
                break
            items.append({"id": aid, "title": atitle})
            count += 1
        
        return jsonify({"items": items})
    except Exception as e:
        current_app.logger.error(f"获取热门列表失败: {e}")
        return jsonify({"items": []})


# ============================================================
# JSON API — 本子详情
# ============================================================

@bp.route("/album/<album_id>")
def album_detail_page(album_id: str):
    """本子详情页."""
    return render_template("album.html", album_id=album_id)


@bp.route("/api/album/<album_id>")
def album_detail_api(album_id: str):
    """本子详情 JSON API."""
    try:
        # 尝试从文本中提取数字作为 ID
        converted = extract_album_id(album_id)
        if converted:
            album_id = converted
        
        client = get_client()
        album = client.get_album_detail(album_id)

        photos = []
        for photo in album:
            photos.append({
                "photo_id": photo.photo_id,
                "title": getattr(photo, "title", ""),
                "index": getattr(photo, "index", 0),
                "publish_date": getattr(photo, "publish_date", ""),
            })

        return jsonify({
            "album_id": album.album_id,
            "title": getattr(album, "title", ""),
            "author": getattr(album, "author", ""),
            "description": getattr(album, "description", "")[:500],
            "tags": getattr(album, "tags", ""),
            "works": getattr(album, "works", ""),
            "actors": getattr(album, "actors", ""),
            "view_count": getattr(album, "view_count", ""),
            "like_count": getattr(album, "like_count", ""),
            "comment_count": getattr(album, "comment_count", ""),
            "publish_date": getattr(album, "publish_date", ""),
            "update_date": getattr(album, "update_date", ""),
            "total_photos": len(photos),
            "photos": photos,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 404


@bp.route("/api/album/<album_id>/photos")
def album_photos_api(album_id: str):
    """获取本子的章节列表（HTMX partial）."""
    try:
        # 尝试从文本中提取数字作为 ID
        converted = extract_album_id(album_id)
        if converted:
            album_id = converted
        
        client = get_client()
        album = client.get_album_detail(album_id)

        photos = []
        for photo in album:
            photos.append({
                "photo_id": photo.photo_id,
                "title": getattr(photo, "title", ""),
                "index": getattr(photo, "index", 0),
            })

        return render_template("partials/photo_list.html", album_id=album_id, photos=photos)
    except Exception as e:
        return f'<div class="alert alert-danger">获取章节失败: {e}</div>'


@bp.route("/api/album/<album_id>/cover")
def album_cover(album_id: str):
    """获取本子封面图 URL（重定向到禁漫 CDN）."""
    try:
        client = get_client()
        album = client.get_album_detail(album_id)
        # 获取封面图的 scrambled URL，然后解码
        cover_url = getattr(album, "cover_url", "")
        if not cover_url:
            # 尝试从第一张图片获取
            photos = list(album)
            if photos:
                first_photo = client.get_photo_detail(photos[0].photo_id)
                images = list(first_photo)
                if images:
                    cover_url = images[0].img_url
        return jsonify({"url": cover_url or ""})
    except Exception as e:
        return jsonify({"error": str(e)}), 404
