// Capture Stream — tracer-bullet POST handler for /api/ui/vault/capture (#151).
// Sends the raw body as { body }, prepends the returned CapturedNote to the
// stream so a card materializes at the top, and clears the input on success.
window.theseusVaultCaptureSubmit = async function theseusVaultCaptureSubmit(app) {
  const body = (app.vaultCaptureBody || "").trim();
  if (!body) return;
  if (app.vaultCapturing) return;
  app.vaultCapturing = true;
  try {
    const resp = await fetch("/api/ui/vault/capture", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body }),
    });
    if (!resp.ok) {
      const detail = await resp.text();
      app.toast("Capture failed: " + (detail || resp.status), "error");
      return;
    }
    const note = await resp.json();
    app.vaultCaptureStream = [note, ...(app.vaultCaptureStream || [])];
    app.vaultCaptureBody = "";
  } catch (error) {
    app.toast("Capture failed: " + error.message, "error");
  } finally {
    app.vaultCapturing = false;
  }
};
