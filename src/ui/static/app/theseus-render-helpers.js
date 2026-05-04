window.theseusBasename = function theseusBasename(path) {
  if (!path) return "";
  const normalized = String(path).replace(/\\/g, "/");
  const parts = normalized.split("/");
  return parts[parts.length - 1] || normalized;
};

window.theseusMemoryLabel = function theseusMemoryLabel(stats, currentChat) {
  const cap = (stats && stats.chat && stats.chat.history_pairs_cap) || 20;
  const messages = (currentChat && currentChat.messages) || [];
  let pairs = 0;
  for (let index = 0; index < messages.length - 1; index++) {
    if (
      messages[index].role === "user" &&
      messages[index + 1].role === "assistant"
    ) {
      pairs++;
      index++;
    }
  }
  const inContext = Math.min(pairs, cap);
  if (pairs === 0) return "multi-turn · follow-ups carry context";
  if (pairs > cap) {
    return `${inContext} of ${pairs} turns in context · older trimmed`;
  }
  return `${inContext} turn${inContext === 1 ? "" : "s"} in context`;
};

window.theseusFormatSource = function theseusFormatSource(source) {
  const raw = source && source.preview ? String(source.preview) : "";
  const out = {
    kind: "text",
    badge: "TEXT",
    caption: "",
    body: raw,
    tableSummary: "",
  };
  if (!raw) {
    out.kind = "unknown";
    out.badge = "EMPTY";
    return out;
  }
  const head = raw.slice(0, 64).toLowerCase();
  const isTable = /\btable analysis\b|\bstructure:\s*<table/i.test(raw);
  const isImage =
    /\bimage analysis\b|\bimage path\s*:/i.test(raw) && !isTable;
  const isEquation = /\bequation analysis\b|\\begin\{equation\}|\$\$/i.test(head);

  const captionMatch = raw.match(/(?:^|\n)\s*Caption\s*:\s*([^\n]+)/i);
  if (captionMatch) {
    const caption = captionMatch[1].trim();
    if (caption && caption.toLowerCase() !== "none") out.caption = caption;
  }

  if (isTable) {
    out.kind = "table";
    out.badge = "TABLE";
    const structureIndex = raw.search(/Structure\s*:/i);
    const structureHtml = structureIndex >= 0 ? raw.slice(structureIndex) : raw;
    const tableRows = structureHtml.match(/<tr[\s>]/gi) || [];
    const firstTableRow = structureHtml.match(/<tr[^>]*>[\s\S]*?<\/tr>/i);
    const cellCount = firstTableRow
      ? (firstTableRow[0].match(/<t[dh][\s>]/gi) || []).length
      : 0;

    let markdownRows = 0;
    let markdownCols = 0;
    if (!tableRows.length) {
      const markdownLines = structureHtml
        .split(/\n/)
        .filter((line) => /^\s*\|.*\|\s*$/.test(line));
      const dataLines = markdownLines.filter(
        (line) => !/^\s*\|[\s:|-]+\|\s*$/.test(line),
      );
      markdownRows = dataLines.length;
      if (dataLines.length) {
        markdownCols = (dataLines[0].match(/\|/g) || []).length - 1;
      }
    }

    const totalRows = tableRows.length || markdownRows;
    const totalCols = cellCount || markdownCols;
    const rowsLabel = totalRows
      ? `${totalRows}${source.truncated ? "+" : ""} rows`
      : "rows unknown";
    const colsLabel = totalCols ? ` × ${totalCols} cols` : "";
    out.tableSummary = `${rowsLabel}${colsLabel}${
      source.truncated ? " (preview clipped)" : ""
    }`;

    const analysisMatch = raw.match(
      /(?:^|\n)\s*Analysis\s*:\s*([\s\S]+?)(?=\n\s*(?:Footnotes|Image Path|Caption|Structure)\s*:|$)/i,
    );
    const footnotesMatch = raw.match(
      /(?:^|\n)\s*Footnotes\s*:\s*([\s\S]+?)(?=\n\s*(?:Analysis|Image Path|Caption|Structure)\s*:|$)/i,
    );
    if (analysisMatch && analysisMatch[1].trim()) {
      out.body = analysisMatch[1].trim();
    } else if (footnotesMatch && footnotesMatch[1].trim()) {
      out.body = footnotesMatch[1].trim();
    } else {
      out.body = raw
        .replace(/(?:^|\n)\s*Image Path\s*:\s*[^\n]+/i, "")
        .replace(/(?:^|\n)\s*Structure\s*:\s*<table[\s\S]*?<\/table>\s*/i, "\n")
        .replace(/(?:^|\n)\s*Structure\s*:\s*<table[\s\S]*$/i, "")
        .replace(/(?:^|\n)\s*Structure\s*:[^\n]*(?:\n\s*\|[^\n]*)+/i, "\n")
        .replace(/\n{3,}/g, "\n\n")
        .trim();
    }
    return out;
  }

  if (isImage) {
    out.kind = "image";
    out.badge = "IMAGE";
    out.body = raw
      .replace(/(?:^|\n)\s*Image Path\s*:\s*[^\n]+/i, "")
      .replace(/(?:^|\n)\s*Caption\s*:\s*[^\n]+/i, "")
      .replace(/^\s*Image Analysis\s*:?\s*/i, "")
      .trim();
    return out;
  }

  if (isEquation) {
    out.kind = "equation";
    out.badge = "EQN";
    out.body = raw.replace(/^\s*Equation Analysis\s*:?\s*/i, "").trim();
    return out;
  }

  out.kind = "text";
  out.badge = "TEXT";
  out.body = raw;
  return out;
};

