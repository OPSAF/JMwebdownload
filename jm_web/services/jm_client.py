"""jmcomic client wrapper — 提供统一接口给 blueprint 调用."""

import os
import re
import tempfile
import threading
from pathlib import Path

import jmcomic
from jmcomic import (
    JmOption,
    JmModuleConfig,
    JmHtmlClient,
    JmApiClient,
    JmMagicConstants,
    JmcomicText,
    create_option_by_file,
)


def extract_album_id(text: str) -> str | None:
    """从文本中提取本子 ID.

    使用 jmcomic 包的正则表达式提取所有连续数字并连接。
    例如: "12级加里奥打出6417" -> "126417"

    Returns:
        提取到的 ID 字符串，如果找不到则返回 None
    """
    if not text:
        return None

    # 使用正则提取所有连续数字
    numbers = re.findall(r'\d+', text)
    if numbers:
        return ''.join(numbers)
    return None

# 项目根目录（支持环境变量覆盖）
# 在服务器部署时，可以通过环境变量指定路径
_env_root = os.environ.get("JMD_ROOT")
PROJECT_ROOT = Path(_env_root) if _env_root else Path(__file__).resolve().parent.parent.parent

# 配置文件路径（支持环境变量覆盖）
# 优先使用 JMD_CONFIG_DIR 指定的目录，否则使用项目根目录
_config_dir_env = os.environ.get("JMD_CONFIG_DIR")
if _config_dir_env:
    DEFAULT_CONFIG_PATH = Path(_config_dir_env) / "config.yml"
else:
    DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yml"

# 下载目录（支持环境变量覆盖）
_download_dir_env = os.environ.get("JMD_DOWNLOAD_DIR")
if _download_dir_env:
    DEFAULT_DOWNLOAD_DIR = Path(_download_dir_env)
else:
    DEFAULT_DOWNLOAD_DIR = PROJECT_ROOT / "downloads"

# ============================================================
# Web 模式检测：无持久化文件系统时自动启用临时目录模式
# ============================================================
_WEB_MODE = False
_WEB_TEMP_DIR = None


def is_web_mode() -> bool:
    """检测当前是否运行在 Web/无持久存储环境（如 Vercel）."""
    global _WEB_MODE, _WEB_TEMP_DIR
    if _WEB_TEMP_DIR is not None:
        return _WEB_MODE

    # 尝试在默认下载目录写入测试文件
    test_path = DEFAULT_DOWNLOAD_DIR / ".write_test"
    try:
        DEFAULT_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
        test_path.write_text("test", encoding="utf-8")
        test_path.unlink()
        _WEB_MODE = False
        return False
    except (OSError, PermissionError):
        # 写入失败 → 切换到临时目录模式
        _WEB_MODE = True
        _WEB_TEMP_DIR = tempfile.mkdtemp(prefix="jmd_web_")
        print(f"[Web Mode] 默认目录不可写，使用临时目录: {_WEB_TEMP_DIR}")
        return True


def get_download_dir() -> str:
    """返回下载根目录.

    Web 模式下自动回退到系统临时目录。
    """
    if is_web_mode():
        global _WEB_TEMP_DIR
        if _WEB_TEMP_DIR and os.path.isdir(_WEB_TEMP_DIR):
            return _WEB_TEMP_DIR
        # 临时目录被清理了，重新创建
        _WEB_TEMP_DIR = tempfile.mkdtemp(prefix="jmd_web_")
        return _WEB_TEMP_DIR
    return str(DEFAULT_DOWNLOAD_DIR)

# 线程本地存储，每个线程持有独立的 option/client
_tls = threading.local()


def get_default_config_path() -> str:
    """返回默认配置文件的绝对路径."""
    return str(DEFAULT_CONFIG_PATH)


