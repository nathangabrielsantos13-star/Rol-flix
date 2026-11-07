// Na Vercel, cada envio para em 4,5 MB: as fotos encolhem aqui, e o álbum sobe um arquivo por vez.
(function () {
  var LIMIT = Number(document.currentScript.dataset.maxUpload);
  var COMPRESS_ABOVE = 1024 * 1024;
  var MAX_SIDE = 2000;

  function compress(file) {
    if (file.type.indexOf("image/") !== 0 || file.type === "image/gif" || file.size <= COMPRESS_ABOVE) {
      return Promise.resolve(file);
    }
    return createImageBitmap(file).then(function (bitmap) {
      var scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
      var canvas = document.createElement("canvas");
      canvas.width = Math.round(bitmap.width * scale);
      canvas.height = Math.round(bitmap.height * scale);
      canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
      return new Promise(function (resolve) { canvas.toBlob(resolve, "image/jpeg", 0.82); });
    }).then(function (blob) {
      if (!blob || blob.size >= file.size) return file;
      return new File([blob], file.name.replace(/\.[^.]+$/, "") + ".jpg", { type: "image/jpeg" });
    }).catch(function () {
      return file; // Formato que o navegador não abre: o servidor dá a resposta certa.
    });
  }

  function tooLarge(file) {
    return file.name + ": passa do limite de " + Math.round(LIMIT / (1024 * 1024)) + " MB por arquivo.";
  }

  // Troca os arquivos escolhidos pelas versões menores, mantendo o formulário normal.
  function prepare(input) {
    return Promise.all(Array.prototype.map.call(input.files, compress)).then(function (files) {
      var list = new DataTransfer();
      files.forEach(function (file) { list.items.add(file); });
      input.files = list.files;
      var big = files.filter(function (file) { return file.size > LIMIT; })[0];
      input.setCustomValidity(big ? tooLarge(big) : "");
      if (big) input.reportValidity();
    });
  }

  window.roleflixCompress = compress;
  window.roleflixPrepare = prepare;

  document.addEventListener("change", function (event) {
    var input = event.target;
    if (!input.matches || !input.matches("input[type=file]") || !input.files.length) return;
    if (input.matches("[data-avatar-input], [data-cover-upload], [data-one-by-one] input, [name=music_file]")) return;
    var buttons = input.form ? input.form.querySelectorAll("button[type=submit]") : [];
    buttons.forEach(function (button) { button.disabled = true; });
    prepare(input).finally(function () {
      buttons.forEach(function (button) { button.disabled = false; });
    });
  });

  function send(form, file) {
    var body = new FormData();
    body.append("csrfmiddlewaretoken", form.elements.csrfmiddlewaretoken.value);
    body.append("caption", form.elements.caption.value);
    body.append("files", file);
    return fetch(form.action, { method: "POST", body: body, headers: { "X-Requested-With": "fetch" } }).then(function (response) {
      if (response.status === 413) throw new Error(tooLarge(file));
      return response.json().then(function (result) {
        if (!response.ok) throw new Error(result.error);
      });
    });
  }

  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (!form.matches("[data-one-by-one]")) return;
    event.preventDefault();
    var files = Array.prototype.slice.call(form.elements.files.files);
    var status = form.querySelector("[data-upload-status]");
    var button = form.querySelector("button[type=submit]");
    var errors = [];
    var sent = 0;
    button.disabled = true;
    status.hidden = false;
    files.reduce(function (previous, file, index) {
      return previous.then(function () {
        status.textContent = "Enviando " + (index + 1) + " de " + files.length + "…";
        return compress(file);
      }).then(function (ready) {
        if (ready.size > LIMIT) throw new Error(tooLarge(ready));
        return send(form, ready);
      }).then(function () {
        sent += 1;
      }).catch(function (error) {
        errors.push(error.message || (file.name + ": não foi possível enviar."));
      });
    }, Promise.resolve()).then(function () {
      if (!errors.length) { location.reload(); return; }
      status.textContent = sent + " de " + files.length + " enviados. " + errors.join(" ");
      button.disabled = false;
    });
  });
})();