window.theseusEntityColor = function theseusEntityColor(type) {
  const palette = {
    document: "#00f0ff",
    document_section: "#22c1f5",
    amendment: "#7df9ff",
    clause: "#a78bfa",
    regulatory_reference: "#c084fc",
    requirement: "#ff2bd6",
    proposal_instruction: "#ff6ad5",
    evaluation_factor: "#ffb020",
    subfactor: "#ffd166",
    performance_standard: "#fbbf24",
    compliance_artifact: "#f59e0b",
    deliverable: "#00ff9c",
    work_scope_item: "#34d399",
    transition_activity: "#10b981",
    contract_line_item: "#84cc16",
    workload_metric: "#a3e635",
    technical_specification: "#bef264",
    organization: "#ff3b6b",
    person: "#fb7185",
    labor_category: "#f472b6",
    strategic_theme: "#ec4899",
    customer_priority: "#d946ef",
    pain_point: "#ef4444",
    past_performance_reference: "#f97316",
    proposal_volume: "#fdba74",
    equipment: "#60a5fa",
    technology: "#3b82f6",
    government_furnished_item: "#1d4ed8",
    pricing_element: "#fde047",
    program: "#facc15",
    concept: "#94a3b8",
    event: "#cbd5e1",
    location: "#64748b",
  };
  return palette[type] || "#64748b";
};

window.theseusStudioFormatFor = function theseusStudioFormatFor(deliverable) {
  const ext = (deliverable.ext || "").toLowerCase().replace(/^\./, "");
  if (ext === "pdf") return "pdf";
  if (ext === "mp4" || ext === "webm" || ext === "mov") return "video";
  if (["png", "jpg", "jpeg", "gif", "webp", "svg"].includes(ext)) {
    return "image";
  }
  if (ext === "md" || ext === "markdown") return "md";
  if (ext === "json") return "json";
  if (ext === "csv") return "csv";
  if (ext === "txt" || ext === "log" || ext === "yaml" || ext === "yml") {
    return "text";
  }
  if (ext === "docx") return "docx";
  if (ext === "xlsx" || ext === "xls") return "xlsx";
  return "unsupported";
};

window.theseusExtractJsonChunkIds = function theseusExtractJsonChunkIds(text) {
  if (!text) return [];
  const re = /chunk-[0-9a-f]{8,}/gi;
  const seen = new Set();
  const out = [];
  let match;
  while ((match = re.exec(text)) !== null) {
    const id = match[0];
    if (!seen.has(id)) {
      seen.add(id);
      out.push(id);
    }
    if (out.length >= 200) break;
  }
  return out;
};

