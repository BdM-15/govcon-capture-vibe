window.theseusOpenProcLog = function theseusOpenProcLog(app) {
  if (app.procLog.es) return;
  try {
    const es = new EventSource("/api/ui/processing-log/stream?limit=1500");
    app.procLog.es = es;
    app.procLog.error = null;
    es.addEventListener("open", () => {
      app.procLog.streaming = true;
    });
    es.addEventListener("snapshot", (event) => {
      try {
        const payload = JSON.parse(event.data);
        app.procLog.events = payload.events || [];
        window.theseusScrollProcLog(app);
      } catch {}
    });
    es.addEventListener("event", (event) => {
      try {
        const entry = JSON.parse(event.data);
        app.procLog.events.push(entry);
        if (app.procLog.events.length > 2000) {
          app.procLog.events.splice(0, app.procLog.events.length - 2000);
        }
        window.theseusScrollProcLog(app);
      } catch {}
    });
    es.onerror = () => {
      app.procLog.streaming = false;
      app.procLog.error = "stream interrupted (will retry)";
    };
  } catch (error) {
    app.procLog.error = String(error);
  }
};

window.theseusCloseProcLog = function theseusCloseProcLog(app) {
  if (app.procLog.es) {
    try {
      app.procLog.es.close();
    } catch {}
    app.procLog.es = null;
  }
  app.procLog.streaming = false;
};

window.theseusClearProcLog = function theseusClearProcLog(app) {
  app.procLog.events = [];
};

window.theseusFilteredProcLog = function theseusFilteredProcLog(app) {
  const category = app.procLog.category;
  const filter = app.procLog.filter;
  let events = app.procLog.events;
  if (category && category !== "all") {
    events = events.filter((event) => (event.category || "other") === category);
  }
  if (filter === "phase") {
    events = events.filter((event) => event.kind === "phase" || event.phase);
  } else if (filter === "errors") {
    events = events.filter(
      (event) => event.kind === "error" || event.kind === "warning",
    );
  }
  return events;
};

window.theseusScrollProcLog = function theseusScrollProcLog(app) {
  if (!app.procLog.autoscroll) return;
  app.$nextTick(() => {
    const el = app.$refs.procLogScroll;
    if (el) el.scrollTop = el.scrollHeight;
  });
};

window.theseusLoadDocuments = async function theseusLoadDocuments(app) {
  try {
    const data = await app.api("/documents");
    const docs = [];
    const buckets = data.statuses || {};
    for (const [status, list] of Object.entries(buckets)) {
      for (const doc of list) docs.push({ ...doc, status });
    }
    docs.sort((left, right) =>
      (right.created_at || "").localeCompare(left.created_at || ""),
    );
    app.documents = docs;
  } catch {
    app.documents = [];
  }
};

const theseusUpdateUploadCollection = function theseusUpdateUploadCollection(
  app,
  collectionKey,
  id,
  patch,
) {
  app[collectionKey] = app[collectionKey].map((entry) =>
    entry.id === id ? { ...entry, ...patch } : entry,
  );
};

const theseusStageOnlyUpload = async function theseusStageOnlyUpload(
  app,
  file,
  options,
) {
  const {
    collectionKey,
    pendingStatus,
    successStatus,
    successMessage,
  } = options;

  const id = Math.random().toString(36).slice(2);
  app[collectionKey].unshift({ id, name: file.name, status: pendingStatus });

  const formData = new FormData();
  formData.append("file", file);
  try {
    const response = await fetch("/documents/upload?stage_only=true", {
      method: "POST",
      body: formData,
    });
    const payload = await response.json();
    theseusUpdateUploadCollection(app, collectionKey, id, {
      status: response.ok ? successStatus : "error",
      msg: response.ok ? successMessage : payload.message || "failed",
    });
    return response.ok;
  } catch {
    theseusUpdateUploadCollection(app, collectionKey, id, {
      status: "error",
      msg: "network",
    });
    return false;
  }
};

const theseusScheduleDocumentRefresh = function theseusScheduleDocumentRefresh(
  app,
  delayMs,
  actions,
) {
  setTimeout(() => {
    if (actions.documents) app.loadDocuments();
    if (actions.stats) app.loadStats();
    if (actions.docStats) app.loadDocStats();
  }, delayMs);
};

window.theseusUploadFiles = async function theseusUploadFiles(app, fileList) {
  const files = Array.from(fileList || []);
  if (!files.length) return;

  const tasks = files.map((file) =>
    theseusStageOnlyUpload(app, file, {
      collectionKey: "uploads",
      pendingStatus: "uploading",
      successStatus: "done",
      successMessage: "queued",
    }),
  );

  const results = await Promise.all(tasks);
  const okCount = results.filter(Boolean).length;
  const failCount = results.length - okCount;

  if (okCount === 0) {
    app.toast(`Upload failed for all ${failCount} file(s)`, "error");
    return;
  }

  try {
    app.docStats.scanning = true;
    const response = await app.api("/scan-rfp", { method: "POST" });
    const message = failCount
      ? `${okCount} file(s) queued (${failCount} failed) - extraction running`
      : `${okCount} file(s) queued - extraction running`;
    app.toast(response.message || message);
  } catch (error) {
    app.toast(`Files staged but scan failed to start: ${error.message}`, "error");
  } finally {
    app.docStats.scanning = false;
  }

  theseusScheduleDocumentRefresh(app, 1500, {
    documents: true,
    stats: true,
    docStats: true,
  });
};

