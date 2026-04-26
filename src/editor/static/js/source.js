// ═══════════════════════════════════════════════════════════════════════════
// Source Photos Mode Logic
// ═══════════════════════════════════════════════════════════════════════════

let currentEventIndex = 0;
let currentEventFolder = null;
let eventFolders = [];
let currentEventPhotos = [];
let selectedSourcePhoto = null;
let eventPanelOpen = true;
let eventPanelFocused = false;
let sourcePhotoListFocused = false;
let sourceSortableInstance = null;
let draggingSourceFilenames = [];
let _crossEventDropHandled = false;

// Initialize source mode when tab is active
async function initSourceMode() {
    log('INFO', 'SOURCE_MODE_INIT', {});

    await loadEventFolders();
    setupSourceEventListeners();

    if (eventFolders.length > 0) {
        await loadEvent(0);
    }
}

function setupSourceEventListeners() {
    document.getElementById('delete-source-photo-btn')?.addEventListener('click', deleteSourcePhoto);
    document.getElementById('rename-event-btn')?.addEventListener('click', renameEvent);
    document.getElementById('control-event-btn')?.addEventListener('click', deleteEvent);

    document.addEventListener('keydown', handleSourceKeyboard);
}

// ── Generation button label ──────────────────────────────────────────────────
function updateRegenBtnLabel() {
    const btn = document.getElementById('source-regen-btn');
    if (!btn) return;
    const isPending = typeof HAS_PAGES !== 'undefined' && !HAS_PAGES;
    btn.textContent = isPending ? '📷 Generar álbum' : '🔄 Regenerar álbum';
    if (isPending) {
        btn.classList.add('cta-pending');
    } else {
        btn.classList.remove('cta-pending');
    }
}

function handleSourceKeyboard(e) {
    if (currentTab !== 'source') return;
    
    if (e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
        if (e.key === 'ArrowLeft') {
            if (sourcePhotoListFocused) {
                e.preventDefault();
                focusEventPanel();
            }
        } else if (e.key === 'ArrowRight') {
            if (eventPanelFocused) {
                e.preventDefault();
                focusSourcePhotoList();
            }
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            if (eventPanelFocused && eventPanelOpen) {
                navigateEventPanelSelection(-1);
            } else {
                navigateSourcePhotoSelection(-1);
            }
        } else if (e.key === 'ArrowDown') {
            e.preventDefault();
            if (eventPanelFocused && eventPanelOpen) {
                navigateEventPanelSelection(1);
            } else {
                navigateSourcePhotoSelection(1);
            }
        } else if (e.key === 'd' || e.key === 'D') {
            if (selectedSourcePhoto) deleteSourcePhoto();
        }
    }
}

