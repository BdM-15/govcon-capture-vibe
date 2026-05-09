const ARIADNE_BUCKETS = ["inbox", "notes", "llm-wiki", "intel"];

const theseusSafeArray = function theseusSafeArray(value) {
  return Array.isArray(value) ? value : [];
};

const theseusAriadneBucket = function theseusAriadneBucket(app, bucket) {
  return theseusSafeArray(app.ariadne?.buckets?.[bucket]);
};

window.theseusAriadneWorkspaceRows = function theseusAriadneWorkspaceRows(app) {
  const active = app.stats?.workspace || app.ariadne?.active || "";
  const inventoryByName = new Map(
    theseusSafeArray(app.ariadne?.inventory).map((row) => [row.name, row]),
  );
  const names = new Set([
    ...theseusSafeArray(app.ariadne?.workspaces).map((row) => row.name),
    ...theseusSafeArray(app.ariadne?.inventory).map((row) => row.name),
  ]);

  return Array.from(names)
    .filter(Boolean)
    .map((name) => {
      const workspace = theseusSafeArray(app.ariadne?.workspaces).find(
        (row) => row.name === name,
      ) || { name };
      const inventory = inventoryByName.get(name) || {};
      return {
        ...workspace,
        ...inventory,
        name,
        is_active: name === active || !!inventory.is_active,
        documents: workspace.documents ?? 0,
        entities: workspace.entities ?? 0,
        chats: workspace.chats ?? 0,
        neo4j_nodes: inventory.neo4j_nodes ?? 0,
        storage_mb: inventory.storage_mb ?? null,
        inputs_files: inventory.inputs_files ?? 0,
      };
    })
    .sort((left, right) => {
      if (left.is_active !== right.is_active) return left.is_active ? -1 : 1;
      return (right.documents || 0) - (left.documents || 0) || left.name.localeCompare(right.name);
    });
};

window.theseusAriadneStage = function theseusAriadneStage(row) {
  if (!row || (!row.documents && !row.entities && !row.neo4j_nodes)) return "intake";
  if ((row.entities || 0) > 0 && (row.neo4j_nodes || 0) > 0) return "knowledge-ready";
  if ((row.documents || 0) > 0) return "processing";
  return "staged";
};

window.theseusAriadneStageClass = function theseusAriadneStageClass(row) {
  const stage = window.theseusAriadneStage(row);
  if (stage === "knowledge-ready") return "bg-neon-lime/10 text-neon-lime border-neon-lime/30";
  if (stage === "processing") return "bg-neon-cyan/10 text-neon-cyan border-neon-cyan/30";
  if (stage === "staged") return "bg-neon-amber/10 text-neon-amber border-neon-amber/30";
  return "bg-ink-800 text-slate-400 border-edge";
};

window.theseusAriadneMetrics = function theseusAriadneMetrics(app) {
  const rows = window.theseusAriadneWorkspaceRows(app);
  const inbox = theseusAriadneBucket(app, "inbox");
  const notes = theseusAriadneBucket(app, "notes");
  const wiki = theseusAriadneBucket(app, "llm-wiki");
  const intel = theseusAriadneBucket(app, "intel");
  const documents = rows.reduce((total, row) => total + (row.documents || 0), 0);
  const entities = rows.reduce((total, row) => total + (row.entities || 0), 0);
  const activeOpps = rows.filter(
    (row) => (row.documents || 0) || (row.entities || 0) || (row.inputs_files || 0),
  ).length;

  return [
    {
      label: "opportunities",
      value: activeOpps || rows.length,
      hint: `${rows.length} workspace${rows.length === 1 ? "" : "s"}`,
      icon: "briefcase",
      accent: "cyan",
      color: "text-neon-cyan",
    },
    {
      label: "knowledge",
      value: entities.toLocaleString(),
      hint: `${documents.toLocaleString()} source docs`,
      icon: "network",
      accent: "magenta",
      color: "text-neon-magenta",
    },
    {
      label: "capture queue",
      value: (inbox.length + notes.length).toLocaleString(),
      hint: `${inbox.length} inbox · ${notes.length} notes`,
      icon: "inbox",
      accent: "amber",
      color: "text-neon-amber",
    },
    {
      label: "intel library",
      value: (wiki.length + intel.length).toLocaleString(),
      hint: `${intel.length} intel · ${wiki.length} wiki`,
      icon: "radar",
      accent: "lime",
      color: "text-neon-lime",
    },
  ];
};

