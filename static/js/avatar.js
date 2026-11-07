// Salva assim que a foto é escolhida: sem isto, seria preciso achar um botão a mais.
(function () {
  var input = document.querySelector("[data-avatar-input]");
  if (!input) return;
  input.addEventListener("change", function () {
    if (!input.files.length) return;
    input.closest("form").querySelector(".avatar-edit-label").textContent = "Enviando…";
    input.form.submit();
  });
})();