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
  const isImage = /\bimage analysis\b|\bimage path\s*:/i.test(raw) && !isTable;
  const isEquation = /\bequation analysis\b|\\begin\{equation\}|\$\$/i.test(
    head,
  );

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

const THESEUS_IMAGE_EXTENSIONS = new Set([
  "png",
  "jpg",
  "jpeg",
  "gif",
  "webp",
  "svg",
]);

const THESEUS_VIDEO_EXTENSIONS = new Set(["mp4", "webm", "mov"]);
const THESEUS_TEXT_EXTENSIONS = new Set(["txt", "log", "yaml", "yml"]);
const THESEUS_SPREADSHEET_EXTENSIONS = new Set(["xlsx", "xls"]);
const THESEUS_DOCUMENT_EXTENSIONS = new Set(["docx", "doc"]);
const THESEUS_CODE_ARTIFACT_EXTENSIONS = new Set([
  "json",
  "yaml",
  "yml",
  "md",
  "txt",
]);
const THESEUS_ARCHIVE_EXTENSIONS = new Set(["zip", "tar", "gz"]);

const theseusNormalizedExtension = function theseusNormalizedExtension(value) {
  return (value || "").toLowerCase().replace(/^\./, "");
};

window.theseusStudioFormatFor = function theseusStudioFormatFor(deliverable) {
  const ext = theseusNormalizedExtension(deliverable.ext);
  if (ext === "pdf") return "pdf";
  if (THESEUS_VIDEO_EXTENSIONS.has(ext)) return "video";
  if (THESEUS_IMAGE_EXTENSIONS.has(ext)) {
    return "image";
  }
  if (ext === "md" || ext === "markdown") return "md";
  if (ext === "json") return "json";
  if (ext === "csv") return "csv";
  if (THESEUS_TEXT_EXTENSIONS.has(ext)) {
    return "text";
  }
  if (ext === "docx") return "docx";
  if (THESEUS_SPREADSHEET_EXTENSIONS.has(ext)) return "xlsx";
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
  const ext = theseusNormalizedExtension((name || "").split(".").pop());
  if (normalizedMime.startsWith("image/") || THESEUS_IMAGE_EXTENSIONS.has(ext)) {
    return "image";
  }
  if (normalizedMime.startsWith("video/") || THESEUS_VIDEO_EXTENSIONS.has(ext)) {
    return "film";
  }
  if (normalizedMime.startsWith("audio/")) return "music";
  if (ext === "pdf" || normalizedMime === "application/pdf") return "file-text";
  if (["pptx", "ppt"].includes(ext)) return "presentation";
  if (THESEUS_DOCUMENT_EXTENSIONS.has(ext)) return "file-text";
  if (THESEUS_SPREADSHEET_EXTENSIONS.has(ext) || ext === "csv") return "table";
  if (THESEUS_CODE_ARTIFACT_EXTENSIONS.has(ext)) return "file-code";
  if (THESEUS_ARCHIVE_EXTENSIONS.has(ext)) return "archive";
  return "file";
};

window.theseusStudioArtifactHref = function theseusStudioArtifactHref(
  skill,
  runId,
  filename,
) {
  const parts = String(filename || "")
    .split("/")
    .filter(Boolean)
    .map((part) => encodeURIComponent(part));
  return (
    "/api/ui/skills/" +
    encodeURIComponent(skill) +
    "/runs/" +
    encodeURIComponent(runId) +
    "/artifacts/" +
    parts.join("/")
  );
};

window.theseusStudioDownloadHref = function theseusStudioDownloadHref(
  deliverable,
) {
  return window.theseusStudioArtifactHref(
    deliverable.skill,
    deliverable.run_id,
    deliverable.filename,
  );
};

const THESEUS_EXPAND_BARE_CITE_DIGITS = (digits) => {
  if (digits.length <= 1) return [digits];
  const parts = digits.split("");
  if (parts.every((d) => d >= "1" && d <= "5")) return parts;
  return [digits];
};

