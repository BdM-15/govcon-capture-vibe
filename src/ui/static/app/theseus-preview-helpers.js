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
const THESEUS_REASONING_SOURCE_EXTENSIONS = new Set(["md", "markdown", "json"]);
const THESEUS_COMPAREABLE_PREVIEW_KINDS = new Set([
  "md",
  "json",
  "csv",
  "text",
  "docx",
]);

const theseusNormalizeExtension = function theseusNormalizeExtension(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/^\./, "");
};

const theseusStudioComparableKind = function theseusStudioComparableKind(
  deliverable,
) {
  return window.theseusStudioFormatFor(deliverable);
};

const theseusStripHtmlToText = function theseusStripHtmlToText(html) {
  const tmp = document.createElement("div");
  tmp.innerHTML = html || "";
  return (tmp.textContent || tmp.innerText || "").replace(/\r\n/g, "\n");
};

const theseusNormalizeCompareText = function theseusNormalizeCompareText(text) {
  return String(text || "")
    .replace(/\r\n/g, "\n")
    .trim();
};

const theseusArtifactRoleMeta = function theseusArtifactRoleMeta(artifact) {
  if (artifact.isCurrent) {
    return { label: "Current product", tone: "current" };
  }
  if (artifact.isSource) {
    return { label: "Source artifact", tone: "source" };
  }
  return { label: "Sibling product", tone: "sibling" };
};

const theseusVersionBadgeMeta = function theseusVersionBadgeMeta(artifact) {
  if (artifact.isCurrent) {
    return { label: "Current version", tone: "current" };
  }
  return { label: "Older version", tone: "previous" };
};

const theseusSummarizeCompareText = function theseusSummarizeCompareText(
  currentText,
  previousText,
) {
  const current = theseusNormalizeCompareText(currentText);
  const previous = theseusNormalizeCompareText(previousText);
  const currentLines = current ? current.split("\n") : [];
  const previousLines = previous ? previous.split("\n") : [];
  const maxLen = Math.max(currentLines.length, previousLines.length);
  let firstChangedIndex = -1;
  for (let index = 0; index < maxLen; index += 1) {
    if ((currentLines[index] || "") !== (previousLines[index] || "")) {
      firstChangedIndex = index;
      break;
    }
  }
  return {
    identical: current === previous,
    currentLineCount: currentLines.length,
    previousLineCount: previousLines.length,
    lineDelta: currentLines.length - previousLines.length,
    firstChangedLine: firstChangedIndex >= 0 ? firstChangedIndex + 1 : null,
    currentExcerpt:
      firstChangedIndex >= 0 ? currentLines[firstChangedIndex] || "" : "",
    previousExcerpt:
      firstChangedIndex >= 0 ? previousLines[firstChangedIndex] || "" : "",
  };
};

const theseusFetchPreviewResponse = async function theseusFetchPreviewResponse(
  href,
) {
  const response = await fetch(href);
  if (!response.ok) throw new Error("HTTP " + response.status);
  return response;
};

const theseusFetchReasoningPayload =
  async function theseusFetchReasoningPayload(skill, runId) {
    const response = await fetch(
      "/api/ui/skills/" +
        encodeURIComponent(skill) +
        "/runs/" +
        encodeURIComponent(runId) +
        "/reasoning",
    );
    if (!response.ok) throw new Error("HTTP " + response.status);
    return response.json();
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
  app.studioPreview.provenanceLoading = false;
  app.studioPreview.provenanceError = null;
  app.studioPreview.provenanceSummary = null;
  app.studioPreview.provenanceSteps = [];
  app.studioPreview.provenanceArtifacts = [];
  app.studioPreview.history = [];
  app.studioPreview.compareLoading = false;
  app.studioPreview.compareError = null;
  app.studioPreview.compareTarget = null;
  app.studioPreview.compareSummary = null;
};