function focusEventPanel() {
    sourcePhotoListFocused = false;
    eventPanelFocused = true;
    document.getElementById('source-sidebar')?.classList.remove('panel-has-focus');
    document.getElementById('event-panel')?.classList.add('panel-has-focus');

    const items = document.querySelectorAll('#event-panel .page-list-item');
    items.forEach((item, i) => {
        item.classList.toggle('keyboard-focus', i === currentEventIndex);
    });
    items[currentEventIndex]?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function focusSourcePhotoList() {
    eventPanelFocused = false;
    sourcePhotoListFocused = true;
    document.getElementById('event-panel')?.classList.remove('panel-has-focus');
    document.getElementById('source-sidebar')?.classList.add('panel-has-focus');

    const items = document.querySelectorAll('#source-photo-list .photo-item');
    if (items.length === 0) return;
    const alreadySelected = Array.from(items).find(i => i.classList.contains('selected'));
    if (alreadySelected) {
        alreadySelected.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    } else {
        const first = items[0];
        selectSourcePhoto(first.dataset.filename, first);
        first.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
}

// Load list of event folders
async function loadEventFolders() {
    log('INFO', 'LOAD_EVENT_FOLDERS_START', {});
    
    try {
        const response = await fetch('/api/source/folders');
        const data = await response.json();
        
        if (data.success) {
            eventFolders = data.folders || [];
            log('INFO', 'LOAD_EVENT_FOLDERS_SUCCESS', { count: eventFolders.length });
            initEventPanel();
        } else {
            log('ERROR', 'LOAD_EVENT_FOLDERS_FAILED', { error: data.error });
            showToast(t('error.load_folders') + data.error, { type: 'error' });
        }
    } catch (error) {
        log('ERROR', 'LOAD_EVENT_FOLDERS_EXCEPTION', { error: error.message });
        showToast(t('error.connection_load_folders'), { type: 'error' });
    }
}

// Load a specific event folder
async function loadEvent(index) {
    if (index < 0 || index >= eventFolders.length) {
        log('WARN', 'LOAD_EVENT_INVALID', { index });
        return;
    }
    
    currentEventIndex = index;
    currentEventFolder = eventFolders[index];
    
    log('INFO', 'LOAD_EVENT_START', { folder: currentEventFolder.name });
    
    try {
        const response = await fetch(`/api/source/folder/${currentEventFolder.name}`);
        const data = await response.json();
        
        if (data.success) {
            const event = data.folder;
            currentEventPhotos = event.photos || [];
            
            log('INFO', 'LOAD_EVENT_SUCCESS', { photoCount: currentEventPhotos.length });
            renderSourceEventDetails(event);
            updateEventPanelActiveItem(index);
        } else {
            log('ERROR', 'LOAD_EVENT_FAILED', { error: data.error });
            showToast(t('error.load_event') + data.error, { type: 'error' });
        }
    } catch (error) {
        log('ERROR', 'LOAD_EVENT_EXCEPTION', { error: error.message });
        showToast(t('error.connection_load_event'), { type: 'error' });
    }
}

// Render event details in sidebar
function renderSourceEventDetails(event) {
    const photoList = document.getElementById('source-photo-list');
    if (!photoList) return;

    photoList.textContent = '';

    currentEventPhotos.forEach((filename, idx) => {
        const div = document.createElement('div');
        div.className = 'photo-item';
        div.dataset.filename = filename;
        div.dataset.index = idx;

        const dragHandle = document.createElement('span');
        dragHandle.className = 'drag-handle';
        dragHandle.textContent = '☰';

        const span = document.createElement('span');
        span.className = 'photo-name';
        span.textContent = filename;

        div.appendChild(dragHandle);
        div.appendChild(span);
        div.addEventListener('click', (e) => selectSourcePhoto(filename, e.target.closest('.photo-item')));

        photoList.appendChild(div);
    });

    // In-memory reorder via SortableJS
    if (sourceSortableInstance) {
        sourceSortableInstance.destroy();
    }
    sourceSortableInstance = Sortable.create(photoList, {
        animation: 150,
        handle: '.drag-handle',
        ghostClass: 'sortable-ghost',
        setData(dataTransfer, dragEl) {
            // Expose dragged filename(s) so event-panel drop targets can read them
            const filename = dragEl.dataset.filename;
            const selected = Array.from(photoList.querySelectorAll('.photo-item.selected'))
                .map(el => el.dataset.filename);
            draggingSourceFilenames = selected.includes(filename) ? selected : [filename];
            dataTransfer.setData('text/plain', JSON.stringify(draggingSourceFilenames));
        },
        onEnd(evt) {
            if (_crossEventDropHandled) {
                _crossEventDropHandled = false;
                draggingSourceFilenames = [];
                return;
            }
            // Sync in-memory order from DOM
            currentEventPhotos = Array.from(photoList.querySelectorAll('.photo-item'))
                .map(el => el.dataset.filename);
            draggingSourceFilenames = [];
        },
    });

    if (currentEventPhotos.length > 0) {
        selectSourcePhoto(currentEventPhotos[0], document.querySelector('#source-photo-list .photo-item'));
    }
}

// Select a source photo and display it
function selectSourcePhoto(filename, element) {
    document.querySelectorAll('#source-photo-list .photo-item').forEach(item => {
        item.classList.remove('selected');
    });
    
    if (element) {
        element.classList.add('selected');
    }
    
    selectedSourcePhoto = filename;
    
    document.getElementById('delete-source-photo-btn').disabled = false;
    
    // Load and display the image
    const imagePath = encodeURIComponent(currentEventFolder.path + '/' + filename);
    const img = document.getElementById('source-image-viewer');
    if (img) {
        img.src = `/api/source/image?path=${imagePath}`;
    }
}

// Delete a source photo
async function deleteSourcePhoto() {
    if (!selectedSourcePhoto || !currentEventFolder) {
        return;
    }

    try {
        const response = await fetch(`/api/source/folder/${currentEventFolder.name}/photo`, {
            method: 'DELETE',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ filename: selectedSourcePhoto })
        });

        const data = await response.json();

        if (data.success) {
            log('INFO', 'DELETE_SOURCE_PHOTO_SUCCESS', { trash_token: data.trash_token });
            if (data.trash_token && typeof pushUndoState === 'function') {
                pushUndoState('delete_source_photo', {
                    trash_token: data.trash_token,
                    event_index: currentEventIndex,
                });
            }
            selectedSourcePhoto = null;
        } else {
            log('ERROR', 'DELETE_SOURCE_PHOTO_FAILED', { error: data.error });
            showToast(t('error.delete_source_photo') + data.error, { type: 'error' });
        }
    } catch (error) {
        log('ERROR', 'DELETE_SOURCE_PHOTO_EXCEPTION', { error: error.message });
        showToast(t('error.connection_delete_source_photo'), { type: 'error' });
    }

    await loadEvent(currentEventIndex);
}

