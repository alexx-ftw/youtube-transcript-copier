// ==UserScript==
// @name         YouTube - Copiar transcripción completa
// @namespace    eros.youtube.transcript
// @version      1.1.1
// @description  Copia, revisa y guarda la transcripción. Panel moderno/clásico, carga progresiva y avisos de integridad.
// @match        https://www.youtube.com/*
// @match        https://youtube.com/*
// @run-at       document-idle
// @grant        GM_setClipboard
// @grant        GM.setClipboard
// @grant        unsafeWindow
// @noframes
// @license      MIT
// @homepageURL  https://github.com/alexx-ftw/youtube-transcript-copier
// @supportURL   https://github.com/alexx-ftw/youtube-transcript-copier/issues
// @updateURL    https://raw.githubusercontent.com/alexx-ftw/youtube-transcript-copier/main/youtube-copiar-transcripcion.meta.js
// @downloadURL  https://raw.githubusercontent.com/alexx-ftw/youtube-transcript-copier/main/youtube-copiar-transcripcion.user.js
// ==/UserScript==

(() => {
  'use strict';

  const VERSION = '1.1.1';
  const PANEL = [
    'ytd-engagement-panel-section-list-renderer[target-id="PAmodern_transcript_view"]',
    'ytd-engagement-panel-section-list-renderer[target-id="engagement-panel-searchable-transcript"]',
  ].join(',');
  const ROW = 'transcript-segment-view-model, ytd-transcript-segment-renderer';
  const BAR = 'ytcopy-transcript-bar';
  const DIALOG = 'ytcopy-transcript-dialog';
  const OWN = `.${BAR}, .${DIALOG}`;
  const LIMITS = Object.freeze({
    initialWait: 12000,
    scan: 180000,
    step: 180,
    renderWait: 1400,
    bottomQuiet: 1800,
    modelNodes: 60000,
    segments: 60000,
    characters: 12000000,
    gap: 180,
  });
  const controllers = new Map();
  let active = null;
  let mountTimer = null;
  let navigationRevision = 0;

  /** @typedef {{seconds:number, end:number|null, text:string, stamp:string}} Segment */
  const clean = value => String(value ?? '').replace(/\s+/gu, ' ').trim();
  const safe = (object, key) => { try { return object?.[key]; } catch { return undefined; } };
  const videoKey = () => `${location.pathname}?v=${new URL(location.href).searchParams.get('v') || ''}`;
  const abortError = message => new DOMException(message || 'Lectura cancelada.', 'AbortError');

  function secondsFrom(value) {
    const text = clean(value).replace(/[\u200e\u200f\u202a-\u202e\u2066-\u2069]/g, '');
    if (!/^\d+(?::\d{1,2}){1,2}(?:[.,]\d+)?$/.test(text)) return NaN;
    const parts = text.replace(',', '.').split(':').map(Number);
    if (parts.slice(1).some(part => part >= 60)) return NaN;
    return parts.reduce((total, part) => total * 60 + part, 0);
  }

  function timestamp(seconds) {
    const value = Math.max(0, Math.floor(seconds));
    const h = Math.floor(value / 3600);
    const m = Math.floor(value / 60) % 60;
    const s = String(value % 60).padStart(2, '0');
    return h ? `${h}:${String(m).padStart(2, '0')}:${s}` : `${m}:${s}`;
  }

  function youtubeText(value) {
    if (typeof value === 'string') return value;
    if (!value || typeof value !== 'object') return '';
    if (typeof safe(value, 'simpleText') === 'string') return value.simpleText;
    if (typeof safe(value, 'content') === 'string') return value.content;
    return Array.isArray(safe(value, 'runs')) ? value.runs.map(run => safe(run, 'text') || '').join('') : '';
  }

  function visible(element) {
    if (!element || element.hidden || element.closest('[hidden], [aria-hidden="true"]')) return false;
    const style = getComputedStyle(element);
    return element.getClientRects().length > 0 && style.display !== 'none' && style.visibility !== 'hidden';
  }

  function searchInputs(panel) {
    return [...panel.querySelectorAll('input:not([type="checkbox"]):not([type="radio"]), textarea')]
      .filter(el => !el.closest(OWN) && visible(el));
  }

  function searchIsActive(panel) { return searchInputs(panel).some(el => clean(el.value)); }

  function trackKey(panel) {
    // Only language controls, never the moving highlighted transcript row.
    return [...panel.querySelectorAll(
      'ytd-transcript-footer-renderer #label, ytd-transcript-footer-renderer select, ' +
      'ytd-transcript-language-select-renderer, [data-language-code], [data-transcript-language]'
    )].map(el => [el.getAttribute('data-language-code') || el.getAttribute('data-transcript-language') || '',
      el.tagName === 'SELECT' ? el.value : clean(el.textContent)].join(':')).join('|');
  }

  function sameContext(task) {
    return videoKey() === task.video && navigationRevision === task.revision && task.panel.isConnected &&
      task.track === trackKey(task.panel);
  }

  function check(task, deadline = true) {
    if (task.signal.aborted) throw abortError(task.signal.reason?.message);
    if (!sameContext(task)) throw abortError('El vídeo, el idioma o el panel ha cambiado.');
    if (task.panel.getAttribute('visibility') === 'ENGAGEMENT_PANEL_VISIBILITY_HIDDEN') {
      throw abortError('Se ha cerrado la transcripción.');
    }
    if (searchIsActive(task.panel)) throw new Error('Borra la búsqueda del panel para copiar toda la transcripción.');
    if (deadline && Date.now() > task.deadline) {
      const error = new Error('Se alcanzó el límite de lectura; puede faltar texto.');
      error.name = 'ScanTimeout';
      throw error;
    }
  }

  function wait(ms, task) {
    check(task);
    return new Promise((resolve, reject) => {
      const onAbort = () => { clearTimeout(timer); reject(abortError(task.signal.reason?.message)); };
      const timer = setTimeout(() => {
        task.signal.removeEventListener('abort', onAbort);
        try { check(task); resolve(); } catch (error) { reject(error); }
      }, ms);
      task.signal.addEventListener('abort', onAbort, {once: true});
    });
  }

  function makeSegment(textValue, stampValue, seconds = NaN, end = null) {
    const text = clean(textValue);
    const start = Number.isFinite(seconds) ? seconds : secondsFrom(stampValue);
    if (!text || !Number.isFinite(start) || start < 0) return null;
    return {text, seconds: start, stamp: timestamp(start),
      end: Number.isFinite(end) && end > start ? end : null};
  }

  function modelSegment(object) {
    if (!object || typeof object !== 'object') return null;
    const rawMs = safe(object, 'startMs') ?? safe(object, 'startTimeMs');
    const ms = rawMs == null || rawMs === '' ? NaN : Number(rawMs);
    const rawEnd = safe(object, 'endMs') ?? safe(object, 'endTimeMs');
    return makeSegment(
      youtubeText(safe(object, 'snippet')) || youtubeText(safe(object, 'text')) || youtubeText(safe(object, 'simpleText')),
      youtubeText(safe(object, 'timestamp')) || youtubeText(safe(object, 'startTimeText')),
      ms / 1000, rawEnd == null || rawEnd === '' ? null : Number(rawEnd) / 1000
    );
  }

  class SegmentStore {
    constructor() {
      this.dom = new Map();
      this.models = new Map();
      this.characters = 0;
      this.lastChange = Date.now();
      this.warnings = new Set();
    }
    add(segment, source, occurrence = 0) {
      if (!segment) return;
      const map = source === 'model' ? this.models : this.dom;
      const key = `${segment.seconds}\u0000${segment.text}${source === 'dom' ? `\u0000${occurrence}` : ''}`;
      if (map.has(key)) return;
      if (this.dom.size + this.models.size >= LIMITS.segments ||
          this.characters + segment.text.length > LIMITS.characters) {
        const error = new Error('La transcripción supera el límite de memoria; puede faltar texto.');
        error.name = 'ScanTimeout';
        throw error;
      }
      map.set(key, segment);
      this.characters += segment.text.length;
      this.lastChange = Date.now();
    }
    get size() { return this.dom.size + this.models.size; }
    values() {
      // DOM timestamps are rounded, model timestamps can be fractional. Do not round
      // the model: two identical cues in one second can be two genuine repetitions.
      let models = [...this.models.values()];
      const bySecond = new Map();
      for (const segment of models) {
        const t = Math.floor(segment.seconds);
        if (!bySecond.has(t)) bySecond.set(t, new Set());
        bySecond.get(t).add(segment.text);
      }
      const conflict = [...this.dom.values()].some(segment =>
        bySecond.has(Math.floor(segment.seconds)) && !bySecond.get(Math.floor(segment.seconds)).has(segment.text));
      if (conflict) {
        // Never combine contradictory backing data with the visible language.
        models = [];
        this.warnings.add('Los datos internos no coinciden con el panel; se ha conservado solo el texto observado.');
      }
      const modeled = new Map();
      for (const segment of models) {
        const key = `${Math.floor(segment.seconds)}\u0000${segment.text}`;
        modeled.set(key, (modeled.get(key) || 0) + 1);
      }
      const extra = [];
      for (const segment of this.dom.values()) {
        const key = `${Math.floor(segment.seconds)}\u0000${segment.text}`;
        const remaining = modeled.get(key) || 0;
        if (remaining) modeled.set(key, remaining - 1);
        else extra.push(segment);
      }
      return [...models, ...extra].sort((a, b) => a.seconds - b.seconds);
    }
  }

  function readDOM(panel, store) {
    const occurrences = new Map();
    for (const row of panel.querySelectorAll(ROW)) {
      if (row.closest('[hidden], [aria-hidden="true"]')) continue;
      const time = row.querySelector('.ytwTranscriptSegmentViewModelTimestamp, .segment-timestamp');
      const candidates = [...row.querySelectorAll(
        ':scope > span.ytAttributedStringHost, :scope > span[role="text"], ' +
        '.ytwTranscriptSegmentViewModelText, .segment-text, span.yt-core-attributed-string'
      )];
      // Read outermost text spans, excluding accessible time labels and nested duplicates.
      const parts = candidates.filter(el => !candidates.some(other => other !== el && other.contains(el)));
      const text = parts.map(el => el.textContent).join('');
      if (time) {
        const segment = makeSegment(text, time.textContent);
        if (!segment) continue;
        const key = `${segment.seconds}\u0000${segment.text}`;
        const occurrence = occurrences.get(key) || 0;
        occurrences.set(key, occurrence + 1);
        store.add(segment, 'dom', occurrence);
      }
    }
  }

  async function readModels(task, store) {
    let pagePanel;
    try {
      const pageDocument = typeof unsafeWindow !== 'undefined' ? unsafeWindow.document : document;
      pagePanel = [...pageDocument.querySelectorAll(PANEL)].find(el =>
        el.getAttribute('target-id') === task.panel.getAttribute('target-id'));
    } catch { return; }
    if (!pagePanel) return;
    const hosts = [pagePanel, ...pagePanel.querySelectorAll(
      'yt-section-list-renderer, yt-item-section-renderer, ytd-transcript-renderer, ' +
      'ytd-transcript-search-panel-renderer, ytd-transcript-segment-list-renderer, ' + ROW
    )];
    const stack = [];
    for (const host of hosts) {
      for (const owner of [host, safe(host, 'polymerController'), safe(host, 'inst')]) {
        const raw = host.matches(ROW);
        const data = safe(owner, '__data');
        for (const value of [safe(owner, 'data'), safe(owner, 'viewModel'), safe(data, 'data'), safe(data, 'viewModel')]) {
          if (value && typeof value === 'object') stack.push({value, raw});
        }
      }
    }
    const seen = new WeakSet();
    let visits = 0;
    while (stack.length && visits < LIMITS.modelNodes) {
      const {value, raw} = stack.pop();
      if (!value || typeof value !== 'object' || seen.has(value) || safe(value, 'nodeType')) continue;
      seen.add(value);
      visits++;
      if (visits % 1000 === 0) await wait(0, task);
      const segment = safe(value, 'transcriptSegmentRenderer') || safe(value, 'transcriptSegmentViewModel');
      if (segment || raw) {
        const parsed = modelSegment(segment || value);
        if (parsed) { store.add(parsed, 'model'); continue; }
      }
      let keys;
      try { keys = Object.keys(value); } catch { continue; }
      for (let i = keys.length - 1; i >= 0; i--) {
        const child = safe(value, keys[i]);
        if (child && typeof child === 'object') stack.push({value: child, raw: false});
      }
    }
    if (stack.length) store.warnings.add('Los datos internos son muy grandes; su lectura ha sido limitada.');
    check(task);
  }

  function findScroller(panel) {
    const ancestors = [];
    let node = panel.querySelector(ROW)?.parentElement;
    while (node && panel.contains(node)) {
      ancestors.push(node);
      if (node === panel) break;
      node = node.parentElement;
    }
    const candidates = [...new Set([...ancestors, ...panel.querySelectorAll(
      'yt-section-list-renderer, #segments-container, ytd-transcript-segment-list-renderer, #content'
    ), panel])];
    const scrollable = candidates.filter(el => !el.closest(OWN) && el.clientHeight > 0 && el.scrollHeight > el.clientHeight + 2);
    return scrollable.find(el => /auto|scroll|overlay/.test(getComputedStyle(el).overflowY)) || scrollable[0] || null;
  }

  function isLoading(panel) {
    return [...panel.querySelectorAll(
      '[aria-busy="true"], tp-yt-paper-spinner[active], tp-yt-paper-spinner-lite[active], [role="progressbar"]'
    )].some(el => !el.closest(OWN) && visible(el));
  }

  function pendingContinuation(panel) {
    return [...panel.querySelectorAll('ytd-continuation-item-renderer, yt-continuation-item-view-model')]
      .some(el => visible(el) && [...el.querySelectorAll('button, [role="button"]')].some(visible));
  }

  function domSignature(panel) {
    const rows = panel.querySelectorAll(ROW);
    return `${rows.length}|${rows[0]?.textContent || ''}|${rows[rows.length - 1]?.textContent || ''}`;
  }

  function likelyVirtual(panel, scroller) {
    if (!scroller) return false;
    const rows = [...panel.querySelectorAll(ROW)];
    const renderedHeight = rows.reduce((sum, el) => sum + el.getBoundingClientRect().height, 0);
    return rows.length > 0 && renderedHeight > 0 && scroller.scrollHeight > renderedHeight * 1.7 + scroller.clientHeight;
  }

  async function collect(task, update) {
    const store = new SegmentStore();
    const positions = new Map();
    let readError = null;
    let readTimer = null;
    const read = () => { try { readDOM(task.panel, store); } catch (error) { readError = error; } };
    const observer = new MutationObserver(records => {
      if (records.every(record => (record.target.nodeType === 1 ? record.target : record.target.parentElement)?.closest(OWN))) return;
      if (readTimer === null) readTimer = setTimeout(() => { readTimer = null; read(); }, 40);
    });
    const move = (scroller, top) => {
      if (!positions.has(scroller)) {
        const properties = ['scroll-behavior', 'overflow-anchor', 'scroll-snap-type'];
        positions.set(scroller, {top: scroller.scrollTop, styles: properties.map(name =>
          [name, scroller.style.getPropertyValue(name), scroller.style.getPropertyPriority(name)])});
        scroller.style.setProperty('scroll-behavior', 'auto', 'important');
        scroller.style.setProperty('overflow-anchor', 'none', 'important');
        scroller.style.setProperty('scroll-snap-type', 'none', 'important');
      }
      scroller.scrollTop = top;
      scroller.dispatchEvent(new Event('scroll'));
    };
    const scrollAndWait = async (scroller, top) => {
      const oldTop = scroller.scrollTop;
      const signature = domSignature(task.panel);
      const virtual = likelyVirtual(task.panel, scroller);
      move(scroller, top);
      await wait(LIMITS.step, task);
      if (virtual && Math.abs(oldTop - top) > 1) {
        const renderDeadline = Date.now() + LIMITS.renderWait;
        while (domSignature(task.panel) === signature && Date.now() < renderDeadline) await wait(100, task);
        if (domSignature(task.panel) === signature) {
          store.warnings.add('Algunas filas virtualizadas no confirmaron su actualización; puede faltar texto.');
        } else await wait(80, task);
      }
      read();
    };
    const progress = (scroller, phase) => {
      // A percentage describes panel traversal, not transcript completeness.
      const max = scroller ? scroller.scrollHeight - scroller.clientHeight : 0;
      update({count: store.dom.size || store.models.size, phase,
        progress: max > 0 ? Math.min(1, scroller.scrollTop / max) : null});
    };
    check(task);
    observer.observe(task.panel, {childList: true, subtree: true, characterData: true});
    try {
      read();
      await readModels(task, store);
      const initialDeadline = Date.now() + LIMITS.initialWait;
      while (!store.size && Date.now() < initialDeadline) {
        progress(null, 'Esperando segmentos');
        await wait(250, task);
        read();
        if (readError) throw readError;
        if (store.size) break;
        await readModels(task, store);
      }
      if (!store.size) throw new Error('YouTube aún no ha proporcionado segmentos. Abre la transcripción o vuelve a intentarlo.');
      let scroller = findScroller(task.panel);
      if (scroller) await scrollAndWait(scroller, 0);
      else await wait(LIMITS.step, task);
      let stableSince = Date.now();
      let previousHeight = -1;
      let stuck = 0;
      while (true) {
        check(task);
        read();
        if (readError) throw readError;
        const current = findScroller(task.panel);
        if (current && current !== scroller) {
          scroller = current;
          await scrollAndWait(scroller, 0);
          stableSince = Date.now();
          continue;
        }
        const height = scroller?.scrollHeight || 0;
        if (height !== previousHeight) { previousHeight = height; stableSince = Date.now(); }
        const bottom = scroller ? Math.max(0, height - scroller.clientHeight) : 0;
        const atBottom = !scroller || scroller.scrollTop >= bottom - 3;
        progress(scroller, atBottom ? 'Comprobando final' : 'Recorriendo panel');
        if (atBottom) {
          if (!isLoading(task.panel) && Date.now() - Math.max(stableSince, store.lastChange) >= LIMITS.bottomQuiet) break;
          await wait(300, task);
        } else {
          stableSince = Date.now();
          const oldTop = scroller.scrollTop;
          await scrollAndWait(scroller, Math.min(bottom, oldTop + Math.max(1, Math.floor(scroller.clientHeight * 0.6))));
          stuck = scroller.scrollTop <= oldTop + 1 ? stuck + 1 : 0;
          if (stuck > 6) {
            store.warnings.add('El panel dejó de avanzar. Pausa el vídeo y repite la lectura para comprobar el resultado.');
            break;
          }
        }
      }
      read();
      if (readError) throw readError;
      await readModels(task, store);
      if (pendingContinuation(task.panel)) store.warnings.add('El panel todavía muestra un botón para cargar más contenido.');
    } catch (error) {
      if (error.name !== 'ScanTimeout' || !store.size) throw error;
      check(task, false);
      store.warnings.add(error.message);
    } finally {
      observer.disconnect();
      clearTimeout(readTimer);
      for (const [scroller, saved] of positions) {
        // Restore even after an explicit Cancel, but never into another video/track.
        if (sameContext(task) && scroller.isConnected) {
          scroller.scrollTop = saved.top;
          scroller.dispatchEvent(new Event('scroll'));
        }
        for (const [name, value, priority] of saved.styles) {
          if (value) scroller.style.setProperty(name, value, priority);
          else scroller.style.removeProperty(name);
        }
      }
    }
    check(task, false);
    const segments = store.values();
    if (!segments.length) throw new Error('No hay segmentos legibles en la transcripción.');
    return {segments, warnings: [...store.warnings, ...completenessWarnings(segments, task)], task};
  }

  function completenessWarnings(segments, task) {
    const warnings = [];
    if (segments[0].seconds > LIMITS.gap) warnings.push(`El primer segmento comienza en ${segments[0].stamp}.`);
    let largest = null;
    for (let i = 1; i < segments.length; i++) {
      const previous = segments[i - 1];
      const gap = segments[i].seconds - (previous.end ?? previous.seconds);
      if (gap > LIMITS.gap && (!largest || gap > largest.gap)) largest = {gap, from: previous.stamp, to: segments[i].stamp};
    }
    if (largest) warnings.push(`Hay un salto de ${largest.from} a ${largest.to}; puede ser silencio o texto no cargado.`);
    const player = document.querySelector('#movie_player');
    const duration = player?.querySelector('video')?.duration;
    let live = false;
    try {
      const pagePlayer = (typeof unsafeWindow !== 'undefined' ? unsafeWindow.document : document).querySelector('#movie_player');
      const data = pagePlayer?.getVideoData?.();
      live = !!(data?.isLive || data?.isLiveContent);
    } catch { /* Unknown stream type: the notice below remains explicitly tentative. */ }
    const last = segments[segments.length - 1];
    if (sameContext(task) && !live && Number.isFinite(duration) && duration > 0 &&
        !player.matches('.ad-showing, .ad-interrupting') && duration - (last.end ?? last.seconds) > LIMITS.gap) {
      warnings.push(`El último segmento empieza en ${last.stamp}; el vídeo dura ${timestamp(duration)}. Puede faltar el final.`);
    }
    return warnings;
  }

  function format(segments, timed) {
    return timed ? segments.map(segment => `[${segment.stamp}] ${segment.text}`).join('\n') :
      segments.map(segment => segment.text).join(' ');
  }

  function bounded(promise, ms) {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error('El portapapeles no confirmó la copia.')), ms);
      Promise.resolve(promise).then(value => { clearTimeout(timer); resolve(value); }, error => { clearTimeout(timer); reject(error); });
    });
  }

  async function clipboard(text, validate = () => {}) {
    validate();
    // Prefer the documented promise API; legacy callbacks remain supported.
    if (typeof GM !== 'undefined' && typeof GM.setClipboard === 'function') {
      try {
        const result = GM.setClipboard(text, 'text');
        if (!result || typeof result.then !== 'function') throw new Error('Sin confirmación del gestor.');
        await bounded(result, 3000);
        return;
      } catch { validate(); /* Try legacy/native only while this operation is current. */ }
    }
    if (typeof GM_setClipboard === 'function') {
      try {
        await bounded(new Promise((resolve, reject) => {
          try {
            const result = GM_setClipboard(text, 'text', resolve);
            if (result && typeof result.then === 'function') result.then(resolve, reject);
          } catch (error) { reject(error); }
        }), 2500);
        return;
      } catch { validate(); /* A fresh copy gesture in the preview can restore permission. */ }
    }
    if (navigator.clipboard?.writeText) {
      try { await bounded(navigator.clipboard.writeText(text), 3000); return; } catch { /* Keep the text available. */ }
    }
    throw new Error('No se pudo confirmar la copia. Puedes reintentar, guardar TXT o seleccionar el texto y pulsar Ctrl+C.');
  }

  function filename(timed) {
    const raw = clean(document.querySelector('h1.ytd-watch-metadata, #title h1')?.textContent ||
      document.title.replace(/\s*[-–|]\s*YouTube\s*$/i, '') || 'Transcripción');
    const title = raw.replace(/[<>:"/\\|?*\u0000-\u001f]/g, ' ').replace(/\s+/g, ' ').replace(/[. ]+$/g, '').slice(0, 100) || 'Transcripción';
    const id = new URL(location.href).searchParams.get('v');
    return `${title}${id ? ` - ${id.replace(/[^a-zA-Z0-9_-]/g, '')}` : ''}${timed ? ' - con tiempos' : ''}.txt`;
  }

  function download(text, timed) {
    const url = URL.createObjectURL(new Blob([text], {type: 'text/plain;charset=utf-8'}));
    const a = document.createElement('a');
    a.href = url;
    a.download = filename(timed);
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 30000);
  }

  function element(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text !== undefined) el.textContent = text;
    return el;
  }

  function button(parent, label, onClick, className = '') {
    const el = element('button', className, label);
    el.type = 'button';
    if (onClick) el.addEventListener('click', onClick);
    parent.append(el);
    return el;
  }

  function stats(segments, text) {
    const words = text.trim() ? text.trim().split(/\s+/u).length : 0;
    return `${segments.length.toLocaleString()} segmentos · ${words.toLocaleString()} palabras · ${text.length.toLocaleString()} caracteres`;
  }

  function preview(result, timed = false, errorMessage = '', returnFocus = null) {
    document.querySelector(`.${DIALOG}`)?.remove();
    const previousFocus = returnFocus || document.activeElement;
    const dialog = element('dialog', DIALOG);
    dialog.setAttribute('aria-labelledby', 'ytcopy-preview-title');
    const heading = element('div', 'ytcopy-dialog-heading');
    heading.append(element('h2', '', 'Texto recuperado'));
    heading.firstChild.id = 'ytcopy-preview-title';
    const close = () => {
      if (typeof dialog.close === 'function' && dialog.open) dialog.close();
      dialog.remove();
      if (previousFocus?.isConnected && !previousFocus.disabled) previousFocus.focus({preventScroll: true});
    };
    const closeButton = button(heading, 'Cerrar', close);
    closeButton.setAttribute('aria-label', 'Cerrar vista previa');
    const notice = element('div', 'ytcopy-notice');
    if (result.warnings.length) {
      notice.dataset.kind = 'warning';
      notice.textContent = 'Posible transcripción incompleta.\n' + result.warnings.join('\n') +
        '\nRevisa el texto antes de copiarlo o guardarlo.';
    } else notice.textContent = 'Son los segmentos recuperados de YouTube. El recorrido no garantiza por sí solo que la transcripción esté completa.';
    const modes = element('div', 'ytcopy-actions ytcopy-modes');
    const plain = button(modes, 'Texto', () => setMode(false));
    const withTimes = button(modes, 'Con tiempos', () => setMode(true));
    const count = element('div', 'ytcopy-count');
    const text = element('textarea', 'ytcopy-preview-text');
    text.readOnly = true;
    text.spellcheck = false;
    text.dir = 'auto';
    text.setAttribute('aria-label', 'Transcripción recuperada');
    const actions = element('div', 'ytcopy-actions');
    const message = element('div', 'ytcopy-status', errorMessage);
    message.setAttribute('role', 'status');
    message.setAttribute('aria-live', 'polite');
    const copyButton = button(actions, result.warnings.length ? 'Copiar lo recuperado' : 'Copiar texto', async () => {
      try {
        check(result.task, false);
        copyButton.disabled = true;
        await clipboard(text.value, () => check(result.task, false));
        message.textContent = 'Texto copiado.';
      } catch (error) { message.textContent = error.message; }
      finally { copyButton.disabled = false; }
    }, 'ytcopy-primary');
    const saveButton = button(actions, 'Guardar TXT', () => {
      try { check(result.task, false); download(text.value, timed); message.textContent = 'Archivo TXT preparado.'; }
      catch (error) { message.textContent = error.message; }
    });
    button(actions, 'Seleccionar texto', () => { text.focus(); text.select(); message.textContent = 'Pulsa Ctrl+C (o ⌘C en Mac) para copiar la selección.'; });
    function setMode(value) {
      timed = value;
      text.value = format(result.segments, timed);
      plain.setAttribute('aria-pressed', String(!timed));
      withTimes.setAttribute('aria-pressed', String(timed));
      count.textContent = stats(result.segments, format(result.segments, false));
      saveButton.title = `Guardar ${timed ? 'con' : 'sin'} marcas de tiempo`;
    }
    dialog.append(heading, notice, modes, count, text, actions, message);
    document.body.append(dialog);
    setMode(timed);
    dialog.addEventListener('cancel', event => { event.preventDefault(); close(); });
    dialog.addEventListener('click', event => {
      if (event.target !== dialog) return;
      const box = dialog.getBoundingClientRect();
      if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) close();
    });
    if (typeof dialog.showModal === 'function') dialog.showModal();
    else { dialog.setAttribute('open', ''); dialog.setAttribute('role', 'dialog'); dialog.setAttribute('aria-modal', 'true'); }
    closeButton.focus({preventScroll: true});
    if (errorMessage) { text.focus(); text.select(); }
    return dialog;
  }

  function mount(panel) {
    const previous = controllers.get(panel);
    if (previous?.bar.isConnected && previous.bar.parentElement === panel) return;
    previous?.dispose();
    panel.querySelector(`:scope > .${BAR}`)?.remove();
    const bar = element('div', BAR);
    const label = element('div', 'ytcopy-label');
    label.append(element('span', '', 'Copiar transcripción'), element('span', 'ytcopy-version', `v${VERSION}`));
    const actions = element('div', 'ytcopy-actions');
    const status = element('div', 'ytcopy-status', 'Copia el idioma mostrado en el panel.');
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    const meter = element('progress', 'ytcopy-progress');
    meter.max = 1;
    meter.hidden = true;
    meter.setAttribute('aria-label', 'Recorrido del panel, no porcentaje de transcripción recuperada');
    const plain = button(actions, 'Copiar texto', () => run('copy', false), 'ytcopy-primary');
    const timed = button(actions, 'Con tiempos', () => run('copy', true));
    const view = button(actions, 'Ver texto', () => run('preview', false));
    const save = button(actions, 'TXT', () => run('download', false));
    view.title = 'Revisar el texto y elegir formato antes de copiar';
    save.title = 'Guardar la transcripción como archivo de texto';
    const cancel = button(actions, 'Cancelar', () => active?.controller.abort(abortError('Lectura cancelada.')));
    cancel.hidden = true;
    bar.append(label, actions, meter, status);
    const header = panel.querySelector(':scope > #header');
    if (header) header.after(bar); else panel.prepend(bar);
    let disposed = false;
    function busy(value) {
      for (const btn of [plain, timed, view, save]) btn.disabled = value;
      cancel.hidden = !value;
      meter.hidden = !value;
      bar.setAttribute('aria-busy', String(value));
    }
    async function run(action, withTimes) {
      if (disposed) return;
      if (active) { status.textContent = 'Ya hay una lectura en curso.'; return; }
      if (searchIsActive(panel)) { status.textContent = 'Borra la búsqueda del panel para copiar toda la transcripción.'; searchInputs(panel)[0]?.focus(); return; }
      const sourceFocus = document.activeElement;
      const controller = new AbortController();
      const task = {panel, signal: controller.signal, video: videoKey(), revision: navigationRevision,
        track: trackKey(panel), deadline: Date.now() + LIMITS.scan};
      const operation = {controller, task};
      active = operation;
      busy(true);
      status.textContent = 'Leyendo transcripción…';
      let nextPreview = null;
      const onInput = event => {
        if (!bar.contains(event.target)) controller.abort(abortError('La búsqueda o el idioma ha cambiado.'));
      };
      const onKey = event => {
        if (event.key === 'Escape') { controller.abort(abortError('Lectura cancelada.')); event.preventDefault(); event.stopImmediatePropagation(); }
      };
      panel.addEventListener('input', onInput, true);
      panel.addEventListener('change', onInput, true);
      window.addEventListener('keydown', onKey, true);
      try {
        const result = await collect(task, info => {
          status.textContent = `${info.phase} · ${info.count.toLocaleString()} segmentos recogidos…`;
          if (info.progress === null) meter.removeAttribute('value'); else meter.value = info.progress;
        });
        check(task, false);
        const text = format(result.segments, withTimes);
        if (result.warnings.length || action === 'preview') {
          status.textContent = `${result.warnings.length ? 'Revisar: posible texto incompleto. ' : ''}${stats(result.segments, format(result.segments, false))}`;
          nextPreview = {result, withTimes};
        } else if (action === 'download') {
          download(text, withTimes);
          status.textContent = `TXT preparado · ${stats(result.segments, format(result.segments, false))}`;
        } else {
          try {
            await clipboard(text, () => check(task, false));
            check(task, false);
            status.textContent = `Copiado · ${stats(result.segments, format(result.segments, false))}`;
          } catch (error) {
            if (error.name === 'AbortError') throw error;
            status.textContent = 'Texto recuperado; el portapapeles necesita tu intervención.';
            nextPreview = {result, withTimes, error: error.message};
          }
        }
      } catch (error) {
        status.textContent = error.name === 'AbortError' ? error.message : `Error: ${error.message}`;
      } finally {
        panel.removeEventListener('input', onInput, true);
        panel.removeEventListener('change', onInput, true);
        window.removeEventListener('keydown', onKey, true);
        busy(false);
        if (active === operation) active = null;
        if (nextPreview && sameContext(task) && !task.signal.aborted) preview(nextPreview.result, nextPreview.withTimes, nextPreview.error || '', sourceFocus);
      }
    }
    const controller = {bar, reset: () => { if (!active || active.task.panel !== panel) status.textContent = 'Copia el idioma mostrado en el panel.'; },
      dispose: () => { disposed = true; bar.remove(); if (active?.task.panel === panel) active.controller.abort(abortError('El panel se ha reconstruido.')); }};
    controllers.set(panel, controller);
  }

  const styleId = 'ytcopy-transcript-style';
  if (!document.getElementById(styleId)) {
    const style = element('style');
    style.id = styleId;
    style.textContent = `
      .${BAR}, .${DIALOG} { --ytcopy-bg:var(--yt-spec-base-background,#fff); --ytcopy-fg:var(--yt-spec-text-primary,#171717);
        --ytcopy-muted:var(--yt-spec-text-secondary,#606060); --ytcopy-line:var(--yt-spec-10-percent-layer,rgba(127,127,127,.22));
        --ytcopy-chip:var(--yt-spec-badge-chip-background,rgba(127,127,127,.12)); color:var(--ytcopy-fg);
        font:13px/1.45 Roboto,Arial,sans-serif; box-sizing:border-box; text-align:start; }
      html[dark] .${BAR}, html[dark] .${DIALOG} { --ytcopy-bg:var(--yt-spec-base-background,#181818);
        --ytcopy-fg:var(--yt-spec-text-primary,#f1f1f1); --ytcopy-muted:var(--yt-spec-text-secondary,#aaa); }
      .${BAR} { display:block; flex:0 0 auto; min-width:0; padding:10px 14px 12px; background:var(--ytcopy-bg); border-bottom:1px solid var(--ytcopy-line); }
      .ytcopy-label {display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:8px;font-weight:600;}
      .ytcopy-version {font-size:11px;color:var(--ytcopy-muted);font-weight:400;white-space:nowrap;}
      .ytcopy-actions {display:flex;flex-wrap:wrap;gap:6px;align-items:center;}
      .${BAR} button, .${DIALOG} button {appearance:none;box-sizing:border-box;min-height:34px;max-width:100%;padding:7px 11px;
        border:1px solid var(--ytcopy-line);border-radius:18px;background:var(--ytcopy-chip);color:var(--ytcopy-fg);
        font:500 12px/18px Roboto,Arial,sans-serif;cursor:pointer;white-space:normal;}
      .${BAR} button.ytcopy-primary, .${DIALOG} button.ytcopy-primary {background:var(--ytcopy-fg);color:var(--ytcopy-bg);border-color:transparent;}
      .${BAR} button:hover:not(:disabled), .${DIALOG} button:hover:not(:disabled) {filter:brightness(.90);}
      .${BAR} button:disabled, .${DIALOG} button:disabled {opacity:.5;cursor:progress;}
      .${BAR} button:focus-visible, .${DIALOG} button:focus-visible, .${DIALOG} textarea:focus-visible {outline:2px solid var(--ytcopy-fg);outline-offset:2px;}
      .${BAR} [hidden], .${DIALOG} [hidden] {display:none!important;}
      .ytcopy-status {margin-top:8px;color:var(--ytcopy-muted);font-size:12px;overflow-wrap:anywhere;white-space:pre-line;}
      .ytcopy-status:empty {display:none;}
      .ytcopy-progress {display:block;width:100%;height:4px;margin:10px 0 0;border:0;accent-color:var(--ytcopy-fg);}
      .${DIALOG} {width:min(720px,calc(100vw - 32px));max-height:calc(100dvh - 40px);max-width:none;padding:20px;margin:auto;
        border:1px solid var(--ytcopy-line);border-radius:16px;background:var(--ytcopy-bg);box-shadow:0 16px 64px #0005;overflow:auto;}
      .${DIALOG}::backdrop {background:rgba(0,0,0,.56);}
      .ytcopy-dialog-heading {display:flex;justify-content:space-between;align-items:center;gap:16px;margin-bottom:12px;}
      .ytcopy-dialog-heading h2 {font:600 19px/1.3 Roboto,Arial,sans-serif;margin:0;}
      .ytcopy-notice {padding:10px 12px;border:1px solid var(--ytcopy-line);border-radius:10px;white-space:pre-line;color:var(--ytcopy-muted);font-size:12px;}
      .ytcopy-notice[data-kind="warning"] {border-inline-start:4px solid #b87900;color:var(--ytcopy-fg);}
      .ytcopy-modes {margin:14px 0 8px;}
      .${DIALOG} button[aria-pressed="true"] {border-color:var(--ytcopy-fg);box-shadow:inset 0 0 0 1px var(--ytcopy-fg);}
      .ytcopy-count {font-size:12px;color:var(--ytcopy-muted);margin:0 0 8px;overflow-wrap:anywhere;}
      .ytcopy-preview-text {display:block;box-sizing:border-box;width:100%;height:clamp(140px,36dvh,360px);resize:vertical;
        padding:12px;margin:0 0 14px;border:1px solid var(--ytcopy-line);border-radius:10px;background:var(--ytcopy-bg);color:var(--ytcopy-fg);font:14px/1.6 Roboto,Arial,sans-serif;}
      @media(max-width:420px) { .${DIALOG} {padding:14px;width:calc(100vw - 20px);} .${BAR} {padding-inline:10px;} }
      @media(prefers-reduced-motion:reduce) { .${BAR} *, .${DIALOG} * {scroll-behavior:auto!important;} }
    `;
    (document.head || document.documentElement).append(style);
  }

  function mountAll() {
    for (const [panel, controller] of controllers) {
      if (!panel.isConnected || !panel.matches(PANEL)) { controller.dispose(); controllers.delete(panel); }
    }
    document.querySelectorAll(PANEL).forEach(mount);
  }
  function scheduleMount() {
    if (mountTimer !== null) return;
    mountTimer = setTimeout(() => { mountTimer = null; mountAll(); }, 100);
  }
  const pageObserver = new MutationObserver(records => {
    const needsMount = records.some(record => {
      if (record.type === 'attributes') return true;
      if ((record.target.nodeType === 1 ? record.target : record.target.parentElement)?.closest(OWN)) return false;
      return [...record.addedNodes, ...record.removedNodes].some(node => node.nodeType === 1 &&
        (node.matches(`${PANEL}, .${BAR}`) || node.querySelector(`${PANEL}, .${BAR}`)));
    });
    if (needsMount) scheduleMount();
  });
  pageObserver.observe(document.documentElement, {childList: true, subtree: true, attributes: true, attributeFilter: ['target-id', 'visibility']});
  function navigate() {
    navigationRevision++;
    active?.controller.abort(abortError('El vídeo ha cambiado.'));
    document.querySelector(`.${DIALOG}`)?.remove();
    for (const controller of controllers.values()) controller.reset();
  }
  document.addEventListener('yt-navigate-start', navigate);
  document.addEventListener('yt-navigate-finish', () => { scheduleMount(); for (const controller of controllers.values()) controller.reset(); });
  document.addEventListener('yt-page-data-updated', scheduleMount);
  window.addEventListener('popstate', navigate);
  window.addEventListener('pagehide', () => { active?.controller.abort(abortError('Se ha cerrado la página.')); });
  document.addEventListener('click', event => {
    if (!active || event.target.closest?.(OWN)) return;
    // Language choices may live in a popup outside the panel. Ordinary clicks on
    // transcript rows no longer cancel a long extraction.
    if (event.target.closest?.('[role="option"], [role="menuitemradio"], ytd-transcript-footer-renderer')) {
      active.controller.abort(abortError('Se ha seleccionado otro idioma u opción del panel.'));
    }
  }, true);
  mountAll();
})();
