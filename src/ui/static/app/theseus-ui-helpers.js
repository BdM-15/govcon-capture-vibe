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

window.theseusFocusComposer = function theseusFocusComposer(
  app,
  options = {},
) {
  const { placeCaretEnd = false } = options;
  app.$nextTick(() => {
    const composer =
      app.$refs.composer || document.querySelector('textarea[x-model="composer"]');
    if (!composer) return;
    composer.focus();
    if (placeCaretEnd && typeof composer.setSelectionRange === "function") {
      composer.setSelectionRange(composer.value.length, composer.value.length);
    }
  });
};

window.theseusLoadComposerText = function theseusLoadComposerText(
  app,
  text,
  options = {},
) {
  const {
    activateChat = false,
    closePromptPicker = false,
    focus = true,
    placeCaretEnd = false,
    toastMessage = null,
    toastKind = "info",
  } = options;

  app.composer = text;
  if (closePromptPicker) app.promptPicker.open = false;
  if (activateChat) app.active = "chat";
  if (focus) {
    window.theseusFocusComposer(app, { placeCaretEnd });
  }
  if (toastMessage) app.toast(toastMessage, toastKind);
};

window.theseusStartChatWithComposer = function theseusStartChatWithComposer(
  app,
  text,
  rfpContext = null,
) {
  app.composer = text;
  app.newChat(rfpContext);
};