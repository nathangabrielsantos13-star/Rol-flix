// Trailer: acompanha a geração, abre o player, compartilha e organiza as fotos no formulário.
(function () {
  var progress = document.querySelector("[data-trailer-status]");
  if (progress) {
    var bar = progress.querySelector("progress");
    var percent = progress.querySelector("[data-trailer-percent]");
    var text = progress.querySelector("[data-trailer-text]");
    var check = function () {
      fetch(progress.dataset.trailerStatus).then(function (response) {
        return response.json();
      }).then(function (data) {
        bar.value = data.progress;
        percent.textContent = data.progress + "%";
        if (data.status === "ready" || data.status === "failed") {
          // Só um link, sem recarregar: a pessoa pode estar enviando fotos nesta página.
          text.textContent = data.status === "ready" ? "Trailer pronto!" : "A geração não terminou.";
          percent.hidden = bar.hidden = true;
          var done = progress.querySelector("[data-trailer-done]");
          if (data.status === "failed") done.textContent = "Ver detalhes";
          done.hidden = false;
          return;
        }
        setTimeout(check, 2500);
      }).catch(function () {
        setTimeout(check, 6000);
      });
    };
    setTimeout(check, 2500);
  }

  var player = document.getElementById("trailer-player");
  if (player) {
    var video = player.querySelector("video");
    document.querySelector("[data-trailer-open]").addEventListener("click", function () {
      player.showModal();
      video.play().catch(function () {});
    });
    player.addEventListener("close", function () { video.pause(); });
    player.addEventListener("click", function (event) {
      if (event.target === player) player.close();
    });

    // Envia o arquivo, não um link: o álbum é privado e o link só abre para quem tem acesso.
    var share = document.querySelector("[data-trailer-share]");
    var sample = typeof File === "function" ? new File([""], "t.mp4", { type: "video/mp4" }) : null;
    if (share && navigator.canShare && sample && navigator.canShare({ files: [sample] })) {
      share.hidden = false;
      share.addEventListener("click", function () {
        var label = share.textContent;
        share.disabled = true;
        share.textContent = "Preparando…";
        fetch(video.currentSrc || video.src).then(function (response) {
          return response.blob();
        }).then(function (blob) {
          return navigator.share({ files: [new File([blob], video.dataset.shareName, { type: "video/mp4" })] });
        }).catch(function () {}).then(function () {
          share.disabled = false;
          share.textContent = label;
        });
      });
    }
  }

  var list = document.querySelector("[data-trailer-items]");
  if (list) {
    list.addEventListener("click", function (event) {
      var button = event.target.closest("[data-move]");
      if (!button) return;
      var item = button.closest("li");
      var target = button.dataset.move === "-1" ? item.previousElementSibling : item.nextElementSibling;
      if (!target) return;
      list.insertBefore(item, button.dataset.move === "-1" ? target : target.nextElementSibling);
      button.focus();
    });
  }

  var uploadBox = document.querySelector("[data-music-file]");
  if (uploadBox) {
    var upload = document.querySelector("[data-music-upload]");
    document.querySelectorAll('input[name="music"]').forEach(function (radio) {
      radio.addEventListener("change", function () { uploadBox.hidden = !upload.checked; });
    });
  }
})();
