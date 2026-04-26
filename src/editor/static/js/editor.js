// Editor State
let currentPageIndex = 0;
let pendingChanges = 0;
let selectedPhotoName = null;
let sortableInstance = null;
let currentPageCaptions = {};
let currentPhotoOrder = [];

// Page panel state
let pagePanelOpen = false;
let pagePanelFocused = false;
let photoListFocused = false;
let pagePanelKeyboardIndex = -1;

// Undo system
const undoStack = [];
const MAX_UNDO_STEPS = 5;

// Debug logging system
const debugLog = [];
const MAX_LOG_ENTRIES = 500;

function log(level, action, details = {}) {
    const timestamp = new Date().toISOString();
    const entry = {
        timestamp,
        level,
        action,
        details,
        page: currentPageIndex,
        pageId: PAGES_DATA[currentPageIndex]?.id
    };
    
    debugLog.push(entry);
    
    // Keep only last MAX_LOG_ENTRIES
    if (debugLog.length > MAX_LOG_ENTRIES) {
        debugLog.shift();
    }
    
    // Console log for real-time debugging
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
        `${entry.timestamp} | ${entry.level.padEnd(5)} | ${entry.action.padEnd(20)} | Page: ${entry.page} | ${JSON.stringify(entry.details)}`
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
    // Create modal overlay
    const overlay = document.createElement('div');
    overlay.style.cssText = 'position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.8); z-index: 10000; display: flex; align-items: center; justify-content: center;';
    
    const modal = document.createElement('div');
    modal.style.cssText = 'background: #1e1e1e; color: #d4d4d4; padding: 20px; border-radius: 12px; width: 80%; max-width: 1000px; max-height: 80%; overflow: auto; font-family: monospace;';
    
    const header = document.createElement('div');
    header.style.cssText = 'display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;';
    
    const title = document.createElement('h2');
    title.textContent = 'Editor Debug Log';
    title.style.margin = '0';
    
    const closeBtn = document.createElement('button');
    closeBtn.textContent = 'Cerrar';
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
        
        line.textContent = `${entry.timestamp} | ${entry.level.padEnd(5)} | ${entry.action.padEnd(20)} | Page: ${entry.page} | ${JSON.stringify(entry.details)}`;
        logContainer.appendChild(line);
    });
    
    modal.appendChild(header);
    modal.appendChild(logContainer);
    overlay.appendChild(modal);
    document.body.appendChild(overlay);
}

// Initialize editor on page load
document.addEventListener('DOMContentLoaded', () => {
    log('INFO', 'EDITOR_INIT', { totalPages: PAGES_DATA.length });
    
    // Initialize page navigator panel
    initPagePanel();
    
    // Load first page
    if (PAGES_DATA.length > 0) {
        loadPage(0);
    }
    
    // Setup event listeners
    setupEventListeners();
    
    // Initialize theme from localStorage or system preference
    let savedTheme = localStorage.getItem('editorTheme');
    
    // If no saved preference, check system preference
    if (!savedTheme) {
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        savedTheme = prefersDark ? 'dark' : 'light';
    }
    
    const checkbox = document.getElementById('theme-toggle');
    if (savedTheme === 'dark') {
        document.body.classList.add('dark-mode');
        checkbox.checked = true;
    } else {
        checkbox.checked = false;
    }
    
    log('INFO', 'THEME_INIT', { theme: savedTheme });
});

// Setup Event Listeners
function setupEventListeners() {
    // Navigation
    document.getElementById('prev-btn').addEventListener('click', () => navigatePage(-1));
    document.getElementById('next-btn').addEventListener('click', () => navigatePage(1));
    
    // Actions
    document.getElementById('save-btn').addEventListener('click', () => saveChanges(false));
    document.getElementById('exit-btn').addEventListener('click', exitEditor);
    document.getElementById('regenerate-btn').addEventListener('click', regeneratePreview);
    document.getElementById('explode-page-btn').addEventListener('click', explodePage);
    document.getElementById('delete-photo-btn').addEventListener('click', deleteSelectedPhoto);
    document.getElementById('delete-page-btn').addEventListener('click', deletePage);
    document.getElementById('update-title-btn').addEventListener('click', updatePageTitle);
    document.getElementById('update-caption-btn').addEventListener('click', updatePhotoCaption);
    document.getElementById('undo-btn').addEventListener('click', performUndo);
    
    // Page panel toggle
    document.getElementById('page-panel-toggle').addEventListener('click', togglePagePanel);

    // Debug & Theme
    document.getElementById('debug-btn').addEventListener('click', showDebugLog);
    document.getElementById('theme-toggle').addEventListener('change', toggleTheme);
    
    // Keyboard shortcuts
    document.addEventListener('keydown', handleKeyboard);
}

