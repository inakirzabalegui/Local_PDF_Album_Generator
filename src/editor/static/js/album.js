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

// Layout cycling (L / Shift+L). Order mirrors the layout-mode modal.
const LAYOUT_MODE_ORDER = [
    'mesa_de_luz',
    'grid_compacto',
    'hibrido',
    'cuadricula_uniforme',
    'cuadricula_compacta',
    'cuadricula_maximizada',
];
const LAYOUT_MODE_LABEL_KEYS = {
    'mesa_de_luz': 'album.layout_mesa',
    'grid_compacto': 'album.layout_grid',
    'hibrido': 'album.layout_hibrido',
    'cuadricula_uniforme': 'album.layout_cuadricula_uniforme',
    'cuadricula_compacta': 'album.layout_cuadricula_compacta',
    'cuadricula_maximizada': 'album.layout_cuadricula_maximizada',
};
let isLayoutCycling = false;
let isShuffling = false;

// Page Show (fullscreen PDF viewer) state — tecla S
let _showViewerIndex = 0;
let _showViewerRenderTask = null;
let _showViewerPdf = null;

// Photo Viewer origin — null when opened normally, 'show' when entered from Show
// (used to decide whether to re-open Show after deleting the last photo).
let _vEntryOrigin = null;

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

let _albumInitDone = false;