// Rename event folder
async function renameEvent() {
    if (!currentEventFolder) {
        return;
    }

    const current = currentEventFolder.name || '';
    const input = await showPrompt({
        title: 'Renombrar evento',
        message: 'Nuevo nombre del evento:',
        defaultValue: current
    });
    if (input === null) return;
    const newName = input.trim();

    if (!newName) {
        showToast(t('validation.event_name_empty'), { type: 'warning' });
        return;
    }
    if (newName === current) return;

    log('INFO', 'RENAME_EVENT_START', { newName });
    
    try {
        const response = await fetch(`/api/source/folder/${currentEventFolder.name}/rename`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ new_name: newName })
        });
        
        const data = await response.json();
        
        if (data.success) {
            log('INFO', 'RENAME_EVENT_SUCCESS', {});
            showToast(t('success.event_renamed'), { type: 'success' });
            await loadEventFolders();
            if (currentEventIndex < eventFolders.length) {
                await loadEvent(currentEventIndex);
            }
        } else {
            log('ERROR', 'RENAME_EVENT_FAILED', { error: data.error });
            showToast(t('error.rename_event') + data.error, { type: 'error' });
        }
    } catch (error) {
        log('ERROR', 'RENAME_EVENT_EXCEPTION', { error: error.message });
        showToast(t('error.connection_rename_event'), { type: 'error' });
    }
}

// Delete event folder
async function deleteEvent() {
    if (!currentEventFolder) {
        return;
    }

    try {
        const response = await fetch(`/api/source/folder/${currentEventFolder.name}?force=true`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        if (data.success) {
            log('INFO', 'DELETE_EVENT_SUCCESS', { trash_token: data.trash_token });
            if (data.trash_token && typeof pushUndoState === 'function') {
                pushUndoState('delete_source_folder', {
                    trash_token: data.trash_token,
                    folder_name: currentEventFolder.name,
                });
            }
            showToast(t('success.event_deleted'), { type: 'success' });
            await loadEventFolders();
            if (eventFolders.length > 0) {
                await loadEvent(0);
            }
        } else {
            log('ERROR', 'DELETE_EVENT_FAILED', { error: data.error });
            showToast(t('error.delete_event') + data.error, { type: 'error' });
        }
    } catch (error) {
        log('ERROR', 'DELETE_EVENT_EXCEPTION', { error: error.message });
        showToast(t('error.connection_delete_event'), { type: 'error' });
    }
}

// ── Progress modal helpers ───────────────────────────────────────────────────
function showGenerationModal() {
    const modal = document.getElementById('generation-modal');
    if (modal) modal.classList.remove('hidden');
    _setGenStep('Iniciando…');
    _setGenProgress(0, 0);
    document.getElementById('gen-modal-filename').textContent = '';
}

function hideGenerationModal() {
    const modal = document.getElementById('generation-modal');
    if (modal) modal.classList.add('hidden');
}

function _setGenStep(label) {
    const el = document.getElementById('gen-modal-step');
    if (el) el.textContent = label;
}

function _setGenProgress(current, total) {
    const bar = document.getElementById('gen-progress-bar');
    const counter = document.getElementById('gen-modal-counter');
    const pct = total > 0 ? Math.round((current / total) * 100) : 0;
    if (bar) bar.style.width = pct + '%';
    if (counter) counter.textContent = total > 0 ? `${current} / ${total}` : '';
}

// Track whether a regeneration is in flight
let _regenInProgress = false;

// Regenerate album with streaming progress
async function regenerateAlbum() {
    if (_regenInProgress) {
        showToast('Ya hay una generación en curso. Espera a que termine.', { type: 'warning' });
        return;
    }

    const hasPagesNow = typeof HAS_PAGES !== 'undefined' ? HAS_PAGES : true;
    let needsConfirm = false;

    if (hasPagesNow) {
        needsConfirm = true;
        const confirmed = await showConfirm({
            title: 'Regenerar álbum',
            message: t('confirm.regenerate_album')
        });
        if (!confirmed) return;
    }

    _regenInProgress = true;
    const btn = document.getElementById('source-regen-btn');
    if (btn) btn.disabled = true;

    showGenerationModal();

    try {
        const response = await fetch('/api/source/regenerate-album/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ confirm: needsConfirm }),
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
            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;
                let event;
                try { event = JSON.parse(line.slice(6)); } catch { continue; }

                if (event.step === 'scanning') {
                    _setGenStep('Escaneando fotos…');
                    _setGenProgress(0, 0);
                } else if (event.step === 'sorting') {
                    _setGenStep(`Ordenando ${event.total} fotos…`);
                    _setGenProgress(0, event.total);
                } else if (event.step === 'processing') {
                    _setGenStep('Procesando fotos…');
                    _setGenProgress(event.current, event.total);
                    const fnEl = document.getElementById('gen-modal-filename');
                    if (fnEl) fnEl.textContent = event.name || '';
                } else if (event.step === 'writing_configs') {
                    _setGenStep('Escribiendo configuración…');
                } else if (event.step === 'done') {
                    log('INFO', 'REGENERATE_ALBUM_STREAM_DONE', {});
                    hideGenerationModal();

                    // Update local pages data
                    if (event.pages) {
                        PAGES_DATA.length = 0;
                        PAGES_DATA.push(...event.pages);
                    }

                    // Clear pending state and refresh
                    localStorage.removeItem('albumPending');
                    showToast(t('success.album_regenerated'), { type: 'success' });

                    // Switch to Edición tab so user can see the pages
                    if (typeof switchTabAndInit === 'function') {
                        switchTabAndInit('album');
                    } else {
                        window.location.reload();
                    }
                    return;
                } else if (event.step === 'error') {
                    throw new Error(event.message || 'Error desconocido');
                }
            }
        }
    } catch (error) {
        log('ERROR', 'REGENERATE_ALBUM_STREAM_ERROR', { error: error.message });
        hideGenerationModal();
        showToast((t('error.regenerate_album') || 'Error: ') + error.message, { type: 'error' });
    } finally {
        _regenInProgress = false;
        if (btn) btn.disabled = false;
    }
}

