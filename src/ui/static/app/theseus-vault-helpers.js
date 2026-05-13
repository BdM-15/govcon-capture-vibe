window.theseusLoadVaultNotes = async function theseusLoadVaultNotes(app) {
  app.vaultNotesLoading = true;
  try {
    const params = new URLSearchParams();
    if (app.vaultSearch) params.set("q", app.vaultSearch);
    if (app.vaultFilterType) params.set("type", app.vaultFilterType);
    if (app.vaultFilterStatus) params.set("status", app.vaultFilterStatus);
    if (app.vaultFilterTopic) params.set("topic", app.vaultFilterTopic);
    if (app.vaultFilterPursuit) params.set("pursuit", app.vaultFilterPursuit);
    const qs = params.toString() ? "?" + params.toString() : "";
    const data = await app.api("/api/ui/vault/notes" + qs);
    app.vaultNotes = data.notes || [];
  } catch (error) {
    app.toast("Failed to load vault notes: " + error.message, "error");
  } finally {
    app.vaultNotesLoading = false;
  }
};

window.theseusVaultSelectNote = async function theseusVaultSelectNote(app, note) {
  try {
    // Fetch full note (includes body)
    const full = await app.api("/api/ui/vault/notes/" + note.id);
    app.vaultActiveNote = { ...full };
    app.vaultEditorMode = "editor";
  } catch (error) {
    app.toast("Failed to load note: " + error.message, "error");
  }
};

window.theseusVaultNewNote = async function theseusVaultNewNote(app) {
  try {
    const resp = await fetch("/api/ui/vault/notes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: "New Note", body: "", note_type: "raw", topic: "", source: "manual" }),
    });
    if (!resp.ok) throw new Error("Create failed");
    const note = await resp.json();
    app.vaultActiveNote = { ...note };
    app.vaultEditorMode = "editor";
    await window.theseusLoadVaultNotes(app);
  } catch (error) {
    app.toast("Failed to create note: " + error.message, "error");
  }
};

window.theseusVaultSaveNote = async function theseusVaultSaveNote(app) {
  if (!app.vaultActiveNote) return;
  try {
    const resp = await fetch("/api/ui/vault/notes/" + app.vaultActiveNote.id, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: app.vaultActiveNote.title,
        body: app.vaultActiveNote.body,
        note_type: app.vaultActiveNote.type,
        topic: app.vaultActiveNote.topic || "",
        source: app.vaultActiveNote.source || "manual",
        status: app.vaultActiveNote.status || "raw",
        pursuit: app.vaultActiveNote.pursuit || null,
        tags: app.vaultActiveNote.tags || [],
      }),
    });
    if (!resp.ok) throw new Error("Save failed");
    const updated = await resp.json();
    app.vaultActiveNote = { ...updated };
    await window.theseusLoadVaultNotes(app);
  } catch (error) {
    app.toast("Auto-save failed: " + error.message, "error");
  }
};

window.theseusVaultScheduleSave = function theseusVaultScheduleSave(app) {
  if (app.vaultAutoSaveTimer) clearTimeout(app.vaultAutoSaveTimer);
  app.vaultAutoSaveTimer = setTimeout(() => window.theseusVaultSaveNote(app), 2000);
};



window.theseusDeleteVaultNote = async function theseusDeleteVaultNote(app, id) {
  try {
    const resp = await fetch("/api/ui/vault/notes/" + id, { method: "DELETE" });
    if (!resp.ok) throw new Error("Delete failed");
    await window.theseusLoadVaultNotes(app);
  } catch (error) {
    app.toast("Failed to delete note: " + error.message, "error");
  }
};

window.theseusPolishVaultNote = async function theseusPolishVaultNote(app, id) {
  try {
    const resp = await fetch("/api/ui/vault/notes/" + id + "/polish", { method: "POST" });
    if (resp.status === 503) {
      app.toast("Polish requires Ollama — start Ollama and restart Theseus.", "error");
      return;
    }
    if (!resp.ok) throw new Error("Polish failed");
    await window.theseusLoadVaultNotes(app);
    app.toast("Note polished", "success");
  } catch (error) {
    app.toast("Failed to polish note: " + error.message, "error");
  }
};

window.theseusVaultPromoteNote = async function theseusVaultPromoteNote(app, id) {
  try {
    const resp = await fetch("/api/ui/vault/notes/" + id + "/promote", { method: "POST" });
    if (!resp.ok) throw new Error("Promote failed");
    const updated = await resp.json();
    if (app.vaultActiveNote && app.vaultActiveNote.id === id) {
      app.vaultActiveNote = { ...updated };
    }
    await window.theseusLoadVaultNotes(app);
    app.toast("Note promoted to " + updated.status, "success");
  } catch (error) {
    app.toast("Failed to promote note: " + error.message, "error");
  }
};

