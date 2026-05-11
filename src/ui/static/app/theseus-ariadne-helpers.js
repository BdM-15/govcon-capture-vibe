const ARIADNE_BUCKETS = ["inbox", "notes", "llm-wiki", "intel"];
const ARIADNE_ROUTE_PREFIX = "#ariadne/";
const ARIADNE_VIEWS = [
  {
    id: "today",
    label: "Today",
    icon: "sunrise",
    accent: "cyan",
    detail: "Morning brief, fast capture, open actions.",
  },
  {
    id: "pipeline",
    label: "Pipeline",
    icon: "briefcase",
    accent: "lime",
    detail: "Stage board and pursuit portfolio health.",
  },
  {
    id: "decision-queue",
    label: "Decision Queue",
    icon: "gavel",
    accent: "magenta",
    detail: "Near-term gates, missing PWin, blocked pursuits.",
  },
  {
    id: "intel-desk",
    label: "Intel Desk",
    icon: "satellite",
    accent: "magenta",
    detail: "Cross-opp intel capture and freshness view.",
  },
  {
    id: "opp-360",
    label: "Opp 360",
    icon: "orbit",
    accent: "cyan",
    detail: "Per-opportunity summaries with next-action context.",
  },
  {
    id: "knowledge",
    label: "Knowledge",
    icon: "book-open-text",
    accent: "lime",
    detail: "Inbox, notes, wiki pages, promotion backlog.",
  },
  {
    id: "agent-ops",
    label: "Agent Ops",
    icon: "bot",
    accent: "amber",
    detail: "Skills, chains, studio, ingest command lanes.",
  },
];
const ARIADNE_VIEW_IDS = new Set(ARIADNE_VIEWS.map((view) => view.id));
const ARIADNE_LANE_VIEWS = {
  ingest: "agent-ops",
  intel: "intel-desk",
  knowledge: "knowledge",
  skills: "agent-ops",
  chains: "agent-ops",
  studio: "agent-ops",
};

const theseusSafeArray = function theseusSafeArray(value) {
  return Array.isArray(value) ? value : [];
};

const theseusNormalizeAriadneView = function theseusNormalizeAriadneView(value) {
  const key = String(value || "")
    .trim()
    .toLowerCase();
  return ARIADNE_VIEW_IDS.has(key) ? key : "today";
};

const theseusAriadneHashForView = function theseusAriadneHashForView(view) {
  return `${ARIADNE_ROUTE_PREFIX}${theseusNormalizeAriadneView(view)}`;
};

const theseusReadAriadneHashView = function theseusReadAriadneHashView() {
  if (typeof window === "undefined") return null;
  const hash = String(window.location.hash || "");
  if (!hash.startsWith(ARIADNE_ROUTE_PREFIX)) return null;
  return theseusNormalizeAriadneView(hash.slice(ARIADNE_ROUTE_PREFIX.length));
};

const theseusAriadneBucket = function theseusAriadneBucket(app, bucket) {
  return theseusSafeArray(app.ariadne?.buckets?.[bucket]);
};

window.theseusAriadneViews = function theseusAriadneViews() {
  return ARIADNE_VIEWS;
};

window.theseusAriadneView = function theseusAriadneView(app) {
  return theseusNormalizeAriadneView(
    app?.ariadne?.view || theseusReadAriadneHashView() || "today",
  );
};

window.theseusAriadneViewMeta = function theseusAriadneViewMeta(app) {
  const current = window.theseusAriadneView(app);
  return ARIADNE_VIEWS.find((view) => view.id === current) || ARIADNE_VIEWS[0];
};

window.theseusAriadneIsView = function theseusAriadneIsView(app, view) {
  return window.theseusAriadneView(app) === theseusNormalizeAriadneView(view);
};

window.theseusSetAriadneView = function theseusSetAriadneView(
  app,
  view,
  syncHash = true,
) {
  const next = theseusNormalizeAriadneView(view);
  if (app.ariadne) app.ariadne.view = next;
  if (app.active !== "dashboard") app.active = "dashboard";
  if (syncHash && typeof window !== "undefined") {
    const hash = theseusAriadneHashForView(next);
    if (window.location.hash !== hash) {
      window.location.hash = hash;
    }
  }
  window.theseusAfterRender(app);
};

window.theseusAriadneInitRouting = function theseusAriadneInitRouting(app) {
  const hashView = theseusReadAriadneHashView();
  if (hashView && app.ariadne) app.ariadne.view = hashView;
  if (app._ariadneHashBound || typeof window === "undefined") return;
  app._ariadneHashBound = true;
  app._ariadneHashHandler = () => {
    const next = theseusReadAriadneHashView();
    if (!next) return;
    if (app.active !== "dashboard") app.active = "dashboard";
    if (app.ariadne?.view !== next) app.ariadne.view = next;
    else window.theseusAfterRender(app);
  };
  window.addEventListener("hashchange", app._ariadneHashHandler);
};

window.theseusActivateNavItem = function theseusActivateNavItem(app, item) {
  if (!item?.id) return;
  if (item.id === "dashboard") {
    window.theseusSetAriadneView(
      app,
      app?.ariadne?.view || theseusReadAriadneHashView() || "today",
    );
    return;
  }
  app.active = item.id;
};

window.theseusAriadneOpenNewOpportunity =
  function theseusAriadneOpenNewOpportunity(app) {
    window.theseusSetAriadneView(app, "pipeline");
    app.openWorkspaceModal();
  };

window.theseusAriadneRouteLane = function theseusAriadneRouteLane(app, lane) {
  window.theseusSetAriadneView(
    app,
    ARIADNE_LANE_VIEWS[lane] || "today",
  );
};

window.theseusAriadneFocusCapture = function theseusAriadneFocusCapture(
  app,
  bucket = "inbox",
  view = "today",
) {
  if (app.ariadne?.capture) app.ariadne.capture.bucket = bucket;
  window.theseusSetAriadneView(app, view);
  requestAnimationFrame(() => {
    document
      .querySelector("[data-testid=ariadne-capture-desk] textarea")
      ?.focus();
  });
};

window.theseusAriadnePortfolioBrief =
  async function theseusAriadnePortfolioBrief(app) {
    window.theseusSetAriadneView(app, "pipeline");
    await window.theseusAriadneAsk(
      app,
      "Give me a capture manager portfolio brief across all active Theseus workspaces. Focus on opportunity status, missing intel, compliance risk, proposal-product status, and next decisions.",
    );
  };

const ARIADNE_PURSUIT_STAGES = new Set([
  "identify",
  "qualify",
  "capture",
  "proposal",
  "submitted",
  "award",
]);

const theseusAriadneParseDueMs = function theseusAriadneParseDueMs(value) {
  const raw = String(value || "").trim();
  if (!raw) return null;
  const iso = raw.length <= 10 ? `${raw}T00:00:00Z` : raw;
  const ms = Date.parse(iso);
  return Number.isFinite(ms) ? ms : null;
};

const theseusAriadneDaysUntil = function theseusAriadneDaysUntil(value) {
  const dueMs = theseusAriadneParseDueMs(value);
  if (dueMs === null) return null;
  return Math.ceil((dueMs - Date.now()) / (ARIADNE_DAY_SECONDS * 1000));
};

const theseusAriadneDueLabel = function theseusAriadneDueLabel(value) {
  const days = theseusAriadneDaysUntil(value);
  if (days === null) return "-";
  if (days < 0) return `${Math.abs(days)}d late`;
  if (days === 0) return "today";
  return `${days}d`;
};

const theseusAriadneReadinessClass = function theseusAriadneReadinessClass(
  score,
) {
  if (score === null) return "bg-ink-800 border-edge";
  if (score >= 4) return "bg-neon-lime/70 border-neon-lime/40";
  if (score >= 3) return "bg-neon-cyan/60 border-neon-cyan/40";
  if (score >= 2) return "bg-neon-amber/60 border-neon-amber/40";
  return "bg-neon-magenta/50 border-neon-magenta/40";
};

