// ═══════════════════════════════════════════════════════════════════════════
// Album Edition Mode Logic
// ═══════════════════════════════════════════════════════════════════════════

// Album Editor State
let currentPageIndex = 0;
let pendingChanges = 0;
let selectedPhotoName = null;
let sortableInstance = null;
let currentPageCaptions = {};
let currentPhotoOrder = [];
let currentPageSectionTitles = [];
let currentPageLayoutMode = 'mesa_de_luz';
// Filenames being dragged for cross-page drops
let draggingAlbumFilenames = [];
// Set to true when a cross-page drop is handled so onEnd skips reorder
let _crossPageDropHandled = false;

// Page panel state (panel is always visible now; kept flags for keyboard nav)
let pagePanelOpen = true;
let pagePanelFocused = false;
let pagePanelKeyboardIndex = -1;
let photoListFocused = false;

// Undo system
const undoStack = [];
const MAX_UNDO_STEPS = 5;

// Initialize album mode when tab is active
function initAlbumMode() {
    log('INFO', 'ALBUM_MODE_INIT', { totalPages: PAGES_DATA.length });
    
    initPagePanel();
    
    if (PAGES_DATA.length > 0) {
        loadPage(0);
    }
    
    setupAlbumEventListeners();
}

// Setup Event Listeners for Album Mode
function setupAlbumEventListeners() {
    // Actions
    document.getElementById('save-btn')?.addEventListener('click', () => saveChanges(false));
    document.getElementById('exit-btn')?.addEventListener('click', exitEditor);
    document.getElementById('explode-page-btn')?.addEventListener('click', explodePage);
    document.getElementById('delete-photo-btn')?.addEventListener('click', deleteSelectedPhoto);
    document.getElementById('delete-page-btn')?.addEventListener('click', deletePage);
    document.getElementById('rename-page-btn')?.addEventListener('click', renamePage);
    document.getElementById('rename-subtitle-btn')?.addEventListener('click', renameSubtitle);
    document.getElementById('update-caption-btn')?.addEventListener('click', updatePhotoCaption);
    document.getElementById('layout-mode-btn')?.addEventListener('click', openLayoutModeModal);
    document.getElementById('apply-layout-mode-btn')?.addEventListener('click', applyLayoutModeFromModal);
    document.getElementById('cancel-layout-mode-btn')?.addEventListener('click', closeLayoutModeModal);
    document.getElementById('undo-btn')?.addEventListener('click', performUndo);

    // Keyboard shortcuts
    document.addEventListener('keydown', handleAlbumKeyboard);
}

// Handle keyboard shortcuts in album mode
function handleAlbumKeyboard(e) {
    if (currentTab !== 'album') return;
    
    if (e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
        if (e.key === 'ArrowLeft') {
            if (photoListFocused) {
                e.preventDefault();
                focusPagePanel();
                return;
            }
            navigatePage(-1);
        } else if (e.key === 'ArrowRight') {
            if (pagePanelFocused) {
                e.preventDefault();
                focusPhotoList();
                return;
            }
            navigatePage(1);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            if (pagePanelFocused && pagePanelOpen) {
                navigatePagePanelSelection(-1);
            } else {
                navigatePhotoSelection(-1);
            }
        } else if (e.key === 'ArrowDown') {
            e.preventDefault();
            if (pagePanelFocused && pagePanelOpen) {
                navigatePagePanelSelection(1);
            } else {
                navigatePhotoSelection(1);
            }
        } else if (e.key === 'd' || e.key === 'D') {
            if (selectedPhotoName) deleteSelectedPhoto();
        }
    }
    
    if ((e.metaKey || e.ctrlKey) && e.key === 's') {
        e.preventDefault();
        saveChanges();
    }
}

// Load a page by index
async function loadPage(index) {
    if (index < 0 || index >= PAGES_DATA.length) {
        log('WARN', 'LOAD_PAGE_INVALID', { index, totalPages: PAGES_DATA.length });
        return;
    }
    
    currentPageIndex = index;
    const page = PAGES_DATA[index];
    
    log('INFO', 'LOAD_PAGE_START', { pageNumber: page.number, pageId: page.id });
    
    // Update UI
    document.getElementById('current-page-num').textContent = page.number;
    updateNavigationButtons();
    
    // Fetch page details from API
    try {
        const response = await fetch(`/api/page/${page.id}`);
        log('INFO', 'FETCH_PAGE_RESPONSE', { status: response.status, ok: response.ok });
        
        const data = await response.json();
        
        if (data.success) {
            log('INFO', 'LOAD_PAGE_SUCCESS', { pageId: page.id, photoCount: data.page.photo_count });
            renderPageDetails(data.page);
            loadPreview(page.id);
            updatePagePanelActiveItem(index);
        } else {
            log('ERROR', 'LOAD_PAGE_FAILED', { error: data.error });
            showToast(t('error.load_page') + data.error, { type: 'error' });
        }
    } catch (error) {
        log('ERROR', 'LOAD_PAGE_EXCEPTION', { error: error.message });
        showToast(t('error.connection_load_page'), { type: 'error' });
    }
}