// Handle keyboard shortcuts
function handleKeyboard(e) {
    // Arrow keys for navigation (only if not in input field)
    if (e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
        if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
            if (pagePanelFocused) {
                e.preventDefault();
                focusPhotoList();
            } else if (photoListFocused) {
                e.preventDefault();
                focusPagePanel();
            }
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            if (pagePanelFocused) {
                navigatePagePanelSelection(-1);
            } else {
                navigatePhotoSelection(-1);
            }
        } else if (e.key === 'ArrowDown') {
            e.preventDefault();
            if (pagePanelFocused) {
                navigatePagePanelSelection(1);
            } else {
                navigatePhotoSelection(1);
            }
        }
    }
    
    // Cmd/Ctrl+S for save
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
            alert('Error al cargar la página: ' + data.error);
        }
    } catch (error) {
        log('ERROR', 'LOAD_PAGE_EXCEPTION', { error: error.message, stack: error.stack });
        alert('Error de conexión al cargar la página');
    }
}

// Render page details in sidebar
function renderPageDetails(page) {
    // Update title input
    const titleInput = document.getElementById('page-title');
    titleInput.value = page.section_titles.join(' / ') || '';
    
    // Store captions for current page
    currentPageCaptions = page.photo_captions || {};
    
    // Update info
    document.getElementById('layout-mode').textContent = page.layout_mode;
    document.getElementById('photo-count').textContent = page.photo_count;
    
    // Render photo list
    const photoList = document.getElementById('photo-list');
    photoList.textContent = '';  // Clear existing content safely
    
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
        
        // Click to select
        div.addEventListener('click', (e) => selectPhoto(filename, e.target.closest('.photo-item')));
        
        photoList.appendChild(div);
    });
    
    // Initialize SortableJS for drag-and-drop
    if (sortableInstance) {
        sortableInstance.destroy();
    }
    
    sortableInstance = Sortable.create(photoList, {
        animation: 150,
        handle: '.drag-handle',
        ghostClass: 'sortable-ghost',
        onStart: function() {
            // Capture order before drag
            currentPhotoOrder = getPhotoOrder();
        },
        onEnd: handlePhotoReorder
    });
}

