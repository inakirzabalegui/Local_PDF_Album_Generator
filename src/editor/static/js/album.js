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

// Page panel state
let pagePanelOpen = false;
let pagePanelFocused = false;
let pagePanelKeyboardIndex = -1;

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
    document.getElementById('regenerate-btn')?.addEventListener('click', regeneratePreview);
    document.getElementById('add-page-btn')?.addEventListener('click', addPageAfterCurrent);
    document.getElementById('delete-photo-btn')?.addEventListener('click', deleteSelectedPhoto);
    document.getElementById('delete-page-btn')?.addEventListener('click', deletePage);
    document.getElementById('update-title-btn')?.addEventListener('click', updatePageTitle);
    document.getElementById('update-caption-btn')?.addEventListener('click', updatePhotoCaption);
    document.getElementById('apply-layout-mode-btn')?.addEventListener('click', updateLayoutMode);
    document.getElementById('undo-btn')?.addEventListener('click', performUndo);
    
    // Page panel toggle
    document.getElementById('page-panel-toggle')?.addEventListener('click', togglePagePanel);
    
    // Keyboard shortcuts
    document.addEventListener('keydown', handleAlbumKeyboard);
}

// Handle keyboard shortcuts in album mode
function handleAlbumKeyboard(e) {
    if (currentTab !== 'album') return;
    
    if (e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
        if (e.key === 'ArrowLeft') {
            navigatePage(-1);
        } else if (e.key === 'ArrowRight') {
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
            alert(t('error.load_page') + data.error);
        }
    } catch (error) {
        log('ERROR', 'LOAD_PAGE_EXCEPTION', { error: error.message });
        alert(t('error.connection_load_page'));
    }
}

// Render page details in sidebar
function renderPageDetails(page) {
    const titleInput = document.getElementById('page-title');
    titleInput.value = page.section_titles.join(' / ') || '';
    
    currentPageCaptions = page.photo_captions || {};
    
    // Update layout mode selector
    const layoutSelect = document.getElementById('layout-mode-select');
    if (layoutSelect) {
        layoutSelect.value = page.layout_mode || 'mesa_de_luz';
    }
    
    document.getElementById('album-layout-mode').textContent = page.layout_mode;
    document.getElementById('photo-count').textContent = page.photo_count;
    
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
        onStart: function() {
            currentPhotoOrder = getPhotoOrder();
        },
        onEnd: handlePhotoReorder
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
            alert(t('error.reorder_photos') + data.error);
            await loadPage(currentPageIndex);
        }
    } catch (error) {
        log('ERROR', 'REORDER_EXCEPTION', { error: error.message });
        alert(t('error.connection_reorder'));
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
    
    const confirmed = confirm(t('confirm.delete_photo', { name: selectedPhotoName }));
    
    if (!confirmed) {
        log('INFO', 'DELETE_PHOTO_CANCELLED', {});
        return;
    }
    
    try {
        const response = await fetch(`/api/page/${pageId}/delete-photo`, {
            method: 'DELETE',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({filename: selectedPhotoName})
        });
        
        const data = await response.json();
        
        if (data.success) {
            log('INFO', 'DELETE_PHOTO_SUCCESS', {});
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
            alert(t('error.delete_photo') + data.error);
        }
    } catch (error) {
        log('ERROR', 'DELETE_PHOTO_EXCEPTION', { error: error.message });
        alert(t('error.connection_delete_photo'));
    }
}

// Add a new empty page after the current page
async function addPageAfterCurrent() {
    const pageNum = PAGES_DATA[currentPageIndex].number;
    
    log('INFO', 'ADD_PAGE_START', { afterPage: pageNum });
    
    const confirmed = confirm(t('confirm.add_page', { num: pageNum }));
    
    if (!confirmed) {
        log('INFO', 'ADD_PAGE_CANCELLED', {});
        return;
    }
    
    try {
        const response = await fetch('/api/pages/create', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ after_page: pageNum })
        });
        
        const data = await response.json();
        
        if (data.success) {
            log('INFO', 'ADD_PAGE_SUCCESS', {});
            
            const newPageEntry = {
                id: data.page.folder_name,
                number: data.page.page_number,
                title: data.page.section_titles[0] || `Página ${data.page.page_number}`,
                photo_count: 0,
                layout_mode: data.page.layout_mode,
            };
            
            PAGES_DATA.splice(currentPageIndex + 1, 0, newPageEntry);
            initPagePanel();
            
            alert(t('success.page_created'));
            
            await loadPage(currentPageIndex + 1);
        } else {
            log('ERROR', 'ADD_PAGE_FAILED', { error: data.error });
            alert(t('error.create_page') + data.error);
        }
    } catch (error) {
        log('ERROR', 'ADD_PAGE_EXCEPTION', { error: error.message });
        alert(t('error.connection_create_page'));
    }
}

