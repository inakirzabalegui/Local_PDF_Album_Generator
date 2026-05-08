// ═══════════════════════════════════════════════════════════════════════════
// Printing configuration dialog.
// Lets the user pick provider/product/paper variant, see resolved page+cover
// dimensions, and override any individual measurement (cm).
// ═══════════════════════════════════════════════════════════════════════════

const PRINTING_STATE = {
    providers: [],
    productsByProvider: {},
    config: null,
    pageCount: 0,
    overrides: { page: {}, cover: {}, rendering: {} },
    provider: { name: 'blurb', product: '', paper_variant: '' },
};

const PAGE_FIELDS = [
    ['trim_w_cm', 'Página trim ancho'],
    ['trim_h_cm', 'Página trim alto'],
    ['bleed_top_cm', 'Sangrado arriba'],
    ['bleed_bottom_cm', 'Sangrado abajo'],
    ['bleed_outside_cm', 'Sangrado exterior'],
    ['bleed_inside_cm', 'Sangrado interior (encuadernación)'],
    ['safe_inset_outside_cm', 'Inset exterior'],
    ['safe_inset_binding_cm', 'Inset encuadernación'],
    ['safe_inset_top_cm', 'Inset arriba'],
    ['safe_inset_bottom_cm', 'Inset abajo'],
];

const COVER_FIELDS = [
    ['trim_w_cm', 'Cover trim ancho total'],
    ['trim_h_cm', 'Cover trim alto'],
    ['bleed_cm', 'Cover sangrado (4 lados)'],
    ['flap_w_cm', 'Solapa'],
    ['spine_w_cm', 'Lomo (spine)'],
    ['hinge_w_cm', 'Hinge / charnela'],
    ['safe_inset_cm', 'Cover inset'],
];

function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    if (attrs) {
        for (const [k, v] of Object.entries(attrs)) {
            if (k === 'class') node.className = v;
            else if (k === 'dataset') Object.assign(node.dataset, v);
            else if (k === 'style') node.style.cssText = v;
            else if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2), v);
            else if (typeof v === 'boolean') {
                if (v) node.setAttribute(k, '');
            } else if (v != null) node.setAttribute(k, v);
        }
    }
    for (const child of children) {
        if (child == null || child === false) continue;
        if (typeof child === 'string' || typeof child === 'number') node.appendChild(document.createTextNode(String(child)));
        else node.appendChild(child);
    }
    return node;
}

async function openPrintingDialog() {
    const dialog = document.getElementById('printing-dialog');
    const body = document.getElementById('printing-dialog-body');
    body.replaceChildren(el('p', { class: 'printing-loading' }, 'Cargando…'));
    dialog.classList.remove('hidden');

    try {
        const [provs, cfg] = await Promise.all([
            fetch('/api/providers').then(r => r.json()),
            fetch('/api/config/global').then(r => r.ok ? r.json() : Promise.reject(r.statusText)),
        ]);
        PRINTING_STATE.providers = provs.providers || [];
        PRINTING_STATE.config = cfg;
        PRINTING_STATE.pageCount = cfg.page_count || 0;
        PRINTING_STATE.provider = { ...cfg.provider };
        PRINTING_STATE.overrides = JSON.parse(JSON.stringify(cfg.overrides || { page: {}, cover: {}, rendering: {} }));

        await ensureProductsLoaded(PRINTING_STATE.provider.name);
        renderPrintingDialog();
    } catch (err) {
        body.replaceChildren(el('p', { style: 'color:#c33;' }, 'Error cargando configuración: ' + err));
    }
}

function closePrintingDialog() {
    document.getElementById('printing-dialog').classList.add('hidden');
}

async function ensureProductsLoaded(name) {
    if (PRINTING_STATE.productsByProvider[name]) return PRINTING_STATE.productsByProvider[name];
    const r = await fetch(`/api/providers/${encodeURIComponent(name)}`);
    const data = await r.json();
    PRINTING_STATE.productsByProvider[name] = data.products || [];
    return data.products || [];
}