const theseusAriadnePwinTitle = function theseusAriadnePwinTitle(pursuit) {
  if (!pursuit) return "";
  const headline = [];
  if (pursuit.source_path) headline.push(`source: ${pursuit.source_path}`);
  if (pursuit.pwin?.value !== null && pursuit.pwin?.value !== undefined) {
    headline.push(
      `PWin ${pursuit.pwin.value}% / ${pursuit.pwin.confidence || "low"} / ${pursuit.pwin.trend || "flat"}`,
    );
  }
  const drivers = theseusSafeArray(pursuit.pwin_drivers).map((driver) => {
    const next = driver.next_action ? ` | next: ${driver.next_action}` : "";
    return `${driver.label}: ${driver.score}/5 @ ${driver.weight}%${next}`;
  });
  return [...headline, ...drivers].filter(Boolean).join("\n");
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
        pursuit: inventory.pursuit ?? null,
      };
    })
    .sort((left, right) => {
      if (left.is_active !== right.is_active) return left.is_active ? -1 : 1;
      return (
        (right.documents || 0) - (left.documents || 0) ||
        left.name.localeCompare(right.name)
      );
    });
};

window.theseusAriadneStage = function theseusAriadneStage(row) {
  const pursuitStage = String(row?.pursuit?.stage || "")
    .trim()
    .toLowerCase();
  if (ARIADNE_PURSUIT_STAGES.has(pursuitStage)) return pursuitStage;
  if (!row || (!row.documents && !row.entities && !row.neo4j_nodes))
    return "intake";
  if ((row.entities || 0) > 0 && (row.neo4j_nodes || 0) > 0)
    return "knowledge-ready";
  if ((row.documents || 0) > 0) return "processing";
  return "staged";
};

window.theseusAriadneStageClass = function theseusAriadneStageClass(row) {
  const stage = window.theseusAriadneStage(row);
  if (stage === "award" || stage === "submitted")
    return "bg-neon-lime/10 text-neon-lime border-neon-lime/30";
  if (stage === "proposal")
    return "bg-neon-magenta/10 text-neon-magenta border-neon-magenta/30";
  if (stage === "capture")
    return "bg-neon-cyan/10 text-neon-cyan border-neon-cyan/30";
  if (stage === "qualify" || stage === "identify")
    return "bg-neon-amber/10 text-neon-amber border-neon-amber/30";
  if (stage === "knowledge-ready")
    return "bg-neon-lime/10 text-neon-lime border-neon-lime/30";
  if (stage === "processing")
    return "bg-neon-cyan/10 text-neon-cyan border-neon-cyan/30";
  if (stage === "staged")
    return "bg-neon-amber/10 text-neon-amber border-neon-amber/30";
  return "bg-ink-800 text-slate-400 border-edge";
};

// 174.4b+: Command-center KPIs answer the 5 morning questions.
// Pursuit schema now feeds gate-driven dashboard signals where available.
const ARIADNE_DAY_SECONDS = 86400;
const ARIADNE_STALE_INTEL_DAYS = 14;

const theseusAriadneNowSec = function theseusAriadneNowSec() {
  return Date.now() / 1000;
};

const theseusAriadneRecentEntries = function theseusAriadneRecentEntries(
  entries,
  withinDays,
) {
  const cutoff = theseusAriadneNowSec() - withinDays * ARIADNE_DAY_SECONDS;
  return entries.filter((entry) => (entry.modified_at || 0) >= cutoff);
};

window.theseusAriadneMetrics = function theseusAriadneMetrics(app) {
  const rows = window.theseusAriadneWorkspaceRows(app);
  const inbox = theseusAriadneBucket(app, "inbox");
  const intel = theseusAriadneBucket(app, "intel");
  const decisionsDue = rows.filter((row) => {
    const days = theseusAriadneDaysUntil(row.pursuit?.gate?.due);
    const pwin = Number(row.pursuit?.pwin?.value);
    const missingPwin = !Number.isFinite(pwin);
    return (days !== null && days <= 7) || missingPwin;
  });
  const upcomingGates = rows.filter((row) => {
    const days = theseusAriadneDaysUntil(row.pursuit?.gate?.due);
    return days !== null && days <= 7;
  });
  const recentIntel = theseusAriadneRecentEntries(
    intel,
    ARIADNE_STALE_INTEL_DAYS,
  );
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
      value: decisionsDue.length,
      hint: decisionsDue.length
        ? "near gate or missing PWin"
        : "no immediate decision flags",
      icon: "gavel",
      accent: "magenta",
      color: "text-neon-magenta",
      placeholder: false,
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
      value: upcomingGates.length,
      hint: upcomingGates.length
        ? upcomingGates
            .map((row) => row.name)
            .slice(0, 2)
            .join(" · ")
        : "no near-term gates",
      icon: "calendar-clock",
      accent: "lime",
      color: "text-neon-lime",
      placeholder: false,
    },
  ];
};