// Delete entire page
async function deletePage() {
    const pageId = PAGES_DATA[currentPageIndex].id;
    const pageNum = PAGES_DATA[currentPageIndex].number;
    
    const confirmed = confirm(t('confirm.delete_page', { num: pageNum }));
    
    if (!confirmed) {
        return;
    }
    
    try {
        const response = await fetch(`/api/page/${pageId}/delete`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        if (data.success) {
            alert(t('success.page_deleted'));
            
            PAGES_DATA.splice(currentPageIndex, 1);
            
            const newIndex = Math.max(0, currentPageIndex - 1);
            if (PAGES_DATA.length > 0) {
                await loadPage(newIndex);
            } else {
                alert(t('success.no_more_pages'));
                exitEditor();
            }
        } else {
            alert(t('error.delete_page') + data.error);
        }
    } catch (error) {
        console.error('Failed to delete page:', error);
        alert(t('error.connection_delete_page'));
    }
}

// Update page title
async function updatePageTitle() {
    const titleInput = document.getElementById('page-title');
    const newTitle = titleInput.value.trim();
    
    log('INFO', 'UPDATE_TITLE_START', { newTitle });
    
    if (!newTitle) {
        log('WARN', 'UPDATE_TITLE_EMPTY', {});
        alert(t('validation.title_empty'));
        return;
    }
    
    const pageId = PAGES_DATA[currentPageIndex].id;
    const titles = [newTitle];
    
    try {
        let oldTitles = [];
        try {
            const response_get = await fetch(`/api/page/${pageId}`);
            const data_get = await response_get.json();
            oldTitles = data_get.success ? data_get.page.section_titles : [];
        } catch (e) {
            log('WARN', 'UPDATE_TITLE_OLD_FETCH_FAILED', {});
        }
        
        const response = await fetch(`/api/page/${pageId}/title`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({titles: titles})
        });
        
        const data = await response.json();
        
        if (data.success) {
            log('INFO', 'UPDATE_TITLE_SUCCESS', {});
            if (oldTitles.length > 0) {
                pushUndoState('title', {
                    oldTitles: oldTitles,
                    newTitles: titles
                });
            }
            
            updatePagePanelTitle(currentPageIndex, titles[0] || `Página ${PAGES_DATA[currentPageIndex].number}`);
            PAGES_DATA[currentPageIndex].title = titles[0];
            
            incrementPendingChanges();
            await regeneratePreview();
        } else {
            log('ERROR', 'UPDATE_TITLE_FAILED', { error: data.error });
            alert(t('error.update_title') + data.error);
        }
    } catch (error) {
        log('ERROR', 'UPDATE_TITLE_EXCEPTION', { error: error.message });
        alert(t('error.connection_update_title'));
    }
}

// Update layout mode
async function updateLayoutMode() {
    const layoutSelect = document.getElementById('layout-mode-select');
    const newMode = layoutSelect?.value || 'mesa_de_luz';
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
            document.getElementById('album-layout-mode').textContent = newMode;
            PAGES_DATA[currentPageIndex].layout_mode = newMode;
            incrementPendingChanges();
            await regeneratePreview();
        } else {
            log('ERROR', 'UPDATE_LAYOUT_MODE_FAILED', { error: data.error });
            alert(t('error.update_layout') + data.error);
        }
    } catch (error) {
        log('ERROR', 'UPDATE_LAYOUT_MODE_EXCEPTION', { error: error.message });
        alert(t('error.connection_update_layout'));
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
            alert(t('error.preview') + data.error);
        }
    } catch (error) {
        log('ERROR', 'REGENERATE_EXCEPTION', { error: error.message });
        alert(t('error.connection_preview'));
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
            alert(t('error.update_caption') + data.error);
        }
    } catch (error) {
        log('ERROR', 'UPDATE_CAPTION_EXCEPTION', { error: error.message });
        alert(t('error.connection_update_caption'));
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Undo System
// ═══════════════════════════════════════════════════════════════════════════

function pushUndoState(action, data) {
    undoStack.push({
        action: action,
        pageId: PAGES_DATA[currentPageIndex].id,
        pageIndex: currentPageIndex,
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
    
    if (state.pageIndex !== currentPageIndex) {
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
        }
    } catch (error) {
        console.error('Failed to perform undo:', error);
        alert(t('error.undo'));
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
        
        pageList.appendChild(item);
    });
    
    const panel = document.getElementById('page-panel');
    if (panel) {
        panel.addEventListener('mouseenter', () => { pagePanelFocused = true; });
        panel.addEventListener('mouseleave', () => { pagePanelFocused = false; });
    }
    
    log('INFO', 'PAGE_PANEL_INIT', { pages: PAGES_DATA.length });
}

function togglePagePanel() {
    const panel = document.getElementById('page-panel');
    if (!panel) return;
    
    pagePanelOpen = !pagePanelOpen;
    
    if (pagePanelOpen) {
        panel.classList.remove('collapsed');
        setTimeout(() => {
            const activeItem = document.querySelector('.page-list-item.active');
            if (activeItem) activeItem.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }, 260);
    } else {
        panel.classList.add('collapsed');
        pagePanelFocused = false;
    }
    
    log('INFO', 'PAGE_PANEL_TOGGLED', { open: pagePanelOpen });
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

// Save changes
async function saveChanges(silent = false) {
    try {
        const response = await fetch('/api/save', {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.success) {
            if (!silent) {
                alert(t('success.title'));
            }
            pendingChanges = 0;
        } else {
            if (!silent) {
                alert(t('error.save') + data.error);
            }
        }
    } catch (error) {
        console.error('Failed to save:', error);
        if (!silent) {
            alert(t('error.connection_save'));
        }
    }
}

// Exit editor
function exitEditor() {
    if (pendingChanges > 0) {
        const confirmed = confirm(t('success.unsaved_changes', { count: pendingChanges }));
        
        if (!confirmed) {
            return;
        }
    }
    
    window.close();
    setTimeout(() => {
        alert(t('success.can_close'));
    }, 100);
}

// Initialize when tab becomes active
document.addEventListener('DOMContentLoaded', () => {
    // Only initialize album mode if we're on the album tab
    if (currentTab === 'album') {
        initAlbumMode();
    }
});
