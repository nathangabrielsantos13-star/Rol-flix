// Abertura do Rolêflix: aparece uma vez por sessão.
// Os navegadores só liberam som depois de um toque, por isso ela começa com "Toque para entrar".
// Com "reduzir movimento" ativo, o CSS troca a animação por um fade simples.
(function () {
  var STORAGE_KEY = "roleflix-intro-vista";
  var HIT = 0.6;           // segundos até o impacto, em sincronia com as letras no CSS
  var LEAVE_AT = 2300;     // ms até começar a saída
  var DONE_AT = 2900;      // ms até remover a abertura

  function alreadySeen() {
    try { return sessionStorage.getItem(STORAGE_KEY) === "1"; } catch (e) { return false; }
  }
  function markSeen() {
    try { sessionStorage.setItem(STORAGE_KEY, "1"); } catch (e) {}
  }

  if (alreadySeen()) return;

  // Assinatura sonora original, sintetizada no navegador: sopro de projetor,
  // impacto grave e um acorde de metais que abre e se dissolve.
  function playSting(ctx) {
    var start = ctx.currentTime + 0.02;
    var hit = start + HIT;
    var end = hit + 1.8;

    var master = ctx.createDynamicsCompressor();
    master.connect(ctx.destination);

    // Sopro crescente até o impacto.
    var length = Math.floor(ctx.sampleRate * HIT);
    var buffer = ctx.createBuffer(1, length, ctx.sampleRate);
    var samples = buffer.getChannelData(0);
    for (var i = 0; i < length; i++) samples[i] = Math.random() * 2 - 1;
    var noise = ctx.createBufferSource();
    noise.buffer = buffer;
    var band = ctx.createBiquadFilter();
    band.type = "bandpass";
    band.frequency.setValueAtTime(400, start);
    band.frequency.exponentialRampToValueAtTime(3200, hit);
    var noiseGain = ctx.createGain();
    noiseGain.gain.setValueAtTime(0.0001, start);
    noiseGain.gain.exponentialRampToValueAtTime(0.22, hit);
    noiseGain.gain.linearRampToValueAtTime(0, hit + 0.02);
    noise.connect(band).connect(noiseGain).connect(master);
    noise.start(start);

    // Impacto grave.
    var boom = ctx.createOscillator();
    boom.frequency.setValueAtTime(120, hit);
    boom.frequency.exponentialRampToValueAtTime(38, hit + 0.35);
    var boomGain = ctx.createGain();
    boomGain.gain.setValueAtTime(0.0001, start);
    boomGain.gain.setValueAtTime(0.9, hit);
    boomGain.gain.exponentialRampToValueAtTime(0.001, hit + 1.2);
    boom.connect(boomGain).connect(master);
    boom.start(hit);
    boom.stop(hit + 1.3);

    // Acorde aberto em ré, com filtro que abre depois do impacto.
    var filter = ctx.createBiquadFilter();
    filter.type = "lowpass";
    filter.frequency.setValueAtTime(250, hit);
    filter.frequency.exponentialRampToValueAtTime(1800, hit + 0.25);
    filter.frequency.exponentialRampToValueAtTime(300, end);
    var chordGain = ctx.createGain();
    chordGain.gain.setValueAtTime(0.0001, start);
    chordGain.gain.setValueAtTime(0.0001, hit);
    chordGain.gain.exponentialRampToValueAtTime(0.1, hit + 0.04);
    chordGain.gain.exponentialRampToValueAtTime(0.001, end);
    filter.connect(chordGain).connect(master);
    [73.42, 110, 164.81, 220, 277.18].forEach(function (freq) {
      [-6, 6].forEach(function (detune) {
        var osc = ctx.createOscillator();
        osc.type = "sawtooth";
        osc.frequency.value = freq;
        osc.detune.value = detune;
        osc.connect(filter);
        osc.start(hit);
        osc.stop(end);
      });
    });
    return end;
  }

  function letters(word, offset, cls) {
    return word.split("").map(function (letter, i) {
      return '<span class="' + cls + '" style="--i:' + (offset + i) + '">' + letter + "</span>";
    }).join("");
  }

  var intro = document.createElement("div");
  intro.className = "intro";
  intro.innerHTML =
    '<div class="intro-flash"></div><div class="intro-line"></div>' +
    '<div class="intro-logo" role="img" aria-label="Rolêflix">' + letters("ROLÊ", 0, "") + letters("FLIX", 4, "red") + "</div>" +
    '<button class="intro-start" type="button">Toque para entrar</button>' +
    '<button class="intro-skip" type="button">Pular</button>';
  document.documentElement.classList.add("intro-open");
  document.body.appendChild(intro);

  var startButton = intro.querySelector(".intro-start");
  var skipButton = intro.querySelector(".intro-skip");
  var started = false;
  startButton.focus();

  function finish() {
    markSeen();
    document.removeEventListener("keydown", onKey);
    document.documentElement.classList.remove("intro-open");
    intro.remove();
  }

  function start() {
    if (started) return;
    started = true;
    markSeen();
    try {
      var AudioCtx = window.AudioContext || window.webkitAudioContext;
      var ctx = new AudioCtx();
      playSting(ctx);
      setTimeout(function () { ctx.close(); }, DONE_AT + 500);
    } catch (e) {
      // Sem som, a abertura continua normalmente.
    }
    intro.classList.add("playing");
    setTimeout(function () { intro.classList.add("leaving"); }, LEAVE_AT);
    setTimeout(finish, DONE_AT);
  }

  function onKey(event) {
    if (event.key === "Escape") finish();
  }

  intro.addEventListener("click", function (event) {
    if (event.target === skipButton) finish(); else start();
  });
  document.addEventListener("keydown", onKey);
})();
