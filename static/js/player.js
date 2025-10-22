// 1. Carga la API de YouTube (sin cambios)
    var tag = document.createElement('script');
    tag.src = "https://www.youtube.com/iframe_api";
    var firstScriptTag = document.getElementsByTagName('script')[0];
    firstScriptTag.parentNode.insertBefore(tag, firstScriptTag);

    // 2. Variables globales (sin cambios)
    let player;
    let playlist = [];
    let currentPlayIndex = 0;
    let timeChecker;
    // Evitar que el navegador restaure la posición de scroll automáticamente al recargar/navegar
    try { if ('scrollRestoration' in history) { history.scrollRestoration = 'manual'; } } catch(_e) {}

    // 3. Funciones de la API de YouTube (onYouTubeIframeAPIReady, onPlayerReady, onStateChange, checkTime - sin cambios)
    function onYouTubeIframeAPIReady() {
    // Buscamos el div del reproductor
    const playerDiv = document.getElementById('player');
    // Leemos el ID del video desde su atributo data-video-id
    const videoId = playerDiv.dataset.videoId;

    player = new YT.Player('player', {
        height: '100%',
        width: '100%', 
        videoId: videoId, // Usamos la variable que acabamos de leer
        playerVars: {
            'playsinline': 1,
            'modestbranding': 1,
            'rel': 0,
        },
        events: {
            'onReady': onPlayerReady,
            'onStateChange': onPlayerStateChange
        }
    });
}

    function onPlayerReady(event) {
        const playBtnEl = document.getElementById('play-selection-btn');
        if (playBtnEl) playBtnEl.disabled = false;
    }

    function onPlayerStateChange(event) {
        if (event.data == YT.PlayerState.PLAYING) { checkTime(); } 
        else { clearInterval(timeChecker); }
    }

    function checkTime() {
        clearInterval(timeChecker);
        timeChecker = setInterval(() => {
            if (playlist.length > 0 && currentPlayIndex < playlist.length) {
                if (player.getCurrentTime() >= playlist[currentPlayIndex].end) {
                    playNextVideo();
                }
            } else {
                clearInterval(timeChecker);
            }
        }, 250);
    }
    
    // --- LÓGICA DE RESALTADO ---

    // Función para limpiar todos los resaltados
    function clearAllHighlights() {
        document.querySelectorAll('.is-playing').forEach(el => {
            el.classList.remove('is-playing');
        });
    }
    
    // Se activa al presionar "Reproducir Selección"
    const nowPlayingPanel = document.getElementById('now-playing-panel');
    const nowPlayingEvent = document.getElementById('now-playing-event');
    const nowPlayingDetails = document.getElementById('now-playing-details');

    function resetNowPlayingPanel() {
        if (nowPlayingPanel) nowPlayingPanel.classList.add('hidden');
        if (nowPlayingEvent) nowPlayingEvent.textContent = '---';
        if (nowPlayingDetails) nowPlayingDetails.textContent = 'Seleccioná jugadas y presioná play';
    }

    const playSelectionBtn = document.getElementById('play-selection-btn');
    if (playSelectionBtn) {
        playSelectionBtn.addEventListener('click', (ev) => {
            // Evitamos que el navegador haga cualquier scroll/focus implícito
            if (ev && typeof ev.preventDefault === 'function') ev.preventDefault();
            if (ev && typeof ev.stopPropagation === 'function') ev.stopPropagation();
            const playerDiv = document.getElementById('player');

            clearAllHighlights(); 
            resetNowPlayingPanel(); // Reseteamos el panel al iniciar

            // Soportar selección desde DataTables (.dt-play) y fallback (.play-checkbox)
            const selectedDT = Array.from(document.querySelectorAll('.dt-play:checked'));
            const selectedClassic = Array.from(document.querySelectorAll('.play-checkbox:checked'));
            const selectedPlays = [...selectedDT, ...selectedClassic];

            playlist = [];
            selectedPlays.forEach(checkbox => {
                let start = parseFloat(checkbox.dataset.start);
                let end = parseFloat(checkbox.dataset.end);
                let eventName = '';
                let details = '';
                // Eliminamos el vínculo visual con filas de la tabla
                let elementId = '';

                if (checkbox.classList.contains('dt-play')) {
                    // DataTables: datos vienen en data-*
                    eventName = checkbox.dataset.event || '';
                    details = checkbox.dataset.equipo || '';
                    // No asociamos fila para evitar resaltados o scroll
                } else {
                    // Lista clásica original
                    const label = checkbox.nextElementSibling;
                    if (label) {
                        const e = label.querySelector('.font-semibold');
                        const d = label.querySelector('.text-xs');
                        eventName = e ? e.textContent : '';
                        details = d ? d.textContent : '';
                    }
                    // Tampoco asociamos contenedor
                }

                if (!isNaN(start) && !isNaN(end)) {
                    playlist.push({
                        elementId,
                        start,
                        end,
                        event: eventName,
                        details: details,
                    });
                }
            });

            if (playlist.length > 0) {
                currentPlayIndex = 0;
                startCurrentVideo();
                // No realizar ningún scroll automático
            }
        });
    }
    
    function startCurrentVideo() {
        clearAllHighlights();
        const currentPlay = playlist[currentPlayIndex];
        // Resaltado en tabla desactivado intencionalmente
        
        // CAMBIO 2: Actualizamos el panel con la información de la jugada activa
        if (nowPlayingEvent) nowPlayingEvent.textContent = currentPlay.event;
        if (nowPlayingDetails) nowPlayingDetails.textContent = currentPlay.details;
        if (nowPlayingPanel) nowPlayingPanel.classList.remove('hidden'); // Lo hacemos visible

        // No realizar ningún scroll automático al cambiar de jugada

        player.seekTo(currentPlay.start, true);
        player.playVideo();
    }

    function playNextVideo() {
        clearInterval(timeChecker);
        currentPlayIndex++;
        
        if (currentPlayIndex < playlist.length) {
            startCurrentVideo();
        } else {
            player.pauseVideo();
            clearAllHighlights();
            // CAMBIO 3: Reseteamos el panel al terminar la playlist
            resetNowPlayingPanel();
        }
    };
    // =============================================================== //
    //           ⌨️  NUEVA SECCIÓN: Atajos de Teclado ⌨️                //
    // =============================================================== //
    window.addEventListener('keydown', function(event) {
        // Nos aseguramos de que el reproductor exista y no estemos escribiendo en un input
        if (!player || document.activeElement.tagName === 'INPUT' || document.activeElement.tagName === 'SELECT') {
            return;
        }

        switch (event.code) {
            case 'Space':
                // Prevenimos el comportamiento por defecto (scroll de la página)
                event.preventDefault(); 
                
                // Chequeamos el estado del video y lo alternamos
                const playerState = player.getPlayerState();
                if (playerState === YT.PlayerState.PLAYING) {
                    player.pauseVideo();
                } else {
                    player.playVideo();
                }
                break;

            case 'ArrowDown':
            case 'ArrowUp':
            case 'PageDown':
            case 'PageUp':
            case 'Home':
            case 'End':
                // Evitar que estas teclas muevan la página mientras estamos en el reproductor
                event.preventDefault();
                break;

            case 'ArrowRight':
                // Adelantamos 5 segundos
                const currentTimeFwd = player.getCurrentTime();
                player.seekTo(currentTimeFwd + 5, true);
                break;

            case 'ArrowLeft':
                // Retrocedemos 5 segundos
                const currentTimeBack = player.getCurrentTime();
                player.seekTo(currentTimeBack - 5, true);
                break;
        }
    });
    // =============================================================== //
    //           ✅ MEJORA : Seleccionar / Deseleccionar Todo ✅      //
    // =============================================================== //
    document.addEventListener('DOMContentLoaded', (event) => {
        const selectAllCheckbox = document.getElementById('select-all-checkbox');
        const playCheckboxes = document.querySelectorAll('.play-checkbox');

        // Nos aseguramos de que el checkbox exista antes de agregarle el evento
        if (selectAllCheckbox) {
            selectAllCheckbox.addEventListener('change', function() {
                // Hacemos que todos los checkboxes de jugadas imiten al checkbox maestro
                playCheckboxes.forEach(checkbox => {
                    checkbox.checked = this.checked;
                });
            });
        }
    });