// Select a photo
function selectPhoto(filename, element) {
    // Deselect all
    document.querySelectorAll('.photo-item').forEach(item => {
        item.classList.remove('selected');
    });
    
    // Select clicked
    element.classList.add('selected');
    selectedPhotoName = filename;
    
    // Enable delete button
    document.getElementById('delete-photo-btn').disabled = false;
    
    // Enable caption textarea and button
    const captionTextarea = document.getElementById('photo-caption');
    const captionBtn = document.getElementById('update-caption-btn');
    
    captionTextarea.disabled = false;
    captionTextarea.value = currentPageCaptions[filename] || '';
    captionBtn.disabled = false;
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
        
        log('INFO', 'REORDER_RESPONSE', { status: response.status, ok: response.ok });
        const data = await response.json();
        
        if (data.success) {
            log('INFO', 'REORDER_SUCCESS', {});
            // Push undo state only if order actually changed
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
            alert('Error al reordenar fotos: ' + data.error);
            // Reload page to reset order
            await loadPage(currentPageIndex);
        }
    } catch (error) {
        log('ERROR', 'REORDER_EXCEPTION', { error: error.message, stack: error.stack });
        alert('Error de conexión al reordenar fotos');
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
    log('INFO', 'DELETE_PHOTO_START', { filename: selectedPhotoName, pageId });
    
    const confirmed = confirm(`¿Borrar la foto "${selectedPhotoName}"?`);
    
    if (!confirmed) {
        log('INFO', 'DELETE_PHOTO_CANCELLED', { filename: selectedPhotoName });
        return;
    }
    
    try {
        log('INFO', 'DELETE_PHOTO_REQUEST', { 
            url: `/api/page/${pageId}/delete-photo`,
            filename: selectedPhotoName 
        });
        
        const response = await fetch(`/api/page/${pageId}/delete-photo`, {
            method: 'DELETE',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({filename: selectedPhotoName})
        });
        
        log('INFO', 'DELETE_PHOTO_RESPONSE', { 
            status: response.status, 
            ok: response.ok,
            statusText: response.statusText 
        });
        
        const data = await response.json();
        log('INFO', 'DELETE_PHOTO_DATA', { success: data.success, data });
        
        if (data.success) {
            log('INFO', 'DELETE_PHOTO_SUCCESS', { filename: selectedPhotoName });
            selectedPhotoName = null;
            document.getElementById('delete-photo-btn').disabled = true;
            
            // Disable caption controls
            document.getElementById('photo-caption').disabled = true;
            document.getElementById('photo-caption').value = '';
            document.getElementById('update-caption-btn').disabled = true;
            
            incrementPendingChanges();
            log('INFO', 'DELETE_PHOTO_RELOAD_START', {});
            await loadPage(currentPageIndex);  // Reload to update list
            log('INFO', 'DELETE_PHOTO_REGENERATE_START', {});
            await regeneratePreview();
            log('INFO', 'DELETE_PHOTO_COMPLETE', {});
        } else {
            log('ERROR', 'DELETE_PHOTO_FAILED', { error: data.error });
            alert('Error al borrar foto: ' + data.error);
        }
    } catch (error) {
        log('ERROR', 'DELETE_PHOTO_EXCEPTION', { 
            error: error.message, 
            stack: error.stack,
            type: error.constructor.name 
        });
        alert('Error de conexión al borrar foto');
    }
}

// Split the current page into two: first half stays, second half moves to a new page right after
async function explodePage() {
    const page = PAGES_DATA[currentPageIndex];
    const n = page.photo_count;
    const stayCount = Math.ceil(n / 2);
    const moveCount = Math.floor(n / 2);

    if (n < 2) {
        alert('Se necesitan al menos 2 fotos para explotar una página.');
        return;
    }

    const confirmed = confirm(
        `¿Explotar la página ${page.number} en dos?\n\n` +
        `• Esta página quedará con ${stayCount} foto${stayCount !== 1 ? 's' : ''} (primera mitad).\n` +
        `• Se creará una nueva página con ${moveCount} foto${moveCount !== 1 ? 's' : ''} (segunda mitad).\n\n` +
        `La numeración final se actualizará en el próximo render.`
    );

    if (!confirmed) return;

    try {
        const response = await fetch(`/api/page/${page.id}/explode`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
        });

        const data = await response.json();

        if (data.success) {
            // Update current page photo_count in local state
            PAGES_DATA[currentPageIndex].photo_count = data.original_page.photo_count;

            // Insert new page entry right after current
            const newEntry = {
                id: data.new_page.id,
                number: data.new_page.number,
                title: data.new_page.section_titles[0] || `Página ${data.new_page.number}`,
                photo_count: data.new_page.photo_count,
                layout_mode: data.new_page.layout_mode,
            };
            PAGES_DATA.splice(currentPageIndex + 1, 0, newEntry);

            initPagePanel();
            await loadPage(currentPageIndex);
        } else {
            alert('Error al explotar página: ' + data.error);
        }
    } catch (error) {
        console.error('Failed to explode page:', error);
        alert('Error de conexión al explotar página');
    }
}

