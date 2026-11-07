// Comportamento da barra superior: busca que se abre no ícone e menu do perfil.
(function () {
  var search = document.querySelector(".nav-search");
  var menu = document.querySelector(".profile-menu");

  if (search) {
    var input = search.querySelector("input");
    search.addEventListener("submit", function (event) {
      if (input.value.trim()) return;
      event.preventDefault();
      search.classList.add("open");
      input.focus();
    });
    input.addEventListener("blur", function () {
      if (!input.value.trim()) search.classList.remove("open");
    });
  }

  if (menu) {
    document.addEventListener("click", function (event) {
      if (!menu.contains(event.target)) menu.open = false;
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && menu.open) {
        menu.open = false;
        menu.querySelector("summary").focus();
      }
    });
    // Instalar abre o tutorial por cima: o menu não precisa continuar aberto.
    menu.addEventListener("click", function (event) {
      if (event.target.closest("[data-install-open]")) menu.open = false;
    });
  }
})();