function renderPrintingDialog() {
    const body = document.getElementById('printing-dialog-body');
    const products = PRINTING_STATE.productsByProvider[PRINTING_STATE.provider.name] || [];
    const currentProduct = products.find(p => p.id === PRINTING_STATE.provider.product) || products[0];
    if (currentProduct && PRINTING_STATE.provider.product !== currentProduct.id) {
        PRINTING_STATE.provider.product = currentProduct.id;
        PRINTING_STATE.provider.paper_variant = currentProduct.default_paper_variant;
    }
    const variants = currentProduct ? currentProduct.paper_variants : [];

    function buildSelect(id, options, selected, change) {
        const sel = el('select', { id });
        for (const opt of options) {
            const o = el('option', { value: opt.value }, opt.label);
            if (opt.value === selected) o.selected = true;
            sel.appendChild(o);
        }
        sel.addEventListener('change', change);
        return sel;
    }

    function row(...nodes) {
        return el('div', { class: 'printing-row' }, ...nodes);
    }

    function provSection() {
        const sec = el('section', { class: 'printing-section' }, el('h3', null, 'Proveedor'));

        sec.appendChild(row(
            el('label', null, 'Proveedor'),
            buildSelect('prov-name',
                PRINTING_STATE.providers.map(p => ({ value: p.name, label: p.label })),
                PRINTING_STATE.provider.name,
                onProviderChange,
            ),
        ));
        sec.appendChild(row(
            el('label', null, 'Producto'),
            buildSelect('prov-product',
                products.map(p => ({ value: p.id, label: p.label })),
                PRINTING_STATE.provider.product,
                onProductChange,
            ),
        ));
        sec.appendChild(row(
            el('label', null, 'Tipo de papel'),
            buildSelect('prov-variant',
                variants.map(v => ({ value: v, label: v })),
                PRINTING_STATE.provider.paper_variant,
                onVariantChange,
            ),
        ));
        sec.appendChild(row(
            el('label', null, 'Páginas actuales'),
            el('span', { id: 'page-count' }, String(PRINTING_STATE.pageCount)),
        ));
        return sec;
    }

    function warnSection() {
        return el('section', { class: 'printing-section', id: 'printing-warnings-section', style: 'display:none' },
            el('h3', null, 'Avisos'),
            el('ul', { class: 'printing-warnings', id: 'printing-warnings' }),
        );
    }

    function fieldRowEl(group, key, label) {
        const ov = (PRINTING_STATE.overrides[group] || {})[key];
        const overridden = ov != null;

        const valueInput = el('input', {
            type: 'number', step: '0.001', min: '0', max: '200',
            class: 'field-value',
            placeholder: 'auto',
        });
        valueInput.dataset.group = group;
        valueInput.dataset.key = key;
        valueInput.disabled = !overridden;

        const overrideCb = el('input', { type: 'checkbox' });
        overrideCb.dataset.group = group;
        overrideCb.dataset.key = key;
        overrideCb.checked = overridden;

        overrideCb.addEventListener('change', () => {
            if (overrideCb.checked) {
                valueInput.disabled = false;
                if (!valueInput.value) {
                    const resolved = (group === 'page' ? PRINTING_STATE.config?.page_spec : PRINTING_STATE.config?.cover_spec) || {};
                    if (resolved[key] != null) valueInput.value = trimNum(resolved[key]);
                }
                valueInput.focus();
                PRINTING_STATE.overrides[group][key] = parseFloat(valueInput.value) || 0;
            } else {
                valueInput.disabled = true;
                valueInput.value = '';
                delete PRINTING_STATE.overrides[group][key];
            }
            refreshPreview();
        });

        valueInput.addEventListener('input', () => {
            const v = parseFloat(valueInput.value);
            if (!isNaN(v)) PRINTING_STATE.overrides[group][key] = v;
            refreshPreview();
        });

        const r = el('div', { class: 'printing-row' },
            el('label', null, label),
            valueInput,
            el('span', { class: 'field-unit' }, 'cm'),
            el('label', { class: 'override-toggle' }, overrideCb, ' override'),
        );
        r.dataset.field = `${group}.${key}`;
        return r;
    }

    function pageSection() {
        const tag = el('span', { class: 'printing-tag', id: 'page-pdf-size' });
        const sec = el('section', { class: 'printing-section' },
            el('h3', null, 'Página interior ', tag),
        );
        for (const [k, label] of PAGE_FIELDS) sec.appendChild(fieldRowEl('page', k, label));
        return sec;
    }

    function coverSection() {
        const tag = el('span', { class: 'printing-tag', id: 'cover-pdf-size' });
        const sec = el('section', { class: 'printing-section', id: 'cover-section' },
            el('h3', null, 'Cover wraparound ', tag),
        );
        for (const [k, label] of COVER_FIELDS) sec.appendChild(fieldRowEl('cover', k, label));
        return sec;
    }

    function otherSection() {
        const sec = el('section', { class: 'printing-section' },
            el('h3', null, 'Otros'),
        );

        const bindingSel = buildSelect('binding-side',
            [{ value: 'left', label: 'Izquierda (convencional)' }, { value: 'right', label: 'Derecha' }],
            PRINTING_STATE.overrides.rendering?.binding_side_for_odd || 'left',
            onBindingChange,
        );
        sec.appendChild(row(
            el('label', null, 'Borde de encuadernación en páginas impares'),
            bindingSel,
        ));

        const cb = el('input', { type: 'checkbox', id: 'ov-max-pages-enabled' });
        const numInput = el('input', { type: 'number', id: 'ov-max-pages-value', min: '2', max: '2000' });
        numInput.disabled = true;

        const maxOv = PRINTING_STATE.overrides.rendering?.max_pages_per_volume;
        if (maxOv != null) {
            cb.checked = true;
            numInput.disabled = false;
            numInput.value = maxOv;
        }
        cb.addEventListener('change', () => {
            numInput.disabled = !cb.checked;
            if (!cb.checked) {
                delete PRINTING_STATE.overrides.rendering.max_pages_per_volume;
            } else if (numInput.value) {
                PRINTING_STATE.overrides.rendering.max_pages_per_volume = parseInt(numInput.value, 10);
            }
            refreshPreview();
        });
        numInput.addEventListener('change', () => {
            PRINTING_STATE.overrides.rendering.max_pages_per_volume = parseInt(numInput.value, 10) || null;
            refreshPreview();
        });

        sec.appendChild(row(
            el('label', null, cb, ' Limitar páginas por volumen'),
            numInput,
        ));
        return sec;
    }

    body.replaceChildren(provSection(), warnSection(), pageSection(), coverSection(), otherSection());
    refreshPreview();
}

