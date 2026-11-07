// Globo 3D em canvas: projeta os pontos de terra e os lugares dos rolês em uma esfera que gira.
window.startGlobe = function (canvas, pins) {
  var DOTS = window.ROLEFLIX_GLOBE_DOTS;
  var DEGREES_PER_SECOND = 70;
  var TO_RAD = Math.PI / 180;
  var ctx = canvas.getContext("2d");
  var ratio = window.devicePixelRatio || 1;
  var size = canvas.clientWidth;
  canvas.width = canvas.height = size * ratio;
  ctx.scale(ratio, ratio);

  var center = size / 2;
  var radius = size * 0.4;
  var firstPin = pins[0];
  var startLon = firstPin ? firstPin.lon + 200 : -50;
  var tilt = (firstPin ? Math.max(-40, Math.min(40, firstPin.lat * 0.6)) : -12) * TO_RAD;
  var sinTilt = Math.sin(tilt);
  var cosTilt = Math.cos(tilt);
  var running = true;
  var started = null;

  function project(lon, lat, centerLon) {
    var lambda = (lon - centerLon) * TO_RAD;
    var phi = lat * TO_RAD;
    var cosPhi = Math.cos(phi);
    var sinPhi = Math.sin(phi);
    var cosLambda = Math.cos(lambda);
    var facing = sinTilt * sinPhi + cosTilt * cosPhi * cosLambda;
    return {
      facing: facing,
      x: center + radius * cosPhi * Math.sin(lambda),
      y: center - radius * (cosTilt * sinPhi - sinTilt * cosPhi * cosLambda),
    };
  }

  function drawSphere() {
    var halo = ctx.createRadialGradient(center, center, radius * 0.9, center, center, radius * 1.24);
    halo.addColorStop(0, "rgba(229,9,20,.5)");
    halo.addColorStop(1, "rgba(229,9,20,0)");
    ctx.fillStyle = halo;
    ctx.fillRect(0, 0, size, size);

    var body = ctx.createRadialGradient(center - radius * 0.35, center - radius * 0.4, radius * 0.1, center, center, radius);
    body.addColorStop(0, "#3a0a10");
    body.addColorStop(0.7, "#17060a");
    body.addColorStop(1, "#090305");
    ctx.fillStyle = body;
    ctx.beginPath();
    ctx.arc(center, center, radius, 0, Math.PI * 2);
    ctx.fill();
  }

  function drawLand(centerLon) {
    var dot = Math.max(1.3, size / 220);
    ctx.fillStyle = "#ff8a8f";
    for (var i = 0; i < DOTS.length; i += 2) {
      var point = project(DOTS[i], DOTS[i + 1], centerLon);
      if (point.facing > 0) {
        ctx.globalAlpha = 0.2 + 0.8 * point.facing;
        ctx.fillRect(point.x, point.y, dot, dot);
      }
    }
    ctx.globalAlpha = 1;
  }

  function drawPins(centerLon, seconds) {
    var pulse = (seconds * 1.4) % 1;
    pins.forEach(function (pin) {
      var point = project(pin.lon, pin.lat, centerLon);
      if (point.facing <= 0) return;
      ctx.strokeStyle = "rgba(255,255,255," + (1 - pulse) + ")";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(point.x, point.y, 4 + pulse * 13, 0, Math.PI * 2);
      ctx.stroke();
      ctx.fillStyle = "#fff";
      ctx.beginPath();
      ctx.arc(point.x, point.y, 4, 0, Math.PI * 2);
      ctx.fill();
    });
  }

  function frame(now) {
    if (!running) return;
    if (started === null) started = now;
    var seconds = (now - started) / 1000;
    var centerLon = startLon - seconds * DEGREES_PER_SECOND;
    ctx.clearRect(0, 0, size, size);
    drawSphere();
    drawLand(centerLon);
    drawPins(centerLon, seconds);
    requestAnimationFrame(frame);
  }

  requestAnimationFrame(frame);
  return function stop() { running = false; };
};
