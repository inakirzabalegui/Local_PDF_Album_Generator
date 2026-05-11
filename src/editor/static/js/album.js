// ═══════════════════════════════════════════════════════════════════════════
// Album Edition Mode Logic
// ═══════════════════════════════════════════════════════════════════════════

// Album Editor State
let currentPageIndex = 0;
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
let photoListFocused = false;

// Undo system
const undoStack = [];
const MAX_UNDO_STEPS = 5;

// PDF.js preview state
let _currentPreviewPdf = null;
let _previewResizeObserver = null;
// Retry counter + cancellation token for the layout-timing fix: the preview
// container may report a 0 or absurdly small clientWidth/Height while the
// browser is still settling the flex cascade. When that happens we reschedule
// via requestAnimationFrame; the token lets a fresh loadPreview() invalidate
// any stale retries queued from a previous page.
let _previewRenderRetries = 0;
let _previewRenderToken = 0;
// PDF.js disallows concurrent page.render() on the same canvas. Track the
// in-flight RenderTask so we can cancel it before starting a new one — this
// prevents the "Cannot use the same canvas during multiple render() operations"
// error that fires when ResizeObserver triggers a re-render mid-render.
let _currentRenderTask = null;
const PREVIEW_RENDER_MAX_RETRIES = 60;       // ~1s at 60 fps
const PREVIEW_MIN_CONTAINER_PX = 100;        // anything below this is "not laid out yet"

// Initialize album mode when tab is active
function initAlbumMode() {
    log('INFO', 'ALBUM_MODE_INIT', { totalPages: PAGES_DATA.length });

    initPagePanel();

    if (PAGES_DATA.length > 0) {
        loadPage(0);
    }

    setupAlbumEventListeners();
    setupPreviewResizeObserver();
}

function setupPreviewResizeObserver() {
    if (_previewResizeObserver) return; // already set up
    const container = document.querySelector('#tab-album-content .preview-container');
    if (!container) return;
    _previewResizeObserver = new ResizeObserver(_debounce(() => {
        if (_currentPreviewPdf) renderCurrentPreviewToCanvas();
    }, 120));
    _previewResizeObserver.observe(container);
}

function _debounce(fn, ms) {
    let timer;
    return function(...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), ms);
    };
}

