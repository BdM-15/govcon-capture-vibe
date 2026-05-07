window.theseusIsMetaSkill = function theseusIsMetaSkill(skill) {
  return (
    (skill.personas_primary || "none") === "none" || skill.capability === "meta"
  );
};

window.theseusSkillMatchesFilters = function theseusSkillMatchesFilters(
  app,
  skill,
) {
  const activePersonas = app.skills.activePersonas;
  const activePhases = app.skills.activePhases;
  const activeCapabilities = app.skills.activeCapabilities;

  if (activePersonas.length) {
    const cfg = app.skillPersonaFilterConfig();
    const expanded = new Set();
    for (const id of activePersonas) {
      const entry = cfg.find((persona) => persona.id === id);
      if (entry) entry.personas.forEach((persona) => expanded.add(persona));
    }
    const primary = skill.personas_primary || "none";
    const secondary = skill.personas_secondary || [];
    if (!expanded.has(primary) && !secondary.some((id) => expanded.has(id))) {
      return false;
    }
  }

  if (activePhases.length) {
    const phases = skill.shipley_phases || [];
    if (!phases.some((phase) => activePhases.includes(phase))) return false;
  }

  if (
    activeCapabilities.length &&
    !activeCapabilities.includes(skill.capability)
  ) {
    return false;
  }

  const query = (app.skills.searchQuery || "").trim().toLowerCase();
  if (query) {
    const haystack = (
      (skill.name || "") +
      " " +
      (skill.description || "")
    ).toLowerCase();
    const tokens = query.split(/\s+/);
    if (!tokens.every((token) => haystack.includes(token))) return false;
  }

  return true;
};

window.theseusSkillsFiltered = function theseusSkillsFiltered(app) {
  const items = (app.skills.items || []).filter((skill) =>
    window.theseusSkillMatchesFilters(app, skill),
  );
  return items.slice().sort((left, right) => {
    const leftMeta = window.theseusIsMetaSkill(left) ? 0 : 1;
    const rightMeta = window.theseusIsMetaSkill(right) ? 0 : 1;
    if (leftMeta !== rightMeta) return leftMeta - rightMeta;
    return left.name.localeCompare(right.name);
  });
};

window.theseusSkillsCountForPersona = function theseusSkillsCountForPersona(
  app,
  id,
) {
  const cfg = app
    .skillPersonaFilterConfig()
    .find((persona) => persona.id === id);
  if (!cfg) return 0;
  const targets = new Set(cfg.personas);
  return (app.skills.items || []).filter((skill) => {
    const primary = skill.personas_primary || "none";
    const secondary = skill.personas_secondary || [];
    return (
      targets.has(primary) || secondary.some((persona) => targets.has(persona))
    );
  }).length;
};

window.theseusSkillsCountForPhase = function theseusSkillsCountForPhase(
  app,
  id,
) {
  return (app.skills.items || []).filter((skill) =>
    (skill.shipley_phases || []).includes(id),
  ).length;
};

window.theseusSkillsCountForCapability =
  function theseusSkillsCountForCapability(app, id) {
    return (app.skills.items || []).filter((skill) => skill.capability === id)
      .length;
  };

const theseusToggleArrayValue = function theseusToggleArrayValue(values, id) {
  const index = values.indexOf(id);
  if (index >= 0) values.splice(index, 1);
  else values.push(id);
};

window.theseusToggleSkillPersona = function theseusToggleSkillPersona(app, id) {
  theseusToggleArrayValue(app.skills.activePersonas, id);
  window.theseusAfterRender(app);
};

window.theseusToggleSkillPhase = function theseusToggleSkillPhase(app, id) {
  theseusToggleArrayValue(app.skills.activePhases, id);
  window.theseusAfterRender(app);
};

window.theseusToggleSkillCapability = function theseusToggleSkillCapability(
  app,
  id,
) {
  theseusToggleArrayValue(app.skills.activeCapabilities, id);
  window.theseusAfterRender(app);
};

window.theseusClearSkillFilters = function theseusClearSkillFilters(app) {
  app.skills.activePersonas = [];
  app.skills.activePhases = [];
  app.skills.activeCapabilities = [];
  app.skills.searchQuery = "";
  window.theseusAfterRender(app);
};

window.theseusPersonaLabel = function theseusPersonaLabel(app, id) {
  const cfg = app.skillPersonaConfig().find((persona) => persona.id === id);
  return cfg ? cfg.label.replace(/s$/, "") : id;
};

