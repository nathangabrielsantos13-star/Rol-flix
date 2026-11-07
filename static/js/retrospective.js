// Montagem da retrospectiva: apresentação em tela cheia com abertura, fotos do ano e encerramento.
(function () {
  var SLIDE_MS = 3800;
  var FADE_MS = 900;     // igual à transição no CSS

  var year = Number(document.currentScript.dataset.year);
  var moments = JSON.parse(document.getElementById("retro-moments").textContent);
  var summary = JSON.parse(document.getElementById("retro-summary").textContent);
  var dialog = document.getElementById("montage");
  var stage = dialog.querySelector(".montage-stage");
  var bar = dialog.querySelector(".montage-progress span");
  var toggle = dialog.querySelector('[data-action="toggle"]');

  var slides = [{ eyebrow: "ROLÊFLIX APRESENTA", title: String(year), text: summary }]
    .concat(moments)
    .concat([{ eyebrow: "FIM DA TEMPORADA", title: "Que venha " + (year + 1), text: "Os próximos rolês ainda vão virar filme." }]);

  var index = 0;
  var timer = null;
  var playing = false;

  function element(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function titleSlide(slide) {
    var node = element("div", "montage-slide montage-title");
    node.appendChild(element("p", "eyebrow", slide.eyebrow));
    node.appendChild(element("h2", "", slide.title));
    node.appendChild(element("p", "", slide.text));
    return node;
  }

  function photoSlide(slide) {
    var node = element("div", "montage-slide montage-photo");
    var backdrop = element("img", "montage-backdrop");
    backdrop.src = slide.url;
    backdrop.alt = "";
    var photo = element("img", "montage-image");
    photo.src = slide.url;
    photo.alt = slide.title;
    var caption = element("div", "montage-caption");
    caption.appendChild(element("h2", "", slide.title));
    caption.appendChild(element("p", "", [slide.place, slide.date].filter(Boolean).join(" • ")));
    node.appendChild(backdrop);
    node.appendChild(photo);
    node.appendChild(caption);
    return node;
  }

  function preload(position) {
    var next = slides[position];
    if (next && next.url) new Image().src = next.url;
  }

  function show(position) {
    index = position;
    var slide = slides[index];
    var node = slide.url ? photoSlide(slide) : titleSlide(slide);
    var previous = stage.querySelectorAll(".montage-slide");
    stage.appendChild(node);
    // O quadro de espera faz o navegador aplicar a transição de entrada.
    requestAnimationFrame(function () {
      requestAnimationFrame(function () { node.classList.add("visible"); });
    });
    previous.forEach(function (old) {
      old.classList.remove("visible");
      setTimeout(function () { old.remove(); }, FADE_MS);
    });
    bar.style.width = ((index + 1) / slides.length) * 100 + "%";
    preload(index + 1);
  }

  function schedule() {
    clearTimeout(timer);
    if (!playing) return;
    timer = setTimeout(function () {
      if (index + 1 < slides.length) {
        show(index + 1);
        schedule();
      } else {
        setPlaying(false);
      }
    }, SLIDE_MS);
  }

  function setPlaying(value) {
    playing = value;
    toggle.textContent = value ? "❚❚" : "▶";
    toggle.setAttribute("aria-label", value ? "Pausar" : "Continuar");
    schedule();
  }

  function go(position) {
    show(Math.max(0, Math.min(slides.length - 1, position)));
    schedule();
  }

  function replayOrToggle() {
    if (!playing && index === slides.length - 1) show(0);
    setPlaying(!playing);
  }

  document.getElementById("montage-open").addEventListener("click", function () {
    stage.textContent = "";
    document.documentElement.classList.add("intro-open");
    dialog.showModal();
    show(0);
    setPlaying(true);
  });

  dialog.addEventListener("click", function (event) {
    var button = event.target.closest("[data-action]");
    if (!button) return;
    var action = button.dataset.action;
    if (action === "prev") go(index - 1);
    if (action === "next") go(index + 1);
    if (action === "toggle") replayOrToggle();
    if (action === "close") dialog.close();
  });

  dialog.addEventListener("keydown", function (event) {
    if (event.key === "ArrowLeft") go(index - 1);
    if (event.key === "ArrowRight") go(index + 1);
    if (event.key === " ") {
      event.preventDefault();
      replayOrToggle();
    }
  });

  dialog.addEventListener("close", function () {
    document.documentElement.classList.remove("intro-open");
    playing = false;
    clearTimeout(timer);
  });
})();
