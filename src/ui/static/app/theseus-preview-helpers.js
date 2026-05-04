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

window.theseusOpenStudioPreview = async function theseusOpenStudioPreview(
  app,
  deliverable,
) {
  app.studioPreview.open = true;
  app.studioPreview.loading = true;
  app.studioPreview.error = null;
  app.studioPreview.deliverable = deliverable;
  app.studioPreview.kind = window.theseusStudioFormatFor(deliverable);
  app.studioPreview.href = window.theseusStudioDownloadHref(deliverable);
  app.studioPreview.text = "";
  app.studioPreview.docxHtml = "";
  app.studioPreview.sheets = [];
  app.studioPreview.sheetIdx = 0;
  app.studioPreview.jsonChunks = [];

  try {
    const kind = app.studioPreview.kind;
    if (kind === "pdf" || kind === "video" || kind === "image") {
      app.studioPreview.loading = false;
    } else if (
      kind === "md" ||
      kind === "json" ||
      kind === "csv" ||
      kind === "text"
    ) {
      const response = await fetch(app.studioPreview.href);
      if (!response.ok) throw new Error("HTTP " + response.status);
      app.studioPreview.text = await response.text();
      if (kind === "json") {
        app.studioPreview.jsonChunks = window.theseusExtractJsonChunkIds(
          app.studioPreview.text,
        );
      }
      app.studioPreview.loading = false;
    } else if (kind === "docx") {
      await window.theseusEnsureScript(
        app,
        "https://cdnjs.cloudflare.com/ajax/libs/mammoth/1.6.0/mammoth.browser.min.js",
      );
      const response = await fetch(app.studioPreview.href);
      if (!response.ok) throw new Error("HTTP " + response.status);
      const buffer = await response.arrayBuffer();
      const out = await window.mammoth.convertToHtml({ arrayBuffer: buffer });
      app.studioPreview.docxHtml = out && out.value ? out.value : "";
      app.studioPreview.loading = false;
    } else if (kind === "xlsx") {
      await window.theseusEnsureScript(
        app,
        "https://cdn.jsdelivr.net/npm/xlsx@0.18.5/dist/xlsx.full.min.js",
      );
      const response = await fetch(app.studioPreview.href);
      if (!response.ok) throw new Error("HTTP " + response.status);
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
      app.studioPreview.loading = false;
    } else {
      app.studioPreview.loading = false;
    }
  } catch (error) {
    app.studioPreview.error = error?.message || String(error);
    app.studioPreview.loading = false;
  }

  app.$nextTick(() => {
    if (window.lucide) lucide.createIcons();
  });
};

window.theseusCloseStudioPreview = function theseusCloseStudioPreview(app) {
  app.studioPreview.open = false;
};

window.theseusStudioSetSheet = function theseusStudioSetSheet(app, idx) {
  app.studioPreview.sheetIdx = idx;
};

window.theseusOpenReasoning = async function theseusOpenReasoning(app, deliverable) {
  app.reasoning.open = true;
  app.reasoning.loading = true;
  app.reasoning.error = null;
  app.reasoning.skill = deliverable.skill;
  app.reasoning.run_id = deliverable.run_id;
  app.reasoning.title = deliverable.title || "";
  app.reasoning.created_at = deliverable.created_at || "";
  app.reasoning.steps = [];
  app.reasoning.summary = null;
  app.reasoning.artifacts = [];
  app.reasoning.expanded = {};

  try {
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
  } catch (error) {
    app.reasoning.error = error?.message || String(error);
  } finally {
    app.reasoning.loading = false;
    app.$nextTick(() => {
      if (window.lucide) lucide.createIcons();
    });
  }
};

window.theseusCloseReasoning = function theseusCloseReasoning(app) {
  app.reasoning.open = false;
};

window.theseusToggleReasoningStep = function theseusToggleReasoningStep(app, idx) {
  app.reasoning.expanded[idx] = !app.reasoning.expanded[idx];
};

window.theseusCopyToClipboard = function theseusCopyToClipboard(app, text) {
  try {
    navigator.clipboard.writeText(text);
    app.toast("Copied: " + text, "success");
  } catch (error) {
    app.toast("Copy failed", "error");
  }
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
  app.chunkPreview.loading = true;
  app.chunkPreview.error = null;
  app.chunkPreview.chunk_id = chunkId;
  app.chunkPreview.file_path = null;
  app.chunkPreview.full_doc_id = null;
  app.chunkPreview.chunk_order_index = null;
  app.chunkPreview.tokens = null;
  app.chunkPreview.length = 0;
  app.chunkPreview.content = "";

  try {
    const record = await window.theseusFetchChunk(app, chunkId);
    app.chunkPreview.file_path = record.file_path;
    app.chunkPreview.full_doc_id = record.full_doc_id;
    app.chunkPreview.chunk_order_index = record.chunk_order_index;
    app.chunkPreview.tokens = record.tokens;
    app.chunkPreview.length = record.length;
    app.chunkPreview.content = record.content;
    app.chunkPreview.view = record.view;
    app.chunkPreview.showRaw = false;
  } catch (error) {
    app.chunkPreview.error = error?.message || String(error);
  } finally {
    app.chunkPreview.loading = false;
    app.$nextTick(() => {
      if (window.lucide) lucide.createIcons();
    });
  }
};

window.theseusCloseChunkPreview = function theseusCloseChunkPreview(app) {
  app.chunkPreview.open = false;
};