async function renderCurrentPreviewToCanvas() {
    if (!_currentPreviewPdf) return;
    const canvas = document.getElementById('pdf-preview');
    if (!canvas) return;
    const container = canvas.closest('.preview-container');
    if (!container) return;

    // Cancel any in-flight render on this canvas. PDF.js raises
    // "Cannot use the same canvas during multiple render() operations"
    // if a previous render hasn't finished — common when ResizeObserver
    // fires while the initial render is still in progress.
    if (_currentRenderTask) {
        try { _currentRenderTask.cancel(); } catch (_) { /* noop */ }
        _currentRenderTask = null;
    }

    // Layout-timing guard: container may report 0 (not laid out yet) or a tiny
    // positive width during the initial flex cascade. Retry on next frame.
    const rect = container.getBoundingClientRect();
    const rawW = rect.width || container.clientWidth;
    const rawH = rect.height || container.clientHeight;
    const containerW = rawW - 56; // subtract padding (28px each side)
    const containerH = rawH - 56;
    const tooSmall =
        containerW < PREVIEW_MIN_CONTAINER_PX ||
        containerH < PREVIEW_MIN_CONTAINER_PX;

    if (tooSmall) {
        if (_previewRenderRetries >= PREVIEW_RENDER_MAX_RETRIES) {
            console.warn(
                '[PDF preview] container never reached a usable size after',
                PREVIEW_RENDER_MAX_RETRIES,
                'frames; final measurement:',
                { rawW, rawH, containerW, containerH }
            );
            return;
        }
        _previewRenderRetries++;
        const tokenAtSchedule = _previewRenderToken;
        const pdfAtSchedule = _currentPreviewPdf;
        requestAnimationFrame(() => {
            if (tokenAtSchedule !== _previewRenderToken) return;
            if (pdfAtSchedule !== _currentPreviewPdf) return;
            renderCurrentPreviewToCanvas();
        });
        return;
    }

    const pdfAtStart = _currentPreviewPdf;
    let renderTask = null;
    try {
        const page = await pdfAtStart.getPage(1);
        // Bail if a newer loadPreview() superseded us during the await.
        if (pdfAtStart !== _currentPreviewPdf) return;

        const baseViewport = page.getViewport({ scale: 1 });
        const scale = Math.min(containerW / baseViewport.width, containerH / baseViewport.height);
        const viewport = page.getViewport({ scale });
        const dpr = window.devicePixelRatio || 1;

        canvas.width  = Math.round(viewport.width  * dpr);
        canvas.height = Math.round(viewport.height * dpr);
        canvas.style.width  = Math.round(viewport.width)  + 'px';
        canvas.style.height = Math.round(viewport.height) + 'px';

        const ctx = canvas.getContext('2d');
        ctx.scale(dpr, dpr);

        renderTask = page.render({ canvasContext: ctx, viewport });
        _currentRenderTask = renderTask;
        await renderTask.promise;

        // Clear only if we're still the latest task — a newer cancel may have
        // already nulled this out.
        if (_currentRenderTask === renderTask) _currentRenderTask = null;

        _previewRenderRetries = 0;
        // Hide the skeleton placeholder now that a real page is on the canvas.
        const skel = document.getElementById('pdf-preview-skeleton');
        if (skel) skel.classList.add('hidden');
    } catch (err) {
        // PDF.js rejects with RenderingCancelledException when .cancel() is
        // called. That's our intended flow — silently ignore it.
        if (err && (err.name === 'RenderingCancelledException' || err.message === 'Rendering cancelled')) {
            if (_currentRenderTask === renderTask) _currentRenderTask = null;
            return;
        }
        if (_currentRenderTask === renderTask) _currentRenderTask = null;
        console.error('[PDF preview render]', err);
        log('WARN', 'PREVIEW_RENDER_ERROR', { err: err.message });
        if (typeof showToast === 'function') {
            showToast('Error al renderizar preview: ' + err.message, { type: 'error' });
        }
    }
}

// Setup Event Listeners for Album Mode
function setupAlbumEventListeners() {
    // Actions
    document.getElementById('exit-btn')?.addEventListener('click', exitEditor);
    document.getElementById('explode-page-btn')?.addEventListener('click', explodePage);
    document.getElementById('delete-photo-btn')?.addEventListener('click', deleteSelectedPhoto);
    document.getElementById('delete-page-btn')?.addEventListener('click', deletePage);
    document.getElementById('update-caption-btn')?.addEventListener('click', updatePhotoCaption);
    document.getElementById('layout-mode-btn')?.addEventListener('click', openLayoutModeModal);
    document.getElementById('apply-layout-mode-btn')?.addEventListener('click', applyLayoutModeFromModal);
    document.getElementById('cancel-layout-mode-btn')?.addEventListener('click', closeLayoutModeModal);
    document.getElementById('shuffle-layout-btn')?.addEventListener('click', shuffleLayout);
    document.getElementById('toggle-page-completed-btn')?.addEventListener('click', togglePageCompleted);

    // Keyboard shortcuts
    document.addEventListener('keydown', handleAlbumKeyboard);
}

