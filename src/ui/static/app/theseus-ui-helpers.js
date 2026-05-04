window.theseusRefreshIcons = function theseusRefreshIcons() {
  if (window.lucide) lucide.createIcons();
};

window.theseusAfterRender = function theseusAfterRender(
  app,
  callback,
  options = {},
) {
  const { iconsFirst = false } = options;
  const run = () => {
    if (iconsFirst) window.theseusRefreshIcons();
    if (typeof callback === "function") callback();
    if (!iconsFirst) window.theseusRefreshIcons();
  };

  if (app && typeof app.$nextTick === "function") {
    app.$nextTick(run);
    return;
  }

  run();
};

window.theseusCopyText = async function theseusCopyText(
  app,
  text,
  messages = {},
) {
  const {
    success = "Copied to clipboard",
    error = "Copy failed",
    kind = "info",
  } = messages;

  try {
    await navigator.clipboard.writeText(text);
    if (app && typeof app.toast === "function") {
      app.toast(success, kind);
    }
    return true;
  } catch (copyError) {
    if (app && typeof app.toast === "function") {
      app.toast(
        error === "Copy failed" ? error : `${error}: ${copyError.message}`,
        "error",
      );
    }
    return false;
  }
};