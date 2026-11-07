// Página do mapa: o globo gira enquanto o mapa carrega por baixo e depois se abre nele.
(function () {
  var MIN_GLOBE_MS = 2400;      // tempo mínimo para o globo ser visto
  var MAX_WAIT_MS = 6000;       // não prende a pessoa se o mapa demorar
  var LEAVE_MS = 700;           // igual à transição no CSS

  var places = JSON.parse(document.getElementById("map-places").textContent);
  var loader = document.getElementById("map-loader");
  var stopGlobe = window.startGlobe(document.getElementById("globe"), places);

  var map = L.map("map", { worldCopyJump: true, minZoom: 2, zoomControl: true }).setView([-15, -50], 2);

  map.attributionControl.setPrefix('<a href="https://leafletjs.com">Leaflet</a>');

  var tiles = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18,
    className: "map-tiles",
    // O Django bloqueia o Referer por padrão, e o OpenStreetMap recusa pedidos sem ele.
    referrerPolicy: "strict-origin-when-cross-origin",
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }).addTo(map);

  function albumRow(album) {
    var row = document.createElement("a");
    row.className = "map-album";
    row.href = album.url;
    if (album.cover) {
      var image = document.createElement("img");
      image.src = album.cover;
      image.alt = "";
      row.appendChild(image);
    }
    var text = document.createElement("span");
    var title = document.createElement("b");
    title.textContent = album.title;
    text.appendChild(title);
    if (album.date) {
      var date = document.createElement("small");
      date.textContent = album.date;
      text.appendChild(date);
    }
    row.appendChild(text);
    return row;
  }

  function popupFor(place) {
    var box = document.createElement("div");
    var heading = document.createElement("p");
    heading.className = "map-place";
    heading.textContent = "📍 " + place.label;
    box.appendChild(heading);
    place.albums.forEach(function (album) { box.appendChild(albumRow(album)); });
    return box;
  }

  function markerFor(place) {
    var count = place.albums.length;
    var icon = L.divIcon({
      className: "",
      html: '<span class="map-pin">' + (count > 1 ? count : "") + "</span>",
      iconSize: [30, 30],
      iconAnchor: [15, 15],
      popupAnchor: [0, -14],
    });
    return L.marker([place.lat, place.lon], { icon: icon, title: place.label }).addTo(map).bindPopup(popupFor(place));
  }

  var markers = places.map(function (place) {
    return { place: place, marker: markerFor(place) };
  });

  function focusedMarker() {
    var id = Number(new URLSearchParams(location.search).get("album"));
    var match = markers.filter(function (item) {
      return item.place.albums.some(function (album) { return album.id === id; });
    })[0];
    return match ? match.marker : null;
  }

  var focused = focusedMarker();
  if (focused) {
    map.setView(focused.getLatLng(), 8);
  } else if (markers.length === 1) {
    map.setView(markers[0].marker.getLatLng(), 6);
  } else if (markers.length) {
    map.fitBounds(L.latLngBounds(markers.map(function (item) { return item.marker.getLatLng(); })), { padding: [60, 60], maxZoom: 7 });
  }

  var opened = false;
  var startedAt = performance.now();

  function reveal() {
    if (opened) return;
    opened = true;
    setTimeout(function () {
      loader.classList.add("leaving");
      map.invalidateSize();
      if (focused) focused.openPopup();
      setTimeout(function () {
        stopGlobe();
        loader.remove();
      }, LEAVE_MS);
    }, Math.max(0, MIN_GLOBE_MS - (performance.now() - startedAt)));
  }

  tiles.once("load", reveal);
  setTimeout(reveal, MAX_WAIT_MS);
})();
