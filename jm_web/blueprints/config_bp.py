"""配置管理 blueprint — YAML 编辑器 + domain 测试."""

import concurrent.futures
import os

import yaml
from flask import Blueprint, render_template, request, jsonify, current_app

from ..services.jm_client import (
    get_option, get_client, get_default_config_path, get_download_dir,
    clear_thread_cache,
)

bp = Blueprint("config", __name__, url_prefix="/config")


@bp.route("/")
def index():
    """配置管理页面."""
    return render_template("config.html")


@bp.route("/api/get")
def api_get_config():
    """获取当前 YAML 配置."""
    config_path = get_default_config_path()
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            content = f.read()
        return jsonify({"content": content, "path": config_path})
    except FileNotFoundError:
        return jsonify({"content": DEFAULT_CONFIG_TEMPLATE, "path": config_path})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/save", methods=["POST"])
def api_save_config():
    """保存 YAML 配置."""
    data = request.get_json() or {}
    content = data.get("content", "")

    config_path = get_default_config_path()
    try:
        # 尝试解析 YAML，确保语法正确
        yaml.safe_load(content)

        with open(config_path, "w", encoding="utf-8") as f:
            f.write(content)

        # 清除缓存，下次请求会读新配置
        clear_thread_cache()

        return jsonify({"message": "配置已保存"})
    except yaml.YAMLError as e:
        return jsonify({"error": f"YAML 语法错误: {e}"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@bp.route("/api/test-domain", methods=["POST"])
def api_test_domain():
    """测试禁漫域名可达性."""
    data = request.get_json() or {}
    domains_str = data.get("domains", "").strip()
    if not domains_str:
        # 默认使用常见域名
        domains = [
            "18comic.vip", "18comic.org", "jmcomic1.me", "jmcomic.me",
            "18comic-palworld.vip", "18comic-c.art",
        ]
    else:
        domains = [d.strip() for d in domains_str.split("\n") if d.strip()]

    results = {}

    def test_one(domain: str):
        try:
            option = get_option()
            client = option.new_jm_client(impl="html", domain_list=[domain])
            client.get_album_detail("123456")
            return domain, "ok"
        except Exception as e:
            # 提取简短错误信息
            msg = str(e.args[0]) if e.args else str(e)
            if len(msg) > 100:
                msg = msg[:100] + "..."
            return domain, msg

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(10, len(domains))) as pool:
        futures = {pool.submit(test_one, d): d for d in domains}
        for future in concurrent.futures.as_completed(futures):
            domain, status = future.result()
            results[domain] = status

    return jsonify({"results": results})


@bp.route("/api/reset", methods=["POST"])
def api_reset_config():
    """重置为默认配置."""
    config_path = get_default_config_path()
    try:
        # 备份旧配置
        if os.path.exists(config_path):
            backup = config_path + ".bak"
            os.rename(config_path, backup)

        from jmcomic import JmOption
        default_option = JmOption.default()
        default_option.dir_rule.base_dir = get_download_dir()
        default_option.to_file(config_path)

        clear_thread_cache()
        return jsonify({"message": "已重置为默认配置"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================================
# 默认配置模板
# ============================================================

DEFAULT_CONFIG_TEMPLATE = """# JMComic 下载配置
# 修改后点击保存，即时生效

log: true

client:
  impl: html  # html=网页端, api=APP端
  retry_times: 5
  cache: true

  postman:
    meta_data:
      proxies: system  # system=系统代理, null=无代理, 127.0.0.1:7890=自定义
      # cookies:
      #   AVS: your_cookie_value_here

download:
  cache: true
  image:
    decode: true
    suffix: .jpg  # 图片格式: .jpg, .png, .webp
  threading:
    image: 30
    photo: 16

dir_rule:
  base_dir: downloads/
  rule: Bd_Aid_Pindex
  # Ptitle=按章节标题, Aid_Pindex=按本子ID/章节序号
"""