// Delete entire page
async function deletePage() {
    const pageId = PAGES_DATA[currentPageIndex].id;
    const pageNum = PAGES_DATA[currentPageIndex].number;
    
    const confirmed = confirm(
        `¿Borrar completamente la página ${pageNum}?\n\n` +
        `Esta acción no se puede deshacer.`
    );
    
    if (!confirmed) {
        return;
    }
    
    try {
        const response = await fetch(`/api/page/${pageId}/delete`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        if (data.success) {
            alert('Página borrada. Las páginas se renumerarán en el próximo render.');
            
            // Remove from local array
            PAGES_DATA.splice(currentPageIndex, 1);
            
            // Navigate to previous page or first page
            const newIndex = Math.max(0, currentPageIndex - 1);
            if (PAGES_DATA.length > 0) {
                await loadPage(newIndex);
            } else {
                alert('No quedan más páginas en el álbum.');
                exitEditor();
            }
        } else {
            alert('Error al borrar página: ' + data.error);
        }
    } catch (error) {
        console.error('Failed to delete page:', error);
        alert('Error de conexión al borrar página');
    }
}

// Update page title
async function updatePageTitle() {
    const titleInput = document.getElementById('page-title');
    const newTitle = titleInput.value.trim();
    
    log('INFO', 'UPDATE_TITLE_START', { newTitle });
    
    if (!newTitle) {
        log('WARN', 'UPDATE_TITLE_EMPTY', {});
        alert('El título no puede estar vacío');
        return;
    }
    
    const pageId = PAGES_DATA[currentPageIndex].id;
    
    // FIX: No hacer split por "/" ya que las fechas usan ese separador (DD/MM/YYYY)
    // El usuario edita un campo de texto libre, enviamos como un solo título
    const titles = [newTitle];
    
    log('INFO', 'UPDATE_TITLE_PARSED', { titles });
    
    try {
        // Get current page data to store old titles for undo
        let oldTitles = [];
        try {
            log('INFO', 'UPDATE_TITLE_FETCH_OLD', { pageId });
            const response_get = await fetch(`/api/page/${pageId}`);
            const data_get = await response_get.json();
            oldTitles = data_get.success ? data_get.page.section_titles : [];
            log('INFO', 'UPDATE_TITLE_OLD_FETCHED', { oldTitles });
        } catch (e) {
            log('WARN', 'UPDATE_TITLE_OLD_FETCH_FAILED', { error: e.message });
        }
        
        log('INFO', 'UPDATE_TITLE_REQUEST', { pageId, titles });
        const response = await fetch(`/api/page/${pageId}/title`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({titles: titles})
        });
        
        log('INFO', 'UPDATE_TITLE_RESPONSE', { status: response.status, ok: response.ok });
        const data = await response.json();
        
        if (data.success) {
            log('INFO', 'UPDATE_TITLE_SUCCESS', {});
            // Push undo state only if we have old titles
            if (oldTitles.length > 0) {
                pushUndoState('title', {
                    oldTitles: oldTitles,
                    newTitles: titles
                });
            }
            
            // Sync title in page navigator panel
            updatePagePanelTitle(currentPageIndex, titles[0] || `Página ${PAGES_DATA[currentPageIndex].number}`);
            PAGES_DATA[currentPageIndex].title = titles[0];
            
            incrementPendingChanges();
            await regeneratePreview();
        } else {
            log('ERROR', 'UPDATE_TITLE_FAILED', { error: data.error });
            alert('Error al actualizar título: ' + data.error);
        }
    } catch (error) {
        log('ERROR', 'UPDATE_TITLE_EXCEPTION', { error: error.message, stack: error.stack });
        alert('Error de conexión al actualizar título');
    }
}

// Regenerate preview
async function regeneratePreview() {
    const pageId = PAGES_DATA[currentPageIndex].id;
    
    log('INFO', 'REGENERATE_START', { pageId });
    showLoading();
    
    try {
        const response = await fetch(`/api/page/${pageId}/regenerate`, {
            method: 'POST'
        });
        
        log('INFO', 'REGENERATE_RESPONSE', { status: response.status, ok: response.ok });
        const data = await response.json();
        
        if (data.success) {
            log('INFO', 'REGENERATE_SUCCESS', {});
            // Reload preview with cache-busting timestamp
            loadPreview(pageId);
        } else {
            log('ERROR', 'REGENERATE_FAILED', { error: data.error });
            alert('Error al regenerar vista previa: ' + data.error);
        }
    } catch (error) {
        log('ERROR', 'REGENERATE_EXCEPTION', { error: error.message, stack: error.stack });
        alert('Error de conexión al regenerar vista previa');
    } finally {
        hideLoading();
    }
}

