# JM Downloader

基于 **Flask + htmx + Alpine.js** 的禁漫下载管理器 Web 应用。

## ✨ 功能特性

- 🔍 **搜索浏览** - 支持关键词搜索、分类筛选、热门排行榜
- 📥 **下载管理** - 批量下载、断点续传、实时进度追踪
- 📁 **文件浏览** - 本地图库管理、批量导出
- 🔖 **书签管理** - 本地书签收藏、标签分类、导入导出
- 🎨 **现代化UI** - 响应式设计、明暗主题切换、看板娘

## 🚀 快速开始

### 环境要求

- Python 3.8+
- pip 包管理工具

### 安装依赖

```bash
pip install -r requirements.txt
```

### 运行应用

```bash
# 开发模式
python app.py

# 或设置环境变量
DEBUG=true python app.py
```

应用将在 `http://localhost:5000` 启动。

### 配置说明

配置文件为 `config.yml`，首次运行会自动生成。

```yaml
# 下载目录
download_dir: downloads/

# 并发下载数
max_concurrent_downloads: 3

# 超时设置（秒）
timeout: 30

# 代理设置（可选）
proxy:
  enabled: false
  http: ""
  https: ""
```

## 📁 项目结构

```
JM Downloader/
├── app.py                    # 应用入口
├── requirements.txt          # 依赖列表
├── config.yml                # 配置文件
├── .gitignore               # Git 忽略配置
├── static/                  # 静态资源
│   ├── css/
│   └── js/
└── jm_web/                  # 应用代码
    ├── __init__.py
    ├── blueprints/          # Flask 蓝图
    │   ├── search.py        # 搜索浏览
    │   ├── download.py      # 下载管理
    │   ├── files.py         # 文件浏览
    │   ├── favorites.py     # 书签管理
    │   └── config_bp.py     # 配置管理
    ├── services/            # 服务层
    │   ├── jm_client.py     # JM Comic 客户端
    │   ├── downloader.py    # 下载器服务
    │   └── bookmarks.py     # 书签服务
    └── templates/           # Jinja2 模板
        ├── base.html        # 基础模板
        ├── index.html       # 首页
        ├── browse.html      # 搜索浏览页
        ├── album.html       # 本子详情页
        ├── download.html    # 下载管理页
        ├── files.html       # 文件浏览页
        ├── favorites.html   # 书签管理页
        ├── config.html      # 配置页
        └── partials/        # 部分模板
```

## 🎯 使用说明

### 搜索浏览

1. 在首页或搜索页面输入关键词
2. 支持按时间（今日/本周/本月/全部）筛选
3. 支持按观看/点赞/最新排序

### 下载管理

1. 点击本子详情页的下载按钮
2. 或在列表中点击下载图标
3. 支持批量添加下载任务

### 书签管理

1. 在本子详情页添加书签
2. 支持添加标签分类
3. 支持批量下载书签中的本子

## 🔧 技术栈

- **后端**: Flask 2.0+
- **前端**: htmx, Alpine.js, Bootstrap 5
- **漫画引擎**: jmcomic
- **图标**: Bootstrap Icons

## 📝 License

MIT License

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

---

⭐ 如果这个项目对你有帮助，请给个 Star！