// Morning Brief: answers "what changed since yesterday?" + recommended actions.
window.theseusAriadneMorningBrief = function theseusAriadneMorningBrief(app) {
  const buckets = ARIADNE_BUCKETS.flatMap((bucket) =>
    theseusAriadneBucket(app, bucket).map((entry) => ({
      ...entry,
      _bucket: bucket,
    })),
  );
  const last24h = theseusAriadneRecentEntries(buckets, 1);
  const last24hByBucket = ARIADNE_BUCKETS.reduce((acc, bucket) => {
    acc[bucket] = last24h.filter((entry) => entry._bucket === bucket).length;
    return acc;
  }, {});

  const inbox = theseusAriadneBucket(app, "inbox");
  const rows = window.theseusAriadneWorkspaceRows(app);
  const blocked = rows
    .map((row) => ({
      row,
      days: theseusAriadneDaysUntil(row.pursuit?.gate?.due),
    }))
    .filter((entry) => entry.days !== null && entry.days <= 7)
    .sort((left, right) => left.days - right.days)[0];
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
        ARIADNE_BUCKETS.map(
          (bucket) => `${last24hByBucket[bucket]} ${bucket}`,
        ).join(" · ") +
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
    detail: blocked
      ? `${blocked.row.name}: ${blocked.row.pursuit?.gate?.name || "gate"} due ${theseusAriadneDueLabel(blocked.row.pursuit?.gate?.due)}.`
      : rows.length
        ? "No gate deadlines inside the next 7 days."
        : "No pursuits yet — create a workspace to start tracking.",
    placeholder: false,
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

// Action Queue (174.4b slice 2): unified to-do list across vault + workspaces.
// Each row = one capture-manager action with a single primary CTA.
// Categories: triage (inbox notes), ingest (unprocessed inputs),
// extract (docs without entities), refresh (stale intel).
// 174.6 will add: decision (bid/no-bid), gate (gate review due),
// risk (risk register entries past mitigation date).
window.theseusAriadneActionQueue = function theseusAriadneActionQueue(
  app,
  limit = 12,
) {
  const actions = [];
  const inbox = theseusAriadneBucket(app, "inbox");
  inbox.forEach((entry) => {
    actions.push({
      key: `triage:${entry.path}`,
      kind: "triage",
      icon: "inbox",
      accent: "cyan",
      title: entry.frontmatter?.title || entry.path,
      detail: `Promote raw note from inbox · ${entry.path}`,
      cta: "Promote",
      path: entry.path,
      sort: entry.modified_at || 0,
    });
  });

  const rows = window.theseusAriadneWorkspaceRows(app);
  rows.forEach((row) => {
    if ((row.inputs_files || 0) > 0 && (row.documents || 0) === 0) {
      actions.push({
        key: `ingest:${row.name}`,
        kind: "ingest",
        icon: "upload-cloud",
        accent: "amber",
        title: row.name,
        detail: `${row.inputs_files} input file${row.inputs_files === 1 ? "" : "s"} unprocessed — kick off ingest.`,
        cta: "Open ingest",
        workspace: row.name,
        sort: 1e12,
      });
    } else if ((row.documents || 0) > 0 && (row.entities || 0) === 0) {
      actions.push({
        key: `extract:${row.name}`,
        kind: "extract",
        icon: "git-fork",
        accent: "amber",
        title: row.name,
        detail: `${row.documents} doc${row.documents === 1 ? "" : "s"} ingested but no entities yet — re-run extraction.`,
        cta: "Open workspace",
        workspace: row.name,
        sort: 9e11,
      });
    }
  });

  const intel = theseusAriadneBucket(app, "intel");
  const lastIntel = intel.reduce(
    (max, entry) => Math.max(max, entry.modified_at || 0),
    0,
  );
  const intelAgeDays = lastIntel
    ? Math.floor((theseusAriadneNowSec() - lastIntel) / ARIADNE_DAY_SECONDS)
    : null;
  if (intelAgeDays !== null && intelAgeDays > ARIADNE_STALE_INTEL_DAYS) {
    actions.push({
      key: "refresh:intel",
      kind: "refresh",
      icon: "clock-alert",
      accent: "magenta",
      title: "Cross-opp intel stale",
      detail: `Last intel entry ${intelAgeDays}d ago — capture customer/competitor read.`,
      cta: "Capture intel",
      sort: 8e11,
    });
  }

  actions.sort((a, b) => (b.sort || 0) - (a.sort || 0));
  return actions.slice(0, limit);
};

window.theseusAriadneDecisionQueue = function theseusAriadneDecisionQueue(
  app,
  limit = 12,
) {
  const cards = window.theseusAriadneOpportunityCards(app);
  const items = cards
    .map((card) => {
      const gateDays = theseusAriadneDaysUntil(card.gate_due?.date);
      const reasons = [];
      if (gateDays !== null && gateDays <= 14) {
        reasons.push(
          `${card.gate_due?.name || "gate"} ${theseusAriadneDueLabel(card.gate_due?.date)}`,
        );
      }
      if (!Number.isFinite(card.pwin?.value)) reasons.push("PWin unset");
      if (card.top_blocker?.detail) reasons.push(card.top_blocker.detail);
      const lowReadiness = card.readiness
        .filter((bar) => bar.score !== null && bar.score <= 2)
        .map((bar) => bar.dim)
        .slice(0, 2);
      if (lowReadiness.length) {
        reasons.push(`low readiness: ${lowReadiness.join(", ")}`);
      }
      return {
        key: `decision:${card.name}`,
        workspace: card.name,
        stage: card.stage,
        stage_class: card.stage_class,
        gate_label: card.gate_due?.label || "-",
        pwin_label: card.pwin?.label || "-",
        reasons,
        priority:
          gateDays !== null && gateDays <= 7
            ? 4
            : gateDays !== null && gateDays <= 14
              ? 3
              : card.top_blocker
                ? 2
                : 1,
      };
    })
    .filter((item) => item.reasons.length);

  items.sort((left, right) => {
    if (left.priority !== right.priority) return right.priority - left.priority;
    return left.workspace.localeCompare(right.workspace);
  });
  return items.slice(0, limit);
};

window.theseusAriadneDecisionSummary = function theseusAriadneDecisionSummary(
  app,
) {
  const cards = window.theseusAriadneOpportunityCards(app);
  const queue = window.theseusAriadneDecisionQueue(app, 999);
  const urgent = cards.filter((card) => {
    const days = theseusAriadneDaysUntil(card.gate_due?.date);
    return days !== null && days <= 7;
  });
  const missingPwin = cards.filter((card) => !Number.isFinite(card.pwin?.value));
  const lowReadiness = cards.filter((card) =>
    card.readiness.some((bar) => bar.score !== null && bar.score <= 2),
  );
  const blocked = cards.filter((card) => card.top_blocker?.detail);

  return [
    {
      label: "queued",
      value: queue.length,
      detail: queue.length ? queue[0].workspace : "decision pressure clear",
      icon: "gavel",
      accent: "magenta",
    },
    {
      label: "gate ≤ 7d",
      value: urgent.length,
      detail: urgent.length
        ? urgent
            .map((card) => card.name)
            .slice(0, 2)
            .join(" · ")
        : "no immediate gates",
      icon: "calendar-clock",
      accent: "amber",
    },
    {
      label: "missing PWin",
      value: missingPwin.length,
      detail: missingPwin.length
        ? missingPwin
            .map((card) => card.name)
            .slice(0, 2)
            .join(" · ")
        : "all scored",
      icon: "target",
      accent: "cyan",
    },
    {
      label: "blocked / low-readiness",
      value: Math.max(blocked.length, lowReadiness.length),
      detail: blocked.length
        ? blocked
            .map((card) => card.name)
            .slice(0, 2)
            .join(" · ")
        : lowReadiness.length
          ? lowReadiness
              .map((card) => card.name)
              .slice(0, 2)
              .join(" · ")
          : "no visible pressure",
      icon: "shield-alert",
      accent: "lime",
    },
  ];
};

window.theseusAriadneDecisionEscalations =
  function theseusAriadneDecisionEscalations(app, limit = 4) {
    return window.theseusAriadneDecisionQueue(app, 999)
      .map((item) => ({
        ...item,
        primary_reason: item.reasons[0] || "decision review needed",
        extra_reasons: Math.max(item.reasons.length - 1, 0),
      }))
      .slice(0, limit);
  };

window.theseusAriadneTodayFocus = function theseusAriadneTodayFocus(
  app,
  limit = 4,
) {
  const rows = window.theseusAriadneWorkspaceRows(app);
  const items = [];
  const seen = new Set();
  const pushItem = (item) => {
    if (!item || seen.has(item.key)) return;
    seen.add(item.key);
    items.push(item);
  };

  const decision = window.theseusAriadneDecisionQueue(app, 1)[0];
  if (decision) {
    pushItem({
      key: `decision:${decision.workspace}`,
      kind: "decision",
      icon: "gavel",
      accent: "magenta",
      title: decision.workspace,
      detail: decision.reasons.join(" · "),
      cta: "Review decision",
      workspace: decision.workspace,
      stage: decision.stage,
      stage_class: decision.stage_class,
    });
  }

  const ingest = rows.find(
    (row) => (row.inputs_files || 0) > 0 && (row.documents || 0) === 0,
  );
  if (ingest) {
    pushItem({
      key: `ingest:${ingest.name}`,
      kind: "ingest",
      icon: "upload-cloud",
      accent: "amber",
      title: ingest.name,
      detail: `${ingest.inputs_files} input file${ingest.inputs_files === 1 ? "" : "s"} still waiting for ingest.`,
      cta: "Open ingest",
      workspace: ingest.name,
      stage: window.theseusAriadneStage(ingest),
      stage_class: window.theseusAriadneStageClass(ingest),
    });
  }

  const extract = rows.find(
    (row) =>
      row.name !== ingest?.name &&
      (row.documents || 0) > 0 &&
      (row.entities || 0) === 0,
  );
  if (extract) {
    pushItem({
      key: `extract:${extract.name}`,
      kind: "extract",
      icon: "git-fork",
      accent: "amber",
      title: extract.name,
      detail: `${extract.documents} document${extract.documents === 1 ? "" : "s"} loaded but no entities extracted yet.`,
      cta: "Open workspace",
      workspace: extract.name,
      stage: window.theseusAriadneStage(extract),
      stage_class: window.theseusAriadneStageClass(extract),
    });
  }

  const inbox = theseusAriadneBucket(app, "inbox");
  if (inbox.length) {
    pushItem({
      key: "inbox:backlog",
      kind: "inbox",
      icon: "inbox",
      accent: "cyan",
      title: "Inbox backlog",
      detail: `${inbox.length} note${inbox.length === 1 ? "" : "s"} waiting for promotion or routing.`,
      cta: "Review inbox",
    });
  }

  const intel = theseusAriadneBucket(app, "intel");
  const lastIntel = intel.reduce(
    (max, entry) => Math.max(max, entry.modified_at || 0),
    0,
  );
  const intelAgeDays = lastIntel
    ? Math.floor((theseusAriadneNowSec() - lastIntel) / ARIADNE_DAY_SECONDS)
    : null;
  if (intelAgeDays === null || intelAgeDays > ARIADNE_STALE_INTEL_DAYS) {
    pushItem({
      key: "intel:freshness",
      kind: "refresh",
      icon: "clock-alert",
      accent: "magenta",
      title: "Intel freshness",
      detail:
        intelAgeDays === null
          ? "No cross-opp intel captured yet."
          : `Last intel ${intelAgeDays}d ago — refresh customer and competitor read.`,
      cta: "Capture intel",
    });
  }

  if (!items.length) {
    const lead =
      window.theseusAriadneOpportunityCards(app).find((card) => card.is_active) ||
      window.theseusAriadneOpportunityCards(app)[0];
    if (lead) {
      pushItem({
        key: `workspace:${lead.name}`,
        kind: "workspace",
        icon: "briefcase",
        accent: "lime",
        title: lead.name,
        detail: `${lead.stage} stage · PWin ${lead.pwin?.label || "-"} · ${lead.gate_due?.label || "no gate set"}`,
        cta: "Open workspace",
        workspace: lead.name,
        stage: lead.stage,
        stage_class: lead.stage_class,
      });
    }
  }

  return items.slice(0, limit);
};

window.theseusAriadnePipelineSummary = function theseusAriadnePipelineSummary(
  app,
) {
  const cards = window.theseusAriadneOpportunityCards(app);
  const nearGates = cards.filter((card) => {
    const days = theseusAriadneDaysUntil(card.gate_due?.date);
    return days !== null && days <= 14;
  });
  const scoredPwins = cards
    .map((card) => card.pwin?.value)
    .filter((value) => Number.isFinite(value));
  const avgPwin = scoredPwins.length
    ? Math.round(
        scoredPwins.reduce((sum, value) => sum + value, 0) /
          scoredPwins.length,
      )
    : null;
  const captureAndProposal = cards.filter(
    (card) => card.stage === "capture" || card.stage === "proposal",
  );
  const lateStage = cards.filter(
    (card) =>
      card.stage === "proposal" ||
      card.stage === "submitted" ||
      card.stage === "award",
  );

  return [
    {
      label: "tracked",
      value: cards.length,
      detail: `${captureAndProposal.length} in capture / proposal`,
      icon: "briefcase",
      accent: "cyan",
    },
    {
      label: "near gates ≤ 14d",
      value: nearGates.length,
      detail: nearGates.length
        ? nearGates
            .map((card) => card.name)
            .slice(0, 2)
            .join(" · ")
        : "no gate pressure",
      icon: "calendar-clock",
      accent: "magenta",
    },
    {
      label: "avg PWin",
      value: avgPwin === null ? "-" : `${avgPwin}%`,
      detail: scoredPwins.length
        ? `${scoredPwins.length} pursuit${scoredPwins.length === 1 ? "" : "s"} scored`
        : "no PWin values yet",
      icon: "target",
      accent: "lime",
    },
    {
      label: "late-stage",
      value: lateStage.length,
      detail: lateStage.length
        ? lateStage
            .map((card) => card.name)
            .slice(0, 2)
            .join(" · ")
        : "nothing submitted yet",
      icon: "trophy",
      accent: "amber",
    },
  ];
};

window.theseusAriadnePipelinePressure =
  function theseusAriadnePipelinePressure(app, limit = 6) {
    const items = window.theseusAriadneOpportunityCards(app)
      .map((card) => {
        const reasons = [];
        let score = 0;
        const gateDays = theseusAriadneDaysUntil(card.gate_due?.date);
        if (gateDays !== null && gateDays <= 7) {
          score += 5;
          reasons.push(
            `${card.gate_due?.name || "gate"} ${theseusAriadneDueLabel(card.gate_due?.date)}`,
          );
        } else if (gateDays !== null && gateDays <= 14) {
          score += 4;
          reasons.push(
            `${card.gate_due?.name || "gate"} ${theseusAriadneDueLabel(card.gate_due?.date)}`,
          );
        }
        if (!Number.isFinite(card.pwin?.value)) {
          score += 2;
          reasons.push("PWin unset");
        }
        if (card.top_blocker?.detail) {
          score += 2;
          reasons.push(card.top_blocker.detail);
        }
        if (card.intel_age_days === null) {
          score += 1;
          reasons.push("no tagged intel");
        } else if (card.intel_age_days > ARIADNE_STALE_INTEL_DAYS) {
          score += 2;
          reasons.push(`${card.intel_age_days}d since intel`);
        }
        const lowReadiness = card.readiness
          .filter((bar) => bar.score !== null && bar.score <= 2)
          .map((bar) => bar.dim)
          .slice(0, 2);
        if (lowReadiness.length) {
          score += 1;
          reasons.push(`low readiness: ${lowReadiness.join(", ")}`);
        }
        return {
          workspace: card.name,
          stage: card.stage,
          stage_class: card.stage_class,
          reasons,
          score,
        };
      })
      .filter((item) => item.score > 0)
      .sort((left, right) => {
        if (left.score !== right.score) return right.score - left.score;
        return left.workspace.localeCompare(right.workspace);
      });

    return items.slice(0, limit);
  };

const theseusAriadneIntelEntriesForWorkspace = function theseusAriadneIntelEntriesForWorkspace(
  row,
  intelEntries,
) {
  const workspaceName = String(row?.name || "").toLowerCase();
  if (!workspaceName) return [];
  return intelEntries.filter((entry) => {
    const tags = (entry.frontmatter?.tags || []).map((tag) =>
      String(tag).toLowerCase(),
    );
    const path = String(entry.path || "").toLowerCase();
    return tags.includes(workspaceName) || path.includes(workspaceName);
  });
};

const theseusAriadneIntelAgeDaysForWorkspace = function theseusAriadneIntelAgeDaysForWorkspace(
  row,
  intelEntries,
) {
  const matchingEntries = theseusAriadneIntelEntriesForWorkspace(
    row,
    intelEntries,
  );
  const lastIntelTs = matchingEntries.reduce(
    (max, entry) => Math.max(max, entry.modified_at || 0),
    0,
  );
  return lastIntelTs
    ? Math.floor((theseusAriadneNowSec() - lastIntelTs) / ARIADNE_DAY_SECONDS)
    : null;
};

const theseusAriadneTimeAgo = function theseusAriadneTimeAgo(value) {
  if (!value) return "-";
  const raw = Number(value);
  const ms = Number.isFinite(raw)
    ? raw < 1000000000000
      ? raw * 1000
      : raw
    : Date.parse(String(value));
  if (!Number.isFinite(ms)) return "-";
  const days = Math.floor((Date.now() - ms) / (ARIADNE_DAY_SECONDS * 1000));
  if (days < 0) return "scheduled";
  if (days === 0) return "today";
  return `${days}d ago`;
};

const theseusAriadneIsoDate = function theseusAriadneIsoDate(ms) {
  if (!Number.isFinite(ms)) return "";
  return new Date(ms).toISOString().slice(0, 10);
};

const theseusAriadneLatestModified = function theseusAriadneLatestModified(entries) {
  return entries.reduce((max, entry) => Math.max(max, entry.modified_at || 0), 0);
};

const theseusAriadneEntryTags = function theseusAriadneEntryTags(entry) {
  return (entry?.frontmatter?.tags || []).map((tag) => String(tag).toLowerCase());
};

const ARIADNE_PATTERN_MODES = ["capture", "intel", "proposal", "color-team"];

const theseusAriadnePatternLabel = function theseusAriadnePatternLabel(value) {
  return value === "color-team" ? "color team" : value;
};

const theseusAriadnePatternFilter = function theseusAriadnePatternFilter(app) {
  const value = String(app?.ariadne?.patternFilter || "all")
    .trim()
    .toLowerCase();
  return value === "all" || ARIADNE_PATTERN_MODES.includes(value) ? value : "all";
};

const theseusAriadnePatternEntries = function theseusAriadnePatternEntries(app) {
  return theseusAriadneBucket(app, "intel")
    .filter((entry) => theseusAriadneEntryTags(entry).includes("pattern"))
    .slice()
    .sort((left, right) => (right.modified_at || 0) - (left.modified_at || 0))
    .map((entry) => {
      const tags = theseusAriadneEntryTags(entry);
      return {
        ...entry,
        title: theseusAriadneEntryTitle(entry),
        age_label: theseusAriadneTimeAgo(entry.modified_at),
        mode_tags: ARIADNE_PATTERN_MODES.filter((mode) => tags.includes(mode)),
      };
    });
};

const theseusAriadneEntryTitle = function theseusAriadneEntryTitle(entry) {
  return entry?.frontmatter?.title || entry?.path || "untitled";
};

const theseusAriadneLowestReadiness = function theseusAriadneLowestReadiness(
  readiness,
) {
  return readiness
    .filter((bar) => Number.isFinite(bar.score))
    .sort((left, right) => left.score - right.score)[0] || null;
};

const theseusAriadneSkillForReadiness = function theseusAriadneSkillForReadiness(
  dim,
) {
  const mapping = {
    customer: "grill-me-capture",
    compete: "competitive-intel",
    solution: "proposal-generator",
    team: "grill-me-bid-strategy",
    price: "price-to-win",
    compliance: "compliance-auditor",
    proposal: "proposal-generator",
  };
  return mapping[dim] || "grill-me-govcon";
};

const theseusAriadneSkillLabel = function theseusAriadneSkillLabel(skill) {
  return String(skill || "")
    .split("-")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
};

const theseusAriadneNextActionForCard = function theseusAriadneNextActionForCard(
  row,
  blocker,
  readiness,
) {
  const low = theseusAriadneLowestReadiness(readiness);
  let skill = "grill-me-govcon";
  let label = "Pressure-test pursuit";
  let detail = "No major blocker surfaced; run focused capture challenge.";
  let icon = "sparkles";
  let accent = "cyan";

  if (blocker?.kind === "ingest") {
    skill = "govcon-ontology";
    label = "Ingest source material";
    detail = blocker.detail;
    icon = "upload-cloud";
    accent = "amber";
  } else if (blocker?.kind === "extract") {
    skill = "govcon-ontology";
    label = "Repair extraction gap";
    detail = blocker.detail;
    icon = "git-fork";
    accent = "amber";
  } else if (low && low.score <= 3) {
    skill = theseusAriadneSkillForReadiness(low.dim);
    label = `Raise ${low.dim} readiness`;
    detail = `${low.dim} readiness ${low.score}/5; use ${theseusAriadneSkillLabel(skill)} next.`;
    icon = "target";
    accent = low.score <= 2 ? "magenta" : "amber";
  } else if (row?.pursuit?.stage === "proposal") {
    skill = "proposal-generator";
    label = "Draft proposal roadmap";
    detail = "Proposal stage; build outline, win themes, and compliance trail.";
    icon = "file-text";
    accent = "magenta";
  } else if (row?.pursuit?.stage === "capture") {
    skill = "grill-me-capture";
    label = "Stress-test capture plan";
    detail = "Capture stage; challenge customer, competitor, and discriminator assumptions.";
    icon = "flame";
    accent = "cyan";
  }

  return {
    skill,
    label,
    detail,
    icon,
    accent,
    cta: theseusAriadneSkillLabel(skill),
    prompt: `${label} for workspace ${row?.name || "this pursuit"}. Use available Theseus workspace evidence, global llm-wiki context, and current pursuit metadata. Start with exact gaps and next 3 actions.`,
  };
};

const theseusAriadneAnalysisPosture = function theseusAriadneAnalysisPosture(
  row,
  counts,
) {
  if ((counts.inputs || 0) > 0 && (counts.documents || 0) === 0) {
    return {
      label: "ingest pending",
      detail: `${counts.inputs} input file${counts.inputs === 1 ? "" : "s"} waiting before analysis can be trusted.`,
      skill: "govcon-ontology",
      accent: "amber",
      prompt: `For workspace ${row.name}, identify what source material still needs ingest before compliant outline, audit, or fit assessment can run.`,
    };
  }
  if ((counts.documents || 0) > 0 && (counts.entities || 0) === 0) {
    return {
      label: "extraction needed",
      detail: `${counts.documents} document${counts.documents === 1 ? "" : "s"} loaded but ontology entities are missing.`,
      skill: "govcon-ontology",
      accent: "amber",
      prompt: `For workspace ${row.name}, diagnose extraction readiness and list next steps to get requirements, CLINs, evaluation factors, and instructions into the KG.`,
    };
  }
  if ((counts.entities || 0) > 0) {
    return {
      label: "analysis ready",
      detail: `${counts.entities} KG entities available for compliance audit, proposal outline, and solutioning prompts.`,
      skill: "compliance-auditor",
      accent: "lime",
      prompt: `Run a compliance-roadmap style review for workspace ${row.name}. Summarize instruction/evaluation coverage, requirement gaps, and which llm-wiki capability notes could mitigate gaps.`,
    };
  }
  return {
    label: "workspace empty",
    detail: "No processed content yet; stage source docs before analysis.",
    skill: "govcon-ontology",
    accent: "amber",
    prompt: `For workspace ${row.name}, recommend first ingest and ontology extraction steps.`,
  };
};

const theseusAriadneSuggestedGateDate = function theseusAriadneSuggestedGateDate(
  row,
) {
  const proposalMs = theseusAriadneParseDueMs(row?.pursuit?.proposal_due);
  if (!Number.isFinite(proposalMs)) return "";
  const stage = window.theseusAriadneStage(row);
  const offsets = {
    identify: 45,
    qualify: 35,
    capture: 21,
    proposal: 10,
    submitted: 0,
    award: 0,
  };
  const offset = offsets[stage] ?? 21;
  const targetMs = proposalMs - offset * ARIADNE_DAY_SECONDS * 1000;
  return targetMs < Date.now()
    ? theseusAriadneIsoDate(Date.now())
    : theseusAriadneIsoDate(targetMs);
};

const theseusAriadneGateReviewForCard = function theseusAriadneGateReviewForCard(
  row,
) {
  const gate = row?.pursuit?.gate || {};
  const suggested = theseusAriadneSuggestedGateDate(row);
  return {
    current: gate.name || "gate unset",
    due: gate.due || "",
    due_label: gate.due ? theseusAriadneDueLabel(gate.due) : "-",
    suggested,
    suggested_label: suggested ? theseusAriadneDueLabel(suggested) : "proposal due unset",
  };
};

const theseusAriadneSolutioningChips = function theseusAriadneSolutioningChips(
  row,
  readiness,
) {
  const low = theseusAriadneLowestReadiness(readiness);
  const base = [
    {
      skill: "grill-me-capture",
      label: "Capture grill",
      icon: "flame",
      prompt: `Grill me on the capture plan for workspace ${row.name}. Use customer intel, competitor clues, win themes, proof points, and missing assumptions. One hard question at a time.`,
    },
    {
      skill: "proposal-generator",
      label: "Win themes",
      icon: "sparkles",
      prompt: `Generate and stress-test win themes for workspace ${row.name}. Tie each theme to evaluation factors, requirements, proof points, and llm-wiki capability evidence where available.`,
    },
    {
      skill: "grill-me-proposal",
      label: "Pink-team risk",
      icon: "shield-alert",
      prompt: `Stress-test proposal strategy for workspace ${row.name}. Focus on traceability, discriminator credibility, hot-button coverage, and proof-point gaps.`,
    },
  ];
  if (low?.dim === "price" || row?.pursuit?.stage === "proposal") {
    base.push({
      skill: "price-to-win",
      label: "PTW check",
      icon: "calculator",
      prompt: `Build a price-to-win risk check for workspace ${row.name}. Focus on scope magnitude, likely cost drivers, incumbent pressure, and pricing assumptions to verify.`,
    });
  }
  return base.slice(0, 3);
};

// Opportunity Card (174.4b slice 3): per-pursuit summary card.
// Today: name + heuristic phase + derivable blocker + intel age.
// 174.6: agency, PWin + confidence + trend, gate_due, 7 readiness bars,
// proposal_due — all read from `pursuits/<slug>/00_pursuit.yaml`.
const ARIADNE_READINESS_DIMS = [
  "customer",
  "compete",
  "solution",
  "team",
  "price",
  "compliance",
  "proposal",
];

window.theseusAriadneOpportunityCards = function theseusAriadneOpportunityCards(
  app,
) {
  const rows = window.theseusAriadneWorkspaceRows(app);
  const queue = window.theseusAriadneActionQueue(app, 99);
  const intel = theseusAriadneBucket(app, "intel");

  return rows.map((row) => {
    const pursuit = row.pursuit || null;
    const blocker = queue.find((action) => action.workspace === row.name);
    const intelAgeDays = theseusAriadneIntelAgeDaysForWorkspace(row, intel);
    const intelEntries = theseusAriadneIntelEntriesForWorkspace(row, intel)
      .sort((left, right) => (right.modified_at || 0) - (left.modified_at || 0))
      .slice(0, 3)
      .map((entry) => ({
        title: theseusAriadneEntryTitle(entry),
        path: entry.path,
        age_label: theseusAriadneTimeAgo(entry.modified_at),
        preview: entry.preview || "",
      }));
    const pwinValue = Number(pursuit?.pwin?.value);
    const gateDue = pursuit?.gate?.due || null;
    const proposalDue = pursuit?.proposal_due || null;
    const counts = {
      documents: row.documents || 0,
      entities: row.entities || 0,
      inputs: row.inputs_files || 0,
    };
    const readiness = ARIADNE_READINESS_DIMS.map((dim) => {
      const raw = Number(pursuit?.readiness?.[dim]);
      const score = Number.isFinite(raw)
        ? Math.max(0, Math.min(5, raw))
        : null;
      return {
        dim,
        score,
        title: `${dim}: ${score === null ? "unset" : `${score}/5`}`,
        class_name: theseusAriadneReadinessClass(score),
      };
    });
    const analysisPosture = theseusAriadneAnalysisPosture(row, counts);

    return {
      name: row.name,
      is_active: row.is_active,
      stage: window.theseusAriadneStage(row),
      stage_class: window.theseusAriadneStageClass(row),
      pursuit,
      agency: pursuit?.agency || null,
      pwin: pursuit
        ? {
            value: Number.isFinite(pwinValue) ? pwinValue : null,
            label: Number.isFinite(pwinValue)
              ? `${Math.round(pwinValue)}%`
              : "-",
            detail: [pursuit.pwin?.confidence, pursuit.pwin?.trend]
              .filter(Boolean)
              .join(" / "),
            title: theseusAriadnePwinTitle(pursuit),
          }
        : null,
      gate_due: pursuit?.gate
        ? {
            name: pursuit.gate.name || "gate",
            date: gateDue,
            label: gateDue ? theseusAriadneDueLabel(gateDue) : "-",
            title: gateDue
              ? `${pursuit.gate.name || "gate"}: ${gateDue}`
              : pursuit.gate.name || "gate",
          }
        : null,
      proposal_due: proposalDue
        ? {
            date: proposalDue,
            label: theseusAriadneDueLabel(proposalDue),
            title: `proposal due: ${proposalDue}`,
          }
        : null,
      top_blocker: blocker
        ? { kind: blocker.kind, detail: blocker.detail, cta: blocker.cta }
        : null,
      intel_age_days: intelAgeDays,
      intel_entries: intelEntries,
      readiness,
      next_action: theseusAriadneNextActionForCard(row, blocker, readiness),
      analysis_posture: analysisPosture,
      solutioning: theseusAriadneSolutioningChips(row, readiness),
      gate_review: theseusAriadneGateReviewForCard(row),
      counts,
    };
  });
};

// Stage Board (174.4b slice 3): six-column Shipley-aligned board.
// Today: heuristic stage placement off ingest/extraction state.
// 174.6: real placement from pursuit.stage in 00_pursuit.yaml.
const ARIADNE_STAGES = [
  { id: "identify", label: "Identify", accent: "amber" },
  { id: "qualify", label: "Qualify", accent: "amber" },
  { id: "capture", label: "Capture", accent: "cyan" },
  { id: "proposal", label: "Proposal", accent: "magenta" },
  { id: "submitted", label: "Submitted", accent: "lime" },
  { id: "award", label: "Award", accent: "lime" },
];
const ARIADNE_STAGE_IDS = new Set(ARIADNE_STAGES.map((stage) => stage.id));

window.theseusAriadneStageBoard = function theseusAriadneStageBoard(app) {
  const cards = window.theseusAriadneOpportunityCards(app);
  const placement = (card) => {
    if (ARIADNE_STAGE_IDS.has(card.stage)) return card.stage;
    if (card.stage === "intake") return "identify";
    if (card.stage === "staged") return "qualify";
    if (card.stage === "processing") return "capture";
    if (card.stage === "knowledge-ready") return "capture";
    return "identify";
  };
  return ARIADNE_STAGES.map((stage) => ({
    ...stage,
    cards: cards.filter((card) => placement(card) === stage.id),
  }));
};

window.theseusAriadneKnowledgeFeed = function theseusAriadneKnowledgeFeed(
  app,
  limit = 12,
) {
  const entries = [
    ...theseusAriadneBucket(app, "notes").map((entry) => ({
      ...entry,
      kind: "notes",
      accent: "cyan",
    })),
    ...theseusAriadneBucket(app, "llm-wiki").map((entry) => ({
      ...entry,
      kind: "llm-wiki",
      accent: "lime",
    })),
    ...theseusAriadneBucket(app, "inbox").map((entry) => ({
      ...entry,
      kind: "inbox",
      accent: "amber",
    })),
  ];
  entries.sort((left, right) => (right.modified_at || 0) - (left.modified_at || 0));
  return entries.slice(0, limit);
};

window.theseusAriadneKnowledgeSummary = function theseusAriadneKnowledgeSummary(
  app,
) {
  return ARIADNE_BUCKETS.map((bucket) => {
    const entries = theseusAriadneBucket(app, bucket);
    const latest = theseusAriadneLatestModified(entries);
    const labels = {
      inbox: "inbox",
      notes: "notes",
      "llm-wiki": "llm wiki",
      intel: "intel",
    };
    const icons = {
      inbox: "inbox",
      notes: "notebook-text",
      "llm-wiki": "book-open-text",
      intel: "radar",
    };
    const accents = {
      inbox: "amber",
      notes: "cyan",
      "llm-wiki": "lime",
      intel: "magenta",
    };
    return {
      bucket,
      label: labels[bucket] || bucket,
      value: entries.length,
      latest_label: latest ? theseusAriadneTimeAgo(latest) : "empty",
      icon: icons[bucket] || "file-text",
      accent: accents[bucket] || "cyan",
    };
  });
};

window.theseusAriadneWikiLeaderboard = function theseusAriadneWikiLeaderboard(
  app,
  limit = 5,
) {
  return theseusAriadneBucket(app, "llm-wiki")
    .slice()
    .sort((left, right) => (right.modified_at || 0) - (left.modified_at || 0))
    .slice(0, limit)
    .map((entry) => ({
      title: theseusAriadneEntryTitle(entry),
      path: entry.path,
      age_label: theseusAriadneTimeAgo(entry.modified_at),
      preview: entry.preview || "",
    }));
};

const theseusAriadnePromotionStatusAccent = function (status) {
  if (status === "processed") return "lime";
  if (status === "refreshing") return "cyan";
  if (status === "failed") return "magenta";
  return "amber";
};

window.theseusAriadnePromotionRows = function theseusAriadnePromotionRows(
  app,
  limit = 8,
) {
  const activeWorkspace = app.ariadne?.active || app.stats?.workspace || "";
  const byWorkspace = app.ariadne?.promotions || {};
  return Object.entries(byWorkspace)
    .flatMap(([workspace, promotions]) =>
      theseusSafeArray(promotions).map((record) => {
        const status = record.ingestion_status || "pending";
        const busyKey = `${workspace}:${record.source}`;
        return {
          ...record,
          workspace,
          busy_key: busyKey,
          busy: !!app.ariadne?.promotionBusy?.[busyKey],
          is_active_workspace: workspace === activeWorkspace,
          status,
          status_accent: theseusAriadnePromotionStatusAccent(status),
          updated_label: theseusAriadneTimeAgo(
            record.last_refresh_at || record.updated_at || record.promoted_at,
          ),
        };
      }),
    )
    .sort((left, right) => {
      const leftTime = Date.parse(
        left.last_refresh_at || left.updated_at || left.promoted_at || "",
      );
      const rightTime = Date.parse(
        right.last_refresh_at || right.updated_at || right.promoted_at || "",
      );
      return (rightTime || 0) - (leftTime || 0);
    })
    .slice(0, limit);
};

window.theseusAriadneKnowledgeFitSeeds = function theseusAriadneKnowledgeFitSeeds(
  app,
) {
  const wiki = theseusAriadneBucket(app, "llm-wiki");
  const rows = window.theseusAriadneWorkspaceRows(app);
  const readyRows = rows.filter((row) => (row.entities || 0) > 0);
  const promotions = window.theseusAriadnePromotionRows(app, 999);
  const processedPromotions = promotions.filter(
    (record) => record.status === "processed",
  );
  const pendingPromotions = promotions.filter(
    (record) => record.status !== "processed",
  );
  return [
    {
      label: "capability wiki",
      value: wiki.length,
      detail: wiki.length ? "global_wiki-style material present" : "seed company capability notes",
      icon: "book-open-check",
      accent: "lime",
    },
    {
      label: "pursuit KGs",
      value: readyRows.length,
      detail: readyRows.length ? "requirements can be compared later" : "process RFPs first",
      icon: "network",
      accent: "cyan",
    },
    {
      label: "promoted sources",
      value: processedPromotions.length,
      detail: pendingPromotions.length
        ? `${pendingPromotions.length} pending refresh`
        : "manifest-backed round-trip sources",
      icon: "refresh-cw",
      accent: processedPromotions.length ? "lime" : "amber",
    },
  ];
};

window.theseusAriadneRequirementsFitScores = function theseusAriadneRequirementsFitScores(
  app,
  limit = 6,
) {
  return theseusSafeArray(app.ariadne?.fitScores).slice(0, limit);
};

window.theseusAriadneAgentOpsSummary = function theseusAriadneAgentOpsSummary(
  app,
) {
  return [
    {
      label: "workspaces",
      value: window.theseusAriadneWorkspaceRows(app).length,
      detail: "tracked pursuits",
      icon: "briefcase",
      accent: "cyan",
    },
    {
      label: "open actions",
      value: window.theseusAriadneActionQueue(app, 999).length,
      detail: "capture queue",
      icon: "list-checks",
      accent: "amber",
    },
    {
      label: "skill chains",
      value: app.chains?.items?.length || 0,
      detail: app.chains?.loaded ? "loaded" : "lazy load on this view",
      icon: "workflow",
      accent: "magenta",
    },
    {
      label: "deliverables",
      value: app.studio?.deliverables?.length || 0,
      detail: app.studio?.loaded ? "studio indexed" : "lazy load on this view",
      icon: "archive",
      accent: "lime",
    },
  ];
};

window.theseusAriadneAgentActivity = function theseusAriadneAgentActivity(
  app,
  limit = 8,
) {
  const chains = (app.chains?.items || []).map((chain) => ({
    key: `chain:${chain.chain_id}`,
    kind: "chain",
    title: chain.name || chain.chain_id,
    detail: `${chain.status || "unknown"} · ${chain.step_count || 0} steps · ${chain.workspace || "workspace unset"}`,
    when: chain.updated_at || chain.finished_at || chain.created_at || "",
    when_label: theseusAriadneTimeAgo(
      chain.updated_at || chain.finished_at || chain.created_at,
    ),
    icon: "workflow",
    accent: chain.status === "completed" ? "lime" : "amber",
  }));
  const deliverables = (app.studio?.deliverables || []).map((item) => ({
    key: `artifact:${item.skill}:${item.run_id}:${item.filename}`,
    kind: "artifact",
    title: item.display_name || item.filename || item.run_id,
    detail: `${item.skill || "skill"} · ${item.ext || item.mime || "artifact"}`,
    when: item.created_at || "",
    when_label: theseusAriadneTimeAgo(item.created_at),
    icon: "file-output",
    accent: "cyan",
  }));
  return [...chains, ...deliverables]
    .map((item) => ({
      ...item,
      sort: Date.parse(item.when || "") || 0,
    }))
    .sort((left, right) => right.sort - left.sort)
    .slice(0, limit);
};

window.theseusAriadneIntelSummary = function theseusAriadneIntelSummary(app) {
  const rows = window.theseusAriadneWorkspaceRows(app);
  const intel = theseusAriadneBucket(app, "intel");
  const wiki = theseusAriadneBucket(app, "llm-wiki");
  const staleRows = rows.filter((row) => {
    const ageDays = theseusAriadneIntelAgeDaysForWorkspace(row, intel);
    return ageDays === null || ageDays > ARIADNE_STALE_INTEL_DAYS;
  });
  const nearGateRows = rows.filter((row) => {
    const gateDays = theseusAriadneDaysUntil(row.pursuit?.gate?.due);
    const intelAgeDays = theseusAriadneIntelAgeDaysForWorkspace(row, intel);
    return (
      gateDays !== null &&
      gateDays <= 14 &&
      (intelAgeDays === null || intelAgeDays > ARIADNE_STALE_INTEL_DAYS)
    );
  });
  const lastIntel = intel.reduce(
    (max, entry) => Math.max(max, entry.modified_at || 0),
    0,
  );
  const freshness = lastIntel
    ? Math.floor((theseusAriadneNowSec() - lastIntel) / ARIADNE_DAY_SECONDS)
    : null;

  return [
    {
      label: "intel notes",
      value: intel.length,
      detail:
        freshness === null
          ? "no cross-opp intel yet"
          : `last capture ${freshness}d ago`,
      icon: "radar",
      accent: "magenta",
    },
    {
      label: "stale pursuits",
      value: staleRows.length,
      detail: staleRows.length
        ? staleRows
            .map((row) => row.name)
            .slice(0, 2)
            .join(" · ")
        : "all within freshness window",
      icon: "clock-alert",
      accent: "amber",
    },
    {
      label: "gate + stale",
      value: nearGateRows.length,
      detail: nearGateRows.length
        ? nearGateRows
            .map((row) => row.name)
            .slice(0, 2)
            .join(" · ")
        : "no near-gate intel gaps",
      icon: "siren",
      accent: "cyan",
    },
    {
      label: "wiki pages",
      value: wiki.length,
      detail: wiki.length ? "llm-wiki active" : "wiki not seeded yet",
      icon: "book-open-text",
      accent: "lime",
    },
  ];
};

window.theseusAriadnePatternFeed = function theseusAriadnePatternFeed(
  app,
  limit = 5,
) {
  const selected = theseusAriadnePatternFilter(app);
  return theseusAriadnePatternEntries(app)
    .filter(
      (entry) => selected === "all" || entry.mode_tags.includes(selected),
    )
    .slice(0, limit);
};

window.theseusAriadnePatternFilters = function theseusAriadnePatternFilters(app) {
  const entries = theseusAriadnePatternEntries(app);
  const selected = theseusAriadnePatternFilter(app);
  return [
    {
      id: "all",
      label: "all",
      count: entries.length,
      active: selected === "all",
    },
    ...ARIADNE_PATTERN_MODES.map((mode) => ({
      id: mode,
      label: theseusAriadnePatternLabel(mode),
      count: entries.filter((entry) => entry.mode_tags.includes(mode)).length,
      active: selected === mode,
    })),
  ];
};

window.theseusAriadneIntelTargets = function theseusAriadneIntelTargets(
  app,
  limit = 6,
) {
  const rows = window.theseusAriadneWorkspaceRows(app);
  const intel = theseusAriadneBucket(app, "intel");
  const items = rows
    .map((row) => {
      const intelAgeDays = theseusAriadneIntelAgeDaysForWorkspace(row, intel);
      const gateDays = theseusAriadneDaysUntil(row.pursuit?.gate?.due);
      const reasons = [];
      let score = 0;

      if (intelAgeDays === null) {
        score += 4;
        reasons.push("no tagged intel");
      } else if (intelAgeDays > ARIADNE_STALE_INTEL_DAYS) {
        score += 3;
        reasons.push(`${intelAgeDays}d since intel`);
      }
      if (gateDays !== null && gateDays <= 7) {
        score += 4;
        reasons.push(`gate ${theseusAriadneDueLabel(row.pursuit?.gate?.due)}`);
      } else if (gateDays !== null && gateDays <= 14) {
        score += 3;
        reasons.push(`gate ${theseusAriadneDueLabel(row.pursuit?.gate?.due)}`);
      }
      if (row.pursuit?.stage === "capture" || row.pursuit?.stage === "proposal") {
        score += 1;
        reasons.push(`${row.pursuit.stage} stage`);
      }

      return {
        workspace: row.name,
        stage: window.theseusAriadneStage(row),
        stage_class: window.theseusAriadneStageClass(row),
        intel_age_days: intelAgeDays,
        reasons,
        score,
      };
    })
    .filter((item) => item.score > 0)
    .sort((left, right) => {
      if (left.score !== right.score) return right.score - left.score;
      return left.workspace.localeCompare(right.workspace);
    });

  return items.slice(0, limit);
};

window.theseusAriadnePromoteOptions = function theseusAriadnePromoteOptions(
  app,
) {
  return window.theseusAriadneWorkspaceRows(app).map((row) => row.name);
};

window.theseusLoadAriadneBucket = async function theseusLoadAriadneBucket(
  app,
  bucket,
) {
  const response = await app.api(`/api/global/${bucket}?limit=50`);
  app.ariadne.buckets[bucket] = response.entries || [];
};

window.theseusLoadAriadnePromotions = async function theseusLoadAriadnePromotions(
  app,
  workspace,
) {
  if (!workspace) return;
  try {
    const response = await app.api(
      `/api/global/promotions?workspace=${encodeURIComponent(workspace)}&active_only=true`,
    );
    app.ariadne.promotions = {
      ...(app.ariadne.promotions || {}),
      [workspace]: response.promotions || [],
    };
  } catch {
    app.ariadne.promotions = {
      ...(app.ariadne.promotions || {}),
      [workspace]: [],
    };
  }
};

window.theseusLoadAriadneFitScores = async function theseusLoadAriadneFitScores(
  app,
) {
  if (!app.ariadne) return;
  try {
    const response = await app.api("/api/ariadne/fit-scores?limit=20");
    app.ariadne.fitScores = response.scores || [];
    app.ariadne.fitFormulaVersion = response.formula_version || "";
  } catch {
    app.ariadne.fitScores = [];
    app.ariadne.fitFormulaVersion = "";
  }
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
      ARIADNE_BUCKETS.map((bucket) =>
        window.theseusLoadAriadneBucket(app, bucket),
      ),
    );
    const promotionWorkspaces = Array.from(
      new Set([
        app.ariadne.active,
        ...window.theseusAriadneWorkspaceRows(app).map((row) => row.name),
      ]),
    ).filter(Boolean);
    await Promise.all(
      promotionWorkspaces.map((workspace) =>
        window.theseusLoadAriadnePromotions(app, workspace),
      ),
    );
    await window.theseusLoadAriadneFitScores(app);
    app.ariadne.loaded = true;
  } catch (error) {
    app.ariadne.error = error.message || String(error);
  } finally {
    app.ariadne.loading = false;
    window.theseusAfterRender(app);
  }
};

