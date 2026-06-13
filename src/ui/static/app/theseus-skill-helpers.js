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

window.theseusSkillsFilteredDomain = function theseusSkillsFilteredDomain(app) {
  return window
    .theseusSkillsFiltered(app)
    .filter((s) => !window.theseusIsMetaSkill(s));
};

window.theseusSkillsFilteredMeta = function theseusSkillsFilteredMeta(app) {
  return window
    .theseusSkillsFiltered(app)
    .filter((s) => window.theseusIsMetaSkill(s));
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
    if (typeof app.skills.resumeDrafts?.[runId] !== "string") {
      app.skills.resumeDrafts[runId] = "";
    }
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
  if (!confirm(`Permanently delete run ${runId}? This cannot be undone.`)) {
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
    if (app.skills.run?.run_id === runId) {
      app.skills.run = null;
      app.skills.transcriptOpen = false;
      app.skills.transcriptExpanded = {};
    }
    app.toast("Run deleted: " + runId, "ok");
    await Promise.all([app.loadSkillRuns(name), app.loadSkillRunTrash(name)]);
  } catch (error) {
    app.toast("Run delete failed: " + (error?.message || error), "error");
  }
};

window.theseusEmptySkillRunTrash = async function theseusEmptySkillRunTrash(
  app,
  name,
) {
  if (!name) return;
  if (
    !confirm(
      "Permanently delete every trashed run for this skill? This cannot be undone.",
    )
  ) {
    return;
  }
  try {
    const result = await app.api(
      "/api/ui/skills/" + encodeURIComponent(name) + "/runs/trash",
      { method: "DELETE" },
    );
    app.toast(
      `Trash emptied: ${result.purged || 0} purged` +
        (result.skipped ? `, ${result.skipped} skipped` : ""),
      "ok",
    );
    await app.loadSkillRunTrash(name);
  } catch (error) {
    app.toast("Empty trash failed: " + (error?.message || error), "error");
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

window.theseusSkillContextArtifactKey =
  function theseusSkillContextArtifactKey(ref) {
    return (
      (ref?.skill || "") +
      "/" +
      (ref?.run_id || "") +
      "/" +
      (ref?.filename || "")
    );
  };

window.theseusSkillContextArtifactLabel =
  function theseusSkillContextArtifactLabel(ref) {
    if (!ref) return "";
    return ref.display_name || ref.filename || "artifact";
  };

window.theseusLoadSkillInvokeArtifacts =
  async function theseusLoadSkillInvokeArtifacts(app) {
    if (app.studio?.loaded || app.skills.invokeArtifactsLoading) return;
    app.skills.invokeArtifactsLoading = true;
    try {
      if (typeof app.loadStudio === "function") {
        await app.loadStudio();
      } else {
        const response = await app.api("/api/ui/studio?limit=500");
        app.studio.deliverables = response.deliverables || [];
        app.studio.loaded = true;
      }
    } catch (error) {
      app.toast(
        "Failed to load Studio deliverables: " + (error?.message || error),
        "warn",
      );
    } finally {
      app.skills.invokeArtifactsLoading = false;
      window.theseusAfterRender(app);
    }
  };

window.theseusSkillContextArtifactSelected =
  function theseusSkillContextArtifactSelected(app, deliverable) {
    const key = window.theseusStudioKey(deliverable);
    return (app.skills.invokeContextArtifacts || []).some(
      (ref) => window.theseusSkillContextArtifactKey(ref) === key,
    );
  };

window.theseusToggleSkillContextArtifact =
  function theseusToggleSkillContextArtifact(app, deliverable) {
    if (!deliverable?.skill || !deliverable?.run_id || !deliverable?.filename) {
      return;
    }
    const key = window.theseusStudioKey(deliverable);
    const current = app.skills.invokeContextArtifacts || [];
    const index = current.findIndex(
      (ref) => window.theseusSkillContextArtifactKey(ref) === key,
    );
    if (index >= 0) {
      current.splice(index, 1);
      app.skills.invokeContextArtifacts = current;
      window.theseusAfterRender(app);
      return;
    }
    if (current.length >= 5) {
      app.toast("At most 5 context artifacts per invoke.", "warn");
      return;
    }
    app.skills.invokeContextArtifacts = current.concat([
      {
        skill: deliverable.skill,
        run_id: deliverable.run_id,
        filename: deliverable.filename,
        display_name: deliverable.display_name || deliverable.filename,
        run_label: deliverable.run_label || "",
      },
    ]);
    window.theseusAfterRender(app);
  };

window.theseusRemoveSkillContextArtifact =
  function theseusRemoveSkillContextArtifact(app, ref) {
    const key = window.theseusSkillContextArtifactKey(ref);
    app.skills.invokeContextArtifacts = (
      app.skills.invokeContextArtifacts || []
    ).filter((item) => window.theseusSkillContextArtifactKey(item) !== key);
    window.theseusAfterRender(app);
  };

window.theseusOpenSkill = async function theseusOpenSkill(app, name) {
  app.skills.invokeResult = "";
  app.skills.invokeMeta = null;
  app.skills.invokePrompt = "";
  app.skills.invokeContextArtifacts = [];
  app.skills.invokeArtifactsOpen = false;
  app.skills.runs = [];
  app.skills.runTrash = [];
  app.skills.runTrashOpen = false;
  try {
    await window.theseusEnsurePromptLibraryLoaded(app);
    const detail = await app.api("/api/ui/skills/" + encodeURIComponent(name));
    app.skills.current = detail;
    app.skills.detailOpen = true;
    const libraryPrompt = window.theseusResolveSkillDefaultPrompt(app, name);
    if (libraryPrompt) {
      app.skills.invokePrompt = libraryPrompt;
    }
    window.theseusAfterRender(app);
    app.loadSkillRuns(name);
    app.loadSkillRunTrash(name);
    window.theseusLoadSkillInvokeArtifacts(app);
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
          context_artifacts: (app.skills.invokeContextArtifacts || []).map(
            (ref) => ({
              skill: ref.skill,
              run_id: ref.run_id,
              filename: ref.filename,
            }),
          ),
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
    if (response.run) {
      app.skills.run = response.run;
      app.skills.transcriptExpanded = {};
      app.skills.transcriptOpen = (response.run.transcript || []).length > 0;
      if (typeof app.skills.resumeDrafts?.[response.run.run_id] !== "string") {
        app.skills.resumeDrafts[response.run.run_id] = "";
      }
    }
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

window.theseusSkillRunInputRequest = function theseusSkillRunInputRequest(run) {
  const request = run?.input_request;
  return request && request.needed ? request : null;
};

window.theseusSkillRunCanResume = function theseusSkillRunCanResume(run) {
  if (!run) return false;
  if (typeof run.can_resume === "boolean") return run.can_resume;
  return !!window.theseusSkillRunInputRequest(run);
};

window.theseusSkillRunResumePlaceholder =
  function theseusSkillRunResumePlaceholder(run) {
    const request = window.theseusSkillRunInputRequest(run);
    const missing = (request?.missing_inputs || []).join("\n- ");
    if (!missing) {
      return "Reply with missing info, decision, or direction. Then resume.";
    }
    return "Provide missing input to continue this skill:\n- " + missing;
  };

window.theseusMountSkillRunInputPanel = function theseusMountSkillRunInputPanel(
  app,
  host,
) {
  if (!host || host.dataset.skillRunInputMounted === "true") return;
  const template = document.getElementById(
    "skill-run-input-request-panel-template",
  );
  if (!template?.content) return;
  host.replaceChildren(template.content.cloneNode(true));
  host.dataset.skillRunInputMounted = "true";
  if (window.Alpine?.initTree) {
    window.Alpine.initTree(host);
  }
  if (window.lucide?.createIcons) {
    window.lucide.createIcons();
  }
  window.theseusAfterRender(app);
};

window.theseusResumeSkillRun = async function theseusResumeSkillRun(
  app,
  name,
  runId,
) {
  if (!name || !runId || app.skills.resumingRun === runId) return;
  const run = app.skills.run?.run_id === runId ? app.skills.run : null;
  const draft = (app.skills.resumeDrafts?.[runId] || "").trim();
  if (window.theseusSkillRunInputRequest(run) && !draft) {
    app.toast("Reply in Missing Input composer, then click Resume.", "info");
    return;
  }
  app.skills.resumingRun = runId;
  try {
    const response = await app.api(
      "/api/ui/skills/" +
        encodeURIComponent(name) +
        "/runs/" +
        encodeURIComponent(runId) +
        "/resume",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_addendum: draft }),
      },
    );
    app.skills.invokeResult = response.response || "(empty response)";
    app.skills.invokeMeta = {
      entities_used: response.entities_used || [],
      elapsed_ms: response.elapsed_ms || 0,
      finish_reason: response.finish_reason || "",
      warnings: response.warnings || [],
      run_id: response.run_id,
      run_dir: response.run_dir,
    };
    app.skills.run = response.run || null;
    app.skills.resumeDrafts[runId] = "";
    if (response.run?.run_id) {
      app.skills.resumeDrafts[response.run.run_id] = "";
    }
    app.skills.transcriptExpanded = {};
    app.skills.transcriptOpen = (response.run?.transcript || []).length > 0;
    if ((response.warnings || []).length) {
      app.toast(response.warnings.join("; "), "warn");
    } else {
      app.toast("Skill resumed", "ok");
    }
    await Promise.all([
      app.loadSkillRuns(name),
      app.loadSkillRunTrash(name),
      app.studio && app.studio.loaded ? app.loadStudio() : Promise.resolve(),
    ]);
  } catch (error) {
    app.toast("Skill resume failed: " + (error?.message || error), "error");
  } finally {
    app.skills.resumingRun = "";
    window.theseusAfterRender(app);
  }
};
