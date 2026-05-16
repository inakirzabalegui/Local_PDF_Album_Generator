// Crear PDF flow: opens the unified create-pdf-modal in config mode; on submit
// persists provider+overrides to /api/config/global and then streams render
// progress via SSE inside the same modal.

(function () {
    let _renderInProgress = false;

    function init() {
        const btn = document.getElementById('render-album-header-btn');
        if (btn) btn.addEventListener('click', () => {
            if (_renderInProgress) {
                showToast('Render ya en curso.', { type: 'warning' });
                return;
            }
            if (typeof openCreatePdfDialog === 'function') openCreatePdfDialog();
        });
    }

    // Called by the modal's "Crear" button (onclick="submitCreatePdf()").
    window.submitCreatePdf = async function submitCreatePdf() {
        if (_renderInProgress) return;

        if (typeof getCurrentPrintingPayload !== 'function') {
            showToast('Configuración de impresión no inicializada.', { type: 'error' });
            return;
        }
        const payload = getCurrentPrintingPayload();

        const submitBtn = document.getElementById('create-pdf-submit-btn');
        const status = document.getElementById('printing-status');
        if (submitBtn) submitBtn.disabled = true;
        if (status) status.textContent = 'Guardando…';

        // 1) Persist provider + overrides to disk. Backend reads from disk for the render.
        try {
            const r = await fetch('/api/config/global', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await r.json();
            if (!r.ok) throw new Error(data.error || 'save failed');
        } catch (err) {
            if (status) status.textContent = `Error: ${err.message}`;
            if (submitBtn) submitBtn.disabled = false;
            showToast(`Error al guardar configuración: ${err.message}`, { type: 'error' });
            return;
        }
        if (status) status.textContent = '';

        // 2) Switch modal to progress mode and start SSE render.
        switchToProgressMode();
        _renderInProgress = true;
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
            enableCloseButton();
        } finally {
            _renderInProgress = false;
        }
    };

    function handleEvent(event) {
        if (event.step === 'reading') setStep('Leyendo workspace…');
        else if (event.step === 'reconciling') setStep('Reconciliando páginas…');
        else if (event.step === 'rebalancing') setStep('Rebalanceando páginas…');
        else if (event.step === 'rendering') setStep(`Renderizando PDF (${event.total} pág)…`);
        else if (event.step === 'done') {
            setStep('✓ PDF creado');
            renderOutputs(event.outputs || []);
            enableCloseButton();
        } else if (event.step === 'error') {
            setStep('Error: ' + (event.message || 'desconocido'));
            showToast('Error en render: ' + (event.message || ''), { type: 'error' });
            enableCloseButton();
        }
    }

    function renderOutputs(outputs) {
        const list = document.getElementById('create-pdf-progress-outputs');
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
    }

    function setStep(text) {
        const el = document.getElementById('create-pdf-progress-step');
        if (el) el.textContent = text;
    }

    function switchToProgressMode() {
        document.getElementById('create-pdf-config-body').style.display = 'none';
        document.getElementById('create-pdf-config-footer').style.display = 'none';
        document.getElementById('create-pdf-progress-body').style.display = '';
        document.getElementById('create-pdf-progress-footer').style.display = '';
    }

    function enableCloseButton() {
        const btn = document.getElementById('create-pdf-close-btn');
        if (btn) btn.disabled = false;
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
