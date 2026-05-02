// ═══════════════════════════════════════════════════════════════════════════
// App Controller - Tab Switching and Initialization
// ═══════════════════════════════════════════════════════════════════════════

// ─── Help modal ─────────────────────────────────────────────────────────────

function openHelp() {
    document.getElementById('help-modal')?.classList.remove('hidden');
}

function closeHelp() {
    document.getElementById('help-modal')?.classList.add('hidden');
}

function handleHelpOverlayClick(e) {
    if (e.target === document.getElementById('help-modal')) closeHelp();
}

window.openHelp  = openHelp;
window.closeHelp = closeHelp;
window.handleHelpOverlayClick = handleHelpOverlayClick;

// Global keyboard shortcuts (help toggle + Esc)
document.addEventListener('keydown', (e) => {
    const modal = document.getElementById('help-modal');
    const isOpen = modal && !modal.classList.contains('hidden');

    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

    if (e.key === '?' || e.key === 'F1') {
        e.preventDefault();
        isOpen ? closeHelp() : openHelp();
        return;
    }

    if (e.key === 'Escape' && isOpen) {
        e.preventDefault();
        closeHelp();
    }
});

// ─── App initialisation ─────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    log('INFO', 'APP_CONTROLLER_INIT', {});

    // If the album has no pages yet, always land on Source tab
    const pending = localStorage.getItem('albumPending') === '1';
    if (typeof HAS_PAGES !== 'undefined' && !HAS_PAGES) {
        localStorage.setItem('albumPending', '1');
        localStorage.setItem('selectedTab', 'source');
    } else if (typeof HAS_PAGES !== 'undefined' && HAS_PAGES) {
        localStorage.removeItem('albumPending');
    }

    // Restore saved tab or default to source
    const savedTab = localStorage.getItem('selectedTab') || 'source';
    switchTab(savedTab);

    // Setup tab button listeners
    const albumTabBtn = document.getElementById('tab-album');
    const sourceTabBtn = document.getElementById('tab-source');

    if (albumTabBtn) {
        albumTabBtn.addEventListener('click', (e) => {
            e.preventDefault();
            switchTabAndInit('album');
        });
    }

    if (sourceTabBtn) {
        sourceTabBtn.addEventListener('click', (e) => {
            e.preventDefault();
            switchTabAndInit('source');
        });
    }

    document.getElementById('regenerate-album-header-btn')?.addEventListener('click', regenerateAlbumFromHeader);
    document.getElementById('undo-btn')?.addEventListener('click', performUndo);

    initPanelResize(document.getElementById('page-panel'), 'sidebar-width-pages');
    initPanelResize(document.getElementById('event-panel'), 'sidebar-width-events');
    initPanelResize(document.getElementById('album-sidebar'), 'sidebar-width-album-photos');
    initPanelResize(document.getElementById('source-sidebar'), 'sidebar-width-source-photos');

    // Initialize based on current tab
    switchTabAndInit(savedTab);
});

// Regenerate album from global header (works from any tab)
async function regenerateAlbumFromHeader() {
    if (typeof _regenInProgress !== 'undefined' && _regenInProgress) {
        showToast('Ya hay una generación en curso. Espera a que termine.', { type: 'warning' });
        return;
    }

    const btn = document.getElementById('regenerate-album-header-btn');
    let needsConfirm = false;

    try {
        const checkResponse = await fetch('/api/source/regenerate-album?check=true');
        const checkData = await checkResponse.json();
        needsConfirm = checkData.exists;
    } catch (e) {
        // Ignore check failures
    }

    if (needsConfirm) {
        const confirmed = await showConfirm({
            title: 'Regenerar álbum',
            message: t('confirm.regenerate_album')
        });
        if (!confirmed) return;
    }

    if (btn) btn.disabled = true;
    if (typeof showLoading === 'function') showLoading(t('loading.album'));

    try {
        const response = await fetch('/api/source/regenerate-album', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ confirm: needsConfirm })
        });

        const data = await response.json();

        if (data.success) {
            log('INFO', 'REGENERATE_ALBUM_HEADER_SUCCESS', {});
            window.location.reload();
        } else {
            log('ERROR', 'REGENERATE_ALBUM_HEADER_FAILED', { error: data.error });
            showToast(t('error.regenerate_album') + data.error, { type: 'error' });
            if (btn) btn.disabled = false;
        }
    } catch (error) {
        log('ERROR', 'REGENERATE_ALBUM_HEADER_EXCEPTION', { error: error.message });
        showToast(t('error.connection_regenerate_album'), { type: 'error' });
        if (btn) btn.disabled = false;
    } finally {
        if (typeof hideLoading === 'function') hideLoading();
    }
}