async function onProviderChange(e) {
    PRINTING_STATE.provider.name = e.target.value;
    await ensureProductsLoaded(e.target.value);
    const products = PRINTING_STATE.productsByProvider[e.target.value] || [];
    if (products.length) {
        PRINTING_STATE.provider.product = products[0].id;
        PRINTING_STATE.provider.paper_variant = products[0].default_paper_variant;
    }
    PRINTING_STATE.overrides = { page: {}, cover: {}, rendering: PRINTING_STATE.overrides.rendering || {} };
    renderPrintingDialog();
}

async function onProductChange(e) {
    PRINTING_STATE.provider.product = e.target.value;
    const products = PRINTING_STATE.productsByProvider[PRINTING_STATE.provider.name] || [];
    const product = products.find(p => p.id === e.target.value);
    if (product) PRINTING_STATE.provider.paper_variant = product.default_paper_variant;
    PRINTING_STATE.overrides = { page: {}, cover: {}, rendering: PRINTING_STATE.overrides.rendering || {} };
    renderPrintingDialog();
}

function onVariantChange(e) {
    PRINTING_STATE.provider.paper_variant = e.target.value;
    refreshPreview();
}

function onBindingChange(e) {
    PRINTING_STATE.overrides.rendering = PRINTING_STATE.overrides.rendering || {};
    PRINTING_STATE.overrides.rendering.binding_side_for_odd = e.target.value;
    refreshPreview();
}