const theseusBuildStudioPreviewHistory =
  function theseusBuildStudioPreviewHistory(app, deliverable) {
    const kind = theseusStudioComparableKind(deliverable);
    return (app.studio.deliverables || [])
      .filter(
        (candidate) =>
          candidate.skill === deliverable.skill &&
          candidate.filename === deliverable.filename,
      )
      .map((candidate) => ({
        ...candidate,
        previewKind: theseusStudioComparableKind(candidate),
        isCurrent:
          window.theseusStudioKey(candidate) ===
          window.theseusStudioKey(deliverable),
        isComparable:
          THESEUS_COMPAREABLE_PREVIEW_KINDS.has(kind) &&
          THESEUS_COMPAREABLE_PREVIEW_KINDS.has(
            theseusStudioComparableKind(candidate),
          ) &&
          theseusStudioComparableKind(candidate) === kind,
      }))
      .map((candidate) => ({
        ...candidate,
        versionBadge: theseusVersionBadgeMeta(candidate),
      }));
  };

const theseusMaterializeComparablePreview =
  async function theseusMaterializeComparablePreview(app, deliverable) {
    const kind = theseusStudioComparableKind(deliverable);
    const href = window.theseusStudioDownloadHref(deliverable);
    if (THESEUS_TEXT_PREVIEW_KINDS.has(kind)) {
      const response = await theseusFetchPreviewResponse(href);
      return { kind, text: await response.text() };
    }
    if (kind === "docx") {
      await window.theseusEnsureScript(
        app,
        "https://cdnjs.cloudflare.com/ajax/libs/mammoth/1.6.0/mammoth.browser.min.js",
      );
      const response = await theseusFetchPreviewResponse(href);
      const buffer = await response.arrayBuffer();
      const out = await window.mammoth.convertToHtml({ arrayBuffer: buffer });
      const html = out && out.value ? out.value : "";
      return { kind, text: theseusStripHtmlToText(html) };
    }
    return { kind, text: "" };
  };