// Load preview PDF
function loadPreview(pageId) {
    const iframe = document.getElementById('pdf-preview');
    // Add timestamp to prevent caching
    iframe.src = `/api/page/${pageId}/preview?t=${Date.now()}`;
}

// Navigate pages
async function navigatePage(delta) {
    const newIndex = currentPageIndex + delta;
    log('INFO', 'NAVIGATE_PAGE', { from: currentPageIndex, to: newIndex, delta });
    
    if (newIndex >= 0 && newIndex < PAGES_DATA.length) {
        // Auto-save before changing page
        if (pendingChanges > 0) {
            log('INFO', 'NAVIGATE_AUTOSAVE', { pendingChanges });
            await saveChanges(true); // true = silent mode
        }
        await loadPage(newIndex);
    } else {
        log('WARN', 'NAVIGATE_OUT_OF_BOUNDS', { newIndex, totalPages: PAGES_DATA.length });
    }
}

// Navigate photo selection with arrow keys
function navigatePhotoSelection(delta) {
    const items = Array.from(document.querySelectorAll('.photo-item'));
    if (items.length === 0) return;
    
    const currentIndex = items.findIndex(item => item.classList.contains('selected'));
    
    let newIndex;
    if (currentIndex === -1) {
        // No selection, start from top or bottom
        newIndex = delta > 0 ? 0 : items.length - 1;
    } else {
        newIndex = currentIndex + delta;
    }
    
    // Wrap around or clamp
    if (newIndex >= 0 && newIndex < items.length) {
        const newItem = items[newIndex];
        const filename = newItem.dataset.filename;
        selectPhoto(filename, newItem);
        // Scroll into view smoothly
        newItem.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
}

// Update navigation button states
function updateNavigationButtons() {
    document.getElementById('prev-btn').disabled = currentPageIndex === 0;
    document.getElementById('next-btn').disabled = currentPageIndex === PAGES_DATA.length - 1;
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
    const newCaption = captionTextarea.value.trim();
    const oldCaption = currentPageCaptions[selectedPhotoName] || '';
    
    const pageId = PAGES_DATA[currentPageIndex].id;
    
    log('INFO', 'UPDATE_CAPTION_START', { filename: selectedPhotoName, newCaption, oldCaption });
    
    try {
        const response = await fetch(`/api/page/${pageId}/caption`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                filename: selectedPhotoName,
                caption: newCaption
            })
        });
        
        log('INFO', 'UPDATE_CAPTION_RESPONSE', { status: response.status, ok: response.ok });
        const data = await response.json();
        
        if (data.success) {
            log('INFO', 'UPDATE_CAPTION_SUCCESS', {});
            // Push undo state
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
            alert('Error al actualizar subtítulo: ' + data.error);
        }
    } catch (error) {
        log('ERROR', 'UPDATE_CAPTION_EXCEPTION', { error: error.message, stack: error.stack });
        alert('Error de conexión al actualizar subtítulo');
    }
}

// Undo system functions
function pushUndoState(action, data) {
    const currentPage = PAGES_DATA && PAGES_DATA[currentPageIndex];
    undoStack.push({
        action: action,
        pageId: currentPage ? currentPage.id : null,
        pageIndex: currentPage ? currentPageIndex : null,
        data: data,
        timestamp: Date.now()
    });
    
    // Keep only last MAX_UNDO_STEPS
    if (undoStack.length > MAX_UNDO_STEPS) {
        undoStack.shift();
    }
    
    // Enable undo button
    document.getElementById('undo-btn').disabled = false;
}

