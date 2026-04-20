// ═══════════════════════════════════════════════════════════════════════════
// App Controller - Tab Switching and Initialization
// ═══════════════════════════════════════════════════════════════════════════

document.addEventListener('DOMContentLoaded', () => {
    log('INFO', 'APP_CONTROLLER_INIT', {});
    
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
    
    // Initialize based on current tab
    switchTabAndInit(savedTab);
});

// Switch tab and initialize the corresponding mode
function switchTabAndInit(tabName) {
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
        if (!confirm(t('confirm.discard_changes'))) {
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
            alert(data.error || t('launcher.dialog_cancelled'));
            btn.disabled = false;
            btn.textContent = t('header.open_folder');
        }
    } catch (error) {
        alert(`${t('launcher.connection_error')}${error.message}`);
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
            alert(data.error || t('launcher.init_error'));
            btn.disabled = false;
            btn.textContent = t('header.open_folder');
        }
    } catch (error) {
        alert(`${t('launcher.connection_error')}${error.message}`);
        btn.disabled = false;
        btn.textContent = t('header.open_folder');
    }
}