window.theseusAriadneQueueItems = function theseusAriadneQueueItems(
  app,
  bucket = "inbox",
  limit = 4,
) {
  return theseusAriadneBucket(app, bucket).slice(0, limit);
};

window.theseusAriadnePromoteOptions = function theseusAriadnePromoteOptions(app) {
  return window.theseusAriadneWorkspaceRows(app).map((row) => row.name);
};

window.theseusLoadAriadneBucket = async function theseusLoadAriadneBucket(app, bucket) {
  const response = await app.api(`/api/global/${bucket}?limit=50`);
  app.ariadne.buckets[bucket] = response.entries || [];
};

window.theseusLoadAriadne = async function theseusLoadAriadne(app) {
  if (!app.ariadne) return;
  app.ariadne.loading = true;
  app.ariadne.error = null;
  try {
    const [workspaceResponse, inventoryResponse] = await Promise.all([
      app.api("/api/ui/workspaces"),
      app.api("/api/ui/workspaces/inventory").catch(() => ({ workspaces: [] })),
    ]);
    app.ariadne.workspaces = workspaceResponse.workspaces || [];
    app.ariadne.active = workspaceResponse.active || app.stats?.workspace || "";
    app.ariadne.inventory = inventoryResponse.workspaces || [];
    await Promise.all(
      ARIADNE_BUCKETS.map((bucket) => window.theseusLoadAriadneBucket(app, bucket)),
    );
    app.ariadne.loaded = true;
  } catch (error) {
    app.ariadne.error = error.message || String(error);
  } finally {
    app.ariadne.loading = false;
    window.theseusAfterRender(app);
  }
};

window.theseusSubmitAriadneCapture = async function theseusSubmitAriadneCapture(app) {
  const capture = app.ariadne.capture;
  const content = (capture.body || "").trim();
  if (!content || capture.busy) return;
  capture.busy = true;
  try {
    const tags = (capture.tags || "")
      .split(",")
      .map((tag) => tag.trim())
      .filter(Boolean);
    const payload = {
      content,
      bucket: capture.bucket || "inbox",
      source: "capture-manager",
      tags: tags.length ? tags : ["capture"],
      priority: capture.priority || "normal",
    };
    if ((capture.slug || "").trim()) payload.slug = capture.slug.trim();
    if ((capture.workspace || "").trim()) payload.workspace = capture.workspace.trim();
    const response = await app.api("/api/global/capture", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    capture.body = "";
    capture.slug = "";
    app.toast(`Captured ${response.path || "global note"}`, "success");
    await window.theseusLoadAriadneBucket(app, payload.bucket);
  } catch (error) {
    app.toast(`Capture failed: ${error.message || error}`, "error");
  } finally {
    capture.busy = false;
    window.theseusAfterRender(app);
  }
};

window.theseusPromoteAriadneNote = async function theseusPromoteAriadneNote(app, path) {
  const workspace = app.ariadne.promoteTarget[path];
  if (!workspace) return;
  try {
    await app.api("/api/global/promote", {
      method: "POST",
      body: JSON.stringify({ path, workspace }),
    });
    delete app.ariadne.promoteTarget[path];
    app.toast(`Promoted to ${workspace}`, "success");
    await window.theseusLoadAriadneBucket(app, "inbox");
  } catch (error) {
    app.toast(`Promote failed: ${error.message || error}`, "error");
  } finally {
    window.theseusAfterRender(app);
  }
};

window.theseusActivateAriadneWorkspace = async function theseusActivateAriadneWorkspace(app, name) {
  if (!name) return;
  if (name === app.stats?.workspace) {
    app.active = "intel";
    return;
  }
  await app.switchWorkspace(name, false);
};

window.theseusAriadneAsk = async function theseusAriadneAsk(app, prompt) {
  await app.newChat({ source: "ariadne-dashboard", prompt });
  app.composer = prompt;
};
