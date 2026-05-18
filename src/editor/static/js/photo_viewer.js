/**
 * photo_viewer.js — Unified fullscreen photo modal.
 *
 * Exposes window.PhotoViewer with open / close / isOpen / currentItem / currentIndex.
 * Handles its own keyboard events (Esc, ←→, V, D, plus extraKeys) and backdrop click.
 *
 * Must load BEFORE album.js and source.js.
 */
(function () {
    'use strict';

    // Module-private state
    let _state = null; // null when closed; { config, items, idx } when open

    // Single keydown listener registered lazily on first open
    let _listenerRegistered = false;

    // ── DOM helpers ────────────────────────────────────────────────────────────

    function _modal()   { return document.getElementById('photo-viewer-modal'); }
    function _img()     { return document.getElementById('photo-viewer-img'); }
    function _caption() { return document.getElementById('photo-viewer-caption'); }
    function _navHint() { return document.getElementById('photo-viewer-nav-hint'); }

    // ── Core operations ────────────────────────────────────────────────────────

    function _show(items, idx, config) {
        const modal = _modal();
        const img   = _img();
        if (!modal || !img) return;

        const item = items[idx];

        img.src = config.imageUrlFor(item);

        const cap = _caption();
        if (cap) cap.textContent = config.captionFor ? config.captionFor(item) : String(item);

        const nh = _navHint();
        if (nh) {
            nh.textContent = (typeof t === 'function') ? t('photo_viewer.nav_hint') : '';
        }

        modal.classList.remove('hidden');
    }

    function _navigate(delta) {
        if (!_state) return;
        const { items, idx, config } = _state;
        const n = items.length;
        if (n === 0) return;
        const wrap = config.wrap !== false; // default true
        let newIdx;
        if (wrap) {
            newIdx = ((idx + delta) % n + n) % n;
        } else {
            newIdx = Math.max(0, Math.min(idx + delta, n - 1));
        }
        if (newIdx === idx) return;
        _state.idx = newIdx;
        _show(items, newIdx, config);
        if (config.onIndexChange) config.onIndexChange(items[newIdx], newIdx);
    }

    // ── Keyboard handler ───────────────────────────────────────────────────────

    function _handleKey(e) {
        if (!_state) return; // viewer not open — pass through

        const key = e.key;

        if (key === 'Escape') {
            e.preventDefault();
            PhotoViewer.close();
            return;
        }

        if (key === 'ArrowLeft' || key === 'ArrowUp') {
            e.preventDefault();
            _navigate(-1);
            return;
        }

        if (key === 'ArrowRight' || key === 'ArrowDown') {
            e.preventDefault();
            _navigate(1);
            return;
        }

        // V always closes (callers may override via extraKeys, but V-close is built-in)
        if (key === 'v' || key === 'V') {
            e.preventDefault();
            PhotoViewer.close();
            return;
        }

        // D — delete
        if (key === 'd' || key === 'D') {
            e.preventDefault();
            const { config, items, idx } = _state;
            if (config.onDeletePhoto) {
                Promise.resolve(config.onDeletePhoto(items[idx], idx)).then((result) => {
                    if (!_state) return; // closed during async
                    if (!result || result.remaining <= 0) {
                        PhotoViewer.close();
                    } else {
                        // result.newItems: refreshed array from caller's DOM (recommended).
                        // result.nextIndex: index into newItems (or old items if newItems absent).
                        const newItems = result.newItems || null;
                        const nextIdx = result.nextIndex;
                        if (newItems && newItems.length > 0) {
                            _state.items = newItems;
                            _state.idx = Math.min(nextIdx, newItems.length - 1);
                        } else {
                            // Fall back: nextIndex into the OLD items array.
                            // Works when the deleted item was in the middle: the item at nextIdx
                            // in the old array is the next surviving file.
                            _state.idx = Math.min(nextIdx, _state.items.length - 1);
                        }
                        _show(_state.items, _state.idx, config);
                        if (config.onIndexChange) {
                            config.onIndexChange(_state.items[_state.idx], _state.idx);
                        }
                    }
                });
            }
            return;
        }

        // extraKeys — case-insensitive
        const { config } = _state;
        if (config.extraKeys) {
            const lk = key.toLowerCase();
            const upperK = key.toUpperCase();
            const handler = config.extraKeys[lk] || config.extraKeys[upperK];
            if (handler) {
                e.preventDefault();
                handler(PhotoViewer.close.bind(PhotoViewer));
                return;
            }
        }

        // Swallow all other keys while viewer is open so they don't leak to album/source handlers
        // (those still check isOpen() and return early, but belt-and-suspenders)
        e.stopImmediatePropagation();
    }

    // ── Backdrop click ─────────────────────────────────────────────────────────

    function _onBackdropClick(e) {
        if (e.target.id === 'photo-viewer-modal') PhotoViewer.close();
    }

    // ── Public API ─────────────────────────────────────────────────────────────

    const PhotoViewer = {
        /**
         * Open the fullscreen photo modal.
         * @param {Object} config
         *   items: Array<any>
         *   initialIndex: number (default 0)
         *   imageUrlFor: (item) => string
         *   captionFor: (item) => string  (optional)
         *   wrap: bool (default true)
         *   onIndexChange: (item, idx) => void  (optional)
         *   onDeletePhoto: (item, idx) => Promise<{remaining: number, nextIndex: number}>  (optional)
         *   extraKeys: { [keyChar]: (close) => void }  (optional)
         *   onClose: () => void  (optional)
         */
        open(config) {
            if (!config || !config.items || config.items.length === 0) return;

            // Lazy-register one global listener
            if (!_listenerRegistered) {
                document.addEventListener('keydown', _handleKey, true); // capture phase — highest priority
                const modal = _modal();
                if (modal) modal.addEventListener('click', _onBackdropClick);
                _listenerRegistered = true;
            }

            const items = config.items;
            const idx = Math.max(0, Math.min(config.initialIndex || 0, items.length - 1));

            _state = { config, items, idx };
            _show(items, idx, config);

            if (config.onIndexChange) config.onIndexChange(items[idx], idx);
        },

        close() {
            if (!_state) return;
            const { config } = _state;
            _state = null;

            const modal = _modal();
            if (modal) modal.classList.add('hidden');
            const img = _img();
            if (img) img.src = '';

            if (config && config.onClose) config.onClose();
        },

        isOpen() {
            return _state !== null;
        },

        currentItem() {
            return _state ? _state.items[_state.idx] : null;
        },

        currentIndex() {
            return _state ? _state.idx : -1;
        },
    };

    window.PhotoViewer = PhotoViewer;
})();
