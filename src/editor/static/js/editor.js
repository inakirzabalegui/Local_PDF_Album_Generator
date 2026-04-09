// Editor State
let currentPageIndex = 0;
let pendingChanges = 0;
let selectedPhotoName = null;
let sortableInstance = null;

// Initialize editor on page load
document.addEventListener('DOMContentLoaded', () => {
    console.log('Editor initialized with', PAGES_DATA.length, 'pages');
    
    // Load first page
    if (PAGES_DATA.length > 0) {
        loadPage(0);
    }
    
    // Setup event listeners
    setupEventListeners();
});

// Setup Event Listeners
function setupEventListeners() {
    // Navigation
    document.getElementById('prev-btn').addEventListener('click', () => navigatePage(-1));
    document.getElementById('next-btn').addEventListener('click', () => navigatePage(1));
    
    // Actions
    document.getElementById('save-btn').addEventListener('click', saveChanges);
    document.getElementById('exit-btn').addEventListener('click', exitEditor);
    document.getElementById('regenerate-btn').addEventListener('click', regeneratePreview);
    document.getElementById('delete-photo-btn').addEventListener('click', deleteSelectedPhoto);
    document.getElementById('delete-page-btn').addEventListener('click', deletePage);
    document.getElementById('update-title-btn').addEventListener('click', updatePageTitle);
    
    // Keyboard shortcuts
    document.addEventListener('keydown', handleKeyboard);
}

// Handle keyboard shortcuts
function handleKeyboard(e) {
    // Arrow keys for navigation (only if not in input field)
    if (e.target.tagName !== 'INPUT' && e.target.tagName !== 'TEXTAREA') {
        if (e.key === 'ArrowLeft') {
            navigatePage(-1);
        } else if (e.key === 'ArrowRight') {
            navigatePage(1);
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
        return;
    }
    
    currentPageIndex = index;
    const page = PAGES_DATA[index];
    
    console.log('Loading page', page.number, ':', page.id);
    
    // Update UI
    document.getElementById('current-page-num').textContent = page.number;
    updateNavigationButtons();
    
    // Fetch page details from API
    try {
        const response = await fetch(`/api/page/${page.id}`);
        const data = await response.json();
        
        if (data.success) {
            renderPageDetails(data.page);
            loadPreview(page.id);
        } else {
            console.error('Failed to load page:', data.error);
            alert('Error al cargar la página: ' + data.error);
        }
    } catch (error) {
        console.error('Failed to fetch page:', error);
        alert('Error de conexión al cargar la página');
    }
}

// Render page details in sidebar
function renderPageDetails(page) {
    // Update title input
    const titleInput = document.getElementById('page-title');
    titleInput.value = page.section_titles.join(' / ') || '';
    
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
}

// Handle photo reorder via drag-and-drop
async function handlePhotoReorder(evt) {
    const newOrder = getPhotoOrder();
    const pageId = PAGES_DATA[currentPageIndex].id;
    
    console.log('Reordering photos:', newOrder);
    
    try {
        const response = await fetch(`/api/page/${pageId}/reorder`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({order: newOrder})
        });
        
        const data = await response.json();
        
        if (data.success) {
            incrementPendingChanges();
            await regeneratePreview();
        } else {
            alert('Error al reordenar fotos: ' + data.error);
            // Reload page to reset order
            await loadPage(currentPageIndex);
        }
    } catch (error) {
        console.error('Failed to reorder photos:', error);
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
        return;
    }
    
    const pageId = PAGES_DATA[currentPageIndex].id;
    const confirmed = confirm(`¿Borrar la foto "${selectedPhotoName}"?`);
    
    if (!confirmed) {
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
            selectedPhotoName = null;
            document.getElementById('delete-photo-btn').disabled = true;
            incrementPendingChanges();
            await loadPage(currentPageIndex);  // Reload to update list
            await regeneratePreview();
        } else {
            alert('Error al borrar foto: ' + data.error);
        }
    } catch (error) {
        console.error('Failed to delete photo:', error);
        alert('Error de conexión al borrar foto');
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
    
    if (!newTitle) {
        alert('El título no puede estar vacío');
        return;
    }
    
    const pageId = PAGES_DATA[currentPageIndex].id;
    
    // Parse title (allow "/" for multiple titles)
    const titles = newTitle.split('/').map(t => t.trim()).filter(t => t);
    
    try {
        const response = await fetch(`/api/page/${pageId}/title`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({titles: titles})
        });
        
        const data = await response.json();
        
        if (data.success) {
            incrementPendingChanges();
            await regeneratePreview();
        } else {
            alert('Error al actualizar título: ' + data.error);
        }
    } catch (error) {
        console.error('Failed to update title:', error);
        alert('Error de conexión al actualizar título');
    }
}

// Regenerate preview
async function regeneratePreview() {
    const pageId = PAGES_DATA[currentPageIndex].id;
    
    showLoading();
    
    try {
        const response = await fetch(`/api/page/${pageId}/regenerate`, {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Reload preview with cache-busting timestamp
            loadPreview(pageId);
        } else {
            alert('Error al regenerar vista previa: ' + data.error);
        }
    } catch (error) {
        console.error('Failed to regenerate preview:', error);
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
function navigatePage(delta) {
    const newIndex = currentPageIndex + delta;
    if (newIndex >= 0 && newIndex < PAGES_DATA.length) {
        loadPage(newIndex);
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
    document.getElementById('changes-count').textContent = pendingChanges;
}

// Save changes (placeholder - changes are auto-saved)
async function saveChanges() {
    try {
        const response = await fetch('/api/save', {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.success) {
            alert('Cambios guardados correctamente');
            pendingChanges = 0;
            document.getElementById('changes-count').textContent = '0';
        } else {
            alert('Error al guardar: ' + data.error);
        }
    } catch (error) {
        console.error('Failed to save:', error);
        alert('Error de conexión al guardar');
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
