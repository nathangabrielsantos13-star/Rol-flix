// Página inicial: setas das fileiras e prévia do mapa, desenhada com os mesmos pontos do globo.
(function () {
  document.querySelectorAll("[data-row]").forEach(function (row) {
    var frame = document.createElement("div");
    frame.className = "row-frame";
    row.parentNode.insertBefore(frame, row);
    frame.appendChild(row);
    var buttons = [-1, 1].map(function (direction) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "row-arrow " + (direction < 0 ? "previous" : "next");
      button.textContent = direction < 0 ? "‹" : "›";
      button.setAttribute("aria-label", direction < 0 ? "Ver anteriores" : "Ver próximos");
      button.addEventListener("click", function () {
        row.scrollBy({ left: direction * row.clientWidth * 0.85, behavior: "smooth" });
      });
      frame.appendChild(button);
      return button;
    });
    var update = function () {
      buttons[0].hidden = row.scrollLeft < 8;
      buttons[1].hidden = row.scrollLeft + row.clientWidth > row.scrollWidth - 8;
    };
    row.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
    update();
  });

  var canvas = document.getElementById("home-map");
  var pinsData = document.getElementById("home-map-pins");
  if (!canvas || !pinsData || !window.ROLEFLIX_GLOBE_DOTS) return;
  var pins = JSON.parse(pinsData.textContent);
  var draw = function () {
    var ratio = window.devicePixelRatio || 1;
    var width = canvas.clientWidth;
    var height = canvas.clientHeight;
    canvas.width = width * ratio;
    canvas.height = height * ratio;
    var context = canvas.getContext("2d");
    context.scale(ratio, ratio);
    // Centraliza nos lugares da pessoa: ao lado do texto no computador, acima dele no celular.
    var narrow = width < 600;
    var middle = function (key) {
      var values = pins.map(function (pin) { return pin[key]; });
      return (Math.min.apply(null, values) + Math.max.apply(null, values)) / 2;
    };
    var centerLon = middle("lon");
    var centerLat = middle("lat");
    var scale = Math.max(width / 300, height / 130);
    var x = function (lon) { return width * (narrow ? 0.5 : 0.72) + (lon - centerLon) * scale; };
    var y = function (lat) { return height * (narrow ? 0.24 : 0.5) + (centerLat - lat) * scale; };
    var dots = window.ROLEFLIX_GLOBE_DOTS;
    context.fillStyle = "#3b3b3b";
    for (var i = 0; i < dots.length; i += 2) {
      context.beginPath();
      context.arc(x(dots[i]), y(dots[i + 1]), Math.max(1, scale * 0.8), 0, Math.PI * 2);
      context.fill();
    }
    pins.forEach(function (pin) {
      context.fillStyle = "rgba(229,9,20,.3)";
      context.beginPath();
      context.arc(x(pin.lon), y(pin.lat), 11, 0, Math.PI * 2);
      context.fill();
      context.fillStyle = "#e50914";
      context.beginPath();
      context.arc(x(pin.lon), y(pin.lat), 5, 0, Math.PI * 2);
      context.fill();
    });
  };
  draw();
  window.addEventListener("resize", draw);
})();