// Navigate photo selection
function navigateSourcePhotoSelection(delta) {
    const items = Array.from(document.querySelectorAll('#source-photo-list .photo-item'));
    if (items.length === 0) return;
    
    const currentIndex = items.findIndex(item => item.classList.contains('selected'));
    
    let newIndex;
    if (currentIndex === -1) {
        newIndex = delta > 0 ? 0 : items.length - 1;
    } else {
        newIndex = currentIndex + delta;
    }
    
    if (newIndex >= 0 && newIndex < items.length) {
        const newItem = items[newIndex];
        const filename = newItem.dataset.filename;
        selectSourcePhoto(filename, newItem);
        newItem.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Event Navigator Panel
// ═══════════════════════════════════════════════════════════════════════════

function initEventPanel() {
    const eventList = document.getElementById('event-list');
    if (!eventList) return;

    eventList.textContent = '';

    eventFolders.forEach((event, index) => {
        const item = document.createElement('div');
        item.className = 'page-list-item';
        item.dataset.index = index;
        item.dataset.folderName = event.name;

        const nameSpan = document.createElement('span');
        nameSpan.className = 'page-list-title';
        nameSpan.textContent = event.name || event.folder;
        nameSpan.style.flex = '1';

        const countSpan = document.createElement('span');
        countSpan.className = 'page-list-num';
        countSpan.id = `event-count-${index}`;
        countSpan.textContent = String(event.photo_count || 0);

        item.appendChild(countSpan);
        item.appendChild(nameSpan);

        item.addEventListener('click', () => loadEvent(index));

        // Drop target: accept dragged source photos
        item.addEventListener('dragover', (e) => {
            if (!sourceSortableInstance) return;
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            document.querySelectorAll('#event-panel .page-list-item').forEach(el => el.classList.remove('drag-over'));
            if (index !== currentEventIndex) item.classList.add('drag-over');
        });
        item.addEventListener('dragleave', () => item.classList.remove('drag-over'));
        item.addEventListener('drop', (e) => {
            e.preventDefault();
            item.classList.remove('drag-over');
            if (index === currentEventIndex) return;
            const filenames = JSON.parse(e.dataTransfer.getData('text/plain') || '[]');
            if (filenames.length) {
                _crossEventDropHandled = true;
                moveSourcePhotosToEvent(filenames, index);
            }
        });

        eventList.appendChild(item);
    });

    const panel = document.getElementById('event-panel');
    if (panel) {
        panel.addEventListener('mouseenter', () => { eventPanelFocused = true; });
        panel.addEventListener('mouseleave', () => {
            eventPanelFocused = false;
            document.querySelectorAll('#event-panel .page-list-item').forEach(el => el.classList.remove('drag-over'));
        });
    }

    const sourceSidebar = document.getElementById('source-sidebar');
    if (sourceSidebar && !sourceSidebar.dataset.focusWired) {
        sourceSidebar.addEventListener('mouseenter', () => { sourcePhotoListFocused = true; });
        sourceSidebar.addEventListener('mouseleave', () => { sourcePhotoListFocused = false; });
        sourceSidebar.dataset.focusWired = '1';
    }

    log('INFO', 'EVENT_PANEL_INIT', { events: eventFolders.length });
}

// Move selected source photos to a different event folder
async function moveSourcePhotosToEvent(filenames, targetEventIndex) {
    const targetEvent = eventFolders[targetEventIndex];
    if (!targetEvent || !currentEventFolder) return;

    log('INFO', 'MOVE_SOURCE_PHOTOS_START', { filenames, target: targetEvent.name });

    try {
        const response = await fetch(
            `/api/source/folder/${currentEventFolder.name}/move-photos`,
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ target_folder: targetEvent.name, filenames }),
            }
        );
        const data = await response.json();

        if (data.success) {
            showToast(`${filenames.length} foto(s) movida(s) a "${targetEvent.name}"`, { type: 'success' });

            // Update in-memory photo list for current event
            currentEventPhotos = (data.source_folder.photos || []);
            renderSourceEventDetails(data.source_folder);

            // Update photo count badges
            const srcCount = document.getElementById(`event-count-${currentEventIndex}`);
            if (srcCount) srcCount.textContent = String(data.source_folder.photo_count || 0);
            const dstCount = document.getElementById(`event-count-${targetEventIndex}`);
            if (dstCount) dstCount.textContent = String(data.target_folder.photo_count || 0);

            // Also sync eventFolders cache
            eventFolders[currentEventIndex].photo_count = data.source_folder.photo_count || 0;
            eventFolders[targetEventIndex].photo_count = data.target_folder.photo_count || 0;

            selectedSourcePhoto = null;
            document.getElementById('delete-source-photo-btn').disabled = true;
        } else {
            log('ERROR', 'MOVE_SOURCE_PHOTOS_FAILED', { error: data.error });
            showToast('Error al mover fotos: ' + data.error, { type: 'error' });
        }
    } catch (error) {
        log('ERROR', 'MOVE_SOURCE_PHOTOS_EXCEPTION', { error: error.message });
        showToast('Error de conexión al mover fotos', { type: 'error' });
    }
}

