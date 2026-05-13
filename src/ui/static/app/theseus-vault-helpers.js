window.theseusLoadVaultNotes = async function theseusLoadVaultNotes(app) {
  app.vaultNotesLoading = true;
  try {
    const data = await app.api("/api/ui/vault/notes");
    app.vaultNotes = data.notes || [];
  } catch (error) {
    app.toast("Failed to load vault notes: " + error.message, "error");
  } finally {
    app.vaultNotesLoading = false;
  }
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
