"""下载 blueprint — 提交下载任务 + SSE 实时进度推送."""

import json
import time

from flask import Blueprint, render_template, request, jsonify, Response, current_app

from ..services.jm_client import extract_album_id
from ..services.downloader import (
    start_download,
    cancel_task,
    delete_task,
    get_task,
    get_all_tasks,
    subscribe_progress,
    unsubscribe_progress,
    task_to_dict,
)

bp = Blueprint("download", __name__, url_prefix="/download")


@bp.route("/")
def index():
    """下载管理页面 → 重定向到 SPA."""
    return redirect("/app#download", code=302)


# ============================================================
# API 端点
# ============================================================

@bp.route("/api/start", methods=["POST"])
def api_start():
    """提交下载任务.

    JSON body:
        album_id: str (必填)
        album_title: str (可选, 显示用)
        image_suffix: str (可选, .jpg/.png/.webp)
        thread_count: int (可选)
        export_formats: list[str] (可选, pdf/zip/long_img)
        login_username: str (可选)
        login_password: str (可选)
        proxy: str (可选)
    """
    data = request.get_json() or {}
    album_id = data.get("album_id", "").strip()
    if not album_id:
        return jsonify({"error": "album_id 必填"}), 400
    
    # 尝试从文本中提取数字作为 ID
    converted = extract_album_id(album_id)
    if converted:
        album_id = converted

    task_id = start_download(
        album_id=album_id,
        image_suffix=data.get("image_suffix"),
        thread_count=data.get("thread_count"),
        export_formats=data.get("export_formats"),
        login_username=data.get("login_username"),
        login_password=data.get("login_password"),
        proxy=data.get("proxy"),
    )

    # 返回 task_id，前端可以用它订阅 SSE
    return jsonify({"task_id": task_id})


@bp.route("/api/start/batch", methods=["POST"])
def api_start_batch():
    """批量提交下载任务."""
    data = request.get_json() or {}
    album_ids = data.get("album_ids", [])
    options = {
        "image_suffix": data.get("image_suffix"),
        "thread_count": data.get("thread_count"),
        "export_formats": data.get("export_formats"),
        "login_username": data.get("login_username"),
        "login_password": data.get("login_password"),
        "proxy": data.get("proxy"),
    }

    task_ids = []
    for aid in album_ids:
        album_id = str(aid).strip()
        # 尝试从文本中提取数字作为 ID
        converted = extract_album_id(album_id)
        if converted:
            album_id = converted
        task_id = start_download(album_id=album_id, **options)
        task_ids.append(task_id)

    return jsonify({"task_ids": task_ids})


@bp.route("/api/tasks")
def api_tasks_list():
    """获取所有任务列表."""
    tasks = [task_to_dict(t) for t in get_all_tasks()]
    return jsonify({"tasks": tasks})


@bp.route("/api/tasks/<task_id>")
def api_task_detail(task_id: str):
    """获取单个任务详情."""
    task = get_task(task_id)
    if task is None:
        return jsonify({"error": "任务不存在"}), 404
    return jsonify(task_to_dict(task))


@bp.route("/api/tasks/<task_id>/progress")
def api_task_progress(task_id: str):
    """SSE 端点 — 实时推送任务进度."""

    def generate():
        # 先推送当前状态
        task = get_task(task_id)
        if task is None:
            yield f"data: {json.dumps({'error': '任务不存在'})}\n\n"
            return

        yield f"data: {json.dumps(task_to_dict(task))}\n\n"

        # 如果任务已经终结，直接返回
        if task.status in ("completed", "failed", "cancelled"):
            yield f"data: {json.dumps({'event': 'done', 'status': task.status})}\n\n"
            return

        # 否则订阅更新，持续推送
        queue = []

        def on_progress(data):
            queue.append(data)

        subscribe_progress(task_id, on_progress)

        try:
            while True:
                # 非阻塞地检查更新
                while queue:
                    item = queue.pop(0)
                    yield f"data: {json.dumps(item)}\n\n"

                # 检查任务是否终结
                task = get_task(task_id)
                if task and task.status in ("completed", "failed", "cancelled"):
                    yield f"data: {json.dumps({'event': 'done', 'status': task.status})}\n\n"
                    break

                time.sleep(0.3)
        except GeneratorExit:
            pass
        finally:
            unsubscribe_progress(task_id, on_progress)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@bp.route("/api/tasks/<task_id>/cancel", methods=["POST"])
def api_cancel_task(task_id: str):
    """取消下载任务."""
    ok = cancel_task(task_id)
    if ok:
        return jsonify({"message": "已取消"})
    return jsonify({"error": "无法取消（任务可能已完成）"}), 400


@bp.route("/api/tasks/<task_id>", methods=["DELETE"])
def api_delete_task(task_id: str):
    """删除任务记录."""
    ok = delete_task(task_id)
    if ok:
        return jsonify({"message": "已删除"})
    return jsonify({"error": "无法删除（任务仍在运行）"}), 400


# ============================================================
# HTMX partial — 任务列表 HTML 片段
# ============================================================

@bp.route("/partial/task-list")
def task_list_partial():
    """HTMX partial — 渲染任务列表."""
    tasks = [task_to_dict(t) for t in get_all_tasks()]
    return render_template("partials/task_list.html", tasks=tasks)


@bp.route("/partial/task-card/<task_id>")
def task_card_partial(task_id: str):
    """HTMX partial — 单个任务卡片."""
    task = get_task(task_id)
    if task is None:
        return '<div class="alert alert-warning">任务不存在或已删除</div>'
    return render_template("partials/task_card.html", task=task_to_dict(task))
