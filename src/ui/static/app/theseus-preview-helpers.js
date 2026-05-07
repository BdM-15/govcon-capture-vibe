window.theseusEnsureScript = function theseusEnsureScript(app, url) {
  if (!app._scriptCache) app._scriptCache = {};
  if (app._scriptCache[url]) return app._scriptCache[url];
  app._scriptCache[url] = new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = url;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Failed to load script: " + url));
    document.head.appendChild(script);
  });
  return app._scriptCache[url];
};

const THESEUS_TEXT_PREVIEW_KINDS = new Set(["md", "json", "csv", "text"]);

const theseusFetchPreviewResponse = async function theseusFetchPreviewResponse(
  href,
) {
  const response = await fetch(href);
  if (!response.ok) throw new Error("HTTP " + response.status);
  return response;
};

const theseusResetStudioPreview = function theseusResetStudioPreview(
  app,
  deliverable,
) {
  app.studioPreview.open = true;
  app.studioPreview.error = null;
  app.studioPreview.deliverable = deliverable;
  app.studioPreview.kind = window.theseusStudioFormatFor(deliverable);
  app.studioPreview.href = window.theseusStudioDownloadHref(deliverable);
  app.studioPreview.text = "";
  app.studioPreview.docxHtml = "";
  app.studioPreview.sheets = [];
  app.studioPreview.sheetIdx = 0;
  app.studioPreview.jsonChunks = [];
};

const theseusLoadTextStudioPreview =
  async function theseusLoadTextStudioPreview(app) {
    const response = await theseusFetchPreviewResponse(app.studioPreview.href);
    app.studioPreview.text = await response.text();
    if (app.studioPreview.kind === "json") {
      app.studioPreview.jsonChunks = window.theseusExtractJsonChunkIds(
        app.studioPreview.text,
      );
    }
  };

const theseusLoadDocxStudioPreview =
  async function theseusLoadDocxStudioPreview(app) {
    await window.theseusEnsureScript(
      app,
      "https://cdnjs.cloudflare.com/ajax/libs/mammoth/1.6.0/mammoth.browser.min.js",
    );
    const response = await theseusFetchPreviewResponse(app.studioPreview.href);
    const buffer = await response.arrayBuffer();
    const out = await window.mammoth.convertToHtml({ arrayBuffer: buffer });
    app.studioPreview.docxHtml = out && out.value ? out.value : "";
  };

const theseusLoadXlsxStudioPreview =
  async function theseusLoadXlsxStudioPreview(app) {
    await window.theseusEnsureScript(
      app,
      "https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js",
    );
    const response = await theseusFetchPreviewResponse(app.studioPreview.href);
    const buffer = await response.arrayBuffer();
    const workbook = window.XLSX.read(buffer, { type: "array" });
    app.studioPreview.sheets = (workbook.SheetNames || []).map((name) => ({
      name,
      html: window.XLSX.utils.sheet_to_html(workbook.Sheets[name], {
        header: "",
        footer: "",
      }),
    }));
    app.studioPreview.sheetIdx = 0;
  };

const theseusRunPreviewLoad = async function theseusRunPreviewLoad(
  app,
  panel,
  task,
  options = {},
) {
  const { onError } = options;
  panel.loading = true;
  panel.error = null;
  try {
    await task();
  } catch (error) {
    panel.error = onError ? onError(error) : error?.message || String(error);
  } finally {
    panel.loading = false;
    window.theseusAfterRender(app);
  }
};

window.theseusOpenStudioPreview = async function theseusOpenStudioPreview(
  app,
  deliverable,
) {
  app.studioPreview.loading = true;
  theseusResetStudioPreview(app, deliverable);

  try {
    const kind = app.studioPreview.kind;
    if (THESEUS_TEXT_PREVIEW_KINDS.has(kind)) {
      await theseusLoadTextStudioPreview(app);
    } else if (kind === "docx") {
      await theseusLoadDocxStudioPreview(app);
    } else if (kind === "xlsx") {
      await theseusLoadXlsxStudioPreview(app);
    }
  } catch (error) {
    app.studioPreview.error = error?.message || String(error);
  } finally {
    app.studioPreview.loading = false;
    window.theseusAfterRender(app);
  }
};

window.theseusCloseStudioPreview = function theseusCloseStudioPreview(app) {
  app.studioPreview.open = false;
};

window.theseusStudioSetSheet = function theseusStudioSetSheet(app, idx) {
  app.studioPreview.sheetIdx = idx;
};