// Render page details in sidebar
function renderPageDetails(page) {
    currentPageSectionTitles = Array.isArray(page.section_titles) ? page.section_titles.slice() : [];
    currentPageLayoutMode = page.layout_mode || 'mesa_de_luz';
    currentPageCaptions = page.photo_captions || {};

    const layoutSelect = document.getElementById('layout-mode-select');
    if (layoutSelect) {
        layoutSelect.value = currentPageLayoutMode;
    }

    const photoList = document.getElementById('photo-list');
    photoList.textContent = '';
    
    page.images.forEach((filename) => {
        const div = document.createElement('div');
        div.className = 'photo-item';
        div.dataset.filename = filename;
        
        const dragHandle = document.createElement('span');
        dragHandle.className = 'drag-handle';
        dragHandle.textContent = '☰';
        
        const photoName = document.createElement('span');
        photoName.className = 'photo-name';
        photoName.textContent = filename;
        
        div.appendChild(dragHandle);
        div.appendChild(photoName);
        
        div.addEventListener('click', (e) => selectPhoto(filename, e.target.closest('.photo-item')));
        
        photoList.appendChild(div);
    });
    
    if (sortableInstance) {
        sortableInstance.destroy();
    }
    
    sortableInstance = Sortable.create(photoList, {
        animation: 150,
        handle: '.drag-handle',
        ghostClass: 'sortable-ghost',
        setData(dataTransfer, dragEl) {
            const filename = dragEl.dataset.filename;
            const selected = Array.from(photoList.querySelectorAll('.photo-item.selected'))
                .map(el => el.dataset.filename);
            draggingAlbumFilenames = selected.includes(filename) ? selected : [filename];
            currentPhotoOrder = getPhotoOrder();
            dataTransfer.setData('text/plain', JSON.stringify(draggingAlbumFilenames));
        },
        onEnd(evt) {
            if (_crossPageDropHandled) {
                _crossPageDropHandled = false;
                draggingAlbumFilenames = [];
                return;
            }
            draggingAlbumFilenames = [];
            handlePhotoReorder(evt);
        },
    });
}

// Select a photo
function selectPhoto(filename, element) {
    document.querySelectorAll('.photo-item').forEach(item => {
        item.classList.remove('selected');
    });
    
    element.classList.add('selected');
    selectedPhotoName = filename;
    
    document.getElementById('delete-photo-btn').disabled = false;
    
    const captionTextarea = document.getElementById('photo-caption');
    const captionBtn = document.getElementById('update-caption-btn');
    
    if (captionTextarea) captionTextarea.disabled = false;
    if (captionTextarea) captionTextarea.value = currentPageCaptions[filename] || '';
    if (captionBtn) captionBtn.disabled = false;
}

// Handle photo reorder via drag-and-drop
async function handlePhotoReorder(evt) {
    const oldOrder = currentPhotoOrder;
    const newOrder = getPhotoOrder();
    const pageId = PAGES_DATA[currentPageIndex].id;
    
    log('INFO', 'REORDER_START', { oldOrder, newOrder });
    
    try {
        const response = await fetch(`/api/page/${pageId}/reorder`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({order: newOrder})
        });
        
        const data = await response.json();
        
        if (data.success) {
            log('INFO', 'REORDER_SUCCESS', {});
            
            // Reload page to update data-filename with canonical names before pushing undo
            await loadPage(currentPageIndex);
            
            if (JSON.stringify(oldOrder) !== JSON.stringify(newOrder)) {
                pushUndoState('reorder', {
                    oldOrder: oldOrder,
                    newOrder: newOrder
                });
            }
            
            incrementPendingChanges();
            await regeneratePreview();
        } else {
            log('ERROR', 'REORDER_FAILED', { error: data.error });
            showToast(t('error.reorder_photos') + data.error, { type: 'error' });
            await loadPage(currentPageIndex);
        }
    } catch (error) {
        log('ERROR', 'REORDER_EXCEPTION', { error: error.message });
        showToast(t('error.connection_reorder'), { type: 'error' });
        await loadPage(currentPageIndex);
    }
}

