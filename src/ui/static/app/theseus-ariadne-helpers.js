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

// 174.4b: Command-center KPIs answer the 5 morning questions.
// Real data where derivable today; placeholders flag schema arriving in 174.6.
const ARIADNE_DAY_SECONDS = 86400;
const ARIADNE_STALE_INTEL_DAYS = 14;

const theseusAriadneNowSec = function theseusAriadneNowSec() {
  return Date.now() / 1000;
};

const theseusAriadneRecentEntries = function theseusAriadneRecentEntries(entries, withinDays) {
  const cutoff = theseusAriadneNowSec() - withinDays * ARIADNE_DAY_SECONDS;
  return entries.filter((entry) => (entry.modified_at || 0) >= cutoff);
};

window.theseusAriadneMetrics = function theseusAriadneMetrics(app) {
  const rows = window.theseusAriadneWorkspaceRows(app);
  const inbox = theseusAriadneBucket(app, "inbox");
  const intel = theseusAriadneBucket(app, "intel");
  const recentIntel = theseusAriadneRecentEntries(intel, ARIADNE_STALE_INTEL_DAYS);
  const staleWorkspaces = rows.length
    ? Math.max(rows.length - recentIntel.length, 0)
    : 0;
  const pursuitsNeedingAction = rows.filter((row) => {
    if ((row.inputs_files || 0) > 0 && (row.documents || 0) === 0) return true; // unprocessed
    if ((row.documents || 0) > 0 && (row.entities || 0) === 0) return true; // ingest stalled
    return false;
  }).length;

  return [
    {
      label: "needs action",
      value: pursuitsNeedingAction,
      hint: `${rows.length} pursuit${rows.length === 1 ? "" : "s"} tracked`,
      icon: "alert-triangle",
      accent: "amber",
      color: "text-neon-amber",
      placeholder: false,
    },
    {
      label: "decisions due",
      value: 0,
      hint: "schema arrives 174.6",
      icon: "gavel",
      accent: "magenta",
      color: "text-neon-magenta",
      placeholder: true,
    },
    {
      label: "stale intel",
      value: staleWorkspaces,
      hint: `>${ARIADNE_STALE_INTEL_DAYS}d since cross-opp intel`,
      icon: "clock-alert",
      accent: "magenta",
      color: "text-neon-magenta",
      placeholder: false,
    },
    {
      label: "notes to promote",
      value: inbox.length,
      hint: `${inbox.length} in global inbox`,
      icon: "inbox",
      accent: "cyan",
      color: "text-neon-cyan",
      placeholder: false,
    },
    {
      label: "gates ≤ 7d",
      value: 0,
      hint: "schema arrives 174.6",
      icon: "calendar-clock",
      accent: "lime",
      color: "text-neon-lime",
      placeholder: true,
    },
  ];
};

// Morning Brief: answers "what changed since yesterday?" + recommended actions.
window.theseusAriadneMorningBrief = function theseusAriadneMorningBrief(app) {
  const buckets = ARIADNE_BUCKETS.flatMap((bucket) =>
    theseusAriadneBucket(app, bucket).map((entry) => ({ ...entry, _bucket: bucket })),
  );
  const last24h = theseusAriadneRecentEntries(buckets, 1);
  const last24hByBucket = ARIADNE_BUCKETS.reduce((acc, bucket) => {
    acc[bucket] = last24h.filter((entry) => entry._bucket === bucket).length;
    return acc;
  }, {});

  const inbox = theseusAriadneBucket(app, "inbox");
  const rows = window.theseusAriadneWorkspaceRows(app);
  const intel = theseusAriadneBucket(app, "intel");
  const lastIntel = intel.reduce(
    (max, entry) => Math.max(max, entry.modified_at || 0),
    0,
  );
  const intelAgeDays = lastIntel
    ? Math.floor((theseusAriadneNowSec() - lastIntel) / ARIADNE_DAY_SECONDS)
    : null;

  const items = [];
  items.push({
    icon: "activity",
    accent: "cyan",
    label: "What changed since yesterday",
    detail: last24h.length
      ? `${last24h.length} new vault entr${last24h.length === 1 ? "y" : "ies"} (` +
        ARIADNE_BUCKETS.map((bucket) => `${last24hByBucket[bucket]} ${bucket}`).join(" · ") +
        `)`
      : "No vault changes in last 24h.",
  });

  const stalled = rows.find(
    (row) => (row.inputs_files || 0) > 0 && (row.documents || 0) === 0,
  );
  items.push({
    icon: "alert-triangle",
    accent: "amber",
    label: "Pursuit needs attention",
    detail: stalled
      ? `${stalled.name}: ${stalled.inputs_files} input${stalled.inputs_files === 1 ? "" : "s"} unprocessed.`
      : rows.length
        ? "All tracked pursuits look current."
        : "No pursuits yet — create a workspace to start tracking.",
    action: stalled ? { label: "Open", workspace: stalled.name } : null,
  });

  items.push({
    icon: "gavel",
    accent: "magenta",
    label: "Decisions blocked",
    detail: "Decision queue arrives in 174.6 (00_pursuit.yaml + bid/no-bid log).",
    placeholder: true,
  });

  items.push({
    icon: "clock-alert",
    accent: "magenta",
    label: "Intel freshness",
    detail:
      intelAgeDays === null
        ? "No cross-opp intel captured yet."
        : intelAgeDays > ARIADNE_STALE_INTEL_DAYS
          ? `Last intel was ${intelAgeDays}d ago — refresh customer/competitor reads.`
          : `Last intel ${intelAgeDays}d ago — within ${ARIADNE_STALE_INTEL_DAYS}d window.`,
  });

  items.push({
    icon: "inbox",
    accent: "lime",
    label: "Raw notes awaiting promotion",
    detail: inbox.length
      ? `${inbox.length} note${inbox.length === 1 ? "" : "s"} in global inbox — triage and promote.`
      : "Inbox clear.",
  });

  return items;
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