// Drag-to-resize for sidebar panels, with localStorage persistence.
// Pass { reverse: true } for right-side panels where dragging left grows the panel.
function initPanelResize(panel, storageKey, { reverse = false } = {}) {
    if (!panel) return;

    const handle = panel.querySelector('.panel-resize-handle');
    if (!handle) return;

    // For right-side panels the handle sits on the left edge
    if (reverse) {
        handle.style.left = '0';
        handle.style.right = 'auto';
    }

    const savedWidth = parseInt(localStorage.getItem(storageKey) || '', 10);
    if (!Number.isNaN(savedWidth) && savedWidth >= 180 && savedWidth <= 500) {
        panel.style.width = savedWidth + 'px';
    }

    let startX = 0;
    let startWidth = 0;

    function onMouseMove(e) {
        const delta = e.clientX - startX;
        let newWidth = reverse ? startWidth - delta : startWidth + delta;
        newWidth = Math.max(180, Math.min(500, newWidth));
        panel.style.width = newWidth + 'px';
    }

    function onMouseUp() {
        document.removeEventListener('mousemove', onMouseMove);
        document.removeEventListener('mouseup', onMouseUp);
        handle.classList.remove('dragging');
        document.body.style.cursor = '';
        document.body.style.userSelect = '';

        const width = parseInt(panel.style.width, 10);
        if (!Number.isNaN(width)) {
            localStorage.setItem(storageKey, String(width));
        }
    }

    handle.addEventListener('mousedown', (e) => {
        e.preventDefault();
        startX = e.clientX;
        startWidth = panel.getBoundingClientRect().width;
        handle.classList.add('dragging');
        document.body.style.cursor = 'ew-resize';
        document.body.style.userSelect = 'none';
        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
    });
}

// Switch tab and initialize the corresponding mode
async function switchTabAndInit(tabName) {
    // If switching to album tab with no pages, show an informative modal
    if (tabName === 'album' && typeof HAS_PAGES !== 'undefined' && !HAS_PAGES) {
        const confirmed = await showConfirm({
            title: 'No hay páginas generadas',
            message: 'Todavía no se han generado las páginas del álbum. ¿Quieres generar el álbum ahora a partir de las fotos de la fuente?',
            okLabel: 'Generar álbum',
            cancelLabel: 'Cancelar'
        });
        if (!confirmed) return;
        await regenerateAlbumFromHeader();
        return;
    }

    currentTab = tabName;

    // Update tab buttons
    const albumTabBtn = document.getElementById('tab-album');
    const sourceTabBtn = document.getElementById('tab-source');

    if (albumTabBtn) albumTabBtn.classList.toggle('active', tabName === 'album');
    if (sourceTabBtn) sourceTabBtn.classList.toggle('active', tabName === 'source');

    // Update tab content visibility
    const albumContent = document.getElementById('tab-album-content');
    const sourceContent = document.getElementById('tab-source-content');

    if (albumContent) albumContent.classList.toggle('active', tabName === 'album');
    if (sourceContent) sourceContent.classList.toggle('active', tabName === 'source');

    // Save preference
    localStorage.setItem('selectedTab', tabName);

    // Initialize the corresponding mode
    if (tabName === 'album' && typeof initAlbumMode === 'function') {
        log('INFO', 'SWITCHING_TO_ALBUM', {});
        initAlbumMode();
    } else if (tabName === 'source' && typeof initSourceMode === 'function') {
        log('INFO', 'SWITCHING_TO_SOURCE', {});
        initSourceMode();
    }

    log('INFO', 'TAB_SWITCHED', { tab: tabName });
}

// Global switchTab function for onclick
window.switchTab = switchTabAndInit;

// Open another folder (album switcher from header)
async function openAnotherFolder() {
    // Check for pending changes
    if (pendingChanges > 0) {
        const confirmed = await showConfirm({
            title: 'Descartar cambios',
            message: t('confirm.discard_changes'),
            danger: true
        });
        if (!confirmed) {
            return;
        }
    }
    
    const btn = document.getElementById('open-folder-btn');
    btn.disabled = true;
    
    // Create loading spinner
    const spinner = document.createElement('span');
    spinner.className = 'loading-spinner';
    btn.textContent = '';
    btn.appendChild(spinner);
    btn.appendChild(document.createTextNode(t('loading.dialog')));
    
    try {
        const response = await fetch('/api/pick-folder', { method: 'POST' });
        const data = await response.json();
        
        if (data.success && data.path) {
            await bootstrapNewFolder(data.path);
        } else {
            showToast(data.error || t('launcher.dialog_cancelled'), { type: 'error' });
            btn.disabled = false;
            btn.textContent = t('header.open_folder');
        }
    } catch (error) {
        showToast(`${t('launcher.connection_error')}${error.message}`, { type: 'error' });
        btn.disabled = false;
        btn.textContent = t('header.open_folder');
    }
}

async function bootstrapNewFolder(sourcePath) {
    const btn = document.getElementById('open-folder-btn');
    
    // Create loading spinner
    const spinner = document.createElement('span');
    spinner.className = 'loading-spinner';
    btn.textContent = '';
    btn.appendChild(spinner);
    btn.appendChild(document.createTextNode(t('loading.init')));
    
    try {
        const response = await fetch('/api/bootstrap', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ source_path: sourcePath })
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Persist the last opened album path
            localStorage.setItem('lastAlbumPath', sourcePath);
            // Reload the page to load the new workspace
            window.location.href = data.redirect;
        } else {
            showToast(data.error || t('launcher.init_error'), { type: 'error' });
            btn.disabled = false;
            btn.textContent = t('header.open_folder');
        }
    } catch (error) {
        showToast(`${t('launcher.connection_error')}${error.message}`, { type: 'error' });
        btn.disabled = false;
        btn.textContent = t('header.open_folder');
    }
}
