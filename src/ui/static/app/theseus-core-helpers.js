window.theseusInit = async function theseusInit(app) {
  app.$watch("active", () =>
    app.$nextTick(() => {
      lucide.createIcons();
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

  app.$watch("documents", () => app.$nextTick(() => lucide.createIcons()));
  app.$watch("docStats.pipeline.busy", () =>
    app.$nextTick(() => lucide.createIcons()),
  );
  app.$watch("docStats.counts", () =>
    app.$nextTick(() => lucide.createIcons()),
  );
  app.$watch("uploads", () => app.$nextTick(() => lucide.createIcons()));
  app.$watch("chats", () => app.$nextTick(() => lucide.createIcons()));
  app.$watch("currentChat", () =>
    app.$nextTick(() => {
      lucide.createIcons();
      app.scrollMsgs();
    }),
  );
  app.$watch("graph.selected", () => app.$nextTick(() => lucide.createIcons()));
  app.$watch("palette.open", () => app.$nextTick(() => lucide.createIcons()));
  app.$watch("wsModal.open", () => app.$nextTick(() => lucide.createIcons()));
  app.$watch("wsModal.items", () => app.$nextTick(() => lucide.createIcons()));
  app.$watch("promptPicker.open", () =>
    app.$nextTick(() => {
      lucide.createIcons();
      if (app.promptPicker.open && app.$refs.promptPickerSearch) {
        app.$refs.promptPickerSearch.focus();
      }
    }),
  );
  app.$watch("promptPicker.query", () =>
    app.$nextTick(() => lucide.createIcons()),
  );
  app.$watch("restarting", () => app.$nextTick(() => lucide.createIcons()));
  app.$watch("reasoning.open", () => app.$nextTick(() => lucide.createIcons()));
  app.$watch("reasoning.expanded", () =>
    app.$nextTick(() => lucide.createIcons()),
  );
  app.$watch("chunkPreview.open", () =>
    app.$nextTick(() => lucide.createIcons()),
  );
  app.$watch("studioPreview.open", () =>
    app.$nextTick(() => lucide.createIcons()),
  );
  app.$watch("studioPreview.sheetIdx", () =>
    app.$nextTick(() => lucide.createIcons()),
  );

  app._loadStudioPinned();

  await app.refreshAll();
  lucide.createIcons();
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