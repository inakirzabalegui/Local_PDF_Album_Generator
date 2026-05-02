// ═══════════════════════════════════════════════════════════════════════════
// Dialog System - Custom Modals and Toasts (replaces native browser dialogs)
// ═══════════════════════════════════════════════════════════════════════════

let activeDialog = null;
let previouslyFocusedElement = null;

/**
 * Show a modal text input dialog. Replaces prompt().
 * @param {Object} options - { title, message?, defaultValue?, placeholder?, okLabel?, cancelLabel? }
 * @returns {Promise<string|null>} User input or null if cancelled
 */
async function showPrompt(options) {
  if (activeDialog) {
    console.warn('A dialog is already open. Ignoring new prompt request.');
    return null;
  }

  const {
    title = '',
    message = '',
    defaultValue = '',
    placeholder = '',
    okLabel = 'Aceptar',
    cancelLabel = 'Cancelar'
  } = options;

  const dialog = document.getElementById('generic-dialog');
  const titleEl = document.getElementById('generic-dialog-title');
  const messageEl = document.getElementById('generic-dialog-message');
  const input = document.getElementById('generic-dialog-input');
  const okBtn = document.getElementById('generic-dialog-ok');
  const cancelBtn = document.getElementById('generic-dialog-cancel');

  // Setup
  previouslyFocusedElement = document.activeElement;
  titleEl.textContent = title;
  messageEl.textContent = message;
  messageEl.style.display = message ? 'block' : 'none';
  input.value = defaultValue;
  input.placeholder = placeholder;
  input.style.display = 'block';
  okBtn.textContent = okLabel;
  cancelBtn.textContent = cancelLabel;
  okBtn.className = 'btn btn-primary';

  dialog.classList.remove('hidden');
  dialog.setAttribute('role', 'dialog');
  dialog.setAttribute('aria-modal', 'true');
  dialog.setAttribute('aria-labelledby', 'generic-dialog-title');

  activeDialog = 'prompt';
  input.focus();
  input.select();

  return new Promise((resolve) => {
    function cleanup() {
      dialog.classList.add('hidden');
      activeDialog = null;
      input.removeEventListener('keydown', handleInputKeydown);
      okBtn.removeEventListener('click', handleOk);
      cancelBtn.removeEventListener('click', handleCancel);
      dialog.removeEventListener('click', handleBackdropClick);
      if (previouslyFocusedElement) previouslyFocusedElement.focus();
    }

    function handleOk() {
      cleanup();
      resolve(input.value);
    }

    function handleCancel() {
      cleanup();
      resolve(null);
    }

    function handleInputKeydown(e) {
      if (e.key === 'Enter') {
        handleOk();
      } else if (e.key === 'Escape') {
        handleCancel();
      }
    }

    function handleBackdropClick(e) {
      if (e.target === dialog) {
        handleCancel();
      }
    }

    input.addEventListener('keydown', handleInputKeydown);
    okBtn.addEventListener('click', handleOk);
    cancelBtn.addEventListener('click', handleCancel);
    dialog.addEventListener('click', handleBackdropClick);
  });
}

/**
 * Show a modal confirmation dialog. Replaces confirm().
 * @param {Object} options - { title, message, okLabel?, cancelLabel?, danger? }
 * @returns {Promise<boolean>} true if OK, false if cancelled
 */