window.theseusLoadSkillRuns = async function theseusLoadSkillRuns(app, name) {
  if (!name) return;
  app.skills.runsLoading = true;
  try {
    const response = await app.api(
      "/api/ui/skills/" + encodeURIComponent(name) + "/runs",
    );
    app.skills.runs = response.runs || [];
  } catch (error) {
    app.skills.runs = [];
  } finally {
    app.skills.runsLoading = false;
    window.theseusAfterRender(app);
  }
};

window.theseusLoadSkillRunTrash = async function theseusLoadSkillRunTrash(
  app,
  name,
) {
  if (!name) return;
  app.skills.runTrashLoading = true;
  try {
    const response = await app.api(
      "/api/ui/skills/" + encodeURIComponent(name) + "/runs/trash",
    );
    app.skills.runTrash = response.runs || [];
  } catch (error) {
    app.skills.runTrash = [];
  } finally {
    app.skills.runTrashLoading = false;
    window.theseusAfterRender(app);
  }
};

window.theseusToggleSkillRunTrash = function theseusToggleSkillRunTrash(app) {
  app.skills.runTrashOpen = !app.skills.runTrashOpen;
  if (app.skills.runTrashOpen && app.skills.current?.name) {
    app.loadSkillRunTrash(app.skills.current.name);
  }
  window.theseusAfterRender(app);
};

window.theseusLoadSkillRun = async function theseusLoadSkillRun(
  app,
  name,
  runId,
) {
  if (!name || !runId) return;
  try {
    const response = await app.api(
      "/api/ui/skills/" +
        encodeURIComponent(name) +
        "/runs/" +
        encodeURIComponent(runId),
    );
    app.skills.invokeResult = response.response || "(empty)";
    app.skills.invokePrompt = response.metadata?.prompt_preview || "";
    app.skills.invokeMeta = {
      entities_used: response.metadata?.entities_used || [],
      elapsed_ms: response.metadata?.elapsed_ms || 0,
      finish_reason: response.metadata?.finish_reason || "",
      warnings: [],
      run_id: response.run_id,
      run_dir: response.run_dir,
    };
    app.skills.run = response;
    app.skills.transcriptExpanded = {};
    app.skills.transcriptOpen = (response.transcript || []).length > 0;
    window.theseusAfterRender(app);
  } catch (error) {
    app.toast("Failed to load run: " + (error?.message || error), "error");
  }
};

window.theseusDeleteSkillRun = async function theseusDeleteSkillRun(
  app,
  name,
  runId,
) {
  if (!name || !runId) return;
  if (!confirm(`Move run ${runId} to trash? You can restore it later.`)) {
    return;
  }
  try {
    const result = await app.api(
      "/api/ui/skills/" +
        encodeURIComponent(name) +
        "/runs/" +
        encodeURIComponent(runId),
      { method: "DELETE" },
    );
    if (app.skills.run?.run_id === runId) {
      app.skills.run = null;
      app.skills.transcriptOpen = false;
      app.skills.transcriptExpanded = {};
    }
    app.toast(
      "Run moved to trash: " + (result.trashed?.run_id || runId),
      "ok",
    );
    await Promise.all([app.loadSkillRuns(name), app.loadSkillRunTrash(name)]);
  } catch (error) {
    app.toast("Run trash move failed: " + (error?.message || error), "error");
  }
};

window.theseusRestoreSkillRun = async function theseusRestoreSkillRun(
  app,
  name,
  trashId,
) {
  if (!name || !trashId || app.skills.restoringRunTrash === trashId) return;
  app.skills.restoringRunTrash = trashId;
  try {
    const result = await app.api(
      "/api/ui/skills/" + encodeURIComponent(name) + "/runs/trash/restore",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ runs: [{ trash_id: trashId }] }),
      },
    );
    if (!result.restored_count) {
      throw new Error("No runs restored");
    }
    app.toast("Run restored", "ok");
    await Promise.all([app.loadSkillRuns(name), app.loadSkillRunTrash(name)]);
  } catch (error) {
    app.toast("Run restore failed: " + (error?.message || error), "error");
  } finally {
    app.skills.restoringRunTrash = "";
  }
};

const theseusSkillErrorMessage = function theseusSkillErrorMessage(error) {
  return error?.message || error;
};