const theseusCurrentPreviewComparableText =
  function theseusCurrentPreviewComparableText(app) {
    if (THESEUS_TEXT_PREVIEW_KINDS.has(app.studioPreview.kind)) {
      return app.studioPreview.text || "";
    }
    if (app.studioPreview.kind === "docx") {
      return theseusStripHtmlToText(app.studioPreview.docxHtml || "");
    }
    return "";
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

const theseusLoadStudioPreviewProvenance =
  async function theseusLoadStudioPreviewProvenance(app, deliverable) {
    app.studioPreview.provenanceLoading = true;
    app.studioPreview.provenanceError = null;
    try {
      const payload = await theseusFetchReasoningPayload(
        deliverable.skill,
        deliverable.run_id,
      );
      app.studioPreview.provenanceSummary = payload.summary || null;
      app.studioPreview.provenanceSteps = payload.steps || [];
      app.studioPreview.provenanceArtifacts = payload.artifacts || [];
    } catch (error) {
      app.studioPreview.provenanceError = error?.message || String(error);
    } finally {
      app.studioPreview.provenanceLoading = false;
      window.theseusAfterRender(app);
    }
  };

window.theseusOpenStudioPreview = async function theseusOpenStudioPreview(
  app,
  deliverable,
) {
  app.studioPreview.loading = true;
  theseusResetStudioPreview(app, deliverable);
  app.studioPreview.history = theseusBuildStudioPreviewHistory(
    app,
    deliverable,
  );
  const provenancePromise = theseusLoadStudioPreviewProvenance(
    app,
    deliverable,
  );

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

  await provenancePromise;
};

window.theseusCloseStudioPreview = function theseusCloseStudioPreview(app) {
  app.studioPreview.open = false;
};

window.theseusStudioPreviewCanCompare = function theseusStudioPreviewCanCompare(
  app,
) {
  return THESEUS_COMPAREABLE_PREVIEW_KINDS.has(app.studioPreview.kind || "");
};

window.theseusStudioPreviewHistory = function theseusStudioPreviewHistory(app) {
  return app.studioPreview.history || [];
};

window.theseusStudioPreviewClearCompare =
  function theseusStudioPreviewClearCompare(app) {
    app.studioPreview.compareLoading = false;
    app.studioPreview.compareError = null;
    app.studioPreview.compareTarget = null;
    app.studioPreview.compareSummary = null;
  };

window.theseusStudioPreviewCompareVersion =
  async function theseusStudioPreviewCompareVersion(app, deliverable) {
    if (!deliverable || deliverable.isCurrent) return;
    app.studioPreview.compareLoading = true;
    app.studioPreview.compareError = null;
    app.studioPreview.compareTarget = deliverable;
    app.studioPreview.compareSummary = null;
    try {
      const currentText = theseusCurrentPreviewComparableText(app);
      const previous = await theseusMaterializeComparablePreview(
        app,
        deliverable,
      );
      app.studioPreview.compareSummary = {
        ...theseusSummarizeCompareText(currentText, previous.text),
        current: app.studioPreview.deliverable,
        previous: deliverable,
        kind: app.studioPreview.kind,
        sizeDelta:
          Number((app.studioPreview.deliverable || {}).size || 0) -
          Number(deliverable.size || 0),
      };
    } catch (error) {
      app.studioPreview.compareError = error?.message || String(error);
    } finally {
      app.studioPreview.compareLoading = false;
      window.theseusAfterRender(app);
    }
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
  app.reasoning.filename = deliverable.filename || "";
  app.reasoning.title = deliverable.title || "";
  app.reasoning.created_at = deliverable.created_at || "";
  app.reasoning.promoting = "";
  app.reasoning.steps = [];
  app.reasoning.summary = null;
  app.reasoning.artifacts = [];
  app.reasoning.expanded = {};

  await theseusRunPreviewLoad(app, app.reasoning, async () => {
    const payload = await theseusFetchReasoningPayload(
      deliverable.skill,
      deliverable.run_id,
    );
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

const theseusReasoningArtifactDeliverable =
  function theseusReasoningArtifactDeliverable(scope, artifact) {
    const filename = artifact.filename || artifact.name || "";
    const ext = theseusNormalizeExtension(
      artifact.ext || filename.split(".").pop() || "",
    );
    return {
      skill: scope.skill,
      run_id: scope.run_id,
      filename,
      display_name: artifact.display_name || filename,
      title: scope.title || artifact.display_name || filename,
      created_at: scope.created_at || "",
      ext,
      mime: artifact.mime || "",
      size: Number(artifact.size || 0),
    };
  };

const theseusNormalizeRunArtifacts = function theseusNormalizeRunArtifacts(
  scope,
  artifacts,
  currentFilename,
) {
  const current = currentFilename || "";
  return (artifacts || []).map((artifact) => {
    const deliverable = theseusReasoningArtifactDeliverable(scope, artifact);
    const isSource = THESEUS_REASONING_SOURCE_EXTENSIONS.has(deliverable.ext);
    const renderStatus = String(artifact.render_status || "").toLowerCase();
    return {
      ...artifact,
      ...deliverable,
      isCurrent: deliverable.filename === current,
      isSource,
      roleBadge: theseusArtifactRoleMeta({
        isCurrent: deliverable.filename === current,
        isSource,
      }),
      renderStatus,
      hasRenderFailure: renderStatus === "failed",
      renderMessage: artifact.render_message || "",
      renderTargets: Array.isArray(artifact.render_targets)
        ? artifact.render_targets
        : [],
      renderLogs: Array.isArray(artifact.render_logs)
        ? artifact.render_logs
        : [],
      renderLogExcerpt: artifact.render_log_excerpt || "",
    };
  });
};

window.theseusReasoningArtifacts = function theseusReasoningArtifacts(app) {
  const items = theseusNormalizeRunArtifacts(
    {
      skill: app.reasoning.skill,
      run_id: app.reasoning.run_id,
      title: app.reasoning.title,
      created_at: app.reasoning.created_at,
    },
    app.reasoning.artifacts,
    app.reasoning.filename,
  );
  const rank = (item) =>
    item.isCurrent ? 0 : item.hasRenderFailure ? 1 : item.isSource ? 3 : 2;
  return items.sort((left, right) => {
    const byRank = rank(left) - rank(right);
    if (byRank) return byRank;
    return (left.display_name || left.filename || "").localeCompare(
      right.display_name || right.filename || "",
    );
  });
};

window.theseusReasoningArtifactDownloadHref =
  function theseusReasoningArtifactDownloadHref(app, artifact) {
    return window.theseusStudioDownloadHref(
      theseusReasoningArtifactDeliverable(
        {
          skill: app.reasoning.skill,
          run_id: app.reasoning.run_id,
          title: app.reasoning.title,
          created_at: app.reasoning.created_at,
        },
        artifact,
      ),
    );
  };

window.theseusOpenReasoningArtifactPreview =
  async function theseusOpenReasoningArtifactPreview(app, artifact) {
    return window.theseusOpenStudioPreview(
      app,
      theseusReasoningArtifactDeliverable(
        {
          skill: app.reasoning.skill,
          run_id: app.reasoning.run_id,
          title: app.reasoning.title,
          created_at: app.reasoning.created_at,
        },
        artifact,
      ),
    );
  };

window.theseusStudioPreviewArtifacts = function theseusStudioPreviewArtifacts(
  app,
) {
  const deliverable = app.studioPreview.deliverable || {};
  const items = theseusNormalizeRunArtifacts(
    {
      skill: deliverable.skill || "",
      run_id: deliverable.run_id || "",
      title:
        deliverable.title ||
        deliverable.display_name ||
        deliverable.filename ||
        "",
      created_at: deliverable.created_at || "",
    },
    app.studioPreview.provenanceArtifacts,
    deliverable.filename || "",
  );
  const rank = (item) =>
    item.isCurrent ? 0 : item.hasRenderFailure ? 1 : item.isSource ? 3 : 2;
  return items.sort((left, right) => {
    const byRank = rank(left) - rank(right);
    if (byRank) return byRank;
    return (left.display_name || left.filename || "").localeCompare(
      right.display_name || right.filename || "",
    );
  });
};

window.theseusPromoteReasoningArtifact =
  async function theseusPromoteReasoningArtifact(app, artifact) {
    if (!artifact || !artifact.isSource) return;
    const skill = app.reasoning.skill || artifact.skill;
    const runId = app.reasoning.run_id || artifact.run_id;
    const busyKey = artifact.filename || "__reasoning_render__";
    if (!skill || !runId || app.reasoning.promoting === busyKey) return;
    app.reasoning.promoting = busyKey;
    try {
      const response = await fetch(
        "/api/ui/skills/" +
          encodeURIComponent(skill) +
          "/runs/" +
          encodeURIComponent(runId) +
          "/artifacts/render",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
        },
      );
      const contentType = response.headers.get("content-type") || "";
      const payload = contentType.includes("application/json")
        ? await response.json()
        : await response.text();
      if (
        app.skills.current?.name === skill &&
        app.skills.run?.run_id === runId
      ) {
        await app.loadSkillRun(skill, runId);
      }
      if (response.ok) {
        await window.theseusLoadStudio(app);
      }
      await window.theseusOpenReasoning(app, {
        skill,
        run_id: runId,
        filename: app.reasoning.filename || artifact.filename || "",
        title:
          app.reasoning.title ||
          artifact.display_name ||
          artifact.filename ||
          "",
        created_at: app.reasoning.created_at || "",
      });
      if (!response.ok) {
        const detail =
          (payload &&
            typeof payload === "object" &&
            (payload.detail || payload.message)) ||
          (typeof payload === "string" && payload) ||
          `${response.status} ${response.statusText}`;
        throw new Error(String(detail));
      }
      const created = ((payload && payload.created) || [])
        .map(
          (deliverable) =>
            deliverable.display_name || deliverable.filename || "",
        )
        .filter(Boolean);
      app.toast(
        created.length
          ? "Rendered to Studio: " + created.join(", ")
          : "Studio products refreshed for this run",
        "success",
      );
    } catch (error) {
      app.toast("Render failed: " + (error?.message || error), "error");
    } finally {
      app.reasoning.promoting = "";
      window.theseusAfterRender(app);
    }
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
  app.studio.loading = true;
  app.studio.error = null;
  app.studio.trashLoading = true;
  app.studio.trashError = null;
  try {
    const [studioResponse, trashResponse] = await Promise.all([
      app.api("/api/ui/studio"),
      app.api("/api/ui/studio/trash"),
    ]);
    app.studio.deliverables = studioResponse.deliverables || [];
    app.studio.trash = trashResponse.artifacts || [];
    window.theseusPruneStudioSelection(app);
    app.studio.loaded = true;
    app.studio.trashLoaded = true;
  } catch (error) {
    app.studio.deliverables = [];
    app.studio.trash = [];
    app.studio.error =
      "Failed to load deliverables: " + (error?.message || error);
    app.studio.trashError =
      "Failed to load trash: " + (error?.message || error);
  } finally {
    app.studio.loading = false;
    app.studio.trashLoading = false;
    window.theseusAfterRender(app);
  }
};

window.theseusToggleStudioTrash = function theseusToggleStudioTrash(app) {
  app.studio.trashOpen = !app.studio.trashOpen;
};

window.theseusEmptyStudioTrash = async function theseusEmptyStudioTrash(app) {
  const trash = app.studio.trash || [];
  if (!trash.length || app.studio.emptyingTrash) return;
  if (
    !confirm(
      "Permanently delete every trashed Studio artifact? This cannot be undone.",
    )
  ) {
    return;
  }
  app.studio.emptyingTrash = true;
  try {
    const result = await app.api("/api/ui/studio/trash", { method: "DELETE" });
    app.toast(
      `Studio trash emptied: ${result.purged || 0} purged` +
        (result.skipped ? `, ${result.skipped} skipped` : ""),
      "ok",
    );
    await window.theseusLoadStudio(app);
  } catch (error) {
    app.toast(
      "Studio trash empty failed: " + (error?.message || error),
      "error",
    );
  } finally {
    app.studio.emptyingTrash = false;
  }
};

window.theseusStudioSelectedCount = function theseusStudioSelectedCount(app) {
  return Object.keys(app.studio.selected || {}).length;
};

window.theseusPruneStudioSelection = function theseusPruneStudioSelection(app) {
  const live = new Set(
    (app.studio.deliverables || []).map(window.theseusStudioKey),
  );
  const next = {};
  for (const key of Object.keys(app.studio.selected || {})) {
    if (live.has(key)) next[key] = app.studio.selected[key];
  }
  app.studio.selected = next;
};

window.theseusPruneStudioSelectionToFiltered =
  function theseusPruneStudioSelectionToFiltered(app) {
    const live = new Set(
      window.theseusStudioFiltered(app).map(window.theseusStudioKey),
    );
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

window.theseusStudioAllFilteredSelected =
  function theseusStudioAllFilteredSelected(app) {
    const rows = window.theseusStudioFiltered(app);
    if (!rows.length) return false;
    const selected = app.studio.selected || {};
    return rows.every(
      (deliverable) => selected[window.theseusStudioKey(deliverable)],
    );
  };

window.theseusToggleStudioSelectAllFiltered =
  function theseusToggleStudioSelectAllFiltered(app) {
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

window.theseusDeleteSelectedStudioArtifacts =
  async function theseusDeleteSelectedStudioArtifacts(app) {
    const artifacts = Object.values(app.studio.selected || {});
    if (!artifacts.length || app.studio.deleting) return;
    const label =
      artifacts.length === 1 ? "1 artifact" : artifacts.length + " artifacts";
    const names = artifacts
      .slice(0, 12)
      .map((artifact) => "- " + artifact.filename)
      .join("\n");
    const extra =
      artifacts.length > 12
        ? "\n- ...and " + (artifacts.length - 12) + " more"
        : "";
    const message =
      "Move " +
      label +
      " to Studio trash? You can recover them later.\n\n" +
      names +
      extra;
    if (!confirm(message)) {
      return;
    }
    app.studio.deleting = true;
    try {
      const result = await app.api("/api/ui/studio/artifacts", {
        method: "DELETE",
        body: JSON.stringify({ artifacts }),
      });
      app.toast(
        "Moved " + result.trashed_count + " artifact(s) to trash",
        "success",
      );
      window.theseusClearStudioSelection(app);
      await window.theseusLoadStudio(app);
    } catch (error) {
      app.toast("Trash move failed: " + (error?.message || error), "error");
    } finally {
      app.studio.deleting = false;
      window.theseusAfterRender(app);
    }
  };

window.theseusRestoreTrashedStudioArtifact =
  async function theseusRestoreTrashedStudioArtifact(app, artifact) {
    const trashId = artifact && artifact.trash_id;
    if (!trashId || app.studio.restoringTrash === trashId) return;
    app.studio.restoringTrash = trashId;
    try {
      const result = await app.api("/api/ui/studio/trash/restore", {
        method: "POST",
        body: JSON.stringify({ artifacts: [{ trash_id: trashId }] }),
      });
      if (result.conflict_count) {
        const conflict = (result.conflicts || [])[0];
        throw new Error(conflict?.reason || "restore-conflict");
      }
      app.toast(
        "Restored " + (artifact.display_name || artifact.filename),
        "success",
      );
      await window.theseusLoadStudio(app);
    } catch (error) {
      app.toast("Restore failed: " + (error?.message || error), "error");
    } finally {
      app.studio.restoringTrash = "";
      window.theseusAfterRender(app);
    }
  };

window.theseusDownloadSelectedStudioZip =
  async function theseusDownloadSelectedStudioZip(app) {
    const artifacts = Object.values(app.studio.selected || {});
    if (!artifacts.length || app.studio.zipping) return;
    app.studio.zipping = true;
    try {
      const response = await fetch("/api/ui/studio/artifacts.zip", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ artifacts }),
      });
      if (!response.ok) {
        throw new Error(response.status + " " + response.statusText);
      }
      const blob = await response.blob();
      const disposition = response.headers.get("content-disposition") || "";
      const match = disposition.match(/filename="?([^";]+)"?/i);
      const filename = match ? match[1] : "theseus-studio-products.zip";
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      const count =
        response.headers.get("x-theseus-zip-count") || artifacts.length;
      app.toast("Downloaded " + count + " product(s) as ZIP", "success");
    } catch (error) {
      app.toast("ZIP download failed: " + (error?.message || error), "error");
    } finally {
      app.studio.zipping = false;
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

window.theseusStudioLatestGroupKey = function theseusStudioLatestGroupKey(
  deliverable,
) {
  return (deliverable.skill || "") + "/" + (deliverable.filename || "");
};

window.theseusStudioGroupDescriptor = function theseusStudioGroupDescriptor(
  deliverable,
  mode,
) {
  if (mode === "chain") {
    const chain = window.theseusPrimaryChain(deliverable);
    if (chain?.chain_id) {
      return {
        key: "chain/" + chain.chain_id,
        title: chain.name || chain.chain_id,
        metaPrefix: "Chain · " + (chain.status || "unknown"),
      };
    }
    const skill = deliverable.skill || "unknown-skill";
    const runId = deliverable.run_id || "unknown-run";
    return {
      key: "single/" + skill + "/" + runId,
      title: runId,
      metaPrefix: "Single run · " + skill,
    };
  }
  if (mode === "skill") {
    const skill = deliverable.skill || "unknown-skill";
    return {
      key: "skill/" + skill,
      title: skill,
      metaPrefix: "Skill",
    };
  }
  if (mode === "run") {
    const skill = deliverable.skill || "unknown-skill";
    const runId = deliverable.run_id || "unknown-run";
    return {
      key: "run/" + skill + "/" + runId,
      title: runId,
      metaPrefix: skill,
    };
  }
  if (mode === "date") {
    const createdAt = String(deliverable.created_at || "");
    const day = createdAt.slice(0, 10) || "unknown-date";
    return {
      key: "date/" + day,
      title: day,
      metaPrefix: "Created",
    };
  }
  return {
    key: "all",
    title: "All deliverables",
    metaPrefix: "Studio",
  };
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

window.theseusStudioGrouped = function theseusStudioGrouped(app) {
  const deliverables = window.theseusStudioFiltered(app);
  const mode = app.studio.groupBy || "";
  if (!mode) {
    return [
      {
        key: "all",
        title: "All deliverables",
        meta: deliverables.length + " item(s)",
        items: deliverables,
      },
    ];
  }

  const groups = [];
  const index = new Map();
  for (const deliverable of deliverables) {
    const descriptor = window.theseusStudioGroupDescriptor(deliverable, mode);
    let group = index.get(descriptor.key);
    if (!group) {
      group = {
        key: descriptor.key,
        title: descriptor.title,
        metaPrefix: descriptor.metaPrefix,
        items: [],
      };
      index.set(descriptor.key, group);
      groups.push(group);
    }
    group.items.push(deliverable);
  }

  return groups.map((group) => ({
    key: group.key,
    title: group.title,
    meta: group.metaPrefix + " · " + group.items.length + " item(s)",
    items: group.items,
  }));
};

window.theseusStudioRenderableRows = function theseusStudioRenderableRows(app) {
  const groups = window.theseusStudioGrouped(app);
  const mode = app.studio.groupBy || "";
  if (!mode) {
    return (groups[0]?.items || []).map((deliverable) => ({
      kind: "item",
      key: window.theseusStudioKey(deliverable),
      deliverable,
    }));
  }

  return groups.flatMap((group) => {
    const rows = [
      {
        kind: "group",
        key: group.key,
        group,
      },
    ];
    for (const deliverable of group.items || []) {
      rows.push({
        kind: "item",
        key: window.theseusStudioKey(deliverable),
        deliverable,
      });
    }
    return rows;
  });
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