window.theseusVaultAskTheseus = async function theseusVaultAskTheseus(app, id) {
  if (!id) return;
  app.vaultAskLoading = true;
  app.vaultAskAnswer = "";
  app.vaultAskSources = [];
  try {
    const resp = await fetch("/api/ui/vault/notes/" + id + "/ask-theseus", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workspace: app.stats ? app.stats.workspace : null }),
    });
    if (!resp.ok) throw new Error("Ask Theseus failed (" + resp.status + ")");
    const data = await resp.json();
    app.vaultAskAnswer = data.answer || "";
    app.vaultAskSources = data.sources || [];
  } catch (error) {
    app.toast("Ask Theseus error: " + error.message, "error");
  } finally {
    app.vaultAskLoading = false;
  }
};

window.theseusVaultSaveAsNote = async function theseusVaultSaveAsNote(app) {
  if (!app.vaultAskAnswer || !app.vaultActiveNote) return;
  try {
    const resp = await fetch(
      "/api/ui/vault/notes/" + app.vaultActiveNote.id + "/ask-theseus/save",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          answer: app.vaultAskAnswer,
          source_title: app.vaultActiveNote.title || "",
        }),
      }
    );
    if (!resp.ok) throw new Error("Save as Note failed (" + resp.status + ")");
    await window.theseusLoadVaultNotes(app);
    app.toast("Insight saved to vault", "success");
  } catch (error) {
    app.toast("Save as Note error: " + error.message, "error");
  }
};

window.theseusVaultLoadRecommendations = async function theseusVaultLoadRecommendations(app) {
  const workspace = app.stats && app.stats.workspace ? app.stats.workspace : null;
  if (!workspace) {
    app.vaultRecommendations = [];
    return;
  }
  app.vaultRecommendLoading = true;
  try {
    const data = await app.api("/api/ui/vault/recommend?workspace=" + encodeURIComponent(workspace) + "&limit=5");
    app.vaultRecommendations = data.recommendations || [];
  } catch (error) {
    app.toast("Failed to load recommendations: " + error.message, "error");
    app.vaultRecommendations = [];
  } finally {
    app.vaultRecommendLoading = false;
  }
};

window.theseusVaultFeedToWorkspace = async function theseusVaultFeedToWorkspace(app, id) {
  const workspace = app.stats && app.stats.workspace ? app.stats.workspace : null;
  if (!workspace || !id) return;
  try {
    const resp = await fetch("/api/ui/vault/notes/" + id + "/feed", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workspace }),
    });
    if (!resp.ok) throw new Error("Feed failed (" + resp.status + ")");
    app.toast("Note fed to workspace", "success");
    await window.theseusVaultLoadRecommendations(app);
  } catch (error) {
    app.toast("Feed to workspace error: " + error.message, "error");
  }
};

/**
 * Preview polish for a vault note. Calls POST /polish without accept=true,
 * stores the diff result and opens the diff overlay.
 */
window.theseusVaultPreviewPolish = async function theseusVaultPreviewPolish(app, id) {
  if (!id) return;
  app.vaultPolishLoading = true;
  app.vaultDiffOpen = false;
  app.vaultDiffResult = null;
  try {
    const resp = await fetch("/api/ui/vault/notes/" + id + "/polish", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model: app.vaultPolishModel || "qwen", accept: false }),
    });
    if (!resp.ok) throw new Error("Polish preview failed (" + resp.status + ")");
    app.vaultDiffResult = await resp.json();
    app.vaultDiffOpen = true;
  } catch (error) {
    app.toast("Polish preview error: " + error.message, "error");
  } finally {
    app.vaultPolishLoading = false;
  }
};

/**
 * Accept the current polish diff and persist the rewritten body to the store.
 * Closes the diff overlay and refreshes the active note.
 */
window.theseusVaultAcceptPolish = async function theseusVaultAcceptPolish(app, id) {
  if (!id) return;
  app.vaultPolishLoading = true;
  try {
    const resp = await fetch("/api/ui/vault/notes/" + id + "/polish", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model: app.vaultPolishModel || "qwen", accept: true }),
    });
    if (!resp.ok) throw new Error("Accept polish failed (" + resp.status + ")");
    const updated = await resp.json();
    app.vaultDiffOpen = false;
    app.vaultDiffResult = null;
    app.vaultActiveNote = updated;
    app.toast("Note polished and saved", "success");
    if (window.theseusLoadVaultNotes) await window.theseusLoadVaultNotes(app);
  } catch (error) {
    app.toast("Accept polish error: " + error.message, "error");
  } finally {
    app.vaultPolishLoading = false;
  }
};
