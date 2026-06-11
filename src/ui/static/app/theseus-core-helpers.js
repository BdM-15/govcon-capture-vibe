const theseusSyncActivePanels = function theseusSyncActivePanels(app) {
  if (app.active === "documents") app.startDocStatsPoll();
  else app.stopDocStatsPoll();
  if (app.active === "activity") app.openProcLog();
  else app.closeProcLog();
};

const theseusHandleActiveChange = function theseusHandleActiveChange(app) {
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
  app.loadSkillRuntimeSettings();
  if (app.active === "settings" && !app.webResearchSettings.loaded) {
    app.loadWebResearchSettings();
  }
  if (app.active === "settings" && !app.mcps.loaded) {
    app.loadMcps();
  }
  if (app.active === "settings" && !app.dangerZone.loaded) {
    app.loadWorkspaceInventory();
  }
  theseusSyncActivePanels(app);
  if (app.active === "skills" && !app.skills.loaded) app.loadSkills();
  if (app.active === "chains" && !app.chains.loaded) app.loadChains();
  if (app.active === "studio" && !app.studio.loaded) app.loadStudio();
  if (app.active === "prompts") window.theseusAfterRender(app);
  if (app.active === "chat") window.theseusEnsureChatSelection(app);
};

const theseusWatchAfterRender = function theseusWatchAfterRender(app, paths) {
  for (const path of paths) {
    app.$watch(path, () => window.theseusAfterRender(app));
  }
};

window.theseusInit = async function theseusInit(app) {
  app.$watch("active", () =>
    app.$nextTick(() => theseusHandleActiveChange(app)),
  );

  theseusWatchAfterRender(app, [
    "documents",
    "docStats.pipeline.busy",
    "docStats.counts",
    "uploads",
    "chats",
    "chatHistory.filter",
    "chatHistory.deletePendingId",
    "chatHistory.editingId",
    "chatHandoff.open",
    "graph.selected",
    "palette.open",
    "wsModal.open",
    "wsModal.items",
    "queryTuningGuideModal.open",
    "promptPicker.query",
    "promptLibrary",
    "promptFilter",
    "promptFilterMine",
    "restarting",
    "reasoning.open",
    "reasoning.expanded",
    "chunkPreview.open",
    "studioPreview.open",
    "studio.chainTraceOpen",
    "studioPreview.sheetIdx",
    "chains.current",
    "chains.items",
  ]);

  app.$watch("currentChat", () =>
    window.theseusAfterRender(
      app,
      () => {
        app.scrollMsgs();
      },
      { iconsFirst: true },
    ),
  );
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

  app._loadStudioPinned();

  await app.refreshAll();
  window.theseusRefreshIcons();
  theseusSyncActivePanels(app);
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
