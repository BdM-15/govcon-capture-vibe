// Capture Stream — POST handler for /api/ui/vault/capture (#151) with
// graceful-degradation surfacing for #157: 503 → polish-specific toast,
// silent orchestrator fallback (auto_polished=false despite request) → marks
// the card with `_degraded: true` so the template can paint a warning state.
window.theseusVaultCaptureSubmit = async function theseusVaultCaptureSubmit(app) {
  const body = (app.vaultCaptureBody || "").trim();
  if (!body) return;
  if (app.vaultCapturing) return;
  app.vaultCapturing = true;
  const requestedPolish = true;
  try {
    const resp = await fetch("/api/ui/vault/capture", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body, auto_polish: requestedPolish }),
    });
    if (!resp.ok) {
      if (resp.status === 503) {
        app.toast(
          "Polish service unavailable — toggle auto-polish off to capture as raw.",
          "error",
        );
        return;
      }
      const detail = await resp.text();
      app.toast("Capture failed: " + (detail || resp.status), "error");
      return;
    }
    const note = await resp.json();
    if (requestedPolish && note.auto_polished === false) {
      note._degraded = true;
      app.toast(
        "Polish failed — note saved as raw. Edit later to retry.",
        "warn",
      );
    }
    app.vaultCaptureStream = [note, ...(app.vaultCaptureStream || [])];
    app.vaultCaptureBody = "";
  } catch (error) {
    app.toast("Capture failed: " + error.message, "error");
  } finally {
    app.vaultCapturing = false;
  }
};

// #155: tier rail + status chip strip — set filter then reload stream from /api/ui/vault/stream.
window.theseusVaultCaptureSetFilter = async function theseusVaultCaptureSetFilter(app, kind, value) {
  if (kind === "tier") {
    app.vaultCaptureTier = value || "";
  } else if (kind === "status") {
    app.vaultCaptureStatus = value || "";
  } else {
    return;
  }
  return window.theseusVaultCaptureLoadStream(app);
};

window.theseusVaultCaptureLoadStream = async function theseusVaultCaptureLoadStream(app) {
  const params = new URLSearchParams();
  if (app.vaultCaptureTier) params.set("tier", app.vaultCaptureTier);
  if (app.vaultCaptureStatus) params.set("status", app.vaultCaptureStatus);
  const qs = params.toString();
  const url = "/api/ui/vault/stream" + (qs ? "?" + qs : "");
  try {
    const resp = await fetch(url);
    if (!resp.ok) {
      const detail = await resp.text();
      app.toast("Stream load failed: " + (detail || resp.status), "error");
      return;
    }
    const data = await resp.json();
    app.vaultCaptureStream = data.notes || [];
  } catch (error) {
    app.toast("Stream load failed: " + error.message, "error");
  }
};

// #154: wikilink chip accept/reject — pure in-memory mutators on the captured note.
// No fetch/POST. Writeback to the .md file is explicitly out of scope per #149.
window.theseusVaultAcceptWikilink = function theseusVaultAcceptWikilink(note, suggestion) {
  if (!note._wikilinkAccepted) note._wikilinkAccepted = {};
  if (!note._wikilinkRejected) note._wikilinkRejected = {};
  note._wikilinkAccepted[suggestion] = true;
  delete note._wikilinkRejected[suggestion];
};

window.theseusVaultRejectWikilink = function theseusVaultRejectWikilink(note, suggestion) {
  if (!note._wikilinkAccepted) note._wikilinkAccepted = {};
  if (!note._wikilinkRejected) note._wikilinkRejected = {};
  note._wikilinkRejected[suggestion] = true;
  delete note._wikilinkAccepted[suggestion];
};

// #156: click-to-expand inline. Single source of truth: app.vaultCaptureExpandedId.
// Toggling the same note collapses; clicking a different note swaps (only one expanded).
window.theseusVaultCaptureToggleExpand = function theseusVaultCaptureToggleExpand(app, note) {
  if (!note || !note.note_id) return;
  app.vaultCaptureExpandedId =
    app.vaultCaptureExpandedId === note.note_id ? null : note.note_id;
};

// Line-level diff: O(n*m) LCS table → operations list of {type:'eq'|'add'|'del', text}.
// Tiny inputs (capture notes, not full files) keep this cheap.
window.theseusVaultCaptureLineDiff = function theseusVaultCaptureLineDiff(rawText, polishedText) {
  const a = (rawText || "").split("\n");
  const b = (polishedText || "").split("\n");
  const n = a.length;
  const m = b.length;
  const dp = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = 1; i <= n; i++) {
    for (let j = 1; j <= m; j++) {
      dp[i][j] = a[i - 1] === b[j - 1]
        ? dp[i - 1][j - 1] + 1
        : Math.max(dp[i - 1][j], dp[i][j - 1]);
    }
  }
  const ops = [];
  let i = n;
  let j = m;
  while (i > 0 && j > 0) {
    if (a[i - 1] === b[j - 1]) {
      ops.push({ type: "eq", text: a[i - 1] });
      i--; j--;
    } else if (dp[i - 1][j] >= dp[i][j - 1]) {
      ops.push({ type: "del", text: a[i - 1] });
      i--;
    } else {
      ops.push({ type: "add", text: b[j - 1] });
      j--;
    }
  }
  while (i > 0) { ops.push({ type: "del", text: a[--i] }); }
  while (j > 0) { ops.push({ type: "add", text: b[--j] }); }
  return ops.reverse();
};
