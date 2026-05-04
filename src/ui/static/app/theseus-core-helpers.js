window.theseusInit = async function theseusInit(app) {
  app.$watch("active", () =>
    app.$nextTick(() => {
      window.theseusRefreshIcons();
      if (app.active === "graph" && !app.graph.stats.nodes && !app.graph.loading) {
        app.loadGraph();
      }
      if (app.active === "intel" && !app.intel.data && !app.intel.loading) {
        app.loadIntel();
      }
      if (app.active === "settings" && !app.querySettings.loaded) {
        app.loadQuerySettings();
      }
      app.loadSkillSettings();
      if (app.active === "settings" && !app.mcps.loaded) {
        app.loadMcps();
      }
      if (app.active === "settings" && !app.dangerZone.loaded) {
        app.loadWorkspaceInventory();
      }
      if (app.active === "documents") app.startDocStatsPoll();
      else app.stopDocStatsPoll();
      if (app.active === "activity") app.openProcLog();
      else app.closeProcLog();
      if (app.active === "skills" && !app.skills.loaded) app.loadSkills();
      if (app.active === "studio" && !app.studio.loaded) app.loadStudio();
    }),
  );

  app.$watch("documents", () => window.theseusAfterRender(app));
  app.$watch("docStats.pipeline.busy", () => window.theseusAfterRender(app));
  app.$watch("docStats.counts", () => window.theseusAfterRender(app));
  app.$watch("uploads", () => window.theseusAfterRender(app));
  app.$watch("chats", () => window.theseusAfterRender(app));
  app.$watch("currentChat", () =>
    window.theseusAfterRender(
      app,
      () => {
      app.scrollMsgs();
      },
      { iconsFirst: true },
    ),
  );
  app.$watch("graph.selected", () => window.theseusAfterRender(app));
  app.$watch("palette.open", () => window.theseusAfterRender(app));
  app.$watch("wsModal.open", () => window.theseusAfterRender(app));
  app.$watch("wsModal.items", () => window.theseusAfterRender(app));
  app.$watch("promptPicker.open", () =>
    window.theseusAfterRender(
      app,
      () => {
      if (app.promptPicker.open && app.$refs.promptPickerSearch) {
        app.$refs.promptPickerSearch.focus();
      }
      },
      { iconsFirst: true },
    ),
  );
  app.$watch("promptPicker.query", () => window.theseusAfterRender(app));
  app.$watch("restarting", () => window.theseusAfterRender(app));
  app.$watch("reasoning.open", () => window.theseusAfterRender(app));
  app.$watch("reasoning.expanded", () => window.theseusAfterRender(app));
  app.$watch("chunkPreview.open", () => window.theseusAfterRender(app));
  app.$watch("studioPreview.open", () => window.theseusAfterRender(app));
  app.$watch("studioPreview.sheetIdx", () => window.theseusAfterRender(app));

  app._loadStudioPinned();

  await app.refreshAll();
  window.theseusRefreshIcons();
  if (app.active === "activity") app.openProcLog();
  if (app.active === "documents") app.startDocStatsPoll();
  setInterval(() => {
    app.loadStats();
    app.checkHealth();
  }, 15000);
};

window.theseusRefreshAll = async function theseusRefreshAll(app) {
  await Promise.all([
    app.checkHealth(),
    app.loadStats(),
    app.loadDocuments(),
    app.loadChats(),
    app.loadPromptLibrary(),
    app.loadWorkspaceList(),
  ]);
};

window.theseusApi = async function theseusApi(path, opts = {}) {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(opts.headers || {}),
    },
    ...opts,
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  const contentType = response.headers.get("content-type") || "";
  return contentType.includes("application/json")
    ? response.json()
    : response.text();
};

window.theseusToast = function theseusToast(app, msg, kind = "ok") {
  const id = Math.random().toString(36).slice(2);
  app.toasts.push({ id, msg, kind });
  setTimeout(() => {
    app.toasts = app.toasts.filter((toast) => toast.id !== id);
  }, 3500);
};

window.theseusCheckHealth = async function theseusCheckHealth(app) {
  try {
    await app.api("/health");
    app.health = true;
  } catch {
    app.health = false;
  }
};

window.theseusLoadStats = async function theseusLoadStats(app) {
  try {
    app.stats = await app.api("/api/ui/stats");
  } catch {}
};