def _ensure_default_config() -> str:
    """确保默认配置文件存在，不存在则创建一个."""
    global DEFAULT_CONFIG_PATH, DEFAULT_DOWNLOAD_DIR
    
    config_path = get_default_config_path()
    download_dir = get_download_dir()
    
    # 检查配置目录是否可写
    config_dir = os.path.dirname(config_path)
    if not os.access(config_dir, os.W_OK):
        # 尝试使用用户主目录
        user_home = os.path.expanduser("~")
        jmd_dir = os.path.join(user_home, ".jm_downloader")
        if not os.path.exists(jmd_dir):
            try:
                os.makedirs(jmd_dir)
            except Exception:
                # 用户目录也不可写，使用临时目录
                import tempfile
                jmd_dir = tempfile.mkdtemp(prefix="jm_downloader_")
        
        DEFAULT_CONFIG_PATH = Path(jmd_dir) / "config.yml"
        DEFAULT_DOWNLOAD_DIR = Path(jmd_dir) / "downloads"
        config_path = str(DEFAULT_CONFIG_PATH)
        download_dir = str(DEFAULT_DOWNLOAD_DIR)
    
    # 确保下载目录存在
    if not os.path.exists(download_dir):
        os.makedirs(download_dir, exist_ok=True)
    
    if not os.path.exists(config_path):
        default_option = JmOption.default()
        default_option.dir_rule.base_dir = download_dir
        # 关闭代理避免读到系统失效的代理地址
        default_option.client.postman.meta_data['proxies'] = None
        # 降低默认并发，提高稳定性（兼容不同版本）
        try:
            default_option.download_config.threading.image = 8
            default_option.download_config.threading.photo = 4
        except AttributeError:
            # 旧版本 jmcomic 使用字典方式
            try:
                default_option.download['threading']['image'] = 8
                default_option.download['threading']['photo'] = 4
            except Exception:
                pass
        default_option.to_file(config_path)

    # 每次启动都修复已知问题：代理 + 线程数
    option = create_option_by_file(config_path)
    needs_save = False

    # 安全关闭代理
    try:
        if option.client.postman.meta_data.get('proxies'):
            option.client.postman.meta_data['proxies'] = None
            needs_save = True
    except Exception:
        pass

    # 检测并修复下载目录路径问题
    try:
        current_base_dir = option.dir_rule.base_dir
        # 检查路径是否存在或不可写
        base_dir_path = Path(current_base_dir)
        if not base_dir_path.exists():
            # 路径不存在，尝试创建
            try:
                base_dir_path.mkdir(parents=True, exist_ok=True)
            except Exception:
                # 创建失败，使用默认目录
                option.dir_rule.base_dir = download_dir
                needs_save = True
        elif not os.access(str(base_dir_path), os.W_OK):
            # 路径不可写，使用默认目录
            option.dir_rule.base_dir = download_dir
            needs_save = True
    except Exception:
        pass

    # 降低默认并发数
    try:
        if option.download['threading']['image'] > 16:
            option.download['threading']['image'] = 8
            needs_save = True
    except Exception:
        pass
    try:
        if option.download['threading']['photo'] > 8:
            option.download['threading']['photo'] = 4
            needs_save = True
    except Exception:
        pass

    if needs_save:
        option.to_file(config_path)

    return config_path


def get_option(config_path: str | None = None) -> JmOption:
    """获取或创建 JmOption 实例（线程安全，每线程一个）.

    优先顺序: 指定路径 > 默认 config.yml > jmcomic 默认值
    """
    cache_key = f"_option_{config_path or 'default'}"

    # 如果当前线程已有缓存的 option，且配置路径未变，直接返回
    cached = getattr(_tls, cache_key, None)
    if cached is not None:
        return cached

    actual_path = config_path or _ensure_default_config()

    try:
        option = create_option_by_file(actual_path)
    except Exception:
        option = JmOption.default()

    # 确保下载目录存在
    os.makedirs(option.dir_rule.base_dir, exist_ok=True)

    setattr(_tls, cache_key, option)
    return option


def get_client(option: JmOption | None = None, impl: str | None = None):
    """获取 jmcomic 客户端实例（线程安全）."""
    if option is None:
        option = get_option()

    cache_key = f"_client_{impl or 'default'}"
    cached = getattr(_tls, cache_key, None)
    if cached is not None:
        return cached

    if impl:
        client = option.new_jm_client(impl=impl)
    else:
        client = option.new_jm_client()

    setattr(_tls, cache_key, client)
    return client


def clear_thread_cache():
    """清除当前线程的 option/client 缓存."""
    for attr in list(_tls.__dict__.keys()):
        delattr(_tls, attr)


def get_magic_constants() -> dict:
    """返回常用的 JmMagicConstants 值供前端使用."""
    # 使用 getattr 安全获取，避免版本差异导致的 AttributeError
    def _safe(name: str, default=None):
        return getattr(JmMagicConstants, name, default or name)

    return {
        "categories": {
            "CATEGORY_ALL": _safe("CATEGORY_ALL"),
            "CATEGORY_DOUJIN": _safe("CATEGORY_DOUJIN"),
            "CATEGORY_SINGLE": _safe("CATEGORY_SINGLE"),
            "CATEGORY_HANMAN": _safe("CATEGORY_HANMAN"),
            "CATEGORY_SHORT": _safe("CATEGORY_SHORT"),
            "CATEGORY_3D": _safe("CATEGORY_3D"),
        },
        "order_by": {
            "LATEST": _safe("ORDER_BY_LATEST"),
            "VIEW": _safe("ORDER_BY_VIEW"),
            "LIKE": _safe("ORDER_BY_LIKE"),
            "COMMENT": _safe("ORDER_BY_COMMENT"),
            "PICTURE": _safe("ORDER_BY_PICTURE"),
        },
        "time": {
            "ALL": _safe("TIME_ALL"),
            "TODAY": _safe("TIME_TODAY"),
            "WEEK": _safe("TIME_WEEK"),
            "MONTH": _safe("TIME_MONTH"),
        },
    }