const theseusMutateSkillCatalog = async function theseusMutateSkillCatalog(
  app,
  options,
) {
  const {
    confirmMessage,
    busyKey,
    request,
    onSuccess,
    successMessage,
    errorLabel,
  } = options;

  if (confirmMessage && !confirm(confirmMessage)) return;
  if (busyKey) app.skills[busyKey] = true;
  try {
    await request();
    if (onSuccess) onSuccess();
    app.toast(successMessage, "ok");
    await app.loadSkills(true);
  } catch (error) {
    app.toast(`${errorLabel}: ${theseusSkillErrorMessage(error)}`, "error");
  } finally {
    if (busyKey) app.skills[busyKey] = false;
  }
};

window.theseusInstallSkill = async function theseusInstallSkill(app) {
  const url = (app.skills.installUrl || "").trim();
  if (!url) return;
  return theseusMutateSkillCatalog(app, {
    busyKey: "installing",
    request: () =>
      app.api("/api/ui/skills/install", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      }),
    onSuccess: () => {
      app.skills.installModal = false;
      app.skills.installUrl = "";
    },
    successMessage: "Skill installed",
    errorLabel: "Install failed",
  });
};

window.theseusUninstallSkill = async function theseusUninstallSkill(app) {
  if (!app.skills.current) return;
  const name = app.skills.current.name;
  return theseusMutateSkillCatalog(app, {
    confirmMessage: `Uninstall skill "${name}"?`,
    request: () =>
      app.api("/api/ui/skills/" + encodeURIComponent(name), {
        method: "DELETE",
      }),
    onSuccess: () => {
      app.skills.detailOpen = false;
      app.skills.current = null;
    },
    successMessage: "Skill removed",
    errorLabel: "Uninstall failed",
  });
};

window.theseusLoadSkills = async function theseusLoadSkills(
  app,
  force = false,
) {
  app.skills.loading = true;
  app.skills.error = null;
  try {
    const url = force ? "/api/ui/skills/refresh" : "/api/ui/skills";
    const response = await app.api(url, force ? { method: "POST" } : {});
    app.skills.items = response.skills || [];
    app.skills.loaded = true;
  } catch (error) {
    app.skills.error = "Failed to load skills: " + (error?.message || error);
    app.skills.items = [];
  } finally {
    app.skills.loading = false;
    window.theseusAfterRender(app);
  }
};

window.theseusOpenSkill = async function theseusOpenSkill(app, name) {
  app.skills.invokeResult = "";
  app.skills.invokeMeta = null;
  app.skills.invokePrompt = "";
  app.skills.runs = [];
  app.skills.runTrash = [];
  app.skills.runTrashOpen = false;
  try {
    const detail = await app.api("/api/ui/skills/" + encodeURIComponent(name));
    app.skills.current = detail;
    app.skills.detailOpen = true;
    window.theseusAfterRender(app);
    app.loadSkillRuns(name);
    app.loadSkillRunTrash(name);
  } catch (error) {
    app.toast("Failed to load skill: " + (error?.message || error), "error");
  }
};

window.theseusInvokeSkill = async function theseusInvokeSkill(app) {
  if (!app.skills.current) return;
  app.skills.invoking = true;
  app.skills.invokeResult = "";
  app.skills.invokeMeta = null;
  app.skills.run = null;
  app.skills.transcriptOpen = false;
  app.skills.transcriptExpanded = {};
  try {
    const response = await app.api(
      "/api/ui/skills/" +
        encodeURIComponent(app.skills.current.name) +
        "/invoke",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: app.skills.invokePrompt || "",
        }),
      },
    );
    app.skills.invokeResult = response.response || "(empty response)";
    app.skills.invokeMeta = {
      entities_used: response.entities_used,
      elapsed_ms: response.elapsed_ms,
      finish_reason: response.finish_reason || "",
      warnings: response.warnings,
      run_id: response.run_id,
      run_dir: response.run_dir,
    };
    if ((response.warnings || []).length) {
      app.toast(response.warnings.join("; "), "warn");
    }
    if (response.run_id) {
      app.toast("Saved run " + response.run_id, "ok");
      const refreshes = [
        app.loadSkillRuns(app.skills.current.name),
        app.loadSkillRunTrash(app.skills.current.name),
      ];
      // Refresh Studio so freshly-emitted artifacts surface without manual click.
      // Only refresh if Studio has been opened at least once this session — avoids
      // pulling the index for users who never visit Studio.
      if (app.studio && app.studio.loaded) {
        refreshes.push(app.loadStudio());
      }
      Promise.all(refreshes);
    }
  } catch (error) {
    app.toast("Skill invocation failed: " + (error?.message || error), "error");
  } finally {
    app.skills.invoking = false;
    window.theseusAfterRender(app);
  }
};
