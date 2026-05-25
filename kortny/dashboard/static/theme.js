(function () {
  var storageKey = "kortny.theme";
  var media = window.matchMedia
    ? window.matchMedia("(prefers-color-scheme: dark)")
    : null;

  function storedTheme() {
    try {
      return window.localStorage.getItem(storageKey);
    } catch (_error) {
      return null;
    }
  }

  function persistTheme(theme) {
    try {
      window.localStorage.setItem(storageKey, theme);
    } catch (_error) {
      return;
    }
  }

  function resolvedTheme() {
    var stored = storedTheme();
    if (stored === "dark" || stored === "light") {
      return stored;
    }
    return media && media.matches ? "dark" : "light";
  }

  function applyTheme(theme, persist) {
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    if (persist) {
      persistTheme(theme);
    }
    updateToggles(theme);
  }

  function updateToggles(theme) {
    var nextTheme = theme === "dark" ? "light" : "dark";
    document.querySelectorAll("[data-theme-toggle]").forEach(function (button) {
      var value = button.querySelector("[data-theme-toggle-value]");
      button.setAttribute("aria-pressed", theme === "dark" ? "true" : "false");
      button.setAttribute("aria-label", "Switch to " + nextTheme + " theme");
      button.dataset.themeState = theme;
      if (value) {
        value.textContent = theme === "dark" ? "Dark" : "Light";
      }
    });
  }

  function init() {
    applyTheme(resolvedTheme(), false);
    document.querySelectorAll("[data-theme-toggle]").forEach(function (button) {
      button.addEventListener("click", function () {
        var current = document.documentElement.dataset.theme === "dark" ? "dark" : "light";
        applyTheme(current === "dark" ? "light" : "dark", true);
      });
    });
    if (media && typeof media.addEventListener === "function") {
      media.addEventListener("change", function () {
        if (storedTheme() !== "dark" && storedTheme() !== "light") {
          applyTheme(resolvedTheme(), false);
        }
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