async function refreshPreview() {
    const status = document.getElementById('printing-status');
    if (status) status.textContent = 'Calculando…';
    try {
        const r = await fetch('/api/config/preview', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                provider: PRINTING_STATE.provider,
                overrides: PRINTING_STATE.overrides,
                page_count: PRINTING_STATE.pageCount,
            }),
        });
        const data = await r.json();
        if (!r.ok) throw new Error(data.error || 'preview failed');

        PRINTING_STATE.config.page_spec = data.page_spec;
        PRINTING_STATE.config.cover_spec = data.cover_spec;

        PAGE_FIELDS.forEach(([k]) => updateFieldValue('page', k, data.page_spec[k]));
        COVER_FIELDS.forEach(([k]) => updateFieldValue('cover', k, data.cover_spec[k]));

        const pageTag = document.getElementById('page-pdf-size');
        if (pageTag) pageTag.textContent =
            `PDF ${(+data.page_spec.pdf_w_cm).toFixed(3)} × ${(+data.page_spec.pdf_h_cm).toFixed(3)} cm`;

        const coverTag = document.getElementById('cover-pdf-size');
        if (coverTag) coverTag.textContent = data.embedded_cover ? '(modo embebido)' :
            `PDF ${(+data.cover_spec.pdf_w_cm).toFixed(3)} × ${(+data.cover_spec.pdf_h_cm).toFixed(3)} cm`;

        const coverSec = document.getElementById('cover-section');
        if (coverSec) coverSec.style.display = data.embedded_cover ? 'none' : '';

        const warnSection = document.getElementById('printing-warnings-section');
        const warnList = document.getElementById('printing-warnings');
        if (warnSection && warnList) {
            warnList.replaceChildren();
            if (data.warnings && data.warnings.length) {
                warnSection.style.display = '';
                for (const w of data.warnings) {
                    warnList.appendChild(el('li', null, '⚠️ ' + w));
                }
            } else {
                warnSection.style.display = 'none';
            }
        }

        if (status) {
            status.textContent = 'OK';
            setTimeout(() => { if (status.textContent === 'OK') status.textContent = ''; }, 800);
        }
    } catch (err) {
        if (status) status.textContent = `Error: ${err.message}`;
    }
}

function updateFieldValue(group, key, value) {
    const row = document.querySelector(`[data-field="${group}.${key}"]`);
    if (!row) return;
    const input = row.querySelector('input.field-value');
    const cb = row.querySelector('.override-toggle input');
    if (!cb.checked) {
        input.value = value != null ? trimNum(value) : '';
    }
}

function resetPrintingOverrides() {
    PRINTING_STATE.overrides = { page: {}, cover: {}, rendering: { binding_side_for_odd: 'left' } };
    renderPrintingDialog();
}

async function savePrintingConfig() {
    const btn = document.getElementById('printing-save-btn');
    btn.disabled = true;
    const status = document.getElementById('printing-status');
    if (status) status.textContent = 'Guardando…';
    try {
        const r = await fetch('/api/config/global', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                provider: PRINTING_STATE.provider,
                overrides: PRINTING_STATE.overrides,
            }),
        });
        const data = await r.json();
        if (!r.ok) throw new Error(data.error || 'save failed');
        if (status) status.textContent = 'Guardado.';
        if (typeof showToast === 'function') {
            showToast('Configuración de impresión guardada', { type: 'success' });
        }
        setTimeout(closePrintingDialog, 400);
    } catch (err) {
        if (status) status.textContent = `Error: ${err.message}`;
        if (typeof showToast === 'function') {
            showToast(`Error al guardar: ${err.message}`, { type: 'error' });
        }
    } finally {
        btn.disabled = false;
    }
}

function trimNum(v) {
    return (+v).toFixed(4).replace(/0+$/, '').replace(/\.$/, '');
}