window.theseusSubmitAriadneCapture = async function theseusSubmitAriadneCapture(
  app,
) {
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
    if ((capture.workspace || "").trim())
      payload.workspace = capture.workspace.trim();
    const response = await app.api("/api/global/capture", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    capture.body = "";
    capture.slug = "";
    app.toast(`Captured ${response.path || "global note"}`, "success");
    await window.theseusLoadAriadneBucket(app, payload.bucket);
    await window.theseusLoadAriadneFitScores(app);
  } catch (error) {
    app.toast(`Capture failed: ${error.message || error}`, "error");
  } finally {
    capture.busy = false;
    window.theseusAfterRender(app);
  }
};

window.theseusPromoteAriadneNote = async function theseusPromoteAriadneNote(
  app,
  path,
) {
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
    await window.theseusLoadAriadnePromotions(app, workspace);
    await window.theseusLoadAriadneFitScores(app);
  } catch (error) {
    app.toast(`Promote failed: ${error.message || error}`, "error");
  } finally {
    window.theseusAfterRender(app);
  }
};

window.theseusRefreshAriadnePromotion = async function theseusRefreshAriadnePromotion(
  app,
  promotion,
) {
  if (!promotion?.source || !promotion?.workspace) return;
  const busyKey = `${promotion.workspace}:${promotion.source}`;
  app.ariadne.promotionBusy = {
    ...(app.ariadne.promotionBusy || {}),
    [busyKey]: true,
  };
  try {
    await app.api("/api/global/promote/refresh", {
      method: "POST",
      body: JSON.stringify({
        path: promotion.source,
        workspace: promotion.workspace,
        delete_existing: true,
      }),
    });
    app.toast(`Refreshed ${promotion.source}`, "success");
    await window.theseusLoadAriadnePromotions(app, promotion.workspace);
    await window.theseusLoadAriadneFitScores(app);
  } catch (error) {
    app.toast(`Refresh failed: ${error.message || error}`, "error");
  } finally {
    const nextBusy = { ...(app.ariadne.promotionBusy || {}) };
    delete nextBusy[busyKey];
    app.ariadne.promotionBusy = nextBusy;
    window.theseusAfterRender(app);
  }
};

window.theseusUnpromoteAriadneNote = async function theseusUnpromoteAriadneNote(
  app,
  promotion,
) {
  if (!promotion?.source || !promotion?.workspace) return;
  const busyKey = `${promotion.workspace}:${promotion.source}`;
  app.ariadne.promotionBusy = {
    ...(app.ariadne.promotionBusy || {}),
    [busyKey]: true,
  };
  try {
    await app.api("/api/global/promote", {
      method: "DELETE",
      body: JSON.stringify({
        path: promotion.source,
        workspace: promotion.workspace,
      }),
    });
    app.toast(`Unpromoted ${promotion.source}`, "success");
    await window.theseusLoadAriadnePromotions(app, promotion.workspace);
    await window.theseusLoadAriadneFitScores(app);
  } catch (error) {
    app.toast(`Unpromote failed: ${error.message || error}`, "error");
  } finally {
    const nextBusy = { ...(app.ariadne.promotionBusy || {}) };
    delete nextBusy[busyKey];
    app.ariadne.promotionBusy = nextBusy;
    window.theseusAfterRender(app);
  }
};

window.theseusActivateAriadneWorkspace =
  async function theseusActivateAriadneWorkspace(app, name) {
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