window.theseusReasoningStepIcon = function theseusReasoningStepIcon(kind) {
  return (
    {
      system: "settings",
      user: "user",
      assistant_text: "message-circle",
      tool_action: "wrench",
    }[kind] || "circle"
  );
};

window.theseusPrettyJson = function theseusPrettyJson(value) {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
};

window.theseusFormatBytes = function theseusFormatBytes(n) {
  if (!n || n < 0) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let index = 0;
  let value = n;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index++;
  }
  return (index === 0 ? value : value.toFixed(1)) + " " + units[index];
};

window.theseusArtifactIcon = function theseusArtifactIcon(mime, name) {
  const normalizedMime = (mime || "").toLowerCase();
  const ext = ((name || "").split(".").pop() || "").toLowerCase();
  if (
    normalizedMime.startsWith("image/") ||
    ["png", "jpg", "jpeg", "gif", "webp", "svg"].includes(ext)
  ) {
    return "image";
  }
  if (
    normalizedMime.startsWith("video/") ||
    ["mp4", "webm", "mov"].includes(ext)
  ) {
    return "film";
  }
  if (normalizedMime.startsWith("audio/")) return "music";
  if (ext === "pdf" || normalizedMime === "application/pdf") return "file-text";
  if (["pptx", "ppt"].includes(ext)) return "presentation";
  if (["docx", "doc"].includes(ext)) return "file-text";
  if (["xlsx", "xls", "csv"].includes(ext)) return "table";
  if (["json", "yaml", "yml", "md", "txt"].includes(ext)) return "file-code";
  if (["zip", "tar", "gz"].includes(ext)) return "archive";
  return "file";
};

window.theseusStudioDownloadHref = function theseusStudioDownloadHref(deliverable) {
  return (
    "/api/ui/skills/" +
    encodeURIComponent(deliverable.skill) +
    "/runs/" +
    encodeURIComponent(deliverable.run_id) +
    "/artifacts/" +
    encodeURIComponent(deliverable.filename)
  );
};

window.theseusScrollToRefList = function theseusScrollToRefList(app, idx, n) {
  const el = document.getElementById(`cite-${idx}-${n}`);
  if (!el) {
    app.toast(`Reference [${n}] not found in this answer`, "error");
    return;
  }
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  el.classList.remove("cite-flash");
  void el.offsetWidth;
  el.classList.add("cite-flash");
};

window.theseusToggleSources = function theseusToggleSources(app, index, forceOpen) {
  const messages = app.currentChat?.messages;
  if (!messages || !messages[index]) return;
  const current = messages[index];
  const next = forceOpen === true ? true : !current.sourcesOpen;
  const updated = { ...current, sourcesOpen: next };
  messages.splice(index, 1, updated);
};

window.theseusHandleCiteClick = function theseusHandleCiteClick(app, ev) {
  const btn =
    ev.target && ev.target.closest ? ev.target.closest(".cite-chip") : null;
  if (!btn) return;
  ev.preventDefault();
  const n = btn.getAttribute("data-cite");
  const idx = btn.getAttribute("data-msg-idx");
  if (!n || idx == null) return;

  const numericIndex = Number(idx);
  const msg = app.currentChat?.messages?.[numericIndex];
  const hasSources =
    msg && msg.sources && Array.isArray(msg.sources.chunks)
      ? msg.sources.chunks.some((chunk) => String(chunk.reference_id) === String(n))
      : false;

  if (hasSources) {
    if (!msg.sourcesOpen) {
      window.theseusToggleSources(app, numericIndex, true);
    }
    app.$nextTick(() => {
      const row = document.getElementById(`source-${idx}-${n}`);
      if (row) {
        row.scrollIntoView({ behavior: "smooth", block: "center" });
        row.classList.remove("cite-flash");
        void row.offsetWidth;
        row.classList.add("cite-flash");
        return;
      }
      window.theseusScrollToRefList(app, idx, n);
    });
    return;
  }

  window.theseusScrollToRefList(app, idx, n);
};