// Sugere cidades e países enquanto a pessoa digita o local do rolê.
(function () {
  var input = document.querySelector("[data-place-search]");
  if (!input) return;

  var latitude = document.getElementById("id_latitude");
  var longitude = document.getElementById("id_longitude");
  var list = document.createElement("ul");
  list.className = "place-list";
  list.id = "place-list";
  list.setAttribute("role", "listbox");
  list.hidden = true;

  input.parentNode.classList.add("place-field");
  input.parentNode.insertBefore(list, input.nextSibling);
  input.setAttribute("role", "combobox");
  input.setAttribute("aria-autocomplete", "list");
  input.setAttribute("aria-controls", list.id);
  input.setAttribute("aria-expanded", "false");

  var timer = null;
  var pending = null;
  var results = [];
  var active = -1;

  function close() {
    list.hidden = true;
    active = -1;
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
  }

  function highlight(index) {
    active = index;
    Array.prototype.forEach.call(list.querySelectorAll('[role="option"]'), function (option, i) {
      var selected = i === index;
      option.classList.toggle("active", selected);
      option.setAttribute("aria-selected", selected ? "true" : "false");
      if (selected) {
        input.setAttribute("aria-activedescendant", option.id);
        option.scrollIntoView({ block: "nearest" });
      }
    });
  }

  function choose(place) {
    input.value = place.label;
    latitude.value = place.latitude;
    longitude.value = place.longitude;
    close();
  }

  function show(places) {
    results = places;
    list.textContent = "";
    active = -1;
    if (!places.length) {
      close();
      return;
    }
    places.forEach(function (place, index) {
      var option = document.createElement("li");
      option.id = "place-option-" + index;
      option.setAttribute("role", "option");
      option.textContent = "📍 " + place.label;
      // mousedown vem antes do blur do campo, que fecharia a lista.
      option.addEventListener("mousedown", function (event) {
        event.preventDefault();
        choose(place);
      });
      list.appendChild(option);
    });
    var credit = document.createElement("li");
    credit.className = "place-credit";
    credit.textContent = "Lugares: Open-Meteo / GeoNames (CC BY 4.0)";
    list.appendChild(credit);
    list.hidden = false;
    input.setAttribute("aria-expanded", "true");
  }

  function search(query) {
    if (pending) pending.abort();
    pending = new AbortController();
    fetch(input.dataset.placeSearch + "?q=" + encodeURIComponent(query), { signal: pending.signal })
      .then(function (response) { return response.ok ? response.json() : { results: [] }; })
      .then(function (data) { show(data.results); })
      .catch(function () {});
  }

  input.addEventListener("input", function () {
    // O texto mudou: a coordenada escolhida antes já não vale.
    latitude.value = "";
    longitude.value = "";
    clearTimeout(timer);
    var query = input.value.trim();
    if (query.length < 2) {
      if (pending) pending.abort();
      close();
      return;
    }
    timer = setTimeout(function () { search(query); }, 250);
  });

  input.addEventListener("keydown", function (event) {
    if (list.hidden) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      highlight((active + 1) % results.length);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      highlight((active - 1 + results.length) % results.length);
    } else if (event.key === "Enter" && active >= 0) {
      event.preventDefault();
      choose(results[active]);
    } else if (event.key === "Escape") {
      close();
    }
  });

  input.addEventListener("blur", close);
})();
