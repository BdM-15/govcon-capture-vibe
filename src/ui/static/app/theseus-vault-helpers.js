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
