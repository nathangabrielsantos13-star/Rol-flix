// Editor de capas: tudo é desenhado no canvas, e o que se vê é exatamente o arquivo salvo.
(function () {
  var root = document.querySelector("[data-cover-editor]");
  if (!root) return;
  var data = JSON.parse(document.getElementById("cover-data").textContent);
  var config = data.config;
  var canvas = document.getElementById("cover-canvas");
  var context = canvas.getContext("2d");
  var form = root.querySelector("[data-cover-form]");
  var errorBox = root.querySelector("[data-cover-error]");
  var saveButton = root.querySelector("[data-cover-save]");
  var WIDTH = canvas.width;
  var HEIGHT = canvas.height;
  var background = null;
  var hasBackground = false;
  var chosenFile = null;
  var chosenMedia = null;
  var textBox = null;
  var ringColors = ["#b5261e", "#2d6fa8", "#3f8a55", "#b5852a", "#7b3fa0", "#a5324a"];

  var loadImage = function (url) {
    return new Promise(function (resolve, reject) {
      var image = new Image();
      image.onload = function () { resolve(image); };
      image.onerror = reject;
      image.src = url;
    });
  };

  var cast = data.cast.map(function (person) { return { name: person.name, image: null, url: person.avatar }; });
  cast.forEach(function (person) {
    if (person.url) loadImage(person.url).then(function (image) { person.image = image; draw(); }).catch(function () {});
  });

  // Filtros por mistura de camadas: funcionam também no Safari, que não tem context.filter.
  var layer = function (mode, color, alpha) {
    context.save();
    context.globalCompositeOperation = mode;
    context.globalAlpha = alpha === undefined ? 1 : alpha;
    context.fillStyle = color;
    context.fillRect(0, 0, WIDTH, HEIGHT);
    context.restore();
  };
  var FILTERS = {
    none: function () {},
    dark: function () { layer("source-over", "#000", 0.45); },
    light: function () { layer("source-over", "#fff", 0.22); },
    cinematic: function () { layer("multiply", "#7f9aad"); layer("soft-light", "#ff9a4d", 0.3); layer("source-over", "#000", 0.14); },
    ocean: function () { layer("multiply", "#8fd0ff"); layer("soft-light", "#0a6fc0", 0.4); },
    warm: function () { layer("multiply", "#ffcf95"); layer("soft-light", "#ff7a1a", 0.3); },
    vibrant: function () { layer("saturation", "hsl(0,100%,50%)", 0.22); layer("overlay", "#fff", 0.06); },
    vintage: function () { layer("saturation", "#808080", 0.6); layer("multiply", "#f0d6a8"); layer("lighten", "#2a1a10"); },
    mono: function () { layer("saturation", "#808080"); }
  };

  var wrap = function (text, maxWidth) {
    var lines = [];
    text.split("\n").forEach(function (paragraph) {
      var current = "";
      paragraph.split(/\s+/).forEach(function (word) {
        var attempt = current ? current + " " + word : word;
        if (current && context.measureText(attempt).width > maxWidth) {
          lines.push(current);
          current = word;
        } else {
          current = attempt;
        }
      });
      if (current) lines.push(current);
    });
    return lines;
  };

  var titleFont = function () {
    return (config.font === "Playfair Display" || config.font === "Inter" ? "700 " : "400 ") + config.title_size + 'px "' + config.font + '", Arial, sans-serif';
  };

  var measure = function () {
    var margin = 70;
    var room = config.align === "left" ? WIDTH - config.x * WIDTH - margin
      : config.align === "right" ? config.x * WIDTH - margin
      : 2 * Math.min(config.x, 1 - config.x) * WIDTH - margin;
    room = Math.max(320, room);
    context.font = titleFont();
    var titleLines = wrap(config.title || " ", room);
    var lineHeight = config.title_size * 1.04;
    context.font = '500 34px "Inter", Arial, sans-serif';
    var synopsisLines = config.synopsis ? wrap(config.synopsis, Math.min(room, 1000)).slice(0, 3) : [];
    var people = config.show_cast ? cast.slice(0, 6) : [];
    var height = 44 + titleLines.length * lineHeight + (synopsisLines.length ? 18 + synopsisLines.length * 46 : 0) + (people.length ? 110 : 0);
    var top = config.valign === "top" ? config.y * HEIGHT
      : config.valign === "middle" ? config.y * HEIGHT - height / 2
      : config.y * HEIGHT - height;
    top = Math.max(24, Math.min(HEIGHT - height - 24, top));
    return { titleLines: titleLines, lineHeight: lineHeight, synopsisLines: synopsisLines, people: people, height: height, top: top, room: room };
  };

  var drawCast = function (people, x, y) {
    var size = 84;
    var step = 66;
    var width = size + step * (people.length - 1);
    var left = config.align === "left" ? x : config.align === "right" ? x - width : x - width / 2;
    people.forEach(function (person, index) {
      var cx = left + size / 2 + index * step;
      var cy = y + size / 2;
      context.save();
      context.beginPath();
      context.arc(cx, cy, size / 2, 0, Math.PI * 2);
      context.fillStyle = ringColors[index % ringColors.length];
      context.fill();
      context.lineWidth = 5;
      context.strokeStyle = "#0b0b0b";
      context.stroke();
      context.clip();
      if (person.image) {
        var side = Math.min(person.image.width, person.image.height);
        context.drawImage(person.image, (person.image.width - side) / 2, (person.image.height - side) / 2, side, side, cx - size / 2, cy - size / 2, size, size);
      } else {
        context.fillStyle = "#fff";
        context.font = '700 36px "Inter", Arial, sans-serif';
        context.textAlign = "center";
        context.textBaseline = "middle";
        context.fillText(person.name.charAt(0).toUpperCase(), cx, cy + 2);
      }
      context.restore();
    });
  };

  function draw() {
    context.save();
    context.clearRect(0, 0, WIDTH, HEIGHT);
    if (background) {
      var scale = Math.max(WIDTH / background.width, HEIGHT / background.height);
      var w = background.width * scale;
      var h = background.height * scale;
      context.drawImage(background, (WIDTH - w) / 2, (HEIGHT - h) / 2, w, h);
    } else {
      var empty = context.createLinearGradient(0, 0, WIDTH, HEIGHT);
      empty.addColorStop(0, "#3a0a0e");
      empty.addColorStop(1, "#101010");
      context.fillStyle = empty;
      context.fillRect(0, 0, WIDTH, HEIGHT);
    }
    (FILTERS[config.filter] || FILTERS.none)();

    var box = measure();
    var shade = context.createLinearGradient(0, box.top - 160, 0, box.top + box.height + 160);
    shade.addColorStop(0, "rgba(0,0,0,0)");
    shade.addColorStop(0.3, "rgba(0,0,0,.5)");
    shade.addColorStop(0.7, "rgba(0,0,0,.5)");
    shade.addColorStop(1, "rgba(0,0,0,0)");
    context.fillStyle = shade;
    context.fillRect(0, 0, WIDTH, HEIGHT);

    var x = config.x * WIDTH;
    var y = box.top;
    context.textAlign = config.align;
    context.textBaseline = "top";
    context.shadowColor = "rgba(0,0,0,.65)";
    context.shadowBlur = 18;
    context.shadowOffsetY = 3;
    context.font = '700 24px "Inter", Arial, sans-serif';
    context.fillStyle = config.accent;
    context.fillText("UM FILME ORIGINAL ROLÊFLIX", x, y);
    y += 44;
    context.font = titleFont();
    context.fillStyle = config.color;
    box.titleLines.forEach(function (line) {
      context.fillText(line, x, y);
      y += box.lineHeight;
    });
    if (box.synopsisLines.length) {
      y += 18;
      context.font = '500 34px "Inter", Arial, sans-serif';
      context.fillStyle = config.color;
      box.synopsisLines.forEach(function (line) {
        context.fillText(line, x, y);
        y += 46;
      });
    }
    context.shadowColor = "transparent";
    if (box.people.length) drawCast(box.people, x, y + 24);
    context.restore();
    textBox = box;
  }

  var redrawWhenFontReady = function () {
    var weight = config.font === "Playfair Display" || config.font === "Inter" ? "700" : "400";
    Promise.all([
      document.fonts.load(weight + ' 60px "' + config.font + '"', "ÁÊçã"),
      document.fonts.load('500 34px "Inter"', "ÁÊçã"),
      document.fonts.load('700 24px "Inter"', "ÁÊçã")
    ]).then(draw, draw);
  };

  var fields = form.querySelectorAll("[data-field]");
  var syncForm = function () {
    fields.forEach(function (field) {
      var key = field.dataset.field;
      if (field.type === "checkbox") field.checked = !!config[key];
      else field.value = config[key];
    });
    form.querySelectorAll("[data-template]").forEach(function (button) {
      button.setAttribute("aria-pressed", button.dataset.template === config.template ? "true" : "false");
    });
  };

  var applyPosition = function (key) {
    var preset = data.positions[key];
    if (!preset) return;
    config.position = key;
    config.x = preset.x;
    config.y = preset.y;
    config.align = preset.align;
    config.valign = preset.valign;
  };

  var fill = function (select, entries) {
    entries.forEach(function (entry) {
      var option = document.createElement("option");
      option.value = entry[0];
      option.textContent = entry[1];
      select.appendChild(option);
    });
  };
  fill(form.querySelector("[data-fonts]"), data.fonts.map(function (font) { return [font, font]; }));
  fill(form.querySelector("[data-filters]"), Object.keys(data.filters).map(function (key) { return [key, data.filters[key]]; }));
  fill(form.querySelector("[data-positions]"), [["", "Personalizada"]].concat(Object.keys(data.positions).map(function (key) { return [key, data.positions[key].label]; })));

  var templateRow = form.querySelector("[data-templates]");
  Object.keys(data.templates).forEach(function (key) {
    var template = data.templates[key];
    var button = document.createElement("button");
    button.type = "button";
    button.className = "secondary cover-template";
    button.dataset.template = key;
    button.textContent = template.label;
    button.addEventListener("click", function () {
      ["font", "title_size", "color", "accent", "filter"].forEach(function (name) { config[name] = template[name]; });
      config.template = key;
      applyPosition(template.position);
      syncForm();
      redrawWhenFontReady();
    });
    templateRow.appendChild(button);
  });

  fields.forEach(function (field) {
    field.addEventListener("input", function () {
      var key = field.dataset.field;
      if (key === "position") {
        if (field.value) applyPosition(field.value);
        else config.position = "";
      } else if (field.type === "checkbox") {
        config[key] = field.checked;
      } else {
        config[key] = "number" in field.dataset ? Number(field.value) : field.value;
      }
      if (key === "font") redrawWhenFontReady();
      else draw();
    });
  });

  var useBackground = function (url) {
    return loadImage(url).then(function (image) {
      background = image;
      hasBackground = true;
      errorBox.hidden = true;
      draw();
    });
  };

  var photoRow = form.querySelector("[data-cover-photos]");
  data.photos.forEach(function (photo) {
    var button = document.createElement("button");
    button.type = "button";
    button.setAttribute("aria-label", "Usar esta foto do álbum");
    var image = document.createElement("img");
    image.loading = "lazy";
    image.alt = "";
    image.src = photo.url;
    button.appendChild(image);
    button.addEventListener("click", function () {
      chosenMedia = photo.id;
      chosenFile = null;
      form.querySelector("[data-cover-upload]").value = "";
      photoRow.querySelectorAll("button").forEach(function (other) { other.classList.toggle("active", other === button); });
      useBackground(photo.url);
    });
    photoRow.appendChild(button);
  });

  form.querySelector("[data-cover-upload]").addEventListener("change", function (event) {
    var file = event.target.files[0];
    if (!file) return;
    useBackground(URL.createObjectURL(file)).then(function () {
      chosenFile = file;
      chosenMedia = null;
      photoRow.querySelectorAll("button").forEach(function (other) { other.classList.remove("active"); });
    }).catch(function () {
      showError("Não foi possível abrir essa imagem.");
    });
  });

  var showError = function (text) {
    errorBox.textContent = text;
    errorBox.hidden = false;
  };

  var pointerAt = function (event) {
    var rect = canvas.getBoundingClientRect();
    return { x: (event.clientX - rect.left) / rect.width, y: (event.clientY - rect.top) / rect.height };
  };
  var dragging = null;
  canvas.addEventListener("pointerdown", function (event) {
    dragging = { start: pointerAt(event), x: config.x, y: config.y };
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener("pointermove", function (event) {
    if (!dragging) return;
    var now = pointerAt(event);
    config.x = Math.max(0, Math.min(1, dragging.x + now.x - dragging.start.x));
    config.y = Math.max(0, Math.min(1, dragging.y + now.y - dragging.start.y));
    config.position = "";
    form.querySelector("[data-positions]").value = "";
    draw();
  });
  var stopDrag = function () { dragging = null; };
  canvas.addEventListener("pointerup", stopDrag);
  canvas.addEventListener("pointercancel", stopDrag);

  saveButton.addEventListener("click", function () {
    if (!hasBackground) { showError("Escolha uma imagem de fundo."); return; }
    if (!config.title.trim()) { showError("Escreva um título para a capa."); return; }
    errorBox.hidden = true;
    saveButton.disabled = true;
    saveButton.textContent = "Salvando…";
    draw();
    canvas.toBlob(function (blob) {
      var body = new FormData();
      body.append("final", blob, "capa.jpg");
      body.append("config", JSON.stringify(config));
      if (chosenMedia) body.append("background_media", chosenMedia);
      Promise.resolve(chosenFile && window.roleflixCompress ? window.roleflixCompress(chosenFile) : chosenFile).then(function (background) {
        if (background) body.append("background_file", background);
        return fetch(data.save_url, {
          method: "POST",
          body: body,
          headers: { "X-CSRFToken": form.querySelector("[name=csrfmiddlewaretoken]").value }
        });
      }).then(function (response) {
        return response.json().then(function (result) {
          if (!response.ok) throw new Error(result.error);
          location.href = data.album_url;
        });
      }).catch(function (error) {
        showError(error.message || "Não foi possível salvar. Tente novamente.");
        saveButton.disabled = false;
        saveButton.textContent = "Salvar capa";
      });
    }, "image/jpeg", 0.92);
  });

  syncForm();
  redrawWhenFontReady();
  if (data.background) useBackground(data.background).catch(function () {});
})();
