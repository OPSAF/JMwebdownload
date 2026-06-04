/* ========================================
   JM Downloader - 全局脚本
   ======================================== */

// ====== 主题切换 ======
(function () {
    const KEY = 'jmd-theme';
    const toggle = document.getElementById('themeToggle');
    if (!toggle) return;

    // 读取保存的主题或跟随系统
    const saved = localStorage.getItem(KEY);
    if (saved) {
        setTheme(saved);
    } else if (window.matchMedia('(prefers-color-scheme: light)').matches) {
        setTheme('light');
    }

    toggle.addEventListener('click', function () {
        const next = document.documentElement.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
        setTheme(next);
        localStorage.setItem(KEY, next);
    });

    function setTheme(mode) {
        document.documentElement.setAttribute('data-theme', mode);
    }
})();

// ====== Toast 通知 ======
function showToast(type, message, duration) {
    duration = duration || 3000;
    var container = document.getElementById('toastContainer');
    if (!container) return;

    var iconMap = { success: 'bi-check-circle-fill', error: 'bi-exclamation-triangle-fill', info: 'bi-info-circle-fill', warning: 'bi-exclamation-circle-fill' };
    var colorMap = { success: 'text-success', error: 'text-danger', info: 'text-info', warning: 'text-warning' };

    var html = '<div class="toast show" role="alert" aria-live="assertive" aria-atomic="true" style="min-width:280px">' +
        '<div class="toast-body d-flex align-items-center gap-2 py-2 px-3">' +
        '<i class="bi ' + (iconMap[type] || 'bi-info-circle') + ' ' + (colorMap[type] || '') + '" style="font-size:1.1rem"></i>' +
        '<span class="flex-1">' + message + '</span>' +
        '<button type="button" class="btn-close btn-close-white ms-auto" data-bs-dismiss="toast"></button>' +
        '</div></div>';

    var wrapper = document.createElement('div');
    wrapper.innerHTML = html;
    var el = wrapper.firstElementChild;
    container.appendChild(el);

    el.querySelector('.btn-close').addEventListener('click', function () {
        el.remove();
    });

    setTimeout(function () {
        if (el.parentNode) {
            el.classList.remove('show');
            setTimeout(function () { el.remove(); }, 200);
        }
    }, duration);
}

// ====== 任务追踪器 ======
function TaskTracker() {
    this.tasks = {};
}
TaskTracker.prototype.startTracking = function (taskId, title) {
    this.tasks[taskId] = title;
};

// ====== 快速下载（排行榜/搜索结果使用）=====
function quickDownload(albumId, title) {
    fetch('/download/api/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ album_id: albumId }),
    })
    .then(function (r) { return r.json(); })
    .then(function (result) {
        if (result.task_id) {
            showToast('success', '\u5DF2\u6DFB\u52A0\u4E0B\u8F7D: ' + (title || albumId));
            window.TaskManager && window.TaskManager.startTracking(result.task_id, title || albumId);
        } else {
            showToast('error', result.error || '\u4E0B\u8F7D\u5931\u8D25');
        }
    })
    .catch(function (e) {
        showToast('error', '\u8BF7\u6C42\u5931\u8D25: ' + e.message);
    });
}

// ====== Alpine.js Collapse 指令 ======
document.addEventListener('alpine:init', function () {
    Alpine.directive('collapse', function (el, { modifiers }) {
        // 基础实现：x-show + transition
    });
});
