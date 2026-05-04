window.theseusIsMetaSkill = function theseusIsMetaSkill(skill) {
  return (skill.personas_primary || "none") === "none" || skill.capability === "meta";
};

window.theseusSkillMatchesFilters = function theseusSkillMatchesFilters(app, skill) {
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

  if (activeCapabilities.length && !activeCapabilities.includes(skill.capability)) {
    return false;
  }

  const query = (app.skills.searchQuery || "").trim().toLowerCase();
  if (query) {
    const haystack = ((skill.name || "") + " " + (skill.description || "")).toLowerCase();
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

window.theseusSkillsCountForPersona = function theseusSkillsCountForPersona(app, id) {
  const cfg = app.skillPersonaFilterConfig().find((persona) => persona.id === id);
  if (!cfg) return 0;
  const targets = new Set(cfg.personas);
  return (app.skills.items || []).filter((skill) => {
    const primary = skill.personas_primary || "none";
    const secondary = skill.personas_secondary || [];
    return targets.has(primary) || secondary.some((persona) => targets.has(persona));
  }).length;
};

window.theseusSkillsCountForPhase = function theseusSkillsCountForPhase(app, id) {
  return (app.skills.items || []).filter((skill) =>
    (skill.shipley_phases || []).includes(id),
  ).length;
};

window.theseusSkillsCountForCapability = function theseusSkillsCountForCapability(app, id) {
  return (app.skills.items || []).filter((skill) => skill.capability === id).length;
};

window.theseusToggleSkillPersona = function theseusToggleSkillPersona(app, id) {
  const arr = app.skills.activePersonas;
  const idx = arr.indexOf(id);
  if (idx >= 0) arr.splice(idx, 1);
  else arr.push(id);
  app.$nextTick(() => lucide.createIcons());
};

window.theseusToggleSkillPhase = function theseusToggleSkillPhase(app, id) {
  const arr = app.skills.activePhases;
  const idx = arr.indexOf(id);
  if (idx >= 0) arr.splice(idx, 1);
  else arr.push(id);
  app.$nextTick(() => lucide.createIcons());
};

window.theseusToggleSkillCapability = function theseusToggleSkillCapability(app, id) {
  const arr = app.skills.activeCapabilities;
  const idx = arr.indexOf(id);
  if (idx >= 0) arr.splice(idx, 1);
  else arr.push(id);
  app.$nextTick(() => lucide.createIcons());
};

window.theseusClearSkillFilters = function theseusClearSkillFilters(app) {
  app.skills.activePersonas = [];
  app.skills.activePhases = [];
  app.skills.activeCapabilities = [];
  app.skills.searchQuery = "";
  app.$nextTick(() => lucide.createIcons());
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
    app.$nextTick(() => lucide.createIcons());
  }
};

window.theseusLoadSkillRun = async function theseusLoadSkillRun(app, name, runId) {
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
      warnings: [],
      run_id: response.run_id,
      run_dir: response.run_dir,
    };
    app.skills.run = response;
    app.skills.transcriptExpanded = {};
    app.skills.transcriptOpen = (response.transcript || []).length > 0;
    app.$nextTick(() => lucide.createIcons());
  } catch (error) {
    app.toast("Failed to load run: " + (error?.message || error), "error");
  }
};

window.theseusDeleteSkillRun = async function theseusDeleteSkillRun(app, name, runId) {
  if (!name || !runId) return;
  if (!confirm(`Delete run ${runId}? This removes the saved files on disk.`)) {
    return;
  }
  try {
    await app.api(
      "/api/ui/skills/" +
        encodeURIComponent(name) +
        "/runs/" +
        encodeURIComponent(runId),
      { method: "DELETE" },
    );
    app.toast("Run deleted", "ok");
    app.loadSkillRuns(name);
  } catch (error) {
    app.toast("Delete failed: " + (error?.message || error), "error");
  }
};

window.theseusInstallSkill = async function theseusInstallSkill(app) {
  const url = (app.skills.installUrl || "").trim();
  if (!url) return;
  app.skills.installing = true;
  try {
    await app.api("/api/ui/skills/install", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    app.skills.installModal = false;
    app.skills.installUrl = "";
    app.toast("Skill installed", "ok");
    await app.loadSkills(true);
  } catch (error) {
    app.toast("Install failed: " + (error?.message || error), "error");
  } finally {
    app.skills.installing = false;
  }
};

window.theseusUninstallSkill = async function theseusUninstallSkill(app) {
  if (!app.skills.current) return;
  const name = app.skills.current.name;
  if (!confirm(`Uninstall skill "${name}"?`)) return;
  try {
    await app.api("/api/ui/skills/" + encodeURIComponent(name), {
      method: "DELETE",
    });
    app.skills.detailOpen = false;
    app.skills.current = null;
    app.toast("Skill removed", "ok");
    await app.loadSkills(true);
  } catch (error) {
    app.toast("Uninstall failed: " + (error?.message || error), "error");
  }
};

window.theseusLoadSkills = async function theseusLoadSkills(app, force = false) {
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
    app.$nextTick(() => lucide.createIcons());
  }
};

window.theseusOpenSkill = async function theseusOpenSkill(app, name) {
  app.skills.invokeResult = "";
  app.skills.invokeMeta = null;
  app.skills.invokePrompt = "";
  app.skills.runs = [];
  try {
    const detail = await app.api("/api/ui/skills/" + encodeURIComponent(name));
    app.skills.current = detail;
    app.skills.detailOpen = true;
    app.$nextTick(() => lucide.createIcons());
    app.loadSkillRuns(name);
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
      "/api/ui/skills/" + encodeURIComponent(app.skills.current.name) + "/invoke",
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
      warnings: response.warnings,
      run_id: response.run_id,
      run_dir: response.run_dir,
    };
    if ((response.warnings || []).length) {
      app.toast(response.warnings.join("; "), "warn");
    }
    if (response.run_id) {
      app.toast("Saved run " + response.run_id, "ok");
      app.loadSkillRuns(app.skills.current.name);
    }
  } catch (error) {
    app.toast("Skill invocation failed: " + (error?.message || error), "error");
  } finally {
    app.skills.invoking = false;
    app.$nextTick(() => lucide.createIcons());
  }
};