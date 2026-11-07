// Registra o service worker e conduz a instalação: primeiro o tutorial, depois o instalador.
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js");
}

(function () {
  var openButtons = document.querySelectorAll("[data-install-open]");
  var guide = document.getElementById("install-guide");
  var installButton = guide.querySelector("[data-install]");
  var installPrompt = null;

  var installed = matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
  if (installed) return;

  function detectPlatform() {
    var agent = navigator.userAgent;
    if (/iphone|ipad|ipod/i.test(agent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1)) return "ios";
    if (/android/i.test(agent)) return "android";
    return "desktop";
  }

  var device = detectPlatform();
  var selected = device;

  function note(name, visible) {
    guide.querySelector('[data-note="' + name + '"]').hidden = !visible;
  }

  function refresh() {
    guide.querySelectorAll("[data-tab]").forEach(function (tab) {
      var active = tab.dataset.tab === selected;
      tab.classList.toggle("active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
    });
    guide.querySelectorAll("[data-steps]").forEach(function (steps) {
      steps.hidden = steps.dataset.steps !== selected;
    });
    // O instalador só existe para o aparelho que está aberto, e nunca no iPhone.
    installButton.hidden = !(installPrompt && selected === device);
    note("insecure", !window.isSecureContext);
  }

  openButtons.forEach(function (button) {
    button.hidden = false;
    button.addEventListener("click", function () {
      selected = device;
      note("done", false);
      refresh();
      guide.showModal();
    });
  });

  guide.addEventListener("click", function (event) {
    var tab = event.target.closest("[data-tab]");
    if (tab) {
      selected = tab.dataset.tab;
      refresh();
    } else if (event.target.closest("[data-close]") || event.target === guide) {
      guide.close();
    }
  });

  window.addEventListener("beforeinstallprompt", function (event) {
    event.preventDefault();
    installPrompt = event;
    refresh();
  });

  installButton.addEventListener("click", function () {
    installPrompt.prompt();
    installPrompt.userChoice.then(function (choice) {
      if (choice.outcome === "accepted") note("done", true);
    });
    installPrompt = null;
    refresh();
  });

  window.addEventListener("appinstalled", function () {
    openButtons.forEach(function (button) { button.hidden = true; });
    installPrompt = null;
    note("done", true);
    refresh();
  });
})();
