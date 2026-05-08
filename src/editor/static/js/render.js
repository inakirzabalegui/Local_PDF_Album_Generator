// Render album PDF from the web UI with SSE progress.

(function () {
    let _renderInProgress = false;

    function init() {
        const btn = document.getElementById('render-album-header-btn');
        if (btn) btn.addEventListener('click', renderAlbum);
    }

    async function renderAlbum() {
        if (_renderInProgress) {
            showToast('Render ya en curso.', { type: 'warning' });
            return;
        }
        _renderInProgress = true;

        const btn = document.getElementById('render-album-header-btn');
        if (btn) btn.disabled = true;

        showRenderModal();
        setStep('Iniciando render…');

        try {
            const response = await fetch('/api/render/album/stream', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({}),
            });
            if (!response.ok) {
                const err = await response.json().catch(() => ({}));
                throw new Error(err.error || `HTTP ${response.status}`);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';
            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });
                const parts = buffer.split('\n');
                buffer = parts.pop();
                for (const line of parts) {
                    if (!line.startsWith('data: ')) continue;
                    let event;
                    try { event = JSON.parse(line.slice(6)); } catch { continue; }
                    handleEvent(event);
                    if (event.step === 'done' || event.step === 'error') {
                        return;
                    }
                }
            }
        } catch (e) {
            setStep('Error: ' + e.message);
            showToast('Error en render: ' + e.message, { type: 'error' });
            setTimeout(hideRenderModal, 3000);
        } finally {
            _renderInProgress = false;
            if (btn) btn.disabled = false;
        }
    }

    function handleEvent(event) {
        if (event.step === 'reading') setStep('Leyendo workspace…');
        else if (event.step === 'reconciling') setStep('Reconciliando páginas…');
        else if (event.step === 'rebalancing') setStep('Rebalanceando páginas…');
        else if (event.step === 'rendering') setStep(`Renderizando PDF (${event.total} pág)…`);
        else if (event.step === 'done') {
            setStep('✓ Render completado');
            renderOutputs(event.outputs || []);
        } else if (event.step === 'error') {
            setStep('Error: ' + (event.message || 'desconocido'));
            showToast('Error en render: ' + (event.message || ''), { type: 'error' });
            setTimeout(hideRenderModal, 4000);
        }
    }

    function renderOutputs(outputs) {
        const list = document.getElementById('render-modal-outputs');
        if (!list) return;
        while (list.firstChild) list.removeChild(list.firstChild);
        if (!outputs.length) {
            const p = document.createElement('p');
            p.style.opacity = '0.7';
            p.textContent = 'No se generó ningún PDF.';
            list.appendChild(p);
            return;
        }
        for (const o of outputs) {
            const url = '/api/render/output?name=' + encodeURIComponent(o.name);
            const a = document.createElement('a');
            a.href = url;
            a.target = '_blank';
            a.rel = 'noopener';
            a.className = 'render-output-link';
            a.textContent = (o.is_cover ? '📕 ' : '📄 ') + o.name;
            list.appendChild(a);
        }
        const closeBtn = document.getElementById('render-modal-close-btn');
        if (closeBtn) closeBtn.disabled = false;
    }

    function setStep(text) {
        const el = document.getElementById('render-modal-step');
        if (el) el.textContent = text;
    }

    function showRenderModal() {
        let modal = document.getElementById('render-modal');
        if (!modal) {
            modal = buildModal();
            document.body.appendChild(modal);
        }
        const closeBtn = modal.querySelector('#render-modal-close-btn');
        if (closeBtn) closeBtn.disabled = true;
        const list = modal.querySelector('#render-modal-outputs');
        if (list) {
            while (list.firstChild) list.removeChild(list.firstChild);
        }
        modal.classList.remove('hidden');
        modal.style.display = 'flex';
    }

    function buildModal() {
        const modal = document.createElement('div');
        modal.id = 'render-modal';
        modal.className = 'modal';
        modal.setAttribute('role', 'dialog');

        const content = document.createElement('div');
        content.className = 'modal-content';
        content.style.maxWidth = '520px';

        const header = document.createElement('header');
        header.style.cssText = 'display:flex;justify-content:space-between;align-items:center;padding:16px 20px;border-bottom:1px solid var(--color-border, #ddd);';

        const title = document.createElement('h2');
        title.style.cssText = 'margin:0;font-size:1.1rem;';
        title.textContent = '🖨️ Generando PDF';
        header.appendChild(title);

        const closeBtn = document.createElement('button');
        closeBtn.id = 'render-modal-close-btn';
        closeBtn.className = 'btn btn-secondary';
        closeBtn.disabled = true;
        closeBtn.setAttribute('aria-label', 'Cerrar');
        closeBtn.textContent = '✕';
        closeBtn.addEventListener('click', hideRenderModal);
        header.appendChild(closeBtn);

        const body = document.createElement('div');
        body.style.padding = '20px';

        const stepEl = document.createElement('p');
        stepEl.id = 'render-modal-step';
        stepEl.style.margin = '0 0 14px 0';
        stepEl.textContent = 'Iniciando…';
        body.appendChild(stepEl);

        const list = document.createElement('div');
        list.id = 'render-modal-outputs';
        list.style.cssText = 'display:flex;flex-direction:column;gap:8px;';
        body.appendChild(list);

        content.appendChild(header);
        content.appendChild(body);
        modal.appendChild(content);
        return modal;
    }

    function hideRenderModal() {
        const modal = document.getElementById('render-modal');
        if (!modal) return;
        modal.classList.add('hidden');
        modal.style.display = 'none';
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