// Initialize album mode when tab is active
function initAlbumMode() {
    log('INFO', 'ALBUM_MODE_INIT', { totalPages: PAGES_DATA.length });

    initPagePanel();

    if (PAGES_DATA.length > 0) {
        let targetIndex;
        if (!_albumInitDone) {
            const firstIncomplete = PAGES_DATA.findIndex(p => p.completed === false);
            targetIndex = firstIncomplete >= 0 ? firstIncomplete : 0;
            _albumInitDone = true;
        } else {
            targetIndex = Math.max(0, Math.min(PAGES_DATA.length - 1, currentPageIndex));
        }
        loadPage(targetIndex);
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
    document.getElementById('move-page-btn')?.addEventListener('click', openMovePageDialog);
    document.getElementById('delete-photo-btn')?.addEventListener('click', deleteSelectedPhoto);
    document.getElementById('delete-page-btn')?.addEventListener('click', deletePage);
    document.getElementById('update-caption-btn')?.addEventListener('click', updatePhotoCaption);
    document.getElementById('layout-mode-btn')?.addEventListener('click', openLayoutModeModal);
    document.getElementById('apply-layout-mode-btn')?.addEventListener('click', applyLayoutModeFromModal);
    document.getElementById('cancel-layout-mode-btn')?.addEventListener('click', closeLayoutModeModal);
    document.getElementById('shuffle-layout-btn')?.addEventListener('click', shuffleLayout);
    document.getElementById('grid-equalize-btn')?.addEventListener('click', () => updateLayoutMode('cuadricula_uniforme'));
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
        else if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') { e.preventDefault(); navigatePhotoViewer(-1); }
        else if (e.key === 'ArrowDown' || e.key === 'ArrowRight') { e.preventDefault(); navigatePhotoViewer(1); }
        else if (e.key === 'v' || e.key === 'V') { e.preventDefault(); closePhotoViewer(); }
        else if (e.key === 's' || e.key === 'S') { e.preventDefault(); openPageViewerFromV(); }
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
                const wasFromShow = (_vEntryOrigin === 'show');
                playDeleteFeedback({ viewerEl: viewerContent, itemEl }).then(() => {
                    deletePhotoByName(filenameToDelete).then(() => {
                        if (remaining <= 0) {
                            // Deleted last photo on this page
                            if (wasFromShow) {
                                // Return to Show with the now-empty page
                                closePhotoViewer();
                                openPageViewer(currentPageIndex);
                            } else {
                                closePhotoViewer();
                            }
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

    // Page Show viewer (tecla S) has its own navigation keys
    const showModal = document.getElementById('page-show-modal');
    if (showModal && !showModal.classList.contains('hidden')) {
        if (e.key === 'Escape' || e.key === 's' || e.key === 'S') { e.preventDefault(); closePageViewer(); }
        else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') { e.preventDefault(); navigatePageViewer(-1); }
        else if (e.key === 'ArrowRight' || e.key === 'ArrowDown') { e.preventDefault(); navigatePageViewer(1); }
        else if (e.key === 'v' || e.key === 'V') { e.preventDefault(); openPhotoViewerFromShow(); }
        else if ((e.key === 'l' || e.key === 'L') && !e.ctrlKey && !e.metaKey && !e.altKey) {
            e.preventDefault();
            _cycleLayoutFromShow(e.shiftKey ? -1 : 1);
        }
        else if ((e.key === 'a' || e.key === 'A') && !e.ctrlKey && !e.metaKey && !e.altKey) {
            e.preventDefault();
            _shuffleLayoutFromShow();
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
                if (e.ctrlKey || e.metaKey) {
                    navigatePagePanelToNextStateChange(-1);
                } else {
                    navigatePagePanelSelection(-1);
                }
            } else {
                navigatePhotoSelection(-1);
            }
        } else if (e.key === 'ArrowDown') {
            e.preventDefault();
            if (pagePanelFocused && pagePanelOpen) {
                if (e.ctrlKey || e.metaKey) {
                    navigatePagePanelToNextStateChange(1);
                } else {
                    navigatePagePanelSelection(1);
                }
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
        } else if (e.key === 's' || e.key === 'S') {
            e.preventDefault();
            const startIdx = _resolveShowStartIndex();
            if (startIdx !== null) openPageViewer(startIdx);
        } else if (e.key === 'a' || e.key === 'A') {
            e.preventDefault();
            shuffleLayout();
        } else if (e.key === 'e' || e.key === 'E') {
            e.preventDefault();
            explodePage();
        } else if ((e.key === 'l' || e.key === 'L') && !e.ctrlKey && !e.metaKey && !e.altKey) {
            e.preventDefault();
            cycleLayoutMode(e.shiftKey ? -1 : 1);
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

// Cycle through LAYOUT_MODE_ORDER (1 = forward, -1 = backward). Ignored while
// a previous cycle is still in flight to avoid overlapping fetches.
async function cycleLayoutMode(direction) {
    if (isLayoutCycling) return;
    if (!PAGES_DATA || PAGES_DATA.length === 0) return;

    const currentIdx = LAYOUT_MODE_ORDER.indexOf(currentPageLayoutMode);
    const startIdx = currentIdx === -1 ? 0 : currentIdx;
    const len = LAYOUT_MODE_ORDER.length;
    const nextIdx = ((startIdx + direction) % len + len) % len;
    const nextMode = LAYOUT_MODE_ORDER[nextIdx];

    isLayoutCycling = true;
    try {
        const labelKey = LAYOUT_MODE_LABEL_KEYS[nextMode] || nextMode;
        showToast(t('toast.layout_mode') + t(labelKey), { type: 'info', duration: 1800 });
        await updateLayoutMode(nextMode);
    } finally {
        isLayoutCycling = false;
    }
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
    if (isShuffling) return;
    if (!PAGES_DATA || PAGES_DATA.length === 0) return;
    const pageId = PAGES_DATA[currentPageIndex].id;

    log('INFO', 'SHUFFLE_LAYOUT_START', { pageId });
    isShuffling = true;

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
    } finally {
        isShuffling = false;
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

    const navHint = document.getElementById('photo-viewer-nav-hint');
    if (navHint) navHint.textContent = t('photo_viewer.nav_hint');

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
    _vEntryOrigin = null;
}

// Open V from inside Show: syncs the current page first so deletions target
// the right page, then opens V on the first photo of that page.
async function openPhotoViewerFromShow() {
    const pageIdx = _showViewerIndex;
    if (!PAGES_DATA || pageIdx < 0 || pageIdx >= PAGES_DATA.length) return;

    // Close Show without triggering the panel-sync side effect we'd normally want;
    // we'll re-open it later via S, and currentPageIndex is about to be set anyway.
    const showModal = document.getElementById('page-show-modal');
    if (showModal) showModal.classList.add('hidden');
    if (_showViewerRenderTask) {
        try { _showViewerRenderTask.cancel(); } catch (_) { /* noop */ }
        _showViewerRenderTask = null;
    }
    _showViewerPdf = null;

    // Sync the album view so #photo-list contains this page's photos.
    await loadPage(pageIdx);

    // Pick the first photo from the now-rendered photo list.
    const firstItem = document.querySelector('#photo-list .photo-item');
    if (!firstItem) {
        console.warn('[PhotoViewer] Page has no photos to view.');
        return;
    }
    const firstName = firstItem.dataset.filename;
    _vEntryOrigin = 'show';
    openPhotoViewer(firstName);
}

// Open Show from inside V: closes V and re-opens Show on currentPageIndex
// with a fresh preview PDF (cache-busted by _renderShowPage).
function openPageViewerFromV() {
    const modal = document.getElementById('photo-viewer-modal');
    if (modal) modal.classList.add('hidden');
    const img = document.getElementById('photo-viewer-img');
    if (img) img.src = '';
    _vEntryOrigin = null;

    if (!PAGES_DATA || PAGES_DATA.length === 0) return;
    const idx = Math.max(0, Math.min(currentPageIndex, PAGES_DATA.length - 1));
    openPageViewer(idx);
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

// ── Page Show Viewer (tecla S) ────────────────────────────────────────────

/** Resolve the starting index into PAGES_DATA for the Show viewer.
 *  Returns null (and warns) when there are no content pages. */
function _resolveShowStartIndex() {
    if (!PAGES_DATA || PAGES_DATA.length === 0) {
        console.warn('[PageShow] No hay páginas de contenido disponibles.');
        return null;
    }
    if (currentCoverKind === 'cover') return 0;
    if (currentCoverKind === 'backcover') return PAGES_DATA.length - 1;
    return Math.max(0, Math.min(currentPageIndex, PAGES_DATA.length - 1));
}

async function openPageViewer(pageIndex) {
    if (!PAGES_DATA || PAGES_DATA.length === 0) return;
    const modal = document.getElementById('page-show-modal');
    if (!modal) return;

    _showViewerIndex = pageIndex;
    modal.classList.remove('hidden');

    const navHint = document.getElementById('page-show-nav-hint');
    if (navHint) navHint.textContent = t('page_show.nav_hint');

    await _renderShowPage(_showViewerIndex);
}

function closePageViewer() {
    const modal = document.getElementById('page-show-modal');
    if (modal) modal.classList.add('hidden');

    if (_showViewerRenderTask) {
        try { _showViewerRenderTask.cancel(); } catch (_) { /* noop */ }
        _showViewerRenderTask = null;
    }
    _showViewerPdf = null;

    const canvas = document.getElementById('page-show-canvas');
    if (canvas) {
        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);
    }

    // Sync main view to last viewed page so panel + canvas reflect Show's last page
    loadPage(_showViewerIndex);
}

function navigatePageViewer(delta) {
    if (!PAGES_DATA || PAGES_DATA.length === 0) return;
    const n = PAGES_DATA.length;
    const newIdx = ((_showViewerIndex + delta) % n + n) % n;
    _showViewerIndex = newIdx;
    _renderShowPage(newIdx);
}

function handlePageViewerOverlayClick(e) {
    if (e.target.id === 'page-show-modal') closePageViewer();
}

async function _renderShowPage(index) {
    if (!PAGES_DATA || index < 0 || index >= PAGES_DATA.length) return;
    const page = PAGES_DATA[index];

    const skeleton = document.getElementById('page-show-skeleton');
    if (skeleton) skeleton.classList.remove('hidden');

    const caption = document.getElementById('page-show-caption');
    if (caption) {
        const title = page.title || page.id || '';
        caption.textContent = `${t('page_show.page')} ${index + 1} / ${PAGES_DATA.length}${title ? '  —  ' + title : ''}`;
    }

    if (_showViewerRenderTask) {
        try { _showViewerRenderTask.cancel(); } catch (_) { /* noop */ }
        _showViewerRenderTask = null;
    }

    if (typeof pdfjsLib === 'undefined') {
        console.error('[PageShow] pdfjsLib not loaded.');
        return;
    }

    const url = `/api/page/${page.id}/preview?t=${Date.now()}`;
    try {
        const pdf = await pdfjsLib.getDocument({ url }).promise;
        _showViewerPdf = pdf;

        const pdfPage = await pdf.getPage(1);

        const canvas = document.getElementById('page-show-canvas');
        const wrapper = document.getElementById('page-show-canvas-wrapper');
        if (!canvas || !wrapper) return;

        // Bail if a newer render superseded us
        if (_showViewerPdf !== pdf) return;

        const rect = wrapper.getBoundingClientRect();
        const containerW = rect.width || wrapper.clientWidth;
        const containerH = rect.height || wrapper.clientHeight;

        const baseViewport = pdfPage.getViewport({ scale: 1 });
        const scale = Math.min(
            containerW / baseViewport.width,
            containerH / baseViewport.height
        );
        const viewport = pdfPage.getViewport({ scale });
        const dpr = window.devicePixelRatio || 1;

        canvas.width  = Math.round(viewport.width  * dpr);
        canvas.height = Math.round(viewport.height * dpr);
        canvas.style.width  = Math.round(viewport.width)  + 'px';
        canvas.style.height = Math.round(viewport.height) + 'px';

        const ctx = canvas.getContext('2d');
        ctx.scale(dpr, dpr);

        const renderTask = pdfPage.render({ canvasContext: ctx, viewport });
        _showViewerRenderTask = renderTask;
        await renderTask.promise;

        if (_showViewerRenderTask === renderTask) _showViewerRenderTask = null;
        if (skeleton) skeleton.classList.add('hidden');

    } catch (err) {
        if (err && (err.name === 'RenderingCancelledException' || err.message === 'Rendering cancelled')) {
            return;
        }
        console.error('[PageShow render]', err);
        if (skeleton) skeleton.classList.add('hidden');
    }
}

// Caption flash for Show: shows arbitrary text for `durationMs` then restores
// the default "Página N/M — título". One timer at a time; rapid cycles only
// keep the latest flash.
let _captionFlashTimer = null;

function _setShowCaptionDefault(index) {
    const caption = document.getElementById('page-show-caption');
    if (!caption || !PAGES_DATA || index < 0 || index >= PAGES_DATA.length) return;
    const page = PAGES_DATA[index];
    const title = page.title || page.id || '';
    caption.textContent = `${t('page_show.page')} ${index + 1} / ${PAGES_DATA.length}${title ? '  —  ' + title : ''}`;
}

function _flashShowCaption(text, durationMs = 1800) {
    const caption = document.getElementById('page-show-caption');
    if (!caption) return;
    caption.textContent = text;
    if (_captionFlashTimer) clearTimeout(_captionFlashTimer);
    _captionFlashTimer = setTimeout(() => {
        _captionFlashTimer = null;
        _setShowCaptionDefault(_showViewerIndex);
    }, durationMs);
}

// Cycle layout from within Show: syncs the visible page into currentPageIndex,
// runs cycleLayoutMode (which PUTs to the server and regenerates the preview
// PDF), then re-renders the Show canvas and flashes the new mode name in the
// caption. Stale cycles (user navigated away mid-flight) are ignored.
async function _cycleLayoutFromShow(direction) {
    if (isLayoutCycling) return;
    if (!PAGES_DATA || PAGES_DATA.length === 0) return;
    const idx = _showViewerIndex;
    if (idx < 0 || idx >= PAGES_DATA.length) return;

    if (currentPageIndex !== idx) {
        await loadPage(idx);
    }

    await cycleLayoutMode(direction);

    // Only refresh Show if the user hasn't navigated to a different page in the meantime.
    if (_showViewerIndex !== idx) return;

    await _renderShowPage(idx);

    const labelKey = LAYOUT_MODE_LABEL_KEYS[currentPageLayoutMode] || currentPageLayoutMode || '';
    const label = labelKey && labelKey !== currentPageLayoutMode ? t(labelKey) : currentPageLayoutMode;
    _flashShowCaption(`${t('toast.layout_mode')}${label}`);
}

// Shuffle layout from within Show: syncs the visible page into currentPageIndex,
// runs shuffleLayout (which POSTs and regenerates the preview PDF), then
// re-renders the Show canvas and flashes a confirmation in the caption. Stale
// shuffles (user navigated away mid-flight) are ignored.
async function _shuffleLayoutFromShow() {
    if (isShuffling) return;
    if (!PAGES_DATA || PAGES_DATA.length === 0) return;
    const idx = _showViewerIndex;
    if (idx < 0 || idx >= PAGES_DATA.length) return;

    if (currentPageIndex !== idx) {
        await loadPage(idx);
    }

    await shuffleLayout();

    if (_showViewerIndex !== idx) return;

    await _renderShowPage(idx);

    _flashShowCaption(t('toast.shuffled'));
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
    // Cover/backcover detail view
    if (currentCoverKind) {
        const target = currentCoverKind === 'cover' ? COVER_DATA : BACKCOVER_DATA;
        if (!target) return;
        const newCompleted = !target.completed;
        try {
            const response = await fetch(`/api/page/${encodeURIComponent(target.id)}/completed`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ completed: newCompleted }),
            });
            const data = await response.json();
            if (data.success) {
                target.completed = newCompleted;
                const itemEl = document.querySelector(
                    `#page-list .page-list-item.cover-${currentCoverKind}`
                );
                applyCompletedClass(itemEl, newCompleted);
                updateCompletedButton(document.getElementById('toggle-page-completed-btn'), newCompleted);
            }
        } catch (error) {
            log('ERROR', 'TOGGLE_COVER_COMPLETED_ERROR', { error: error.message });
        }
        return;
    }

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
            case 'move_page':
                await restoreMovedPage(state.data.newPageId, state.data.oldIndex);
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

    if (typeof COVER_DATA !== 'undefined' && COVER_DATA) {
        pageList.appendChild(buildCoverPanelItem(COVER_DATA, 'cover'));
    }

    if (typeof BACKCOVER_DATA !== 'undefined' && BACKCOVER_DATA) {
        pageList.appendChild(buildCoverPanelItem(BACKCOVER_DATA, 'backcover'));
    }

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

    // Page drag-and-drop disabled — plan 2026-05-13. Use "↕️ Mover a página" button instead.
    // To re-enable: uncomment the block below and remove the `if (false)` wrapper.
    if (pagePanelSortable) {
        pagePanelSortable.destroy();
        pagePanelSortable = null;
    }
    if (false && typeof Sortable !== 'undefined' && PAGES_DATA.length > 1) { // eslint-disable-line no-constant-condition
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
    // Collect new order from DOM (content pages only — covers don't reorder)
    const items = document.querySelectorAll('#page-list .page-list-item:not(.cover-list-item)');
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

// ─── Move Page to Position ───────────────────────────────────────────────────

async function openMovePageDialog() {
    const contentPages = PAGES_DATA; // all entries are content pages (covers are separate)
    const totalPages = contentPages.length;
    const currentUserNum = currentPageIndex + 1; // 1-based

    const raw = await showPrompt({
        title: '↕️ Mover a página',
        message: `Mover página actual (${currentUserNum}) a la posición:`,
        defaultValue: String(currentUserNum),
        placeholder: `1 – ${totalPages}`,
        okLabel: 'Mover',
        cancelLabel: 'Cancelar',
    });

    if (raw === null) return; // cancelled

    const targetNum = parseInt(raw, 10);
    if (isNaN(targetNum) || targetNum < 1 || targetNum > totalPages) {
        showToast(`Posición fuera de rango. Introduce un número entre 1 y ${totalPages}.`, { type: 'error' });
        return;
    }

    const targetIndex = targetNum - 1; // 0-based
    if (targetIndex === currentPageIndex) return; // no-op

    const activePageId = contentPages[currentPageIndex].id;
    const oldIndex = currentPageIndex;

    // Build new ordered list: remove active page and insert at target index
    const ids = contentPages.map(p => p.id);
    ids.splice(currentPageIndex, 1);
    ids.splice(targetIndex, 0, activePageId);

    try {
        const response = await fetch('/api/pages/reorder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ordered_page_ids: ids, moved_page_id: activePageId }),
        });
        const data = await response.json();

        if (data.success) {
            // Determine the new page id after potential renaming
            let newPageId = activePageId;
            if (data.renamed_pages && data.renamed_pages.length > 0) {
                const renamed = data.renamed_pages.find(r => r.old_id === activePageId);
                if (renamed) newPageId = renamed.new_id;
            }

            // Push undo state BEFORE reloading PAGES_DATA
            pushUndoState('move_page', { newPageId, oldIndex });

            // Reload PAGES_DATA and refocus the moved page
            const pagesResp = await fetch('/api/pages');
            const pagesData = await pagesResp.json();
            if (pagesData.success && pagesData.pages.length > 0) {
                PAGES_DATA.length = 0;
                pagesData.pages.forEach(p => PAGES_DATA.push(p));
                const newIdx = PAGES_DATA.findIndex(p => p.id === newPageId);
                await loadPage(Math.max(0, newIdx !== -1 ? newIdx : targetIndex));
            }
            if (data.section_changed) {
                const shortId = data.section_changed.new_section_id.slice(0, 8);
                showToast(`Página adoptada por sección ${shortId}…`, { type: 'info' });
            } else {
                showToast(`Página movida a la posición ${targetNum}.`, { type: 'success' });
            }
        } else {
            showToast('Error al mover página: ' + (data.error || ''), { type: 'error' });
        }
    } catch (err) {
        console.error('Failed to move page:', err);
        showToast('Error de conexión al mover la página.', { type: 'error' });
    }
}

async function restoreMovedPage(newPageId, oldIndex) {
    // Find the current position of this page (its id may have been renamed again)
    const currentIdx = PAGES_DATA.findIndex(p => p.id === newPageId);
    if (currentIdx === -1) {
        showToast('No se pudo deshacer: la página ya no existe con ese ID.', { type: 'error' });
        return;
    }
    if (currentIdx === oldIndex) return; // already in the right place

    const ids = PAGES_DATA.map(p => p.id);
    ids.splice(currentIdx, 1);
    ids.splice(oldIndex, 0, newPageId);

    try {
        const response = await fetch('/api/pages/reorder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ordered_page_ids: ids, moved_page_id: newPageId }),
        });
        const data = await response.json();

        if (data.success) {
            let restoredId = newPageId;
            if (data.renamed_pages && data.renamed_pages.length > 0) {
                const renamed = data.renamed_pages.find(r => r.old_id === newPageId);
                if (renamed) restoredId = renamed.new_id;
            }
            const pagesResp = await fetch('/api/pages');
            const pagesData = await pagesResp.json();
            if (pagesData.success && pagesData.pages.length > 0) {
                PAGES_DATA.length = 0;
                pagesData.pages.forEach(p => PAGES_DATA.push(p));
                const idx = PAGES_DATA.findIndex(p => p.id === restoredId);
                await loadPage(Math.max(0, idx !== -1 ? idx : oldIndex));
            }
            showToast('Movimiento deshecho.', { type: 'success' });
        } else {
            showToast('Error al deshacer movimiento: ' + (data.error || ''), { type: 'error' });
        }
    } catch (err) {
        console.error('Failed to restore moved page:', err);
        throw err;
    }
}

// Move logical focus to the page panel (left) — highlights + toggles flags
function focusPagePanel() {
    photoListFocused = false;
    pagePanelFocused = true;
    document.getElementById('album-sidebar')?.classList.remove('panel-has-focus');
    document.getElementById('page-panel')?.classList.add('panel-has-focus');

    const items = document.querySelectorAll('#page-panel .page-list-item:not(.cover-list-item)');
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
    const wasInCover = currentCoverKind !== null;
    if (wasInCover) exitCoverDetail();
    const delta = index - currentPageIndex;
    if (delta !== 0) {
        navigatePage(delta);
    } else if (wasInCover) {
        // Same index, but we were in cover mode → re-render the page view.
        loadPage(index);
    }
}

function updatePagePanelActiveItem(index) {
    // Clear active flag on every item (incl. covers), then set on the matching content page.
    document.querySelectorAll('#page-panel .page-list-item').forEach(item => {
        item.classList.remove('active');
    });
    const contentItems = document.querySelectorAll('#page-panel .page-list-item:not(.cover-list-item)');
    const target = contentItems[index];
    if (target) {
        target.classList.add('active');
        target.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
}

function updatePagePanelTitle(index, newTitle) {
    const titleEl = document.getElementById(`page-panel-title-${index}`);
    if (titleEl) titleEl.textContent = newTitle;
}

function navigatePagePanelSelection(delta) {
    // Keyboard ↑/↓ moves within the content pages only — covers aren't part of
    // this navigation, they're focused by clicking.
    const items = Array.from(
        document.querySelectorAll('#page-panel .page-list-item:not(.cover-list-item)')
    );
    if (items.length === 0) return;
    const newIndex = Math.max(0, Math.min(items.length - 1, currentPageIndex + delta));
    if (newIndex !== currentPageIndex) {
        navigateToPageFromPanel(newIndex);
    }
}

function navigatePagePanelToNextStateChange(delta) {
    const items = Array.from(
        document.querySelectorAll('#page-panel .page-list-item:not(.cover-list-item)')
    );
    if (items.length === 0) return;
    const fromIndex = Math.max(0, Math.min(items.length - 1, currentPageIndex));
    const currentCompleted = !!(PAGES_DATA[fromIndex] && PAGES_DATA[fromIndex].completed);
    let i = fromIndex + delta;
    while (i >= 0 && i < items.length) {
        const itemCompleted = !!(PAGES_DATA[i] && PAGES_DATA[i].completed);
        if (itemCompleted !== currentCompleted) {
            navigateToPageFromPanel(i);
            return;
        }
        i += delta;
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

// ═══════════════════════════════════════════════════════════════════════════
// Cover / Backcover editing
// ═══════════════════════════════════════════════════════════════════════════

let currentCoverKind = null;
const COVER_KIND_LABEL = { cover: 'Portada', backcover: 'Contraportada' };

function buildCoverPanelItem(coverData, kind) {
    const item = document.createElement('div');
    item.className = `page-list-item cover-list-item cover-${kind}`;
    item.dataset.coverKind = kind;
    item.dataset.pageId = coverData.id;

    const chip = document.createElement('span');
    chip.className = 'page-list-num cover-chip';
    chip.textContent = kind === 'cover' ? '★' : '◀';

    const titleWrap = document.createElement('span');
    titleWrap.className = 'page-list-title-wrap';
    const titleSpan = document.createElement('span');
    titleSpan.className = 'page-list-title';
    titleSpan.textContent = COVER_KIND_LABEL[kind];
    titleWrap.appendChild(titleSpan);

    const dot = document.createElement('span');
    dot.className = 'completed-dot';
    dot.title = 'Revisado';

    item.appendChild(chip);
    item.appendChild(titleWrap);
    item.appendChild(dot);

    if (coverData.completed) item.classList.add('is-completed');

    item.addEventListener('click', () => loadCoverDetail(kind));

    // Drop zone: dragging a workspace photo onto the cover item clones it as
    // the new cover photo.
    item.addEventListener('dragover', (e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = 'copy';
        item.classList.add('drag-over');
    });
    item.addEventListener('dragleave', () => item.classList.remove('drag-over'));
    item.addEventListener('drop', async (e) => {
        e.preventDefault();
        item.classList.remove('drag-over');
        const filenames = JSON.parse(e.dataTransfer.getData('text/plain') || '[]');
        if (!filenames.length) return;
        _crossPageDropHandled = true;
        const sourcePage = PAGES_DATA[currentPageIndex];
        if (!sourcePage) return;
        await setCoverPhoto(kind, sourcePage.id, filenames[0]);
    });

    return item;
}

async function loadCoverDetail(kind) {
    const data = kind === 'cover' ? COVER_DATA : BACKCOVER_DATA;
    if (!data) return;
    currentCoverKind = kind;

    // Hide the page canvas + skeleton; reveal the cover detail card.
    document.getElementById('pdf-preview')?.classList.add('hidden');
    document.getElementById('pdf-preview-skeleton')?.classList.add('hidden');
    const view = document.getElementById('cover-detail-view');
    if (view) view.classList.remove('hidden');

    // Update header indicator
    const numEl = document.getElementById('current-page-num');
    if (numEl) numEl.textContent = kind === 'cover' ? 'Portada' : 'Contraportada';

    // Hide page-only action buttons; keep the "Completado" toggle wired to this folder.
    togglePageOnlyActions(false);

    // Update the cover image
    const chip = document.getElementById('cover-detail-chip');
    if (chip) chip.textContent = COVER_KIND_LABEL[kind];
    const img = document.getElementById('cover-detail-image');
    if (img) {
        if (data.image) {
            img.src = `/api/page/${encodeURIComponent(data.id)}/image/${encodeURIComponent(data.image)}?t=${Date.now()}`;
            img.alt = COVER_KIND_LABEL[kind];
        } else {
            img.removeAttribute('src');
            img.alt = '(sin foto)';
        }
    }

    // Highlight item in the panel
    document.querySelectorAll('#page-list .page-list-item').forEach(el => {
        el.classList.toggle('active', el.dataset.coverKind === kind);
    });

    // Sync the Completado button with this cover's flag
    const completedBtn = document.getElementById('toggle-page-completed-btn');
    if (completedBtn) updateCompletedButton(completedBtn, !!data.completed);

    log('INFO', 'COVER_DETAIL_LOAD', { kind, image: data.image });
}

function exitCoverDetail() {
    currentCoverKind = null;
    document.getElementById('pdf-preview')?.classList.remove('hidden');
    document.getElementById('pdf-preview-skeleton')?.classList.remove('hidden');
    document.getElementById('cover-detail-view')?.classList.add('hidden');
    togglePageOnlyActions(true);
}

function togglePageOnlyActions(visible) {
    const ids = ['layout-mode-btn', 'shuffle-layout-btn', 'grid-equalize-btn', 'explode-page-btn', 'move-page-btn', 'delete-page-btn'];
    ids.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.style.display = visible ? '' : 'none';
    });
}

const coverPickerState = {
    kind: null,
    tiles: [],
    filteredTiles: [],
    filterText: '',
    debounceTimer: null,
};

function normalizeForSearch(s) {
    return (s || '').toString().toLowerCase().normalize('NFD').replace(/\p{Diacritic}/gu, '');
}

async function openCoverPicker(kind) {
    const modal = document.getElementById('cover-picker-modal');
    const body = document.getElementById('cover-picker-body');
    const title = document.getElementById('cover-picker-title');
    const filterInput = document.getElementById('cover-picker-filter-input');
    if (!modal || !body) return;

    coverPickerState.kind = kind;
    coverPickerState.tiles = [];
    coverPickerState.filteredTiles = [];
    coverPickerState.filterText = '';
    if (filterInput) filterInput.value = '';

    title.textContent = kind === 'cover' ? 'Elegir foto de portada' : 'Elegir foto de contraportada';
    body.innerHTML = '<p class="cover-picker-loading">Cargando fotos…</p>';
    modal.classList.remove('hidden');

    try {
        const tiles = [];
        for (const page of PAGES_DATA) {
            const r = await fetch(`/api/page/${encodeURIComponent(page.id)}`);
            const d = await r.json();
            if (!d.success) continue;
            (d.page.images || []).forEach(img => {
                tiles.push({ pageId: page.id, pageTitle: page.title, pageSubtitle: page.subtitle || '', image: img });
            });
        }
        coverPickerState.tiles = tiles;
        coverPickerState.filteredTiles = tiles.slice();
        renderCoverPickerTiles(body, kind, coverPickerState.filteredTiles);
    } catch (e) {
        body.innerHTML = '<p class="cover-picker-error">Error al cargar fotos.</p>';
    }
}

function applyCoverPickerFilter() {
    const body = document.getElementById('cover-picker-body');
    if (!body) return;
    const query = normalizeForSearch(coverPickerState.filterText);
    if (!query) {
        coverPickerState.filteredTiles = coverPickerState.tiles.slice();
    } else {
        coverPickerState.filteredTiles = coverPickerState.tiles.filter(tile => {
            const target = normalizeForSearch(`${tile.pageTitle} ${tile.pageSubtitle}`);
            return target.indexOf(query) !== -1;
        });
    }
    renderCoverPickerTiles(body, coverPickerState.kind, coverPickerState.filteredTiles);
}

function renderCoverPickerTiles(container, kind, tiles) {
    container.innerHTML = '';
    if (!tiles.length) {
        const msg = coverPickerState.filterText
            ? 'Ninguna foto coincide con el filtro'
            : 'No hay fotos disponibles.';
        container.innerHTML = `<p class="cover-picker-empty">${msg}</p>`;
        return;
    }
    const grid = document.createElement('div');
    grid.className = 'cover-picker-grid';
    tiles.forEach(({ pageId, pageTitle, image }) => {
        const tile = document.createElement('button');
        tile.className = 'cover-picker-tile';
        tile.type = 'button';
        const im = document.createElement('img');
        im.loading = 'lazy';
        im.src = `/api/page/${encodeURIComponent(pageId)}/image/${encodeURIComponent(image)}`;
        im.alt = image;
        const cap = document.createElement('span');
        cap.className = 'cover-picker-tile-caption';
        cap.textContent = pageTitle || pageId;
        tile.appendChild(im);
        tile.appendChild(cap);
        tile.addEventListener('click', () => setCoverPhoto(kind, pageId, image));
        grid.appendChild(tile);
    });
    container.appendChild(grid);
}

function closeCoverPicker() {
    clearTimeout(coverPickerState.debounceTimer);
    const filterInput = document.getElementById('cover-picker-filter-input');
    if (filterInput) filterInput.value = '';
    document.getElementById('cover-picker-modal')?.classList.add('hidden');
}

function handleCoverPickerOverlayClick(event) {
    if (event.target?.id === 'cover-picker-modal') closeCoverPicker();
}

async function setCoverPhoto(kind, sourcePage, sourceImage) {
    try {
        const r = await fetch(`/api/cover/${kind}/photo`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ source_page: sourcePage, source_image: sourceImage }),
        });
        const d = await r.json();
        if (!d.success) {
            showToast('No se pudo cambiar la foto: ' + (d.error || ''), { type: 'error' });
            return;
        }
        // Update in-memory cover data and detail view.
        const target = kind === 'cover' ? COVER_DATA : BACKCOVER_DATA;
        if (target) target.image = d.image;
        if (currentCoverKind === kind) {
            await loadCoverDetail(kind);
        }
        closeCoverPicker();
        showToast('Foto de ' + (kind === 'cover' ? 'portada' : 'contraportada') + ' actualizada', { type: 'success' });
    } catch (e) {
        showToast('Error de conexión', { type: 'error' });
    }
}

// Bind the "Elegir foto" button and the filter input once on init.
document.addEventListener('DOMContentLoaded', () => {
    const pickBtn = document.getElementById('cover-pick-btn');
    if (pickBtn) {
        pickBtn.addEventListener('click', () => {
            if (currentCoverKind) openCoverPicker(currentCoverKind);
        });
    }

    const filterInput = document.getElementById('cover-picker-filter-input');
    if (filterInput) {
        filterInput.addEventListener('input', e => {
            clearTimeout(coverPickerState.debounceTimer);
            coverPickerState.debounceTimer = setTimeout(() => {
                coverPickerState.filterText = e.target.value;
                applyCoverPickerFilter();
            }, 200);
        });
    }
});

// Initialize when tab becomes active
document.addEventListener('DOMContentLoaded', () => {
    // Only initialize album mode if we're on the album tab
    if (currentTab === 'album') {
        initAlbumMode();
    }
});