// Get current photo order from DOM
function getPhotoOrder() {
    const items = document.querySelectorAll('.photo-item');
    return Array.from(items).map(item => item.dataset.filename);
}

// Delete selected photo
async function deleteSelectedPhoto() {
    if (!selectedPhotoName) {
        log('WARN', 'DELETE_PHOTO_NO_SELECTION', {});
        return;
    }
    
    const pageId = PAGES_DATA[currentPageIndex].id;
    log('INFO', 'DELETE_PHOTO_START', { filename: selectedPhotoName });
    
    const confirmed = await showConfirm({
        title: 'Borrar foto',
        message: t('confirm.delete_photo', { name: selectedPhotoName }),
        danger: true
    });

    if (!confirmed) {
        log('INFO', 'DELETE_PHOTO_CANCELLED', {});
        return;
    }
    
    try {
        // #region agent log
        fetch('http://127.0.0.1:7583/ingest/f99a3167-114d-4776-a87f-6f247420d0df',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'02279c'},body:JSON.stringify({sessionId:'02279c',location:'album.js:deleteSelectedPhoto',message:'delete album photo request',data:{pageId:pageId,filename:selectedPhotoName},timestamp:Date.now()})}).catch(()=>{});
        // #endregion
        const response = await fetch(`/api/page/${pageId}/delete-photo`, {
            method: 'DELETE',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({filename: selectedPhotoName})
        });
        
        const data = await response.json();
        
        // #region agent log
        fetch('http://127.0.0.1:7583/ingest/f99a3167-114d-4776-a87f-6f247420d0df',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'02279c'},body:JSON.stringify({sessionId:'02279c',location:'album.js:deleteSelectedPhoto',message:'delete album photo response',data:{status:response.status,success:data.success,error:data.error||null},timestamp:Date.now()})}).catch(()=>{});
        // #endregion
        
        if (data.success) {
            log('INFO', 'DELETE_PHOTO_SUCCESS', { trash_token: data.trash_token });
            if (data.trash_token) {
                pushUndoState('delete_photo', {
                    filename: selectedPhotoName,
                    trash_token: data.trash_token,
                });
            }
            selectedPhotoName = null;
            document.getElementById('delete-photo-btn').disabled = true;

            const captionTextarea = document.getElementById('photo-caption');
            if (captionTextarea) {
                captionTextarea.disabled = true;
                captionTextarea.value = '';
            }

            const captionBtn = document.getElementById('update-caption-btn');
            if (captionBtn) captionBtn.disabled = true;

            incrementPendingChanges();
            await loadPage(currentPageIndex);
            await regeneratePreview();
        } else {
            log('ERROR', 'DELETE_PHOTO_FAILED', { error: data.error });
            showToast(t('error.delete_photo') + data.error, { type: 'error' });
        }
    } catch (error) {
        log('ERROR', 'DELETE_PHOTO_EXCEPTION', { error: error.message });
        showToast(t('error.connection_delete_photo'), { type: 'error' });
    }
}

// Split the current page into two: first half stays, second half moves to a new page right after
async function explodePage() {
    const page = PAGES_DATA[currentPageIndex];
    const n = page.photo_count;
    const stayCount = Math.ceil(n / 2);
    const moveCount = Math.floor(n / 2);

    if (n < 2) {
        showToast('Se necesitan al menos 2 fotos para explotar una página.', { type: 'warning' });
        return;
    }

    const confirmed = await showConfirm({
        title: 'Explotar página',
        message: `¿Explotar la página ${page.number} en dos?\n\n` +
                 `• Esta página quedará con ${stayCount} foto${stayCount !== 1 ? 's' : ''} (primera mitad).\n` +
                 `• Se creará una nueva página con ${moveCount} foto${moveCount !== 1 ? 's' : ''} (segunda mitad).\n\n` +
                 `La numeración final se actualizará en el próximo render.`
    });

    if (!confirmed) return;

    try {
        const response = await fetch(`/api/page/${page.id}/explode`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
        });

        const data = await response.json();

        if (data.success) {
            PAGES_DATA[currentPageIndex].photo_count = data.original_page.photo_count;

            const newEntry = {
                id: data.new_page.id,
                number: data.new_page.number,
                title: data.new_page.section_titles[0] || `Página ${data.new_page.number}`,
                photo_count: data.new_page.photo_count,
                layout_mode: data.new_page.layout_mode,
            };
            PAGES_DATA.splice(currentPageIndex + 1, 0, newEntry);

            initPagePanel();
            await regeneratePreview();
            await loadPage(currentPageIndex);
        } else {
            showToast('Error al explotar página: ' + data.error, { type: 'error' });
        }
    } catch (error) {
        log('ERROR', 'EXPLODE_PAGE_EXCEPTION', { error: error.message });
        showToast('Error de conexión al explotar página', { type: 'error' });
    }
}