window.theseusStageFiles = async function theseusStageFiles(app, fileList) {
  const files = Array.from(fileList || []);
  for (const file of files) {
    const ok = await theseusStageOnlyUpload(app, file, {
      collectionKey: "stagedUploads",
      pendingStatus: "staging",
      successStatus: "staged",
      successMessage: "ready",
    });
    if (ok) {
      app.toast(`${file.name} staged - click Scan now when ready`);
    } else {
      app.toast(`Stage failed: ${file.name}`, "error");
    }
  }
  window.theseusAfterRender(app);
};

window.theseusScanRfp = async function theseusScanRfp(app) {
  app.docStats.scanning = true;
  try {
    const response = await app.api("/scan-rfp", { method: "POST" });
    app.toast(response.message || "Scan started");
    theseusScheduleDocumentRefresh(app, 1500, {
      documents: true,
      docStats: true,
    });
  } catch (error) {
    app.toast("Scan failed: " + error.message, "error");
  } finally {
    app.docStats.scanning = false;
  }
};

window.theseusLoadDocStats = async function theseusLoadDocStats(app) {
  try {
    const counts = await app.api("/documents/status_counts");
    app.docStats.counts = counts.status_counts || counts || {};
  } catch {}

  try {
    const pipeline = await app.api("/documents/pipeline_status");
    app.docStats.pipeline = {
      busy: !!pipeline.busy,
      latest_message: pipeline.latest_message || "",
      job_name: pipeline.job_name || "",
    };
  } catch {
    app.docStats.pipeline = {
      busy: false,
      latest_message: "",
      job_name: "",
    };
  }
};

window.theseusStartDocStatsPoll = function theseusStartDocStatsPoll(app) {
  window.theseusStopDocStatsPoll(app);
  app.loadDocStats();
  app._docStatsTimer = setInterval(() => app.loadDocStats(), 4000);
};

window.theseusStopDocStatsPoll = function theseusStopDocStatsPoll(app) {
  if (!app._docStatsTimer) return;
  clearInterval(app._docStatsTimer);
  app._docStatsTimer = null;
};

window.theseusCancelPipeline = async function theseusCancelPipeline(app) {
  if (
    !confirm(
      "Cancel the running document-processing pipeline? Any in-flight chunk extraction will be aborted at the next checkpoint.",
    )
  ) {
    return;
  }
  app.docStats.cancelling = true;
  try {
    await app.api("/documents/cancel_pipeline", { method: "POST" });
    app.toast("Pipeline cancellation requested");
    theseusScheduleDocumentRefresh(app, 800, { docStats: true });
  } catch (error) {
    app.toast("Cancel failed: " + error.message, "error");
  } finally {
    app.docStats.cancelling = false;
  }
};

window.theseusReprocessFailed = async function theseusReprocessFailed(app) {
  const failed = app.docStats.counts.failed ?? 0;
  if (!confirm(`Re-queue ${failed} failed document(s) for another extraction pass?`)) {
    return;
  }
  app.docStats.reprocessing = true;
  try {
    await app.api("/documents/reprocess_failed", {
      method: "POST",
    });
    app.toast(`Re-queued ${failed} failed document(s)`);
    theseusScheduleDocumentRefresh(app, 1000, {
      documents: true,
      docStats: true,
    });
  } catch (error) {
    app.toast("Reprocess failed: " + error.message, "error");
  } finally {
    app.docStats.reprocessing = false;
  }
};

window.theseusDeleteDocument = async function theseusDeleteDocument(app, doc) {
  const label = doc.file_path || doc.id;
  if (
    !confirm(
      `Permanently delete "${label}" and all derived entities, relationships, chunks, and embeddings?\n\nThis cannot be undone.`,
    )
  ) {
    return;
  }
  app.docStats.deletingId = doc.id;
  try {
    await app.api("/documents/delete_document", {
      method: "DELETE",
      body: JSON.stringify({
        doc_ids: [doc.id],
        delete_file: false,
      }),
    });
    app.documents = app.documents.filter((item) => item.id !== doc.id);
    app.toast(`Deleted ${label}`);
    app.loadDocStats();
    app.loadStats();
  } catch (error) {
    app.toast("Delete failed: " + error.message, "error");
  } finally {
    app.docStats.deletingId = null;
  }
};

window.theseusFilteredDocuments = function theseusFilteredDocuments(app) {
  const query = (app.docFilter.query || "").toLowerCase().trim();
  const status = app.docFilter.status;
  return app.documents.filter((doc) => {
    if (status && doc.status !== status) return false;
    if (query && !(doc.file_path || doc.id || "").toLowerCase().includes(query)) {
      return false;
    }
    return true;
  });
};

window.theseusAskAboutDocument = function theseusAskAboutDocument(app, doc) {
  app.active = "chat";
  app.composer = `Focus on the document "${doc.file_path || doc.id}". `;
  app.newChat(doc.file_path || doc.id);
};