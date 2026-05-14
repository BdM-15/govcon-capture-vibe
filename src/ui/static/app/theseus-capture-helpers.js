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
