/** JM Downloader Web — 全局 JS 工具函数 */


// ============================================================
// ThemeSwitcher — 双主题切换器 (localStorage 持久化)
// ============================================================

const ThemeSwitcher = {
    STORAGE_KEY: 'jmd-theme',
    DEFAULT_THEME: 'light',

    init() {
        const saved = localStorage.getItem(this.STORAGE_KEY);
        const theme = saved || this.DEFAULT_THEME;
        this.apply(theme);

        const toggleBtn = document.getElementById('themeToggle');
        if (toggleBtn) {
            toggleBtn.addEventListener('click', () => this.toggle());
        }

        // 监听系统主题偏好变化
        if (window.matchMedia) {
            window.matchMedia('(prefers-color-scheme: dark)')
                .addEventListener('change', (e) => {
                    if (!localStorage.getItem(this.STORAGE_KEY)) {
                        this.apply(e.matches ? 'dark' : 'light');
                    }
                });
        }
    },

    apply(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem(this.STORAGE_KEY, theme);
    },

    toggle() {
        const current = document.documentElement.getAttribute('data-theme') || this.DEFAULT_THEME;
        const next = current === 'light' ? 'dark' : 'light';
        this.apply(next);
    },

    get() {
        return document.documentElement.getAttribute('data-theme') || this.DEFAULT_THEME;
    }
};


// ============================================================
// Toast 通知
// ============================================================

function showToast(type, message) {
    const container = document.getElementById('toastContainer');
    if (!container) return;

    const id = 'toast-' + Date.now();
    const icons = { success: 'bi-check-circle-fill text-success',
                    error: 'bi-exclamation-circle-fill text-danger',
                    warning: 'bi-exclamation-triangle-fill text-warning',
                    info: 'bi-info-circle-fill text-info' };

    const html = `
        <div id="${id}" class="toast align-items-center border-secondary" role="alert">
            <div class="d-flex">
                <div class="toast-body d-flex align-items-center gap-2">
                    <i class="bi ${icons[type] || icons.info}"></i>
                    <span>${escapeHtml(message)}</span>
                </div>
                <button class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        </div>
    `;

    container.insertAdjacentHTML('beforeend', html);
    const toastEl = document.getElementById(id);
    const toast = new bootstrap.Toast(toastEl, { delay: 4000 });
    toast.show();

    // 自动移除 DOM
    toastEl.addEventListener('hidden.bs.toast', () => toastEl.remove());
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}


// ============================================================
// 任务追踪器 (用于 SSE 进度推送)
// ============================================================

class TaskTracker {
    constructor() {
        this.eventSources = {};  // task_id -> EventSource
    }

    /**
     * 开始追踪任务进度
     * @param {string} taskId
     * @param {string} title  显示用标题
     */
    startTracking(taskId, title) {
        if (this.eventSources[taskId]) return;  // 已在追踪

        const es = new EventSource(`/download/api/tasks/${taskId}/progress`);
        this.eventSources[taskId] = es;

        es.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);

                if (data.event === 'done') {
                    console.log(`[TaskTracker] ${taskId} done: ${data.status}`);
                    this.showNotification(taskId, title, data.status);
                    es.close();
                    delete this.eventSources[taskId];
                    // 刷新任务列表
                    this.refreshTaskList();
                    return;
                }

                // 更新进度显示
                this.updateTaskCard(taskId, data);
            } catch (e) {
                console.error('[TaskTracker] parse error:', e);
            }
        };

        es.onerror = () => {
            console.error(`[TaskTracker] SSE error for ${taskId}`);
            // 立即重试一次
            es.close();
            delete this.eventSources[taskId];
            setTimeout(() => {
                if (!this.eventSources[taskId]) {
                    this.startTracking(taskId, title);
                }
            }, 2000);
        };

        console.log(`[TaskTracker] tracking ${taskId}`);
    }

    stopTracking(taskId) {
        const es = this.eventSources[taskId];
        if (es) {
            es.close();
            delete this.eventSources[taskId];
        }
    }

    showNotification(taskId, title, status) {
        if (status === 'completed') {
            showToast('success', `下载完成: ${title || taskId}`);
        } else if (status === 'failed') {
            showToast('error', `下载失败: ${title || taskId}`);
        }
    }

    updateTaskCard(taskId, data) {
        // 尝试更新页面上的任务卡片（如果存在）
        const card = document.getElementById(`task-${taskId}`);
        if (!card) return;

        // 更新进度条
        const progressBar = card.querySelector('.progress-bar');
        if (progressBar && data.image_percent !== undefined) {
            progressBar.style.width = data.image_percent + '%';
        }

        // 更新状态文字
        const statusBadge = card.querySelector('.badge');
        if (statusBadge && data.status) {
            const statusMap = {
                'pending': '等待',
                'running': '初始化',
                'processing': '下载中',
                'completed': '完成',
                'failed': '失败',
                'cancelled': '已取消',
            };
            statusBadge.textContent = statusMap[data.status] || data.status;
        }
    }

    refreshTaskList() {
        // 触发 HTMX 重新请求任务列表
        const container = document.getElementById('task-list-container');
        if (container) {
            htmx.trigger(container, 'htmx-get');
        }
    }
}

// 全局单例
window.TaskManager = new TaskTracker();


// ============================================================
// HTMX 扩展：发送 Toast 作为 server-sent event
// ============================================================

document.body.addEventListener('htmx:beforeSwap', function(evt) {
    // 检查响应头中是否有自定义 toast 信息
    const toastType = evt.detail.xhr.getResponseHeader('X-Toast-Type');
    const toastMsg = evt.detail.xhr.getResponseHeader('X-Toast-Message');
    if (toastType && toastMsg) {
        showToast(toastType, toastMsg);
    }
});


// ============================================================
// 全局：页面离开确认
// ============================================================

window.addEventListener('beforeunload', function(e) {
    // 检查是否有进行中的下载
    const activeTasks = document.querySelectorAll('.task-card .badge.bg-primary, .task-card .badge.bg-info');
    if (activeTasks.length > 0) {
        e.preventDefault();
        e.returnValue = '有下载任务正在进行中，确定离开吗？';
    }
});


// ============================================================
// 初始化
// ============================================================

ThemeSwitcher.init();
console.log('JM Downloader Web — ready 🚀 | Theme: ' + ThemeSwitcher.get());