window.theseusOpenReasoning = async function theseusOpenReasoning(
  app,
  deliverable,
) {
  app.reasoning.open = true;
  app.reasoning.skill = deliverable.skill;
  app.reasoning.run_id = deliverable.run_id;
  app.reasoning.title = deliverable.title || "";
  app.reasoning.created_at = deliverable.created_at || "";
  app.reasoning.steps = [];
  app.reasoning.summary = null;
  app.reasoning.artifacts = [];
  app.reasoning.expanded = {};

  await theseusRunPreviewLoad(app, app.reasoning, async () => {
    const response = await fetch(
      "/api/ui/skills/" +
        encodeURIComponent(deliverable.skill) +
        "/runs/" +
        encodeURIComponent(deliverable.run_id) +
        "/reasoning",
    );
    if (!response.ok) throw new Error("HTTP " + response.status);
    const payload = await response.json();
    app.reasoning.steps = payload.steps || [];
    app.reasoning.summary = payload.summary || null;
    app.reasoning.artifacts = payload.artifacts || [];
    app.reasoning.title = payload.title || app.reasoning.title;
    app.reasoning.created_at = payload.created_at || app.reasoning.created_at;
  });
};

window.theseusCloseReasoning = function theseusCloseReasoning(app) {
  app.reasoning.open = false;
};

window.theseusToggleReasoningStep = function theseusToggleReasoningStep(
  app,
  idx,
) {
  app.reasoning.expanded[idx] = !app.reasoning.expanded[idx];
};

window.theseusCopyToClipboard = async function theseusCopyToClipboard(
  app,
  text,
) {
  await window.theseusCopyText(app, text, {
    success: "Copied: " + text,
    error: "Copy failed",
    kind: "success",
  });
};

window.theseusFetchChunk = async function theseusFetchChunk(app, chunkId) {
  if (!chunkId) throw new Error("missing chunk id");
  const hit = app._chunkCache[chunkId];
  if (hit) return hit;

  const response = await fetch("/api/ui/chunks/" + encodeURIComponent(chunkId));
  if (!response.ok) {
    if (response.status === 404) {
      throw new Error("Chunk not found in this workspace");
    }
    throw new Error("HTTP " + response.status);
  }

  const payload = await response.json();
  const record = {
    chunk_id: chunkId,
    file_path: payload.file_path,
    full_doc_id: payload.full_doc_id,
    chunk_order_index: payload.chunk_order_index,
    tokens: payload.tokens,
    length: payload.length || 0,
    content: payload.content || "",
    view: window.theseusFormatSource({ preview: payload.content || "" }),
  };
  app._chunkCache[chunkId] = record;
  return record;
};

window.theseusOpenChunkPreview = async function theseusOpenChunkPreview(
  app,
  chunkId,
) {
  if (!chunkId) return;
  app.chunkPreview.open = true;
  app.chunkPreview.chunk_id = chunkId;
  app.chunkPreview.file_path = null;
  app.chunkPreview.full_doc_id = null;
  app.chunkPreview.chunk_order_index = null;
  app.chunkPreview.tokens = null;
  app.chunkPreview.length = 0;
  app.chunkPreview.content = "";

  await theseusRunPreviewLoad(app, app.chunkPreview, async () => {
    const record = await window.theseusFetchChunk(app, chunkId);
    app.chunkPreview.file_path = record.file_path;
    app.chunkPreview.full_doc_id = record.full_doc_id;
    app.chunkPreview.chunk_order_index = record.chunk_order_index;
    app.chunkPreview.tokens = record.tokens;
    app.chunkPreview.length = record.length;
    app.chunkPreview.content = record.content;
    app.chunkPreview.view = record.view;
    app.chunkPreview.showRaw = false;
  });
};

window.theseusCloseChunkPreview = function theseusCloseChunkPreview(app) {
  app.chunkPreview.open = false;
};

window.theseusLoadStudio = async function theseusLoadStudio(app) {
  await theseusRunPreviewLoad(
    app,
    app.studio,
    async () => {
      const response = await app.api("/api/ui/studio");
      app.studio.deliverables = response.deliverables || [];
      window.theseusPruneStudioSelection(app);
      app.studio.loaded = true;
    },
    {
      onError: (error) => {
        app.studio.deliverables = [];
        return "Failed to load deliverables: " + (error?.message || error);
      },
    },
  );
};

window.theseusStudioSelectedCount = function theseusStudioSelectedCount(app) {
  return Object.keys(app.studio.selected || {}).length;
};

window.theseusPruneStudioSelection = function theseusPruneStudioSelection(app) {
  const live = new Set((app.studio.deliverables || []).map(window.theseusStudioKey));
  const next = {};
  for (const key of Object.keys(app.studio.selected || {})) {
    if (live.has(key)) next[key] = app.studio.selected[key];
  }
  app.studio.selected = next;
};

window.theseusToggleStudioSelection = function theseusToggleStudioSelection(
  app,
  deliverable,
) {
  const key = window.theseusStudioKey(deliverable);
  const next = { ...(app.studio.selected || {}) };
  if (next[key]) delete next[key];
  else {
    next[key] = {
      skill: deliverable.skill,
      run_id: deliverable.run_id,
      filename: deliverable.filename,
    };
  }
  app.studio.selected = next;
};

window.theseusStudioAllFilteredSelected = function theseusStudioAllFilteredSelected(app) {
  const rows = window.theseusStudioFiltered(app);
  if (!rows.length) return false;
  const selected = app.studio.selected || {};
  return rows.every((deliverable) => selected[window.theseusStudioKey(deliverable)]);
};

