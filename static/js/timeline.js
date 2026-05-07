// timeline.js — Línea de tiempo interactiva del partido
(function () {
  'use strict';

  window._timelineLoaded = true;
  console.log('[timeline.js] script cargado');

  const playerDiv = document.getElementById('player');
  if (!playerDiv) return;
  const MATCH_ID = playerDiv.dataset.matchId;
  if (!MATCH_ID) return;

  const API_URL = '/api/matches/' + MATCH_ID + '/plays/';

  const ROW_H   = 22;
  const ROW_GAP = 3;

  const PALETTE = [
    '#3b82f6','#10b981','#f59e0b','#ef4444','#8b5cf6',
    '#06b6d4','#f97316','#84cc16','#ec4899','#6366f1',
    '#14b8a6','#fb923c','#a855f7','#f43f5e','#22d3ee',
  ];

  function hashColor(str) {
    let h = 5381;
    for (let i = 0; i < str.length; i++) h = ((h << 5) + h) + str.charCodeAt(i);
    return PALETTE[Math.abs(h) % PALETTE.length];
  }

  function fmtTime(secs) {
    const s  = Math.floor(secs);
    const m  = Math.floor(s / 60);
    const ss = s % 60;
    return ss > 0 ? m + 'm' + ss + 's' : m + 'm';
  }

  // ── Seek + play ──────────────────────────────────────────────────────────────
  // Usa window.player directamente (igual que startCurrentVideo en player.js).
  // Si el player aún no está listo, encola el seek y lo ejecuta cuando esté.
  var _pendingSecs = null;

  function seekAndPlay(secs) {
    var p = window.player;
    if (!p || typeof p.seekTo !== 'function') {
      _pendingSecs = secs;
      console.log('[timeline.js] player no listo, seek encolado a:', secs);
      return;
    }
    _pendingSecs = null;
    p.seekTo(Number(secs), true);
    p.playVideo();
  }

  // player.js dispara 'yt-player-ready' en onPlayerReady.
  // Si había un seek encolado, lo ejecutamos ahora.
  document.addEventListener('yt-player-ready', function () {
    console.log('[timeline.js] yt-player-ready recibido, player listo');
    if (_pendingSecs !== null) {
      var secs = _pendingSecs;
      _pendingSecs = null;
      setTimeout(function () { seekAndPlay(secs); }, 100);
    }
  });

  async function loadTimeline() {
    const statusEl = document.getElementById('timeline-status');
    const qp = new URLSearchParams(window.location.search);
    qp.set('timeline', '1');
    try {
      const res = await fetch(API_URL + '?' + qp.toString(), {
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
      });
      if (!res.ok) throw new Error('HTTP ' + res.status);
      const plays = await res.json();
      if (!plays.length) {
        if (statusEl) statusEl.textContent = 'Sin jugadas para mostrar';
        return;
      }
      renderTimeline(plays);
      if (statusEl) statusEl.textContent = plays.length + ' jugadas';
    } catch (e) {
      console.error('[timeline.js] error:', e);
      if (statusEl) statusEl.textContent = 'Error al cargar la línea de tiempo';
    }
  }

  function renderTimeline(plays) {
    const totalDuration = plays.reduce(function (mx, p) { return Math.max(mx, parseFloat(p.fin) || 0); }, 0);
    if (!totalDuration) return;

    // Agrupar por jugada + equipo
    const groups = new Map();
    plays.forEach(function (p) {
      const key = (p.jugada || '') + '||' + (p.equipo || '');
      if (!groups.has(key)) groups.set(key, { jugada: p.jugada || '—', equipo: p.equipo || '', plays: [] });
      groups.get(key).plays.push(p);
    });

    const labelsEl = document.getElementById('timeline-labels');
    const rowsEl   = document.getElementById('timeline-rows');
    const rulerEl  = document.getElementById('timeline-ruler');
    const cursorEl = document.getElementById('timeline-cursor');
    const innerEl  = document.getElementById('timeline-inner');
    if (!labelsEl || !rowsEl || !rulerEl || !innerEl) return;

    // ── Regla de tiempo ──
    const isDark = document.documentElement.classList.contains('dark');
    const tickColor   = isDark ? '#9ca3af' : '#6b7280';
    const borderColor = isDark ? '#374151' : '#d1d5db';
    rulerEl.style.borderBottomColor = borderColor;

    let stepSecs = 120;
    if (totalDuration <= 600)  stepSecs = 60;
    if (totalDuration <= 300)  stepSecs = 30;
    if (totalDuration > 5400)  stepSecs = 600;

    let rulerHTML = '';
    for (let t = 0; t <= totalDuration; t += stepSecs) {
      const pct = (t / totalDuration) * 100;
      rulerHTML += '<span style="position:absolute;left:' + pct + '%;transform:translateX(-50%);font-size:10px;color:' + tickColor + ';top:3px;white-space:nowrap;">' + fmtTime(t) + '</span>';
    }
    rulerEl.innerHTML = rulerHTML;

    // ── Filas y etiquetas ──
    let labelsHTML = '';
    let rowsHTML   = '';
    const bgRow   = isDark ? '#1f2937' : '#f9fafb';
    const textC   = isDark ? '#d1d5db' : '#374151';
    const badgeBg = isDark ? '#374151' : '#e5e7eb';
    const badgeC  = isDark ? '#9ca3af' : '#4b5563';

    groups.forEach(function (g) {
      const color = hashColor(g.jugada);
      const label = g.equipo ? g.jugada + ' · ' + g.equipo : g.jugada;

      labelsHTML += '<div style="height:' + ROW_H + 'px;margin-bottom:' + ROW_GAP + 'px;display:flex;align-items:center;justify-content:flex-end;padding-right:8px;gap:4px;">'
        + '<span style="font-size:11px;color:' + textC + ';white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:170px;" title="' + label + '">' + label + '</span>'
        + '<span style="background:' + badgeBg + ';border-radius:9999px;font-size:10px;padding:1px 5px;color:' + badgeC + ';flex-shrink:0;">' + g.plays.length + '</span>'
        + '</div>';

      let barsHTML = '';
      g.plays.forEach(function (p) {
        const inicio   = parseFloat(p.inicio) || 0;
        const fin      = parseFloat(p.fin)    || 0;
        const leftPct  = (inicio / totalDuration) * 100;
        const wPct     = Math.max(0.25, ((fin - inicio) / totalDuration) * 100);
        barsHTML += '<div'
          + ' class="tl-bar"'
          + ' data-start="' + inicio + '"'
          + ' data-end="'   + fin    + '"'
          + ' title="' + label + ' [' + fmtTime(inicio) + ' – ' + fmtTime(fin) + ']"'
          + ' style="position:absolute;left:' + leftPct + '%;width:' + wPct + '%;height:' + ROW_H + 'px;background:' + color + ';border-radius:2px;cursor:pointer;opacity:0.82;box-sizing:border-box;"'
          + '></div>';
      });

      rowsHTML += '<div style="position:relative;height:' + ROW_H + 'px;margin-bottom:' + ROW_GAP + 'px;background:' + bgRow + ';border-radius:2px;">' + barsHTML + '</div>';
    });

    labelsEl.innerHTML = labelsHTML;
    rowsEl.innerHTML   = rowsHTML;

    if (cursorEl) cursorEl.style.display = 'block';

    // ── Helpers ──
    function pctFromMouseEvent(e, el) {
      const rect = el.getBoundingClientRect();
      return Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
    }
    function seekToPercent(pct) {
      seekAndPlay(pct * totalDuration);
      if (cursorEl) cursorEl.style.left = (pct * 100) + '%';
    }

    // ── Click en barra → seek al inicio ──
    rowsEl.querySelectorAll('.tl-bar').forEach(function (bar) {
      bar.addEventListener('mouseenter', function () { this.style.opacity = '1'; });
      bar.addEventListener('mouseleave', function () { this.style.opacity = '0.82'; });
      bar.addEventListener('click', function (e) {
        e.stopPropagation();
        const secs = parseFloat(this.dataset.start);
        seekAndPlay(secs);
        if (cursorEl) cursorEl.style.left = ((secs / totalDuration) * 100) + '%';
      });
    });

    // ── Click en zona vacía de filas → seek proporcional ──
    rowsEl.addEventListener('click', function (e) {
      if (e.target.classList.contains('tl-bar')) return;
      seekToPercent(pctFromMouseEvent(e, innerEl));
    });

    // ── Click en regla → seek ──
    rulerEl.style.cursor = 'pointer';
    rulerEl.addEventListener('click', function (e) {
      seekToPercent(pctFromMouseEvent(e, innerEl));
    });

    // ── Tooltip de hover ──
    const tooltipEl = document.createElement('div');
    tooltipEl.style.cssText = 'position:absolute;top:-22px;transform:translateX(-50%);background:#1f2937;color:#f9fafb;font-size:10px;padding:2px 6px;border-radius:4px;pointer-events:none;white-space:nowrap;display:none;z-index:20;';
    innerEl.appendChild(tooltipEl);
    function showTooltip(e) {
      const rect = innerEl.getBoundingClientRect();
      const pct  = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
      tooltipEl.textContent = fmtTime(pct * totalDuration);
      tooltipEl.style.left  = (pct * 100) + '%';
      tooltipEl.style.display = 'block';
    }
    [rowsEl, rulerEl].forEach(function (el) {
      el.addEventListener('mousemove', showTooltip);
      el.addEventListener('mouseleave', function () { tooltipEl.style.display = 'none'; });
    });

    // ── Cursor arrastrable ──
    if (!cursorEl) return;
    cursorEl.style.cursor     = 'ew-resize';
    cursorEl.style.touchAction = 'none';
    let dragging = false;

    cursorEl.addEventListener('mousedown', function (e) {
      e.preventDefault();
      dragging = true;
      document.body.style.userSelect = 'none';
    });
    document.addEventListener('mousemove', function (e) {
      if (!dragging) return;
      cursorEl.style.left = (pctFromMouseEvent(e, innerEl) * 100) + '%';
    });
    document.addEventListener('mouseup', function (e) {
      if (!dragging) return;
      dragging = false;
      document.body.style.userSelect = '';
      seekToPercent(pctFromMouseEvent(e, innerEl));
    });

    // Táctil
    cursorEl.addEventListener('touchstart', function () { dragging = true; }, { passive: true });
    document.addEventListener('touchmove', function (e) {
      if (!dragging) return;
      const t   = e.touches[0];
      const r   = innerEl.getBoundingClientRect();
      cursorEl.style.left = (Math.min(1, Math.max(0, (t.clientX - r.left) / r.width)) * 100) + '%';
    }, { passive: true });
    document.addEventListener('touchend', function (e) {
      if (!dragging) return;
      dragging = false;
      const t = e.changedTouches[0];
      const r = innerEl.getBoundingClientRect();
      seekToPercent(Math.min(1, Math.max(0, (t.clientX - r.left) / r.width)));
    });

    // ── Cursor que sigue el video ──
    setInterval(function () {
      if (dragging) return;
      var p = window.player;
      if (!p || typeof p.getCurrentTime !== 'function') return;
      try {
        const ct  = p.getCurrentTime();
        cursorEl.style.left = (Math.min(1, ct / totalDuration) * 100) + '%';
      } catch (_) {}
    }, 500);
  }

  // Iniciar cuando el DOM esté listo
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', loadTimeline);
  } else {
    loadTimeline();
  }
})();
