"""JM Downloader Web — 基于 Flask + htmx 的禁漫下载管理器."""

import os
import sys
from pathlib import Path

from flask import Flask, render_template

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

    print(f"""
╔══════════════════════════════════════════════════════╗
║          JM Downloader Web                         ║
║  🚀 Starting at http://{host}:{port}                  ║
║  📂 Download dir: downloads/                       ║
║  ⚙️  Config file: config.yml                        ║
║  🌐 Press Ctrl+C to stop                           ║
╚══════════════════════════════════════════════════════╝
    """)

    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == "__main__":
    main()