// Handle keyboard shortcuts in album mode
function handleAlbumKeyboard(e) {
    if (currentTab !== 'album') return;

    // Photo viewer has its own keys and takes priority over everything
    const viewerEl = document.getElementById('photo-viewer-modal');
    if (viewerEl && !viewerEl.classList.contains('hidden')) {
        if (e.key === 'Escape') { e.preventDefault(); closePhotoViewer(); }
        else if (e.key === 'ArrowUp') { e.preventDefault(); navigatePhotoViewer(-1); }
        else if (e.key === 'ArrowDown') { e.preventDefault(); navigatePhotoViewer(1); }
        else if (e.key === 'v' || e.key === 'V') { e.preventDefault(); closePhotoViewer(); }
        else if (e.key === 'd' || e.key === 'D') {
            e.preventDefault();
            if (selectedPhotoName) {
                const filenameToDelete = selectedPhotoName;
                const items = Array.from(document.querySelectorAll('#photo-list .photo-item'));
                const currentIdx = items.findIndex(el => el.dataset.filename === filenameToDelete);
                const remaining = items.length - 1;
                const viewerImg = document.getElementById('photo-viewer-img');
                const viewerContent = viewerImg ? viewerImg.closest('.photo-viewer-content') : null;
                const itemEl = items[currentIdx] || null;
                playDeleteFeedback({ viewerEl: viewerContent, itemEl }).then(() => {
                    deletePhotoByName(filenameToDelete).then(() => {
                        if (remaining <= 0) {
                            closePhotoViewer();
                        } else {
                            const newItems = Array.from(document.querySelectorAll('#photo-list .photo-item'));
                            if (newItems.length > 0) {
                                const nextIdx = Math.min(currentIdx, newItems.length - 1);
                                openPhotoViewer(newItems[nextIdx].dataset.filename);
                            } else {
                                closePhotoViewer();
                            }
                        }
                    });
                });
            }
        }
        return;
    }

    if (document.querySelector('.modal:not(.hidden)')) return;

    if (e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
        if (e.key === 'ArrowLeft') {
            if (photoListFocused) {
                e.preventDefault();
                focusPagePanel();
            }
        } else if (e.key === 'ArrowRight') {
            if (pagePanelFocused) {
                e.preventDefault();
                focusPhotoList();
            }
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
            if (selectedPhotoName) {
                e.preventDefault();
                deleteSelectedPhoto();
            }
        } else if (e.key === 'v' || e.key === 'V') {
            if (selectedPhotoName) {
                e.preventDefault();
                openPhotoViewer(selectedPhotoName);
            }
        } else if (e.key === 'a' || e.key === 'A') {
            e.preventDefault();
            shuffleLayout();
        } else if (e.key === 'e' || e.key === 'E') {
            e.preventDefault();
            explodePage();
        } else if (e.key === 'c' || e.key === 'C') {
            e.preventDefault();
            togglePageCompleted();
        }
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
            // Sync completed flag from server response into PAGES_DATA
            if (typeof data.page.completed === 'boolean') {
                PAGES_DATA[index].completed = data.page.completed;
            }
            renderPageDetails(data.page);
            loadPreview(page.id);
            updatePagePanelActiveItem(index);
            syncPageCompletedUI(index);
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
async function deletePhotoByName(filename) {
    if (!filename) return;
    const pageId = PAGES_DATA[currentPageIndex].id;
    log('INFO', 'DELETE_PHOTO_START', { filename });
    try {
        // #region agent log
        fetch('http://127.0.0.1:7583/ingest/f99a3167-114d-4776-a87f-6f247420d0df',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'02279c'},body:JSON.stringify({sessionId:'02279c',location:'album.js:deleteSelectedPhoto',message:'delete album photo request',data:{pageId:pageId,filename:filename},timestamp:Date.now()})}).catch(()=>{});
        // #endregion
        const response = await fetch(`/api/page/${pageId}/delete-photo`, {
            method: 'DELETE',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({filename: filename})
        });

        const data = await response.json();

        // #region agent log
        fetch('http://127.0.0.1:7583/ingest/f99a3167-114d-4776-a87f-6f247420d0df',{method:'POST',headers:{'Content-Type':'application/json','X-Debug-Session-Id':'02279c'},body:JSON.stringify({sessionId:'02279c',location:'album.js:deleteSelectedPhoto',message:'delete album photo response',data:{status:response.status,success:data.success,error:data.error||null},timestamp:Date.now()})}).catch(()=>{});
        // #endregion

        if (data.success) {
            log('INFO', 'DELETE_PHOTO_SUCCESS', { trash_token: data.trash_token });
            if (data.trash_token) {
                pushUndoState('delete_photo', {
                    filename: filename,
                    trash_token: data.trash_token,
                });
            }

            if (selectedPhotoName === filename) {
                selectedPhotoName = null;
                document.getElementById('delete-photo-btn').disabled = true;

                const captionTextarea = document.getElementById('photo-caption');
                if (captionTextarea) {
                    captionTextarea.disabled = true;
                    captionTextarea.value = '';
                }

                const captionBtn = document.getElementById('update-caption-btn');
                if (captionBtn) captionBtn.disabled = true;
            }

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

async function deleteSelectedPhoto() {
    if (!selectedPhotoName) {
        log('WARN', 'DELETE_PHOTO_NO_SELECTION', {});
        return;
    }

    const confirmed = await showConfirm({
        title: 'Borrar foto',
        message: t('confirm.delete_photo', { name: selectedPhotoName }),
        danger: true
    });

    if (!confirmed) {
        log('INFO', 'DELETE_PHOTO_CANCELLED', {});
        return;
    }

    const previewContainer = document.querySelector('#tab-album-content .preview-container');
    const itemEl = document.querySelector(
        `#photo-list .photo-item[data-filename="${CSS.escape(selectedPhotoName)}"]`
    );
    await playDeleteFeedback({ viewerEl: previewContainer, itemEl });

    await deletePhotoByName(selectedPhotoName);
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
    const currentPage = PAGES_DATA[currentPageIndex];
    const pageId = currentPage.id;
    const pageNum = currentPage.number;
    const sectionId = currentPage.section_id || '';
    const pageTitle = currentPage.title || `Página ${pageNum}`;

    // Determine if this is the last page of its section
    const isLastInSection = sectionId !== '' &&
        PAGES_DATA.filter(p => (p.section_id || '') === sectionId).length === 1;

    const confirmMessage = isLastInSection
        ? t('confirm.delete_page_last_in_section_message', { title: pageTitle })
        : t('confirm.delete_page', { num: pageNum });
    const confirmTitle = isLastInSection
        ? t('confirm.delete_page_last_in_section_title')
        : 'Borrar página';

    const confirmed = await showConfirm({
        title: confirmTitle,
        message: confirmMessage,
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

            // Reload the full pages list so numbering is fresh after server-side renumber
            const pagesResp = await fetch('/api/pages');
            const pagesData = await pagesResp.json();

            if (pagesData.success && pagesData.pages.length > 0) {
                PAGES_DATA.length = 0;
                pagesData.pages.forEach(p => PAGES_DATA.push(p));

                // Navigate to the same position or the previous one
                const newIndex = Math.min(currentPageIndex, PAGES_DATA.length - 1);
                await loadPage(Math.max(0, newIndex));
            } else {
                PAGES_DATA.length = 0;
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

// Shuffle photos into a random order, refresh sidebar and re-render preview
async function shuffleLayout() {
    if (!PAGES_DATA || PAGES_DATA.length === 0) return;
    const pageId = PAGES_DATA[currentPageIndex].id;

    log('INFO', 'SHUFFLE_LAYOUT_START', { pageId });

    try {
        const response = await fetch(`/api/page/${pageId}/shuffle-layout`, {
            method: 'POST'
        });
        const data = await response.json();

        if (data.success) {
            log('INFO', 'SHUFFLE_LAYOUT_SUCCESS', { seed: data.layout_seed });
            // Backend already regenerated the preview PDF; reload sidebar and iframe
            const pageResp = await fetch(`/api/page/${pageId}`);
            const pageData = await pageResp.json();
            if (pageData.success) {
                renderPageDetails(pageData.page);
            }
            loadPreview(pageId);
        } else {
            log('ERROR', 'SHUFFLE_LAYOUT_FAILED', { error: data.error });
            showToast(t('error.shuffle') + data.error, { type: 'error' });
        }
    } catch (error) {
        log('ERROR', 'SHUFFLE_LAYOUT_EXCEPTION', { error: error.message });
        showToast(t('error.connection_shuffle'), { type: 'error' });
    }
}

// Photo Viewer Modal (tecla V)
function openPhotoViewer(filename) {
    if (!filename || !PAGES_DATA || PAGES_DATA.length === 0) return;
    const pageId = PAGES_DATA[currentPageIndex].id;
    const img = document.getElementById('photo-viewer-img');
    const caption = document.getElementById('photo-viewer-caption');
    const modal = document.getElementById('photo-viewer-modal');
    if (!img || !modal) return;

    img.src = `/api/page/${pageId}/image/${encodeURIComponent(filename)}`;
    if (caption) caption.textContent = filename;
    modal.classList.remove('hidden');

    const el = document.querySelector(
        `#photo-list .photo-item[data-filename="${CSS.escape(filename)}"]`
    );
    if (el && selectedPhotoName !== filename) {
        selectPhoto(filename, el);
    }
}

function closePhotoViewer() {
    const modal = document.getElementById('photo-viewer-modal');
    if (modal) modal.classList.add('hidden');
    const img = document.getElementById('photo-viewer-img');
    if (img) img.src = '';
}

function handlePhotoViewerOverlayClick(e) {
    if (e.target.id === 'photo-viewer-modal') closePhotoViewer();
}

function navigatePhotoViewer(delta) {
    const items = Array.from(document.querySelectorAll('#photo-list .photo-item'));
    if (items.length === 0) return;
    const currentIdx = items.findIndex(el => el.dataset.filename === selectedPhotoName);
    const n = items.length;
    const startIdx = currentIdx < 0 ? 0 : currentIdx;
    const newIdx = ((startIdx + delta) % n + n) % n;
    const newFilename = items[newIdx].dataset.filename;
    if (newFilename) openPhotoViewer(newFilename);
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
async function loadPreview(pageId) {
    if (typeof pdfjsLib === 'undefined') {
        log('WARN', 'PDFJS_NOT_LOADED', {});
        console.error('[PDF preview] pdfjsLib not loaded — CDN script may have failed.');
        if (typeof showToast === 'function') {
            showToast('PDF.js no se ha cargado (revisa la conexión a internet).', { type: 'error' });
        }
        return;
    }
    // Invalidate any pending render retries from a previous page and reset
    // the layout-timing retry counter for this fresh load.
    _previewRenderToken++;
    _previewRenderRetries = 0;
    _currentPreviewPdf = null;
    // Abort any render still in flight on the canvas from the previous page.
    if (_currentRenderTask) {
        try { _currentRenderTask.cancel(); } catch (_) { /* noop */ }
        _currentRenderTask = null;
    }
    const canvas = document.getElementById('pdf-preview');
    if (canvas) {
        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);
    }
    // Re-show the skeleton while the new page is being fetched and rendered.
    const skel = document.getElementById('pdf-preview-skeleton');
    if (skel) skel.classList.remove('hidden');
    try {
        const url = `/api/page/${pageId}/preview?t=${Date.now()}`;
        const pdf = await pdfjsLib.getDocument({ url }).promise;
        _currentPreviewPdf = pdf;
        // Always wait for one frame so the browser has a chance to lay out
        // whatever DOM updates landed alongside this load (e.g. sidebar
        // rerender). The render function itself will retry if the container
        // still measures too small after this initial frame.
        requestAnimationFrame(() => {
            // Bail if a newer loadPreview() superseded this attempt.
            if (pdf !== _currentPreviewPdf) return;
            renderCurrentPreviewToCanvas();
        });
    } catch (err) {
        console.error('[PDF preview load]', err);
        log('WARN', 'PREVIEW_LOAD_ERROR', { pageId, err: err.message });
        if (typeof showToast === 'function') {
            showToast('No se pudo cargar el preview: ' + err.message, { type: 'error' });
        }
    }
}

// Navigate pages
async function navigatePage(delta) {
    const newIndex = currentPageIndex + delta;
    log('INFO', 'NAVIGATE_PAGE', { from: currentPageIndex, to: newIndex, delta });
    
    if (newIndex >= 0 && newIndex < PAGES_DATA.length) {
        await loadPage(newIndex);
    } else {
        log('WARN', 'NAVIGATE_OUT_OF_BOUNDS', { newIndex });
    }
}

// Navigate photo selection with arrow keys
function navigatePhotoSelection(delta) {
    const items = Array.from(document.querySelectorAll('#photo-list .photo-item'));
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
// Completed State
// ═══════════════════════════════════════════════════════════════════════════

function applyCompletedClass(itemEl, completed) {
    if (!itemEl) return;
    itemEl.classList.toggle('is-completed', completed);
}

function updateCompletedButton(btnEl, completed) {
    if (!btnEl) return;
    if (completed) {
        btnEl.textContent = '↩️ Marcar pendiente';
        btnEl.classList.add('btn-completed-active');
        btnEl.classList.remove('btn-secondary');
    } else {
        btnEl.textContent = '✅ Completado';
        btnEl.classList.remove('btn-completed-active');
        btnEl.classList.add('btn-secondary');
    }
}

async function togglePageCompleted() {
    if (PAGES_DATA.length === 0) return;

    const page = PAGES_DATA[currentPageIndex];
    const newCompleted = !page.completed;

    try {
        const response = await fetch(`/api/page/${page.id}/completed`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ completed: newCompleted }),
        });
        const data = await response.json();
        if (data.success) {
            page.completed = newCompleted;
            const itemEl = document.querySelector(`#page-list .page-list-item[data-index="${currentPageIndex}"]`);
            applyCompletedClass(itemEl, newCompleted);
            updateCompletedButton(document.getElementById('toggle-page-completed-btn'), newCompleted);
        }
    } catch (error) {
        log('ERROR', 'TOGGLE_PAGE_COMPLETED_ERROR', { error: error.message });
    }
}

function syncPageCompletedUI(index) {
    const page = PAGES_DATA[index];
    if (!page) return;
    const btn = document.getElementById('toggle-page-completed-btn');
    updateCompletedButton(btn, page.completed);
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

// Sortable instance for the page panel (page reordering)
let pagePanelSortable = null;

function initPagePanel() {
    const pageList = document.getElementById('page-list');
    if (!pageList) return;

    pageList.textContent = '';

    PAGES_DATA.forEach((page, index) => {
        const item = document.createElement('div');
        item.className = 'page-list-item';
        item.dataset.index = index;
        item.dataset.pageId = page.id;
        item.dataset.sectionId = page.section_id || '';

        const numSpan = document.createElement('span');
        numSpan.className = 'page-list-num';
        numSpan.textContent = String(page.number).padStart(2, '0');

        const titleWrap = document.createElement('span');
        titleWrap.className = 'page-list-title-wrap';

        const titleSpan = document.createElement('span');
        titleSpan.className = 'page-list-title';
        titleSpan.textContent = page.title || `Página ${page.number}`;
        titleSpan.id = `page-panel-title-${index}`;
        titleWrap.appendChild(titleSpan);

        if (page.subtitle) {
            const subSpan = document.createElement('span');
            subSpan.className = 'page-list-subtitle';
            subSpan.textContent = page.subtitle;
            titleWrap.appendChild(subSpan);
        }

        const dot = document.createElement('span');
        dot.className = 'completed-dot';
        dot.title = 'Revisado';

        item.appendChild(numSpan);
        item.appendChild(titleWrap);
        item.appendChild(dot);

        if (page.completed) {
            item.classList.add('is-completed');
        }

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

    // Attach Sortable for page reordering (within-section only)
    if (pagePanelSortable) {
        pagePanelSortable.destroy();
        pagePanelSortable = null;
    }
    if (typeof Sortable !== 'undefined' && PAGES_DATA.length > 1) {
        pagePanelSortable = Sortable.create(pageList, {
            animation: 150,
            ghostClass: 'page-sortable-ghost',
            chosenClass: 'page-sortable-chosen',
            onMove(evt) {
                const draggedSectionId = evt.dragged.dataset.sectionId || '';
                const relatedSectionId = evt.related.dataset.sectionId || '';
                if (draggedSectionId !== relatedSectionId) {
                    evt.dragged.classList.add('page-drag-forbidden');
                    return false; // cancel the move
                }
                evt.dragged.classList.remove('page-drag-forbidden');
                return true;
            },
            onEnd(evt) {
                evt.item.classList.remove('page-drag-forbidden');
                // If position unchanged, nothing to do
                if (evt.oldIndex === evt.newIndex) return;
                handlePageReorder(evt.item.dataset.pageId);
            },
        });
    }

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

// Handle page reorder after a panel drag-and-drop
async function handlePageReorder(draggedPageId) {
    // Collect new order from DOM
    const items = document.querySelectorAll('#page-list .page-list-item');
    const orderedPageIds = Array.from(items).map(el => el.dataset.pageId);

    try {
        const response = await fetch('/api/pages/reorder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ordered_page_ids: orderedPageIds }),
        });

        const data = await response.json();

        if (data.success) {
            showToast(t('success.pages_reordered'), { type: 'success' });

            // Reload page list and refocus the dragged page by its new id
            const pagesResp = await fetch('/api/pages');
            const pagesData = await pagesResp.json();

            if (pagesData.success && pagesData.pages.length > 0) {
                // Find what the dragged page's new id is from renamed_pages
                let newDraggedId = draggedPageId;
                if (data.renamed_pages && data.renamed_pages.length > 0) {
                    const renamed = data.renamed_pages.find(r => r.old_id === draggedPageId);
                    if (renamed) newDraggedId = renamed.new_id;
                }

                PAGES_DATA.length = 0;
                pagesData.pages.forEach(p => PAGES_DATA.push(p));

                // Find the new index of the dragged page
                const newIndex = PAGES_DATA.findIndex(p => p.id === newDraggedId);
                await loadPage(Math.max(0, newIndex !== -1 ? newIndex : 0));
            }
        } else {
            const errorMsg = data.error === 'Cross-section reordering not allowed'
                ? t('error.reorder_cross_section')
                : t('error.reorder_pages') + (data.error || '');
            showToast(errorMsg, { type: 'error' });

            // Restore visual order by reloading from server
            const pagesResp = await fetch('/api/pages');
            const pagesData = await pagesResp.json();
            if (pagesData.success && pagesData.pages.length > 0) {
                PAGES_DATA.length = 0;
                pagesData.pages.forEach(p => PAGES_DATA.push(p));
                await loadPage(currentPageIndex);
            }
        }
    } catch (error) {
        console.error('Failed to reorder pages:', error);
        showToast(t('error.connection_reorder_pages'), { type: 'error' });

        // Restore visual order
        const pagesResp = await fetch('/api/pages').catch(() => null);
        if (pagesResp && pagesResp.ok) {
            const pagesData = await pagesResp.json();
            if (pagesData.success && pagesData.pages.length > 0) {
                PAGES_DATA.length = 0;
                pagesData.pages.forEach(p => PAGES_DATA.push(p));
                await loadPage(currentPageIndex);
            }
        }
    }
}

// Move logical focus to the page panel (left) — highlights + toggles flags
function focusPagePanel() {
    photoListFocused = false;
    pagePanelFocused = true;
    document.getElementById('album-sidebar')?.classList.remove('panel-has-focus');
    document.getElementById('page-panel')?.classList.add('panel-has-focus');

    const items = document.querySelectorAll('#page-panel .page-list-item');
    items.forEach((item, i) => {
        item.classList.toggle('keyboard-focus', i === currentPageIndex);
    });
    items[currentPageIndex]?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// Move logical focus to the photo list (right)
function focusPhotoList() {
    pagePanelFocused = false;
    photoListFocused = true;
    document.getElementById('page-panel')?.classList.remove('panel-has-focus');
    document.getElementById('album-sidebar')?.classList.add('panel-has-focus');

    const items = document.querySelectorAll('#photo-list .photo-item');
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
    const items = document.querySelectorAll('#page-panel .page-list-item');
    items.forEach((item, i) => {
        item.classList.toggle('active', i === index);
    });
    items[index]?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function updatePagePanelTitle(index, newTitle) {
    const titleEl = document.getElementById(`page-panel-title-${index}`);
    if (titleEl) titleEl.textContent = newTitle;
}

function navigatePagePanelSelection(delta) {
    const items = Array.from(document.querySelectorAll('#page-panel .page-list-item'));
    if (items.length === 0) return;
    const activeItem = document.querySelector('#page-panel .page-list-item.active');
    const currentIndex = items.indexOf(activeItem);
    const newIndex = Math.max(0, Math.min(items.length - 1, currentIndex + delta));
    if (newIndex !== currentIndex) {
        navigateToPageFromPanel(newIndex);
    }
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

// Exit editor
function exitEditor() {
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