window.theseusRenderMd = function theseusRenderMd(text, msgIdx, options) {
  if (!text) return "";
  const light = Boolean(options && options.light);
  const cacheKey =
    !light && msgIdx != null
      ? `${msgIdx}:${text.length}:${text.charCodeAt(0) || 0}:${text.charCodeAt(text.length - 1) || 0}`
      : "";
  if (cacheKey && window.theseusRenderMdCache?.[cacheKey]) {
    return window.theseusRenderMdCache[cacheKey];
  }
  try {
    const html = window.marked
      ? window.marked.parse(text, { breaks: true, gfm: true })
      : text;
    const safe = window.DOMPurify
      ? window.DOMPurify.sanitize(html, {
          ADD_ATTR: ["data-cite", "data-msg-idx", "data-cite-anchor"],
        })
      : html;
    const rendered = light ? safe : window.theseusEnhanceCitations(safe, msgIdx);
    if (cacheKey) {
      if (!window.theseusRenderMdCache) window.theseusRenderMdCache = {};
      window.theseusRenderMdCache[cacheKey] = rendered;
    }
    return rendered;
  } catch (_) {
    return text;
  }
};

window.theseusEnhanceCitations = function theseusEnhanceCitations(html, msgIdx) {
  if (!html || typeof window === "undefined" || !window.document) {
    return html;
  }

  const idx = msgIdx == null ? 0 : msgIdx;
  try {
    const wrap = document.createElement("div");
    wrap.innerHTML = html;

    const headings = wrap.querySelectorAll("h1, h2, h3, h4, h5, h6");
    let refHeading = null;
    for (const heading of headings) {
      const text = (heading.textContent || "").trim().toLowerCase();
      if (
        text === "references" ||
        text === "sources" ||
        text === "citations"
      ) {
        refHeading = heading;
        break;
      }
    }

    const refMap = {};
    if (refHeading) {
      let node = refHeading.nextElementSibling;
      while (node) {
        if (/^H[1-6]$/.test(node.tagName)) break;
        const registerRefLine = (element, text) => {
          const match = (text || "").match(/^\s*\[(\d+)\]/);
          if (!match) return;
          const refNumber = match[1];
          const anchorId = `cite-${idx}-${refNumber}`;
          element.setAttribute("id", anchorId);
          element.setAttribute("data-cite-anchor", refNumber);
          element.classList.add("cite-target");
          refMap[refNumber] = anchorId;
        };
        const items = node.querySelectorAll ? node.querySelectorAll("li") : [];
        items.forEach((item) => registerRefLine(item, item.textContent || ""));
        const paras = node.querySelectorAll ? node.querySelectorAll("p") : [];
        paras.forEach((para) => registerRefLine(para, para.textContent || ""));
        node = node.nextElementSibling;
      }
    }

    const skipParents = new Set(["CODE", "PRE", "A", "BUTTON", "SCRIPT", "STYLE"]);
    const refStart = refHeading || null;
    const inRefSection = (node) => {
      if (!refStart) return false;
      let current = node;
      while (current && current !== wrap) {
        let sibling = current;
        while (sibling) {
          if (sibling === refStart) return true;
          sibling = sibling.previousSibling;
        }
        current = current.parentNode;
      }
      return false;
    };

    const walker = document.createTreeWalker(wrap, NodeFilter.SHOW_TEXT, {
      acceptNode: (node) => {
        if (!node.parentNode) return NodeFilter.FILTER_REJECT;
        if (skipParents.has(node.parentNode.nodeName)) {
          return NodeFilter.FILTER_REJECT;
        }
        if (inRefSection(node)) return NodeFilter.FILTER_REJECT;
        if (!/\[\s*\d+(?:\s*,\s*\d+)*\s*\]/.test(node.nodeValue)) {
          return NodeFilter.FILTER_REJECT;
        }
        return NodeFilter.FILTER_ACCEPT;
      },
    });

    const targets = [];
    let currentNode;
    while ((currentNode = walker.nextNode())) targets.push(currentNode);

    const appendCiteChip = (frag, number) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "cite-chip";
      btn.setAttribute("data-cite", number);
      btn.setAttribute("data-msg-idx", String(idx));
      btn.title = refMap[number]
        ? `Jump to reference [${number}]`
        : `Citation [${number}] (no matching reference)`;
      if (!refMap[number]) btn.classList.add("cite-chip-orphan");
      btn.textContent = number;
      frag.appendChild(btn);
    };

    const replaceCitationsInNode = (node, pattern, extractNumbers, { prefix = "" } = {}) => {
      const text = node.nodeValue;
      const frag = document.createDocumentFragment();
      let last = 0;
      let match;
      pattern.lastIndex = 0;
      while ((match = pattern.exec(text)) !== null) {
        if (match.index > last) {
          frag.appendChild(document.createTextNode(text.slice(last, match.index)));
        }
        if (prefix) frag.appendChild(document.createTextNode(prefix));
        const numbers = extractNumbers(match);
        numbers.forEach((number, numberIndex) => {
          appendCiteChip(frag, number);
          if (numberIndex < numbers.length - 1) {
            frag.appendChild(document.createTextNode(" "));
          }
        });
        last = match.index + match[0].length;
      }
      if (last < text.length) {
        frag.appendChild(document.createTextNode(text.slice(last)));
      }
      node.parentNode.replaceChild(frag, node);
    };

    const citeRe = /\[\s*(\d+(?:\s*,\s*\d+)*)\s*\]/g;
    targets.forEach((node) => {
      replaceCitationsInNode(node, citeRe, (match) =>
        match[1].split(",").map((part) => part.trim()),
      );
    });

    // Models sometimes emit bare trailing numbers (e.g. "...systems. 12" for [1][2]).
    const bareCiteRe =
      /(?<=[.!?)])(?<!\d)\s+(\d{1,4})(?=\s+[A-Z"(]|\s*$)/g;
    const bareTailCiteRe = /(?<=[A-Za-z])\s+(\d{1,4})$/;
    const bareWalker = document.createTreeWalker(wrap, NodeFilter.SHOW_TEXT, {
      acceptNode: (node) => {
        if (!node.parentNode) return NodeFilter.FILTER_REJECT;
        if (skipParents.has(node.parentNode.nodeName)) {
          return NodeFilter.FILTER_REJECT;
        }
        if (inRefSection(node)) return NodeFilter.FILTER_REJECT;
        const value = node.nodeValue || "";
        bareCiteRe.lastIndex = 0;
        if (bareCiteRe.test(value) || bareTailCiteRe.test(value)) {
          bareCiteRe.lastIndex = 0;
          bareTailCiteRe.lastIndex = 0;
          return NodeFilter.FILTER_ACCEPT;
        }
        return NodeFilter.FILTER_REJECT;
      },
    });
    const bareTargets = [];
    while ((currentNode = bareWalker.nextNode())) bareTargets.push(currentNode);
    bareTargets.forEach((node) => {
      replaceCitationsInNode(node, bareCiteRe, (match) =>
        THESEUS_EXPAND_BARE_CITE_DIGITS(match[1] || ""),
      );
      replaceCitationsInNode(node, bareTailCiteRe, (match) =>
        THESEUS_EXPAND_BARE_CITE_DIGITS(match[1] || ""),
      );
    });

    // Unicode circled digits (①②) — some models use these instead of [N].
    const circledCiteRe = /[\u2460-\u2473]/g;
    const circledWalker = document.createTreeWalker(wrap, NodeFilter.SHOW_TEXT, {
      acceptNode: (node) => {
        if (!node.parentNode) return NodeFilter.FILTER_REJECT;
        if (skipParents.has(node.parentNode.nodeName)) {
          return NodeFilter.FILTER_REJECT;
        }
        if (inRefSection(node)) return NodeFilter.FILTER_REJECT;
        if (!circledCiteRe.test(node.nodeValue)) return NodeFilter.FILTER_REJECT;
        circledCiteRe.lastIndex = 0;
        return NodeFilter.FILTER_ACCEPT;
      },
    });
    const circledTargets = [];
    while ((currentNode = circledWalker.nextNode())) circledTargets.push(currentNode);
    circledTargets.forEach((node) => {
      replaceCitationsInNode(node, circledCiteRe, (match) => [
        String(match[0].charCodeAt(0) - 0x245f),
      ]);
    });

    return wrap.innerHTML;
  } catch (_) {
    return html;
  }
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

window.theseusToggleSources = function theseusToggleSources(
  app,
  index,
  forceOpen,
) {
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
      ? msg.sources.chunks.some(
          (chunk) => String(chunk.reference_id) === String(n),
        )
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