window.theseusToggleStudioSelectAllFiltered = function theseusToggleStudioSelectAllFiltered(app) {
  const rows = window.theseusStudioFiltered(app);
  const next = { ...(app.studio.selected || {}) };
  const allSelected = window.theseusStudioAllFilteredSelected(app);
  for (const deliverable of rows) {
    const key = window.theseusStudioKey(deliverable);
    if (allSelected) delete next[key];
    else {
      next[key] = {
        skill: deliverable.skill,
        run_id: deliverable.run_id,
        filename: deliverable.filename,
      };
    }
  }
  app.studio.selected = next;
};

window.theseusClearStudioSelection = function theseusClearStudioSelection(app) {
  app.studio.selected = {};
};

window.theseusDeleteSelectedStudioArtifacts = async function theseusDeleteSelectedStudioArtifacts(app) {
  const artifacts = Object.values(app.studio.selected || {});
  if (!artifacts.length || app.studio.deleting) return;
  const label = artifacts.length === 1 ? "1 artifact" : artifacts.length + " artifacts";
  if (!confirm("Delete " + label + " from Studio? This removes selected files from disk.")) {
    return;
  }
  app.studio.deleting = true;
  try {
    const result = await app.api("/api/ui/studio/artifacts", {
      method: "DELETE",
      body: JSON.stringify({ artifacts }),
    });
    app.toast("Deleted " + result.deleted_count + " artifact(s)", "success");
    window.theseusClearStudioSelection(app);
    await window.theseusLoadStudio(app);
  } catch (error) {
    app.toast("Delete failed: " + (error?.message || error), "error");
  } finally {
    app.studio.deleting = false;
    window.theseusAfterRender(app);
  }
};

window.theseusStudioSkillOptions = function theseusStudioSkillOptions(app) {
  const set = new Set(
    (app.studio.deliverables || []).map((deliverable) => deliverable.skill),
  );
  return Array.from(set).sort();
};

window.theseusStudioFormatOptions = function theseusStudioFormatOptions(app) {
  const set = new Set(
    (app.studio.deliverables || []).map((deliverable) => deliverable.ext || ""),
  );
  return Array.from(set).filter(Boolean).sort();
};

window.theseusStudioKey = function theseusStudioKey(deliverable) {
  return (
    (deliverable.skill || "") +
    "/" +
    (deliverable.run_id || "") +
    "/" +
    (deliverable.filename || "")
  );
};

window.theseusIsStudioPinned = function theseusIsStudioPinned(
  app,
  deliverable,
) {
  return !!(app.studio.pinned || {})[window.theseusStudioKey(deliverable)];
};

window.theseusStudioFiltered = function theseusStudioFiltered(app) {
  const query = (app.studio.search || "").toLowerCase().trim();
  const filtered = (app.studio.deliverables || []).filter((deliverable) => {
    if (
      app.studio.filterSkill &&
      deliverable.skill !== app.studio.filterSkill
    ) {
      return false;
    }
    if (
      app.studio.filterFormat &&
      (deliverable.ext || "") !== app.studio.filterFormat
    ) {
      return false;
    }
    if (
      query &&
      !(deliverable.display_name || "").toLowerCase().includes(query) &&
      !(deliverable.filename || "").toLowerCase().includes(query) &&
      !(deliverable.title || "").toLowerCase().includes(query)
    ) {
      return false;
    }
    return true;
  });
  const pinned = app.studio.pinned || {};
  const pinKey = window.theseusStudioKey;
  return filtered
    .map((deliverable, index) => ({
      deliverable,
      index,
      pinned: pinned[pinKey(deliverable)] ? 1 : 0,
    }))
    .sort(
      (left, right) => right.pinned - left.pinned || left.index - right.index,
    )
    .map((entry) => entry.deliverable);
};

window.theseusStudioOpenRun = function theseusStudioOpenRun(app, deliverable) {
  app.active = "skills";
  app.$nextTick(async () => {
    try {
      if (!app.skills.loaded) await app.loadSkills();
      await app.openSkill(deliverable.skill);
      app.loadSkillRun(deliverable.skill, deliverable.run_id);
    } catch (error) {
      app.toast("Could not open run: " + (error?.message || error), "error");
    }
  });
};

window.theseusToggleStudioPin = function theseusToggleStudioPin(
  app,
  deliverable,
) {
  const key = window.theseusStudioKey(deliverable);
  const next = { ...(app.studio.pinned || {}) };
  if (next[key]) delete next[key];
  else next[key] = true;
  app.studio.pinned = next;
  try {
    localStorage.setItem("theseus.studio.pinned", JSON.stringify(next));
  } catch (_) {
    /* localStorage unavailable */
  }
};

window.theseusLoadStudioPinned = function theseusLoadStudioPinned(app) {
  try {
    const raw = localStorage.getItem("theseus.studio.pinned");
    if (raw) app.studio.pinned = JSON.parse(raw) || {};
  } catch (_) {
    app.studio.pinned = {};
  }
};
