// ═══════════════════════════════════════════════════════════════════════════
// Common Utilities for Album Editor
// ═══════════════════════════════════════════════════════════════════════════

// Debug logging system (shared across all modules)
const debugLog = [];
const MAX_LOG_ENTRIES = 500;

function log(level, action, details = {}) {
    const timestamp = new Date().toISOString();
    const entry = {
        timestamp,
        level,
        action,
        details
    };
    
    debugLog.push(entry);
    
    if (debugLog.length > MAX_LOG_ENTRIES) {
        debugLog.shift();
    }
    
    const prefix = `[${timestamp}] [${level}] [${action}]`;
    if (level === 'ERROR') {
        console.error(prefix, details);
    } else if (level === 'WARN') {
        console.warn(prefix, details);
    } else {
        console.log(prefix, details);
    }
}

function exportDebugLog() {
    const logText = debugLog.map(entry => 
        `${entry.timestamp} | ${entry.level.padEnd(5)} | ${entry.action.padEnd(20)} | ${JSON.stringify(entry.details)}`
    ).join('\n');
    
    const blob = new Blob([logText], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `editor-debug-${new Date().toISOString().replace(/:/g, '-')}.log`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    
    log('INFO', 'LOG_EXPORTED', { entries: debugLog.length });
}

function showDebugLog() {
    const overlay = document.createElement('div');
    overlay.style.cssText = 'position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.8); z-index: 10000; display: flex; align-items: center; justify-content: center;';
    
    const modal = document.createElement('div');
    modal.style.cssText = 'background: #1e1e1e; color: #d4d4d4; padding: 20px; border-radius: 12px; width: 80%; max-width: 1000px; max-height: 80%; overflow: auto; font-family: monospace;';
    
    const header = document.createElement('div');
    header.style.cssText = 'display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;';
    
    const title = document.createElement('h2');
    title.textContent = t ? t('loading.default') : 'Editor Debug Log';
    title.style.margin = '0';
    
    const closeBtn = document.createElement('button');
    closeBtn.textContent = t ? t('loading.default') : 'Cerrar';
    closeBtn.className = 'btn btn-secondary';
    closeBtn.onclick = () => document.body.removeChild(overlay);
    
    header.appendChild(title);
    header.appendChild(closeBtn);
    
    const logContainer = document.createElement('pre');
    logContainer.style.cssText = 'white-space: pre-wrap; word-wrap: break-word; font-size: 12px;';
    
    debugLog.forEach(entry => {
        const line = document.createElement('div');
        line.style.marginBottom = '4px';
        if (entry.level === 'ERROR') line.style.color = '#f48771';
        else if (entry.level === 'WARN') line.style.color = '#dcdcaa';
        else if (entry.level === 'INFO') line.style.color = '#4fc1ff';
        
        line.textContent = `${entry.timestamp} | ${entry.level.padEnd(5)} | ${entry.action.padEnd(20)} | ${JSON.stringify(entry.details)}`;
        logContainer.appendChild(line);
    });
    
    modal.appendChild(header);
    modal.appendChild(logContainer);
    overlay.appendChild(modal);
    document.body.appendChild(overlay);
}

// Theme Toggle
function setupThemeToggle() {
    const checkbox = document.getElementById('theme-toggle');
    
    let savedTheme = localStorage.getItem('editorTheme');
    
    if (!savedTheme) {
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        savedTheme = prefersDark ? 'dark' : 'light';
    }
    
    if (savedTheme === 'dark') {
        document.body.classList.add('dark-mode');
        checkbox.checked = true;
    } else {
        checkbox.checked = false;
    }
    
    checkbox.addEventListener('change', toggleTheme);
    
    log('INFO', 'THEME_INIT', { theme: savedTheme });
}

function toggleTheme() {
    const checkbox = document.getElementById('theme-toggle');
    const isDark = checkbox.checked;
    
    if (isDark) {
        document.body.classList.add('dark-mode');
    } else {
        document.body.classList.remove('dark-mode');
    }
    
    localStorage.setItem('editorTheme', isDark ? 'dark' : 'light');
    
    log('INFO', 'THEME_TOGGLED', { theme: isDark ? 'dark' : 'light' });
}

// Tab Switching
let currentTab = 'album';

function switchTab(tabName) {
    currentTab = tabName;
    
    // Update tab buttons
    document.getElementById('tab-album')?.classList.toggle('active', tabName === 'album');
    document.getElementById('tab-source')?.classList.toggle('active', tabName === 'source');
    
    // Update tab content
    document.getElementById('tab-album-content')?.classList.toggle('active', tabName === 'album');
    document.getElementById('tab-source-content')?.classList.toggle('active', tabName === 'source');
    
    // Save preference
    localStorage.setItem('selectedTab', tabName);
    
    log('INFO', 'TAB_SWITCHED', { tab: tabName });
}

// UI Helpers
function showLoading(message = 'Procesando...') {
    const overlay = document.getElementById('loading-overlay');
    if (overlay) {
        overlay.querySelector('p').textContent = message;
        overlay.style.display = 'flex';
    }
}

function hideLoading() {
    const overlay = document.getElementById('loading-overlay');
    if (overlay) {
        overlay.style.display = 'none';
    }
}

// API Fetch wrapper with error handling
async function apiCall(method, endpoint, body = null) {
    try {
        const options = {
            method,
            headers: { 'Content-Type': 'application/json' }
        };
        
        if (body) {
            options.body = JSON.stringify(body);
        }
        
        const response = await fetch(endpoint, options);
        const data = await response.json();
        
        return { success: response.ok, data, status: response.status };
    } catch (error) {
        log('ERROR', 'API_CALL_EXCEPTION', { method, endpoint, error: error.message });
        return { success: false, error: error.message, status: 0 };
    }
}

// Global init
document.addEventListener('DOMContentLoaded', () => {
    log('INFO', 'APP_INIT', {});
    
    setupThemeToggle();
    
    // Restore saved tab preference
    const savedTab = localStorage.getItem('selectedTab') || 'album';
    switchTab(savedTab);
    
    document.getElementById('debug-btn')?.addEventListener('click', showDebugLog);
});
