// ═══════════════════════════════════════════════════════════════════════════
// Source Photos Mode Logic
// ═══════════════════════════════════════════════════════════════════════════

let currentEventIndex = 0;
let currentEventFolder = null;
let eventFolders = [];
let currentEventPhotos = [];
let selectedSourcePhoto = null;
let eventPanelOpen = false;
let eventPanelFocused = false;

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
    document.getElementById('regenerate-album-btn')?.addEventListener('click', regenerateAlbum);
    document.getElementById('delete-event-btn')?.addEventListener('click', deleteEvent);
    document.getElementById('event-panel-toggle')?.addEventListener('click', toggleEventPanel);
    
    document.addEventListener('keydown', handleSourceKeyboard);
}

function handleSourceKeyboard(e) {
    if (currentTab !== 'source') return;
    
    if (e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
        if (e.key === 'ArrowUp') {
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
            alert(t('error.load_folders') + data.error);
        }
    } catch (error) {
        log('ERROR', 'LOAD_EVENT_FOLDERS_EXCEPTION', { error: error.message });
        alert(t('error.connection_load_folders'));
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
            alert(t('error.load_event') + data.error);
        }
    } catch (error) {
        log('ERROR', 'LOAD_EVENT_EXCEPTION', { error: error.message });
        alert(t('error.connection_load_event'));
    }
}

// Render event details in sidebar
function renderSourceEventDetails(event) {
    const eventNameInput = document.getElementById('event-name-input');
    if (eventNameInput) {
        eventNameInput.value = event.name || '';
    }
    
    document.getElementById('source-event-name').textContent = event.name || '-';
    document.getElementById('source-photo-count').textContent = currentEventPhotos.length;
    
    const photoList = document.getElementById('source-photo-list');
    if (photoList) {
        photoList.textContent = '';
        
        currentEventPhotos.forEach((filename, idx) => {
            const div = document.createElement('div');
            div.className = 'photo-item';
            div.dataset.filename = filename;
            div.dataset.index = idx;
            
            const span = document.createElement('span');
            span.className = 'photo-name';
            span.textContent = filename;
            
            div.appendChild(span);
            div.addEventListener('click', (e) => selectSourcePhoto(filename, e.target.closest('.photo-item')));
            
            photoList.appendChild(div);
        });
    }
    
    if (currentEventPhotos.length > 0) {
        selectSourcePhoto(currentEventPhotos[0], document.querySelector('[data-filename]'));
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
    
    const confirmed = confirm(t('confirm.delete_photo', { name: selectedSourcePhoto }));
    
    if (!confirmed) {
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
            log('INFO', 'DELETE_SOURCE_PHOTO_SUCCESS', {});
            selectedSourcePhoto = null;
            await loadEvent(currentEventIndex);
        } else {
            log('ERROR', 'DELETE_SOURCE_PHOTO_FAILED', { error: data.error });
            alert(t('error.delete_source_photo') + data.error);
        }
    } catch (error) {
        log('ERROR', 'DELETE_SOURCE_PHOTO_EXCEPTION', { error: error.message });
        alert(t('error.connection_delete_source_photo'));
    }
}

// Rename event folder
async function renameEvent() {
    if (!currentEventFolder) {
        return;
    }
    
    const eventNameInput = document.getElementById('event-name-input');
    const newName = eventNameInput?.value.trim();
    
    if (!newName) {
        alert(t('validation.event_name_empty'));
        return;
    }
    
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
            alert(t('success.event_renamed'));
            await loadEventFolders();
            if (currentEventIndex < eventFolders.length) {
                await loadEvent(currentEventIndex);
            }
        } else {
            log('ERROR', 'RENAME_EVENT_FAILED', { error: data.error });
            alert(t('error.rename_event') + data.error);
        }
    } catch (error) {
        log('ERROR', 'RENAME_EVENT_EXCEPTION', { error: error.message });
        alert(t('error.connection_rename_event'));
    }
}

