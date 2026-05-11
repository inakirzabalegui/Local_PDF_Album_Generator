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

    document.getElementById('reset-album-header-btn')?.addEventListener('click', regenerateAlbumFromHeader);
    document.getElementById('sync-album-header-btn')?.addEventListener('click', syncAlbumFromHeader);
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
            title: '⚠️ Reset álbum',
            message: 'Esto reconstruye el álbum desde cero. PERDERÁS:\n\n• Páginas dividas/movidas manualmente\n• Fotos eliminadas en el editor\n• Marcas de "completado"\n• Fotos destacadas/protagonistas\n• Captions y títulos editados\n• Layouts personalizados\n\nSi solo quieres añadir/quitar fotos del source, usa 🔄 Sincronizar.\n\n¿Continuar?'
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

// ── Sync (light, non-destructive) ────────────────────────────────────────────
async function syncAlbumFromHeader() {
    const btn = document.getElementById('sync-album-header-btn');
    if (btn) btn.disabled = true;
    if (typeof showLoading === 'function') showLoading('Calculando cambios…');

    let diff;
    try {
        const res = await fetch('/api/source/sync-album/preview', { method: 'POST' });
        const data = await res.json();
        if (!data.success) throw new Error(data.error || 'Error');
        diff = data.diff;
    } catch (e) {
        if (typeof hideLoading === 'function') hideLoading();
        showToast('Error calculando sync: ' + e.message, { type: 'error' });
        if (btn) btn.disabled = false;
        return;
    } finally {
        if (typeof hideLoading === 'function') hideLoading();
    }

    if (!diff.has_manifests) {
        showToast(
            'Este álbum se creó antes de la versión con sync. Usa Reset álbum para activar el modo sincronización.',
            { type: 'warning', duration: 8000 }
        );
        if (btn) btn.disabled = false;
        return;
    }

    const s = diff.summary;
    const totalChanges = s.added + s.removed + s.renamed + s.new_sections + s.removed_sections;

    // No source-side changes — but apply_sync's title-rebuild step still runs
    // and migrates legacy YAMLs (backfills sub_group_ids from the manifest,
    // reconstructs section_titles[1] for sub-grouped pages). Skip the confirm
    // dialog in this case; the user already clicked the Sincronizar button.
    if (totalChanges === 0) {
        showToast('Sin cambios desde origen — refrescando títulos y subtítulos…', { type: 'info' });
        if (typeof showGenerationModal === 'function') showGenerationModal();
        try {
            const response = await fetch('/api/source/sync-album/apply', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({}),
            });
            if (!response.ok) {
                const errData = await response.json().catch(() => ({}));
                throw new Error(errData.error || `HTTP ${response.status}`);
            }
            // Drain the SSE stream until done (no progress events expected
            // because there are no photos to add/remove).
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const parts = buffer.split('\n');
                buffer = parts.pop();
                for (const line of parts) {
                    if (!line.startsWith('data: ')) continue;
                    let event;
                    try { event = JSON.parse(line.slice(6)); } catch { continue; }
                    if (event.step === 'done') {
                        if (typeof hideGenerationModal === 'function') hideGenerationModal();
                        showToast('Títulos actualizados.', { type: 'success' });
                        setTimeout(() => window.location.reload(), 400);
                        return;
                    } else if (event.step === 'error') {
                        throw new Error(event.message || 'Error desconocido');
                    }
                }
            }
            // Stream ended without explicit done — reload anyway.
            if (typeof hideGenerationModal === 'function') hideGenerationModal();
            window.location.reload();
        } catch (e) {
            if (typeof hideGenerationModal === 'function') hideGenerationModal();
            showToast('Error refrescando títulos: ' + e.message, { type: 'error' });
            if (btn) btn.disabled = false;
        }
        return;
    }

    const lines = [];
    if (s.added) lines.push(`✚ ${s.added} foto(s) añadida(s)`);
    if (s.removed) lines.push(`✖ ${s.removed} foto(s) eliminada(s)`);
    if (s.renamed) lines.push(`✎ ${s.renamed} sección(es) renombrada(s)`);
    if (s.new_sections) lines.push(`＋ ${s.new_sections} sección(es) nueva(s)`);
    if (s.removed_sections) lines.push(`✖ ${s.removed_sections} sección(es) eliminada(s)`);

    const detailsBlocks = [];
    if (diff.renamed_sections.length) {
        detailsBlocks.push('Renombradas:\n' + diff.renamed_sections.map(r => `  "${r.old_title}" → "${r.new_title}"`).join('\n'));
    }
    if (diff.new_sections.length) {
        detailsBlocks.push('Nuevas:\n' + diff.new_sections.map(n => `  "${n.title}" (${n.photo_count} fotos)`).join('\n'));
    }
    if (diff.removed_sections.length) {
        detailsBlocks.push('Eliminadas:\n' + diff.removed_sections.map(r => `  "${r.title}" (${r.page_count} págs)`).join('\n'));
    }

    const message = '🔄 Sincronizar workspace con source\n\n' + lines.join('\n') +
        (detailsBlocks.length ? '\n\n' + detailsBlocks.join('\n\n') : '') +
        '\n\nSe preservan splits, completados, destacadas y otras ediciones.\n\n¿Aplicar?';

    const confirmed = await showConfirm({ title: 'Sincronizar álbum', message });
    if (!confirmed) {
        if (btn) btn.disabled = false;
        return;
    }

    // Apply via SSE
    if (typeof showGenerationModal === 'function') showGenerationModal();

    try {
        const response = await fetch('/api/source/sync-album/apply', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({}),
        });
        if (!response.ok) {
            const errData = await response.json().catch(() => ({}));
            throw new Error(errData.error || `HTTP ${response.status}`);
        }
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const parts = buffer.split('\n');
            buffer = parts.pop();
            for (const line of parts) {
                if (!line.startsWith('data: ')) continue;
                let event;
                try { event = JSON.parse(line.slice(6)); } catch { continue; }
                if (event.step === 'removing_photos') {
                    if (typeof _setGenStep === 'function') _setGenStep(`Eliminando fotos…`);
                    if (typeof _setGenProgress === 'function') _setGenProgress(event.current || 0, event.total || 0);
                } else if (event.step === 'adding_photos') {
                    if (typeof _setGenStep === 'function') _setGenStep('Añadiendo fotos…');
                    if (typeof _setGenProgress === 'function') _setGenProgress(event.current || 0, event.total || 0);
                } else if (event.step === 'adding_sections') {
                    if (typeof _setGenStep === 'function') _setGenStep('Creando secciones nuevas…');
                    if (typeof _setGenProgress === 'function') _setGenProgress(event.current || 0, event.total || 0);
                } else if (event.step === 'done') {
                    if (typeof hideGenerationModal === 'function') hideGenerationModal();
                    showToast('Sincronización completada', { type: 'success' });
                    setTimeout(() => window.location.reload(), 400);
                    return;
                } else if (event.step === 'error') {
                    throw new Error(event.message || 'Error desconocido');
                }
            }
        }
    } catch (e) {
        if (typeof hideGenerationModal === 'function') hideGenerationModal();
        showToast('Error en sync: ' + e.message, { type: 'error' });
    } finally {
        if (btn) btn.disabled = false;
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
