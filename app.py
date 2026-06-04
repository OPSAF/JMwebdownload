"""JM Downloader Web — 基于 Flask + htmx 的禁漫下载管理器."""

import os
import sys
from pathlib import Path

from flask import Flask, render_template, redirect, request

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))


def create_app() -> Flask:
    """Flask 应用工厂."""
    app = Flask(
        __name__,
        template_folder=str(PROJECT_ROOT / "jm_web" / "templates"),
        static_folder=str(PROJECT_ROOT / "static"),
    )
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "jm-downloader-secret-dev")

    # 注册蓝图
    from jm_web.blueprints.search import bp as search_bp
    from jm_web.blueprints.download import bp as download_bp
    from jm_web.blueprints.files import bp as files_bp
    from jm_web.blueprints.favorites import bp as favorites_bp
    from jm_web.blueprints.config_bp import bp as config_bp

    app.register_blueprint(search_bp)
    app.register_blueprint(download_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(favorites_bp)
    app.register_blueprint(config_bp)

    # 首页
    @app.route("/")
    def index():
        return render_template("index.html")

    # SPA 统一工作台（4 个子页面融合为单页应用）
    @app.route("/app")
    def spa_app():
        return render_template("subpages.html")

    # 旧子页面路由 → 重定向到 SPA（保持 hash 兼容）
    @app.route("/browse")
    def redirect_browse():
        return redirect("/app#browse", code=302)

    @app.route("/download")
    def redirect_download():
        return redirect("/app#download", code=302)

    @app.route("/files")
    def redirect_files():
        return redirect("/app#files", code=302)

    @app.route("/favorites")
    def redirect_favorites():
        return redirect("/app#favorites", code=302)

    # 注入模板全局变量
    @app.context_processor
    def inject_globals():
        from jm_web.services.jm_client import get_download_dir
        return {
            "get_download_dir": get_download_dir,
        }

    return app


def main():
    """启动开发服务器."""
    app = create_app()

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("DEBUG", "true").lower() == "true"

    print("=" * 50)
    print("         JM Downloader Web")
    print(f"  Starting at http://{host}:{port}")
    print("  Download dir: downloads/")
    print("  Config file: config.yml")
    print("  Press Ctrl+C to stop")
    print("=" * 50)

    app.run(host=host, port=port, debug=debug, threaded=True)


# 创建顶层 app 实例供 Flask 开发服务器使用
app = create_app()

if __name__ == "__main__":
    main()