// Delete entire page
async function deletePage() {
    const pageId = PAGES_DATA[currentPageIndex].id;
    const pageNum = PAGES_DATA[currentPageIndex].number;
    
    const confirmed = await showConfirm({
        title: 'Borrar página',
        message: t('confirm.delete_page', { num: pageNum }),
        danger: true
    });
    
    if (!confirmed) {
        return;
    }
    
    try {
        const response = await fetch(`/api/page/${pageId}/delete`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        if (data.success) {
            showToast(t('success.page_deleted'), { type: 'success' });
            
            PAGES_DATA.splice(currentPageIndex, 1);
            
            const newIndex = Math.max(0, currentPageIndex - 1);
            if (PAGES_DATA.length > 0) {
                await loadPage(newIndex);
            } else {
                showToast(t('success.no_more_pages'), { type: 'success' });
                exitEditor();
            }
        } else {
            showToast(t('error.delete_page') + data.error, { type: 'error' });
        }
    } catch (error) {
        console.error('Failed to delete page:', error);
        showToast(t('error.connection_delete_page'), { type: 'error' });
    }
}

// Rename page (first title in section_titles)
async function renamePage() {
    const pageId = PAGES_DATA[currentPageIndex].id;
    const currentTitle = currentPageSectionTitles[0] || '';
    const newTitle = await showPrompt({
        title: 'Renombrar página',
        message: 'Nuevo título de la página:',
        defaultValue: currentTitle
    });

    if (newTitle === null) return;
    const trimmed = newTitle.trim();
    if (!trimmed) {
        showToast(t('validation.title_empty'), { type: 'warning' });
        return;
    }
    if (trimmed === currentTitle) return;

    const newTitles = currentPageSectionTitles.slice();
    newTitles[0] = trimmed;
    await saveSectionTitles(pageId, newTitles);
}

// Rename subtitle (second title in section_titles)
async function renameSubtitle() {
    const pageId = PAGES_DATA[currentPageIndex].id;
    const currentSubtitle = currentPageSectionTitles[1] || '';
    const newSubtitle = await showPrompt({
        title: 'Renombrar subtítulo',
        message: 'Subtítulo (vacío = sin subtítulo):',
        defaultValue: currentSubtitle
    });

    if (newSubtitle === null) return;
    const trimmed = newSubtitle.trim();
    if (trimmed === currentSubtitle) return;

    const newTitles = currentPageSectionTitles.slice();
    if (trimmed) {
        newTitles[1] = trimmed;
    } else if (newTitles.length > 1) {
        newTitles.splice(1, 1);
    }
    if (!newTitles[0]) newTitles[0] = `Página ${PAGES_DATA[currentPageIndex].number}`;
    await saveSectionTitles(pageId, newTitles);
}

async function saveSectionTitles(pageId, newTitles) {
    const oldTitles = currentPageSectionTitles.slice();
    log('INFO', 'UPDATE_TITLE_START', { newTitles });

    try {
        const response = await fetch(`/api/page/${pageId}/title`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({titles: newTitles})
        });

        const data = await response.json();

        if (data.success) {
            log('INFO', 'UPDATE_TITLE_SUCCESS', {});
            if (oldTitles.length > 0) {
                pushUndoState('title', { oldTitles, newTitles });
            }

            currentPageSectionTitles = newTitles.slice();
            updatePagePanelTitle(currentPageIndex, newTitles[0] || `Página ${PAGES_DATA[currentPageIndex].number}`);
            PAGES_DATA[currentPageIndex].title = newTitles[0];

            incrementPendingChanges();
            await regeneratePreview();
        } else {
            log('ERROR', 'UPDATE_TITLE_FAILED', { error: data.error });
            showToast(t('error.update_title') + data.error, { type: 'error' });
        }
    } catch (error) {
        log('ERROR', 'UPDATE_TITLE_EXCEPTION', { error: error.message });
        showToast(t('error.connection_update_title'), { type: 'error' });
    }
}

