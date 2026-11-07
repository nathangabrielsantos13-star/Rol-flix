// Mostra uma etapa por vez. Sem JavaScript, todas as etapas ficam visíveis em sequência.
(function () {
  var tutorial = document.querySelector("[data-tutorial]");
  if (!tutorial) return;
  var steps = Array.prototype.slice.call(tutorial.querySelectorAll("[data-step]"));
  var back = tutorial.querySelector("[data-tutorial-back]");
  var next = tutorial.querySelector("[data-tutorial-next]");
  var finish = tutorial.querySelector("[data-tutorial-finish]");
  var count = tutorial.querySelector("[data-tutorial-count]");
  var bar = tutorial.querySelector("progress");
  var current = 0;

  var show = function (index, moveFocus) {
    current = index;
    steps.forEach(function (step, position) { step.hidden = position !== index; });
    var last = index === steps.length - 1;
    back.hidden = index === 0;
    next.hidden = last;
    finish.hidden = !last;
    count.textContent = "Etapa " + (index + 1) + " de " + steps.length;
    bar.value = index + 1;
    if (moveFocus) {
      var title = steps[index].querySelector("h2");
      title.tabIndex = -1;
      title.focus({ preventScroll: true });
      tutorial.scrollIntoView({ block: "start" });
    }
  };

  tutorial.querySelector("[data-tutorial-progress]").hidden = false;
  back.addEventListener("click", function () { show(current - 1, true); });
  next.addEventListener("click", function () { show(current + 1, true); });
  show(0, false);
})();
