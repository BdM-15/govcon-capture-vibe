window.theseusLoadQuerySettings = async function theseusLoadQuerySettings(app) {
  try {
    const data = await app.api("/api/ui/settings/query");
    app.querySettings.values = { ...data.settings };
    app.querySettings.defaults = { ...data.defaults };
    app.querySettings.loaded = true;
  } catch (error) {
    app.toast("Failed loading query settings: " + error.message, "error");
  }
};

window.theseusSaveQuerySettings = async function theseusSaveQuerySettings(app) {
  app.querySettings.saving = true;
  try {
    const data = await app.api("/api/ui/settings/query", {
      method: "PUT",
      body: JSON.stringify(app.querySettings.values),
    });
    app.querySettings.values = { ...data.settings };
    app.toast("Query settings saved");
  } catch (error) {
    app.toast("Save failed: " + error.message, "error");
  } finally {
    app.querySettings.saving = false;
  }
};

window.theseusResetQuerySettings = async function theseusResetQuerySettings(app) {
  if (!confirm("Restore default query parameters for this workspace?")) return;
  try {
    const data = await app.api("/api/ui/settings/query/reset", {
      method: "POST",
    });
    app.querySettings.values = { ...data.settings };
    app.toast("Query settings reset to defaults");
  } catch (error) {
    app.toast("Reset failed: " + error.message, "error");
  }
};

window.theseusLoadSkillSettings = async function theseusLoadSkillSettings(app) {
  try {
    const data = await app.api("/api/ui/settings/skills");
    app.skillSettings.values = { ...data.settings };
    app.skillSettings.defaults = { ...data.defaults };
    app.skillSettings.loaded = true;
  } catch (error) {
    app.toast("Failed loading skill settings: " + error.message, "error");
  }
};

window.theseusSaveSkillSettings = async function theseusSaveSkillSettings(app) {
  app.skillSettings.saving = true;
  try {
    const data = await app.api("/api/ui/settings/skills", {
      method: "PUT",
      body: JSON.stringify(app.skillSettings.values),
    });
    app.skillSettings.values = { ...data.settings };
    app.toast("Skill settings saved");
  } catch (error) {
    app.toast("Save failed: " + error.message, "error");
  } finally {
    app.skillSettings.saving = false;
  }
};

window.theseusResetSkillSettings = async function theseusResetSkillSettings(app) {
  if (!confirm("Restore default skill retrieval settings for this workspace?")) {
    return;
  }
  try {
    const data = await app.api("/api/ui/settings/skills/reset", {
      method: "POST",
    });
    app.skillSettings.values = { ...data.settings };
    app.toast("Skill settings reset to defaults");
  } catch (error) {
    app.toast("Reset failed: " + error.message, "error");
  }
};

window.theseusLoadMcps = async function theseusLoadMcps(app) {
  app.mcps.loading = true;
  try {
    const data = await app.api("/api/ui/mcps");
    app.mcps.items = data.mcps || [];
    app.mcps.loaded = true;
    app.$nextTick(() => lucide.createIcons());
  } catch (error) {
    app.toast("Failed loading MCPs: " + error.message, "error");
  } finally {
    app.mcps.loading = false;
  }
};

window.theseusSaveMcpKeys = async function theseusSaveMcpKeys(app, name) {
  const keys = {};
  for (const key of Object.keys(app.mcps.drafts)) {
    if (!key.startsWith(name + ":")) continue;
    const value = (app.mcps.drafts[key] || "").trim();
    if (value) keys[key.split(":", 2)[1]] = value;
  }
  if (Object.keys(keys).length === 0) {
    app.toast("Nothing to save — all fields blank", "info");
    return;
  }

  app.mcps.saving[name] = true;
  try {
    const data = await app.api(`/api/ui/mcps/${name}/keys`, {
      method: "POST",
      body: JSON.stringify({ keys, restart: true }),
    });
    if (data.status === "restarting") {
      app.toast(`Saved ${data.written.length} key(s) — restarting…`);
      app.restarting = true;
      app.restartTarget = app.stats.workspace;
      app.pollRestart();
    } else {
      app.toast(`Saved ${data.written.length} key(s)`);
      app.loadMcps();
    }
    for (const key of Object.keys(app.mcps.drafts)) {
      if (key.startsWith(name + ":")) app.mcps.drafts[key] = "";
    }
  } catch (error) {
    app.toast("Save failed: " + error.message, "error");
  } finally {
    app.mcps.saving[name] = false;
  }
};

window.theseusTestMcp = async function theseusTestMcp(app, name) {
  app.mcps.testing[name] = true;
  app.mcps.testResult[name] = null;
  try {
    const data = await app.api(`/api/ui/mcps/${name}/test`, {
      method: "POST",
    });
    app.mcps.testResult[name] = data;
    if (data.ok) {
      app.toast(`${name}: handshake ok (${data.tool_count} tools)`);
    } else {
      app.toast(`${name}: ${data.error || "failed"}`, "error");
    }
  } catch (error) {
    app.mcps.testResult[name] = { ok: false, error: error.message };
    app.toast("Test failed: " + error.message, "error");
  } finally {
    app.mcps.testing[name] = false;
  }
};

window.theseusClearLlmCache = async function theseusClearLlmCache(app) {
  if (
    !confirm(
      "Clear the LLM response cache?\n\nAll subsequent queries will re-call the model. Existing extractions and embeddings are unaffected.",
    )
  ) {
    return;
  }
  app.serverOps.clearingCache = true;
  try {
    await app.api("/documents/clear_cache", { method: "POST" });
    app.toast("LLM response cache cleared");
  } catch (error) {
    app.toast("Clear failed: " + error.message, "error");
  } finally {
    app.serverOps.clearingCache = false;
  }
};

window.theseusClearAllDocuments = async function theseusClearAllDocuments(app) {
  const workspace = app.stats.workspace || "this workspace";
  if (
    !confirm(
      `Wipe ALL documents in "${workspace}"?\n\nThis deletes the knowledge graph, vector indexes, and KV stores for every document. Source files in inputs/ are kept. The workspace remains active.\n\nThis cannot be undone.`,
    )
  ) {
    return;
  }
  app.serverOps.clearingDocs = true;
  try {
    await app.api("/documents", { method: "DELETE" });
    app.toast(`Cleared all documents in ${workspace}`);
    await app.loadDocuments();
    await app.loadDocStats();
    await app.refreshAll();
  } catch (error) {
    app.toast("Clear documents failed: " + error.message, "error");
  } finally {
    app.serverOps.clearingDocs = false;
  }
};

window.theseusSettingsExpandAll = function theseusSettingsExpandAll() {
  document.querySelectorAll("details.acc").forEach((detail) => {
    detail.open = true;
  });
};

window.theseusSettingsCollapseAll = function theseusSettingsCollapseAll() {
  document.querySelectorAll("details.acc").forEach((detail) => {
    detail.open = false;
  });
};