// Layout mode modal
function openLayoutModeModal() {
    const modal = document.getElementById('layout-mode-modal');
    const select = document.getElementById('layout-mode-select');
    if (select) select.value = currentPageLayoutMode || 'mesa_de_luz';
    if (modal) modal.classList.remove('hidden');
}

function closeLayoutModeModal() {
    const modal = document.getElementById('layout-mode-modal');
    if (modal) modal.classList.add('hidden');
}

async function applyLayoutModeFromModal() {
    const layoutSelect = document.getElementById('layout-mode-select');
    const newMode = layoutSelect?.value || 'mesa_de_luz';
    closeLayoutModeModal();
    if (newMode === currentPageLayoutMode) return;
    await updateLayoutMode(newMode);
}

async function updateLayoutMode(newMode) {
    const pageId = PAGES_DATA[currentPageIndex].id;

    log('INFO', 'UPDATE_LAYOUT_MODE_START', { newMode });

    try {
        const response = await fetch(`/api/page/${pageId}/layout-mode`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ layout_mode: newMode })
        });

        const data = await response.json();

        if (data.success) {
            log('INFO', 'UPDATE_LAYOUT_MODE_SUCCESS', {});
            currentPageLayoutMode = newMode;
            PAGES_DATA[currentPageIndex].layout_mode = newMode;
            incrementPendingChanges();
            await regeneratePreview();
        } else {
            log('ERROR', 'UPDATE_LAYOUT_MODE_FAILED', { error: data.error });
            showToast(t('error.update_layout') + data.error, { type: 'error' });
        }
    } catch (error) {
        log('ERROR', 'UPDATE_LAYOUT_MODE_EXCEPTION', { error: error.message });
        showToast(t('error.connection_update_layout'), { type: 'error' });
    }
}

