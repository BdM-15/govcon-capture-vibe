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
