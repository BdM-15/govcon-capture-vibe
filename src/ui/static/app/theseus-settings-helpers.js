const theseusLoadSettingsSection = async function theseusLoadSettingsSection(
  app,
  options,
) {
  const { stateKey, endpoint, loadErrorLabel } = options;
  try {
    const data = await app.api(endpoint);
    app[stateKey].values = { ...data.settings };
    app[stateKey].defaults = { ...data.defaults };
    app[stateKey].loaded = true;
  } catch (error) {
    app.toast(`${loadErrorLabel}: ${error.message}`, "error");
  }
};

const theseusSaveSettingsSection = async function theseusSaveSettingsSection(
  app,
  options,
) {
  const { stateKey, endpoint, successMessage } = options;
  app[stateKey].saving = true;
  try {
    const data = await app.api(endpoint, {
      method: "PUT",
      body: JSON.stringify(app[stateKey].values),
    });
    app[stateKey].values = { ...data.settings };
    app.toast(successMessage);
  } catch (error) {
    app.toast("Save failed: " + error.message, "error");
  } finally {
    app[stateKey].saving = false;
  }
};

const theseusResetSettingsSection = async function theseusResetSettingsSection(
  app,
  options,
) {
  const { stateKey, endpoint, confirmMessage, successMessage } = options;
  if (!confirm(confirmMessage)) return;
  try {
    const data = await app.api(endpoint, {
      method: "POST",
    });
    app[stateKey].values = { ...data.settings };
    app.toast(successMessage);
  } catch (error) {
    app.toast("Reset failed: " + error.message, "error");
  }
};

window.theseusOpenQueryTuningGuide = function theseusOpenQueryTuningGuide(app) {
  app.queryTuningGuideModal.open = true;
  window.theseusAfterRender(app);
};

window.theseusCloseQueryTuningGuide = function theseusCloseQueryTuningGuide(
  app,
) {
  app.queryTuningGuideModal.open = false;
};

window.theseusLoadQuerySettings = async function theseusLoadQuerySettings(app) {
  return theseusLoadSettingsSection(app, {
    stateKey: "querySettings",
    endpoint: "/api/ui/settings/query",
    loadErrorLabel: "Failed loading query settings",
  });
};

window.theseusSaveQuerySettings = async function theseusSaveQuerySettings(app) {
  return theseusSaveSettingsSection(app, {
    stateKey: "querySettings",
    endpoint: "/api/ui/settings/query",
    successMessage: "Query settings saved",
  });
};

window.theseusResetQuerySettings = async function theseusResetQuerySettings(
  app,
) {
  return theseusResetSettingsSection(app, {
    stateKey: "querySettings",
    endpoint: "/api/ui/settings/query/reset",
    confirmMessage: "Restore default query parameters for this workspace?",
    successMessage: "Query settings reset to defaults",
  });
};

window.theseusLoadSkillSettings = async function theseusLoadSkillSettings(app) {
  return theseusLoadSettingsSection(app, {
    stateKey: "skillSettings",
    endpoint: "/api/ui/settings/skills",
    loadErrorLabel: "Failed loading skill settings",
  });
};

window.theseusLoadSkillRuntimeSettings =
  async function theseusLoadSkillRuntimeSettings(app) {
    return theseusLoadSettingsSection(app, {
      stateKey: "skillRuntimeSettings",
      endpoint: "/api/ui/settings/skills/runtime",
      loadErrorLabel: "Failed loading skill runtime settings",
    });
  };

window.theseusSaveSkillSettings = async function theseusSaveSkillSettings(app) {
  return theseusSaveSettingsSection(app, {
    stateKey: "skillSettings",
    endpoint: "/api/ui/settings/skills",
    successMessage: "Skill settings saved",
  });
};

window.theseusSaveSkillRuntimeSettings =
  async function theseusSaveSkillRuntimeSettings(app) {
    return theseusSaveSettingsSection(app, {
      stateKey: "skillRuntimeSettings",
      endpoint: "/api/ui/settings/skills/runtime",
      successMessage: "Global skill runtime caps saved",
    });
  };

window.theseusResetSkillSettings = async function theseusResetSkillSettings(
  app,
) {
  return theseusResetSettingsSection(app, {
    stateKey: "skillSettings",
    endpoint: "/api/ui/settings/skills/reset",
    confirmMessage:
      "Restore default skill retrieval settings for this workspace?",
    successMessage: "Skill settings reset to defaults",
  });
};

window.theseusResetSkillRuntimeSettings =
  async function theseusResetSkillRuntimeSettings(app) {
    return theseusResetSettingsSection(app, {
      stateKey: "skillRuntimeSettings",
      endpoint: "/api/ui/settings/skills/runtime/reset",
      confirmMessage: "Restore default global skill runtime caps?",
      successMessage: "Global skill runtime caps reset to defaults",
    });
  };

window.theseusLoadWebResearchSettings =
  async function theseusLoadWebResearchSettings(app) {
    try {
      const data = await app.api("/api/ui/settings/web-research");
      app.webResearchSettings.values = { ...data.settings };
      app.webResearchSettings.defaults = { ...data.defaults };
      app.webResearchSettings.providers = data.providers || null;
      app.webResearchSettings.loaded = true;
    } catch (error) {
      app.toast(`Failed loading web research settings: ${error.message}`, "error");
    }
  };

window.theseusSaveWebResearchSettings =
  async function theseusSaveWebResearchSettings(app) {
    app.webResearchSettings.saving = true;
    try {
      const data = await app.api("/api/ui/settings/web-research", {
        method: "PUT",
        body: JSON.stringify(app.webResearchSettings.values),
      });
      app.webResearchSettings.values = { ...data.settings };
      app.webResearchSettings.providers = data.providers || null;
      app.toast("Web research settings saved");
    } catch (error) {
      app.toast("Save failed: " + error.message, "error");
    } finally {
      app.webResearchSettings.saving = false;
    }
  };

window.theseusResetWebResearchSettings =
  async function theseusResetWebResearchSettings(app) {
    if (
      !confirm(
        "Restore default web research settings for this workspace?",
      )
    ) {
      return;
    }
    try {
      const data = await app.api("/api/ui/settings/web-research/reset", {
        method: "POST",
      });
      app.webResearchSettings.values = { ...data.settings };
      app.webResearchSettings.providers = data.providers || null;
      app.toast("Web research settings reset to defaults");
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
    window.theseusAfterRender(app);
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