async function performUndo() {
    if (undoStack.length === 0) return;
    
    const state = undoStack.pop();
    
    // Navigate to the page where the action was performed if needed
    if (state.pageIndex !== currentPageIndex) {
        await loadPage(state.pageIndex);
    }
    
    // Perform undo based on action type
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
            default:
                console.warn('Unknown undo action:', state.action);
        }
    } catch (error) {
        console.error('Failed to perform undo:', error);
        alert('Error al deshacer la acción');
    }
    
    // Disable undo button if stack is empty
    if (undoStack.length === 0) {
        document.getElementById('undo-btn').disabled = true;
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
            
            // Update UI if this photo is selected
            if (selectedPhotoName === filename) {
                document.getElementById('photo-caption').value = oldCaption;
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
    
    // Track mouse focus for keyboard routing
    const panel = document.getElementById('page-panel');
    panel.addEventListener('mouseenter', () => { pagePanelFocused = true; photoListFocused = false; });
    panel.addEventListener('mouseleave', () => { pagePanelFocused = false; });

    const photoList = document.getElementById('photo-list');
    if (photoList && !photoList.dataset.focusWired) {
        photoList.addEventListener('mouseenter', () => { photoListFocused = true; pagePanelFocused = false; });
        photoList.addEventListener('mouseleave', () => { photoListFocused = false; });
        photoList.dataset.focusWired = '1';
    }

    log('INFO', 'PAGE_PANEL_INIT', { pages: PAGES_DATA.length });
}

function togglePagePanel() {
    const panel = document.getElementById('page-panel');
    pagePanelOpen = !pagePanelOpen;
    
    if (pagePanelOpen) {
        panel.classList.remove('collapsed');
        // Scroll active item into view after animation
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

function focusPagePanel() {
    photoListFocused = false;
    pagePanelFocused = true;
    document.getElementById('photo-list')?.classList.remove('panel-has-focus');
    document.getElementById('page-panel')?.classList.add('panel-has-focus');

    if (!pagePanelOpen) togglePagePanel();

    const items = document.querySelectorAll('.page-list-item');
    items.forEach((item, i) => {
        item.classList.toggle('keyboard-focus', i === pagePanelKeyboardIndex);
    });
    items[pagePanelKeyboardIndex]?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function focusPhotoList() {
    pagePanelFocused = false;
    photoListFocused = true;
    document.getElementById('page-panel')?.classList.remove('panel-has-focus');
    document.getElementById('photo-list')?.classList.add('panel-has-focus');

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

function navigatePagePanelSelection(delta) {
    const items = Array.from(document.querySelectorAll('.page-list-item'));
    if (items.length === 0) return;
    
    const newIndex = Math.max(0, Math.min(items.length - 1, pagePanelKeyboardIndex + delta));
    
    if (newIndex === pagePanelKeyboardIndex) return;
    
    // Visual keyboard focus indicator
    items.forEach((item, i) => {
        item.classList.remove('keyboard-focus');
        if (i === newIndex) item.classList.add('keyboard-focus');
    });
    
    items[newIndex].scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    
    // Navigate editor to this page
    navigateToPageFromPanel(newIndex);
}

// Save changes (placeholder - changes are auto-saved)
async function saveChanges(silent = false) {
    try {
        const response = await fetch('/api/save', {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.success) {
            if (!silent) {
                alert('Cambios guardados correctamente');
            }
            pendingChanges = 0;
        } else {
            if (!silent) {
                alert('Error al guardar: ' + data.error);
            }
        }
    } catch (error) {
        console.error('Failed to save:', error);
        if (!silent) {
            alert('Error de conexión al guardar');
        }
    }
}

// Exit editor
function exitEditor() {
    if (pendingChanges > 0) {
        const confirmed = confirm(
            `Hay ${pendingChanges} cambio(s) pendiente(s).\n\n` +
            `Los cambios ya están guardados automáticamente.\n` +
            `¿Cerrar el editor?`
        );
        
        if (!confirmed) {
            return;
        }
    }
    
    window.close();
    // If window.close() doesn't work (only works for windows opened by JS)
    setTimeout(() => {
        alert('Puedes cerrar esta pestaña manualmente.');
    }, 100);
}

// Show/hide loading overlay
function showLoading() {
    document.getElementById('loading-overlay').style.display = 'flex';
}

function hideLoading() {
    document.getElementById('loading-overlay').style.display = 'none';
}

// Toggle theme between light and dark mode
function toggleTheme() {
    const checkbox = document.getElementById('theme-toggle');
    const isDark = checkbox.checked;
    
    if (isDark) {
        document.body.classList.add('dark-mode');
    } else {
        document.body.classList.remove('dark-mode');
    }
    
    // Save preference to localStorage
    localStorage.setItem('editorTheme', isDark ? 'dark' : 'light');
    
    log('INFO', 'THEME_TOGGLED', { theme: isDark ? 'dark' : 'light' });
}