function updateEventPanelActiveItem(index) {
    document.querySelectorAll('#event-panel .page-list-item').forEach((item, i) => {
        item.classList.toggle('active', i === index);
    });
}

function navigateEventPanelSelection(delta) {
    const items = Array.from(document.querySelectorAll('#event-panel .page-list-item'));
    if (items.length === 0) return;
    
    const activeItem = document.querySelector('#event-panel .page-list-item.active');
    const currentIndex = items.indexOf(activeItem);
    
    const newIndex = Math.max(0, Math.min(items.length - 1, currentIndex + delta));
    
    if (newIndex !== currentIndex) {
        loadEvent(newIndex);
    }
}

// Restore a source-side deletion (photo or folder) via undo
async function restoreSourceDeletion(action, data) {
    try {
        const response = await fetch('/api/source/restore', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ trash_token: data.trash_token })
        });

        const payload = await response.json();

        if (!payload.success) {
            throw new Error(payload.error || 'Restore failed');
        }

        // Refresh UI. Folders need the full list reload; photos just the event.
        if (action === 'delete_source_folder') {
            await loadEventFolders();
            if (eventFolders.length > 0) {
                const idx = eventFolders.findIndex(f => f.name === data.folder_name);
                await loadEvent(idx >= 0 ? idx : 0);
            }
        } else {
            const idx = typeof data.event_index === 'number' ? data.event_index : currentEventIndex;
            await loadEvent(idx);
        }

        showToast(t('success.undo') || 'Restaurado', { type: 'success' });
    } catch (error) {
        log('ERROR', 'RESTORE_SOURCE_DELETION_FAILED', { error: error.message });
        throw error;
    }
}

// Initialize when tab is switched
document.addEventListener('DOMContentLoaded', () => {
    if (currentTab === 'source') {
        initSourceMode();
    }
});