// Regenerate preview
async function regeneratePreview() {
    const pageId = PAGES_DATA[currentPageIndex].id;
    
    log('INFO', 'REGENERATE_START', { pageId });
    showLoading(t('loading.preview'));
    
    try {
        const response = await fetch(`/api/page/${pageId}/regenerate`, {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.success) {
            log('INFO', 'REGENERATE_SUCCESS', {});
            loadPreview(pageId);
        } else {
            log('ERROR', 'REGENERATE_FAILED', { error: data.error });
            showToast(t('error.preview') + data.error, { type: 'error' });
        }
    } catch (error) {
        log('ERROR', 'REGENERATE_EXCEPTION', { error: error.message });
        showToast(t('error.connection_preview'), { type: 'error' });
    } finally {
        hideLoading();
    }
}

// Load preview PDF
function loadPreview(pageId) {
    const iframe = document.getElementById('pdf-preview');
    if (iframe) {
        iframe.src = `/api/page/${pageId}/preview?t=${Date.now()}`;
    }
}

// Navigate pages
async function navigatePage(delta) {
    const newIndex = currentPageIndex + delta;
    log('INFO', 'NAVIGATE_PAGE', { from: currentPageIndex, to: newIndex, delta });
    
    if (newIndex >= 0 && newIndex < PAGES_DATA.length) {
        if (pendingChanges > 0) {
            log('INFO', 'NAVIGATE_AUTOSAVE', { pendingChanges });
            await saveChanges(true);
        }
        await loadPage(newIndex);
    } else {
        log('WARN', 'NAVIGATE_OUT_OF_BOUNDS', { newIndex });
    }
}

// Navigate photo selection with arrow keys
function navigatePhotoSelection(delta) {
    const items = Array.from(document.querySelectorAll('.photo-item'));
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
        selectPhoto(filename, newItem);
        newItem.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
}

// Update navigation button states
function updateNavigationButtons() {
    const prevBtn = document.getElementById('prev-btn');
    const nextBtn = document.getElementById('next-btn');
    if (prevBtn) prevBtn.disabled = currentPageIndex === 0;
    if (nextBtn) nextBtn.disabled = currentPageIndex === PAGES_DATA.length - 1;
}

// Increment pending changes counter
function incrementPendingChanges() {
    pendingChanges++;
    log('INFO', 'PENDING_CHANGES_INCREMENTED', { count: pendingChanges });
}

// Update photo caption
async function updatePhotoCaption() {
    if (!selectedPhotoName) {
        log('WARN', 'UPDATE_CAPTION_NO_SELECTION', {});
        return;
    }
    
    const captionTextarea = document.getElementById('photo-caption');
    const newCaption = captionTextarea?.value.trim() || '';
    const oldCaption = currentPageCaptions[selectedPhotoName] || '';
    
    const pageId = PAGES_DATA[currentPageIndex].id;
    
    log('INFO', 'UPDATE_CAPTION_START', { filename: selectedPhotoName });
    
    try {
        const response = await fetch(`/api/page/${pageId}/caption`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                filename: selectedPhotoName,
                caption: newCaption
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            log('INFO', 'UPDATE_CAPTION_SUCCESS', {});
            pushUndoState('caption', {
                filename: selectedPhotoName,
                oldCaption: oldCaption,
                newCaption: newCaption
            });
            
            currentPageCaptions[selectedPhotoName] = newCaption;
            incrementPendingChanges();
            await regeneratePreview();
        } else {
            log('ERROR', 'UPDATE_CAPTION_FAILED', { error: data.error });
            showToast(t('error.update_caption') + data.error, { type: 'error' });
        }
    } catch (error) {
        log('ERROR', 'UPDATE_CAPTION_EXCEPTION', { error: error.message });
        showToast(t('error.connection_update_caption'), { type: 'error' });
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Undo System
// ═══════════════════════════════════════════════════════════════════════════

function pushUndoState(action, data) {
    const currentPage = PAGES_DATA && PAGES_DATA[currentPageIndex];
    undoStack.push({
        action: action,
        pageId: currentPage ? currentPage.id : null,
        pageIndex: currentPage ? currentPageIndex : null,
        data: data,
        timestamp: Date.now()
    });
    
    if (undoStack.length > MAX_UNDO_STEPS) {
        undoStack.shift();
    }
    
    const undoBtn = document.getElementById('undo-btn');
    if (undoBtn) undoBtn.disabled = false;
}

async function performUndo() {
    if (undoStack.length === 0) return;

    const state = undoStack.pop();

    // Album actions track which page the change happened on; source actions don't.
    if (typeof state.pageIndex === 'number' && state.pageIndex !== currentPageIndex) {
        await loadPage(state.pageIndex);
    }

    try {
        switch (state.action) {
            case 'reorder':
                await restorePhotoOrder(state.data.oldOrder);
                break;
            case 'title':
                await restoreTitle(state.data.oldTitles);
                break;
            case 'caption':
                await restoreCaption(state.data.filename, state.data.oldCaption);
                break;
            case 'delete_photo':
                await restoreDeletedPhoto(state.data.trash_token);
                break;
            case 'delete_source_photo':
            case 'delete_source_folder':
                if (typeof restoreSourceDeletion === 'function') {
                    await restoreSourceDeletion(state.action, state.data);
                }
                break;
        }
    } catch (error) {
        console.error('Failed to perform undo:', error);
        showToast(t('error.undo'), { type: 'error' });
    }
    
    const undoBtn = document.getElementById('undo-btn');
    if (undoBtn && undoStack.length === 0) {
        undoBtn.disabled = true;
    }
}

async function restorePhotoOrder(oldOrder) {
    const pageId = PAGES_DATA[currentPageIndex].id;
    
    try {
        const response = await fetch(`/api/page/${pageId}/reorder`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({order: oldOrder})
        });
        
        const data = await response.json();
        
        if (data.success) {
            await loadPage(currentPageIndex);
            await regeneratePreview();
        }
    } catch (error) {
        console.error('Failed to restore photo order:', error);
        throw error;
    }
}

async function restoreTitle(oldTitles) {
    const pageId = PAGES_DATA[currentPageIndex].id;
    
    try {
        const response = await fetch(`/api/page/${pageId}/title`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({titles: oldTitles})
        });
        
        const data = await response.json();
        
        if (data.success) {
            await loadPage(currentPageIndex);
            await regeneratePreview();
        }
    } catch (error) {
        console.error('Failed to restore title:', error);
        throw error;
    }
}

async function restoreCaption(filename, oldCaption) {
    const pageId = PAGES_DATA[currentPageIndex].id;
    
    try {
        const response = await fetch(`/api/page/${pageId}/caption`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                filename: filename,
                caption: oldCaption
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            currentPageCaptions[filename] = oldCaption;
            
            if (selectedPhotoName === filename) {
                const textarea = document.getElementById('photo-caption');
                if (textarea) textarea.value = oldCaption;
            }
            
            await regeneratePreview();
        }
    } catch (error) {
        console.error('Failed to restore caption:', error);
        throw error;
    }
}

async function restoreDeletedPhoto(trashToken) {
    try {
        const response = await fetch('/api/restore-photo', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ trash_token: trashToken })
        });

        const data = await response.json();

        if (data.success) {
            await loadPage(currentPageIndex);
            await regeneratePreview();
            showToast(t('success.undo') || 'Foto restaurada', { type: 'success' });
        } else {
            throw new Error(data.error || 'Restore failed');
        }
    } catch (error) {
        console.error('Failed to restore deleted photo:', error);
        throw error;
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Page Navigator Panel
// ═══════════════════════════════════════════════════════════════════════════

function initPagePanel() {
    const pageList = document.getElementById('page-list');
    if (!pageList) return;
    
    pageList.textContent = '';
    
    PAGES_DATA.forEach((page, index) => {
        const item = document.createElement('div');
        item.className = 'page-list-item';
        item.dataset.index = index;

        const numSpan = document.createElement('span');
        numSpan.className = 'page-list-num';
        numSpan.textContent = String(page.number).padStart(2, '0');

        const titleSpan = document.createElement('span');
        titleSpan.className = 'page-list-title';
        titleSpan.textContent = page.title || `Página ${page.number}`;
        titleSpan.id = `page-panel-title-${index}`;

        item.appendChild(numSpan);
        item.appendChild(titleSpan);

        item.addEventListener('click', () => navigateToPageFromPanel(index));

        // Drop target: accept dragged album photos from a different page
        item.addEventListener('dragover', (e) => {
            if (!sortableInstance) return;
            e.preventDefault();
            e.dataTransfer.dropEffect = 'move';
            document.querySelectorAll('#page-list .page-list-item').forEach(el => el.classList.remove('drag-over'));
            if (index !== currentPageIndex) item.classList.add('drag-over');
        });
        item.addEventListener('dragleave', () => item.classList.remove('drag-over'));
        item.addEventListener('drop', (e) => {
            e.preventDefault();
            item.classList.remove('drag-over');
            if (index === currentPageIndex) return;
            const filenames = JSON.parse(e.dataTransfer.getData('text/plain') || '[]');
            if (filenames.length) {
                _crossPageDropHandled = true;
                moveAlbumPhotosToPage(filenames, index);
            }
        });

        pageList.appendChild(item);
    });
    
    const panel = document.getElementById('page-panel');
    if (panel) {
        panel.addEventListener('mouseenter', () => { pagePanelFocused = true; });
        panel.addEventListener('mouseleave', () => {
            pagePanelFocused = false;
            document.querySelectorAll('#page-list .page-list-item').forEach(el => el.classList.remove('drag-over'));
        });
    }

    const albumSidebar = document.getElementById('album-sidebar');
    if (albumSidebar && !albumSidebar.dataset.focusWired) {
        albumSidebar.addEventListener('mouseenter', () => { photoListFocused = true; });
        albumSidebar.addEventListener('mouseleave', () => { photoListFocused = false; });
        albumSidebar.dataset.focusWired = '1';
    }

    log('INFO', 'PAGE_PANEL_INIT', { pages: PAGES_DATA.length });
}

// Move logical focus to the page panel (left) — highlights + toggles flags
function focusPagePanel() {
    photoListFocused = false;
    pagePanelFocused = true;
    document.getElementById('album-sidebar')?.classList.remove('panel-has-focus');
    document.getElementById('page-panel')?.classList.add('panel-has-focus');

    const items = document.querySelectorAll('.page-list-item');
    if (pagePanelKeyboardIndex < 0 || pagePanelKeyboardIndex >= items.length) {
        pagePanelKeyboardIndex = currentPageIndex;
    }
    items.forEach((item, i) => {
        item.classList.toggle('keyboard-focus', i === pagePanelKeyboardIndex);
    });
    items[pagePanelKeyboardIndex]?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// Move logical focus to the photo list (right)
function focusPhotoList() {
    pagePanelFocused = false;
    photoListFocused = true;
    document.getElementById('page-panel')?.classList.remove('panel-has-focus');
    document.getElementById('album-sidebar')?.classList.add('panel-has-focus');

    const items = document.querySelectorAll('.photo-item');
    if (items.length === 0) return;
    const alreadySelected = Array.from(items).find(i => i.classList.contains('selected'));
    if (alreadySelected) {
        alreadySelected.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    } else {
        const first = items[0];
        selectPhoto(first.dataset.filename, first);
        first.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
}

function navigateToPageFromPanel(index) {
    const delta = index - currentPageIndex;
    if (delta !== 0) {
        navigatePage(delta);
    }
}

function updatePagePanelActiveItem(index) {
    document.querySelectorAll('.page-list-item').forEach((item, i) => {
        item.classList.toggle('active', i === index);
        item.classList.remove('keyboard-focus');
    });
    
    pagePanelKeyboardIndex = index;
    
    if (pagePanelOpen) {
        const activeItem = document.querySelector('.page-list-item.active');
        if (activeItem) activeItem.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
}

function updatePagePanelTitle(index, newTitle) {
    const titleEl = document.getElementById(`page-panel-title-${index}`);
    if (titleEl) titleEl.textContent = newTitle;
}

function navigatePagePanelSelection(delta) {
    const items = Array.from(document.querySelectorAll('.page-list-item'));
    if (items.length === 0) return;
    
    const newIndex = Math.max(0, Math.min(items.length - 1, pagePanelKeyboardIndex + delta));
    
    if (newIndex === pagePanelKeyboardIndex) return;
    
    items.forEach((item, i) => {
        item.classList.remove('keyboard-focus');
        if (i === newIndex) item.classList.add('keyboard-focus');
    });
    
    items[newIndex].scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    navigateToPageFromPanel(newIndex);
}

// Move photos from the current page to another page via drag-to-panel-item
async function moveAlbumPhotosToPage(filenames, targetPageIndex) {
    const sourcePage = PAGES_DATA[currentPageIndex];
    const targetPage = PAGES_DATA[targetPageIndex];
    if (!sourcePage || !targetPage) return;

    log('INFO', 'MOVE_ALBUM_PHOTOS_START', { filenames, target: targetPage.id });

    try {
        const response = await fetch(`/api/page/${sourcePage.id}/move-photos`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ target_page_id: targetPage.id, filenames }),
        });
        const data = await response.json();

        if (data.success) {
            showToast(`${filenames.length} foto(s) movida(s) a página ${targetPage.number}`, { type: 'success' });
            incrementPendingChanges();
            // Regenerate both pages in parallel, then navigate to the target
            const sourceIdx = currentPageIndex;
            await Promise.all([
                fetch(`/api/page/${sourcePage.id}/regenerate`, { method: 'POST' }),
                fetch(`/api/page/${targetPage.id}/regenerate`, { method: 'POST' }),
            ]);
            // Navigate to the target page so the user sees where the photo landed
            await loadPage(targetPageIndex);
            await regeneratePreview();
        } else {
            log('ERROR', 'MOVE_ALBUM_PHOTOS_FAILED', { error: data.error });
            showToast('Error al mover fotos: ' + data.error, { type: 'error' });
        }
    } catch (error) {
        log('ERROR', 'MOVE_ALBUM_PHOTOS_EXCEPTION', { error: error.message });
        showToast('Error de conexión al mover fotos', { type: 'error' });
    }
}

// Save changes
async function saveChanges(silent = false) {
    try {
        const response = await fetch('/api/save', {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.success) {
            if (!silent) {
                showToast(t('success.title'), { type: 'success' });
            }
            pendingChanges = 0;
        } else {
            if (!silent) {
                showToast(t('error.save') + data.error, { type: 'error' });
            }
        }
    } catch (error) {
        console.error('Failed to save:', error);
        if (!silent) {
            showToast(t('error.connection_save'), { type: 'error' });
        }
    }
}

// Exit editor
async function exitEditor() {
    if (pendingChanges > 0) {
        const confirmed = await showConfirm({
            title: 'Cambios sin guardar',
            message: t('success.unsaved_changes', { count: pendingChanges }),
            danger: true
        });

        if (!confirmed) {
            return;
        }
    }

    window.close();
    setTimeout(() => {
        showToast(t('success.can_close'), { type: 'info' });
    }, 100);
}

// Initialize when tab becomes active
document.addEventListener('DOMContentLoaded', () => {
    // Only initialize album mode if we're on the album tab
    if (currentTab === 'album') {
        initAlbumMode();
    }
});
