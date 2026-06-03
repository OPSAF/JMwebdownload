"""jmcomic client wrapper — 提供统一接口给 blueprint 调用."""

import os
import threading
from pathlib import Path

import jmcomic
from jmcomic import (
    JmOption,
    JmModuleConfig,
    JmHtmlClient,
    JmApiClient,
    JmMagicConstants,
    create_option_by_file,
)

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yml"
DEFAULT_DOWNLOAD_DIR = PROJECT_ROOT / "downloads"

# 线程本地存储，每个线程持有独立的 option/client
_tls = threading.local()


def get_default_config_path() -> str:
    """返回默认配置文件的绝对路径."""
    return str(DEFAULT_CONFIG_PATH)


def get_download_dir() -> str:
    """返回下载根目录."""
    return str(DEFAULT_DOWNLOAD_DIR)


def _ensure_default_config() -> str:
    """确保默认配置文件存在，不存在则创建一个."""
    config_path = get_default_config_path()
    if not os.path.exists(config_path):
        default_option = JmOption.default()
        default_option.dir_rule.base_dir = get_download_dir()
        # 关闭代理避免读到系统失效的代理地址
        default_option.client.postman.meta_data['proxies'] = None
        # 降低默认并发，提高稳定性
        default_option.download_config.threading.image = 8
        default_option.download_config.threading.photo = 4
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
