// Ingresso do Rolê: prévia ao vivo, compartilhamento e a opção no formulário do álbum.
(function () {
  var preview = document.querySelector("[data-ticket-preview]");
  var form = document.querySelector("[data-ticket-form]");
  if (preview && form) {
    var customColor = form.querySelector("[data-custom-color]");
    var accent = form.querySelector("[data-accent]");
    var timer = null;
    var refresh = function () {
      accent.hidden = !customColor.checked;
      var picked = form.querySelector('input[name="style"]:checked');
      var query = new URLSearchParams({ style: picked ? picked.value : "", tagline: form.elements.tagline.value });
      if (customColor.checked) query.set("accent", accent.value);
      preview.src = preview.dataset.url + "?" + query.toString();
    };
    form.addEventListener("input", function () {
      clearTimeout(timer);
      timer = setTimeout(refresh, 300);
    });
    form.addEventListener("submit", function () {
      if (!customColor.checked) accent.disabled = true;
    });
  }

  // Envia a imagem em si, pois o link do álbum só abre para quem tem acesso.
  var sample = typeof File === "function" ? new File([""], "i.png", { type: "image/png" }) : null;
  if (navigator.canShare && sample && navigator.canShare({ files: [sample] })) {
    document.querySelectorAll("[data-ticket-share]").forEach(function (button) {
      button.hidden = false;
      button.addEventListener("click", function () {
        fetch(button.dataset.src).then(function (response) {
          return response.blob();
        }).then(function (blob) {
          return navigator.share({ files: [new File([blob], button.dataset.name, { type: "image/png" })] });
        }).catch(function () {});
      });
    });
  }

  // Formulário do álbum: a opção de ingresso aparece só quando a data é futura.
  var date = document.getElementById("id_event_date");
  var makeTicket = document.getElementById("id_make_ticket");
  if (date && makeTicket) {
    var row = makeTicket.closest("p");
    var today = new Date();
    var limit = today.getFullYear() + "-" + String(today.getMonth() + 1).padStart(2, "0") + "-" + String(today.getDate()).padStart(2, "0");
    var update = function () {
      var future = date.value > limit;
      row.hidden = !future;
      if (!future) makeTicket.checked = false;
    };
    date.addEventListener("input", update);
    update();
  }
})();