// Delete event folder
async function deleteEvent() {
    if (!currentEventFolder) {
        return;
    }
    
    const confirmed = confirm(t('confirm.delete_event', { name: currentEventFolder.name }));
    
    if (!confirmed) {
        return;
    }
    
    try {
        const response = await fetch(`/api/source/folder/${currentEventFolder.name}?force=true`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        if (data.success) {
            log('INFO', 'DELETE_EVENT_SUCCESS', {});
            alert(t('success.event_deleted'));
            await loadEventFolders();
            if (eventFolders.length > 0) {
                await loadEvent(0);
            }
        } else {
            log('ERROR', 'DELETE_EVENT_FAILED', { error: data.error });
            alert(t('error.delete_event') + data.error);
        }
    } catch (error) {
        log('ERROR', 'DELETE_EVENT_EXCEPTION', { error: error.message });
        alert(t('error.connection_delete_event'));
    }
}

// Regenerate album
async function regenerateAlbum() {
    let needsConfirm = false;
    
    try {
        const checkResponse = await fetch('/api/source/regenerate-album?check=true');
        const checkData = await checkResponse.json();
        needsConfirm = checkData.exists;
    } catch (e) {
        // Ignore
    }
    
    if (needsConfirm) {
    const confirmed = confirm(t('confirm.regenerate_album'));
        
        if (!confirmed) {
            return;
        }
    }
    
    showLoading(t('loading.album'));
    
    try {
        const response = await fetch('/api/source/regenerate-album', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ confirm: needsConfirm })
        });
        
        const data = await response.json();
        
        if (data.success) {
            log('INFO', 'REGENERATE_ALBUM_SUCCESS', {});
            alert(t('success.album_regenerated'));
            
            // Refresh album pages if they exist
            if (window.PAGES_DATA) {
                window.PAGES_DATA.length = 0;
                if (data.pages) {
                    window.PAGES_DATA.push(...data.pages);
                }
            }
        } else {
            log('ERROR', 'REGENERATE_ALBUM_FAILED', { error: data.error });
            alert(t('error.regenerate_album') + data.error);
        }
    } catch (error) {
        log('ERROR', 'REGENERATE_ALBUM_EXCEPTION', { error: error.message });
        alert(t('error.connection_regenerate_album'));
    } finally {
        hideLoading();
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
        
        const nameSpan = document.createElement('span');
        nameSpan.className = 'page-list-title';
        nameSpan.textContent = event.name || event.folder;
        nameSpan.style.flex = '1';
        
        const countSpan = document.createElement('span');
        countSpan.className = 'page-list-num';
        countSpan.textContent = String(event.photo_count || 0);
        
        item.appendChild(countSpan);
        item.appendChild(nameSpan);
        
        item.addEventListener('click', () => loadEvent(index));
        
        eventList.appendChild(item);
    });
    
    const panel = document.getElementById('event-panel');
    if (panel) {
        panel.addEventListener('mouseenter', () => { eventPanelFocused = true; });
        panel.addEventListener('mouseleave', () => { eventPanelFocused = false; });
    }
    
    log('INFO', 'EVENT_PANEL_INIT', { events: eventFolders.length });
}

function toggleEventPanel() {
    const panel = document.getElementById('event-panel');
    if (!panel) return;
    
    eventPanelOpen = !eventPanelOpen;
    
    if (eventPanelOpen) {
        panel.classList.remove('collapsed');
        setTimeout(() => {
            const activeItem = document.querySelector('#event-panel .page-list-item.active');
            if (activeItem) activeItem.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }, 260);
    } else {
        panel.classList.add('collapsed');
        eventPanelFocused = false;
    }
    
    log('INFO', 'EVENT_PANEL_TOGGLED', { open: eventPanelOpen });
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

// Initialize when tab is switched
document.addEventListener('DOMContentLoaded', () => {
    if (currentTab === 'source') {
        initSourceMode();
    }
});