async function showConfirm(options) {
  if (activeDialog) {
    console.warn('A dialog is already open. Ignoring new confirm request.');
    return false;
  }

  const {
    title = '',
    message = '',
    okLabel = 'Aceptar',
    cancelLabel = 'Cancelar',
    danger = false
  } = options;

  const dialog = document.getElementById('generic-dialog');
  const titleEl = document.getElementById('generic-dialog-title');
  const messageEl = document.getElementById('generic-dialog-message');
  const input = document.getElementById('generic-dialog-input');
  const okBtn = document.getElementById('generic-dialog-ok');
  const cancelBtn = document.getElementById('generic-dialog-cancel');

  // Setup
  previouslyFocusedElement = document.activeElement;
  titleEl.textContent = title;
  messageEl.textContent = message;
  messageEl.style.display = message ? 'block' : 'none';
  input.style.display = 'none';
  okBtn.textContent = okLabel;
  cancelBtn.textContent = cancelLabel;
  okBtn.className = danger ? 'btn btn-danger' : 'btn btn-primary';

  dialog.classList.remove('hidden');
  dialog.setAttribute('role', 'dialog');
  dialog.setAttribute('aria-modal', 'true');
  dialog.setAttribute('aria-labelledby', 'generic-dialog-title');

  activeDialog = 'confirm';
  okBtn.focus();

  return new Promise((resolve) => {
    function cleanup() {
      dialog.classList.add('hidden');
      activeDialog = null;
      document.removeEventListener('keydown', handleKeydown);
      okBtn.removeEventListener('click', handleOk);
      cancelBtn.removeEventListener('click', handleCancel);
      dialog.removeEventListener('click', handleBackdropClick);
      if (previouslyFocusedElement) previouslyFocusedElement.focus();
    }

    function handleOk() {
      cleanup();
      resolve(true);
    }

    function handleCancel() {
      cleanup();
      resolve(false);
    }

    function handleKeydown(e) {
      if (e.key === 'Enter' && document.activeElement === okBtn) {
        handleOk();
      } else if (e.key === 'Escape') {
        handleCancel();
      }
    }

    function handleBackdropClick(e) {
      if (e.target === dialog) {
        handleCancel();
      }
    }

    document.addEventListener('keydown', handleKeydown);
    okBtn.addEventListener('click', handleOk);
    cancelBtn.addEventListener('click', handleCancel);
    dialog.addEventListener('click', handleBackdropClick);
  });
}

/**
 * Play delete feedback: flash red overlay on the viewer + collapse the list item.
 * Resolves after both animations complete (~220ms).
 * @param {Object} opts
 * @param {Element|null} opts.viewerEl  - The viewer container (image or pdf preview wrapper)
 * @param {Element|null} opts.itemEl   - The .photo-item being removed
 */
function playDeleteFeedback({ viewerEl = null, itemEl = null } = {}) {
    return new Promise((resolve) => {
        if (viewerEl) {
            const overlay = document.createElement('div');
            overlay.className = 'delete-flash-overlay';
            const parent = viewerEl.parentElement || viewerEl;
            const posRef = window.getComputedStyle(parent).position;
            if (posRef === 'static') parent.style.position = 'relative';
            parent.appendChild(overlay);
            overlay.addEventListener('animationend', () => overlay.remove(), { once: true });
        }

        if (itemEl) {
            itemEl.classList.add('removing');
        }

        setTimeout(resolve, 220);
    });
}

/**
 * Show a non-blocking toast notification. Replaces alert().
 * @param {string} message - Toast message
 * @param {Object} options - { type: 'success'|'error'|'info'|'warning', duration?: ms }
 */
function showToast(message, options = {}) {
  const {
    type = 'info',
    duration = null
  } = options;

  const defaultDurations = {
    'success': 3500,
    'error': 5500,
    'warning': 4000,
    'info': 4000
  };

  const finalDuration = duration || defaultDurations[type] || 4000;

  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  toast.setAttribute('role', 'alert');
  toast.setAttribute('aria-live', 'polite');

  container.appendChild(toast);

  // Trigger animation (CSS transition from invisible to visible)
  requestAnimationFrame(() => {
    toast.classList.add('visible');
  });

  function removeToast() {
    toast.classList.remove('visible');
    setTimeout(() => {
      toast.remove();
    }, 200); // Match CSS transition duration
  }

  const timeoutId = setTimeout(removeToast, finalDuration);

  // Click to dismiss
  toast.addEventListener('click', () => {
    clearTimeout(timeoutId);
    removeToast();
  });
}
