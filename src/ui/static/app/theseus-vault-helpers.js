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
