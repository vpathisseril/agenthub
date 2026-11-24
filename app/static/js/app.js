// AgentHub client helpers (CSP-safe: no inline scripts, no eval).
(function () {
  "use strict";
  var root = document.documentElement;
  try { var saved = localStorage.getItem("ah-theme"); if (saved) root.dataset.theme = saved; } catch (e) { /* storage unavailable */ }

  document.addEventListener("click", function (ev) {
    var t = ev.target.closest("[data-theme-toggle]");
    if (t) {
      var next = root.dataset.theme === "light" ? "dark" : "light";
      root.dataset.theme = next;
      try { localStorage.setItem("ah-theme", next); } catch (e) { /* ignore */ }
      return;
    }
    var chip = ev.target.closest("[data-fill]");
    if (chip) {
      var box = document.getElementById(chip.dataset.target || "user_input");
      if (box) { box.value = chip.dataset.fill; box.focus(); }
      return;
    }
    var copy = ev.target.closest("[data-copy]");
    if (copy) {
      var src = document.getElementById(copy.dataset.copy);
      if (src && navigator.clipboard) {
        navigator.clipboard.writeText(src.innerText).then(function () {
          var label = copy.querySelector("span"); if (label) { var old = label.textContent; label.textContent = "Copied"; setTimeout(function () { label.textContent = old; }, 1500); }
        });
      }
    }
  });

  // Live label for range inputs
  document.addEventListener("input", function (ev) {
    if (ev.target.matches("input[type=range][data-out]")) {
      var out = document.getElementById(ev.target.dataset.out);
      if (out) out.textContent = ev.target.value;
    }
  });

  // Confirm dangerous actions without blocking dialogs: two-step button
  document.addEventListener("submit", function (ev) {
    var btn = ev.target.querySelector("[data-confirm]");
    if (btn && !btn.dataset.armed) {
      ev.preventDefault();
      btn.dataset.armed = "1";
      var label = btn.querySelector("span") || btn; label.textContent = btn.dataset.confirm;
      setTimeout(function () { delete btn.dataset.armed; }, 4000);
    }
  });

  // CSRF header for HTMX requests
  document.body.addEventListener("htmx:configRequest", function (ev) {
    var meta = document.querySelector("meta[name=csrf-token]");
    if (meta) ev.detail.headers["X-CSRF-Token"] = meta.content;
  });
})();
