/**
 * ScanScribe waveform-style audio player.
 * Usage: initScanscribeAudioPlayer(containerElement, audioSrc)
 * containerElement is filled with the player; audioSrc is the URL path (e.g. "/audio_storage/file.mp3").
 */
(function () {
  function formatTime(seconds) {
    if (!Number.isFinite(seconds) || seconds < 0) return '00:00';
    var m = Math.floor(seconds / 60);
    var s = Math.floor(seconds % 60);
    return (m < 10 ? '0' : '') + m + ':' + (s < 10 ? '0' : '') + s;
  }

  function drawWaveform(canvas, samples, playedPercent) {
    var dpr = window.devicePixelRatio || 1;
    var w = canvas.offsetWidth;
    var h = canvas.offsetHeight;
    if (w <= 0 || h <= 0) return;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    var ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);
    ctx.fillStyle = 'rgba(0,0,0,0.2)';
    ctx.fillRect(0, 0, w, h);
    var midY = h / 2;
    ctx.strokeStyle = 'rgba(255,255,255,0.2)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, midY);
    ctx.lineTo(w, midY);
    ctx.stroke();
    if (!samples || samples.length < 2) return;
    var maxDeflect = midY - 6;
    var zoom = 4.6;
    var maxAmp = Math.max(0.01, Math.max.apply(null, samples.map(function (x) { return Math.abs(x); })));
    var playedX = playedPercent != null && playedPercent > 0 ? w * (playedPercent / 100) : 0;
    if (playedX > 0) {
      ctx.fillStyle = 'rgba(59, 130, 246, 0.2)';
      ctx.fillRect(0, 0, playedX, h);
    }
    ctx.fillStyle = 'rgba(255,255,255,0.12)';
    ctx.beginPath();
    ctx.moveTo(0, midY);
    for (var i = 0; i < w; i++) {
      var idx = Math.min(Math.floor((i / w) * samples.length), samples.length - 1);
      var amp = Math.min(maxDeflect, (samples[idx] / maxAmp) * maxDeflect * zoom);
      ctx.lineTo(i, midY - amp);
    }
    ctx.lineTo(w, midY);
    ctx.closePath();
    ctx.fill();
    ctx.beginPath();
    ctx.moveTo(0, midY);
    for (var j = 0; j < w; j++) {
      var idx2 = Math.min(Math.floor((j / w) * samples.length), samples.length - 1);
      var amp2 = Math.min(maxDeflect, (samples[idx2] / maxAmp) * maxDeflect * zoom);
      ctx.lineTo(j, midY + amp2);
    }
    ctx.lineTo(w, midY);
    ctx.closePath();
    ctx.fill();
  }

  function loadAndDrawWaveform(audioSrc, canvas, audioEl, root) {
    fetch(audioSrc)
      .then(function (r) { return r.arrayBuffer(); })
      .then(function (buf) {
        var ctx = new (window.AudioContext || window.webkitAudioContext)();
        return ctx.decodeAudioData(buf);
      })
      .then(function (buffer) {
        var ch = buffer.getChannelData(0);
        var step = Math.max(1, Math.floor(ch.length / 1500));
        var samples = [];
        for (var i = 0; i < ch.length; i += step) samples.push(ch[i]);
        root._waveformSamples = samples;
        function updatePlayed() {
          var pct = audioEl.duration ? (audioEl.currentTime / audioEl.duration) * 100 : 0;
          drawWaveform(canvas, samples, pct);
        }
        root._waveformUpdate = updatePlayed;
        updatePlayed();
      })
      .catch(function () {
        drawWaveform(canvas, null, null);
      });
  }

  window.initScanscribeAudioPlayer = function (container, audioSrc) {
    if (!container || !audioSrc) return;
    container.innerHTML = '';
    container.setAttribute('data-inited', '1');

    var root = document.createElement('div');
    root.className = 'sc-audio-player';

    var header = document.createElement('div');
    header.className = 'sc-audio-player__header';
    header.textContent = 'Audio';
    root.appendChild(header);

    var waveWrap = document.createElement('div');
    waveWrap.className = 'sc-audio-player__waveform';
    var canvas = document.createElement('canvas');
    waveWrap.appendChild(canvas);
    root.appendChild(waveWrap);

    var controls = document.createElement('div');
    controls.className = 'sc-audio-player__controls';

    var playBtn = document.createElement('button');
    playBtn.className = 'sc-audio-player__btn sc-audio-player__btn--play';
    playBtn.textContent = 'Play';
    var stopBtn = document.createElement('button');
    stopBtn.className = 'sc-audio-player__btn sc-audio-player__btn--stop';
    stopBtn.textContent = 'Stop';
    var muteBtn = document.createElement('button');
    muteBtn.className = 'sc-audio-player__btn sc-audio-player__btn--mute';
    muteBtn.textContent = 'Mute';

    var volLabel = document.createElement('span');
    volLabel.className = 'sc-audio-player__vol-label';
    volLabel.textContent = 'Vol';
    var volWrap = document.createElement('div');
    volWrap.className = 'sc-audio-player__vol-wrap';
    var volFill = document.createElement('div');
    volFill.className = 'sc-audio-player__vol-fill';
    var volSlider = document.createElement('input');
    volSlider.type = 'range';
    volSlider.className = 'sc-audio-player__vol';
    volSlider.min = '0';
    volSlider.max = '100';
    volSlider.value = '70';
    volWrap.appendChild(volFill);
    volWrap.appendChild(volSlider);

    var timeEl = document.createElement('span');
    timeEl.className = 'sc-audio-player__time';
    timeEl.textContent = '00:00 / 00:00';

    var openLink = document.createElement('a');
    openLink.className = 'sc-audio-player__open';
    openLink.href = audioSrc;
    openLink.target = '_blank';
    openLink.rel = 'noopener';
    openLink.textContent = 'Open audio';

    controls.appendChild(playBtn);
    controls.appendChild(stopBtn);
    controls.appendChild(muteBtn);
    controls.appendChild(volLabel);
    controls.appendChild(volWrap);
    controls.appendChild(timeEl);
    controls.appendChild(openLink);
    root.appendChild(controls);
    container.appendChild(root);

    var audio = new Audio(audioSrc);
    root._audio = audio;

    function setVolPercent() {
      var pct = parseInt(volSlider.value, 10);
      volFill.style.width = pct + '%';
      audio.volume = pct / 100;
    }
    setVolPercent();
    volSlider.addEventListener('input', setVolPercent);

    var rafId = null;
    function updateTime() {
      var cur = audio.currentTime;
      var dur = audio.duration;
      timeEl.textContent = formatTime(cur) + ' / ' + formatTime(dur);
      if (root._waveformUpdate) root._waveformUpdate();
    }
    function tick() {
      updateTime();
      rafId = audio.paused ? null : requestAnimationFrame(tick);
    }

    audio.addEventListener('loadedmetadata', function () {
      updateTime();
      loadAndDrawWaveform(audioSrc, canvas, audio, root);
    });
    audio.addEventListener('timeupdate', updateTime);
    audio.addEventListener('ended', function () {
      if (rafId != null) cancelAnimationFrame(rafId);
      rafId = null;
      playBtn.classList.remove('playing');
      stopBtn.disabled = true;
      updateTime();
    });

    playBtn.addEventListener('click', function () {
      if (audio.paused) {
        audio.play();
        playBtn.classList.add('playing');
        stopBtn.disabled = false;
        tick();
      }
    });
    stopBtn.addEventListener('click', function () {
      audio.pause();
      if (rafId != null) cancelAnimationFrame(rafId);
      rafId = null;
      audio.currentTime = 0;
      playBtn.classList.remove('playing');
      stopBtn.disabled = true;
      updateTime();
    });
    stopBtn.disabled = true;

    var muted = false;
    var prevVolume = 0.7;
    muteBtn.addEventListener('click', function () {
      muted = !muted;
      if (muted) {
        prevVolume = audio.volume;
        audio.volume = 0;
        volSlider.value = 0;
      } else {
        audio.volume = prevVolume;
        volSlider.value = Math.round(prevVolume * 100);
      }
      setVolPercent();
    });

    audio.addEventListener('error', function () {
      timeEl.textContent = '00:00 / 00:00';
      drawWaveform(canvas, null, null);
    });

    window.addEventListener('resize', function () {
      if (root._waveformSamples) drawWaveform(canvas, root._waveformSamples, audio.duration ? (audio.currentTime / audio.duration) * 100 : 0);
    });
  };
})();
