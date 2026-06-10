window.theseusPromptPhaseMeta = function theseusPromptPhaseMeta() {
  return {
    3: {
      label: "Capture & RFP Discovery",
      pillClass: "bg-neon-cyan/10 text-neon-cyan border-neon-cyan/30",
      accentClass: "accent-cyan",
    },
    4: {
      label: "Proposal Planning",
      pillClass: "bg-neon-magenta/10 text-neon-magenta border-neon-magenta/30",
      accentClass: "accent-magenta",
    },
    5: {
      label: "Proposal Development",
      pillClass: "bg-neon-lime/10 text-neon-lime border-neon-lime/30",
      accentClass: "accent-lime",
    },
    6: {
      label: "Color Reviews & Submittal",
      pillClass: "bg-neon-amber/10 text-neon-amber border-neon-amber/30",
      accentClass: "accent-amber",
    },
  };
};

const theseusSearchPrompts = function theseusSearchPrompts(prompts, query) {
  const normalizedQuery = (query || "").trim().toLowerCase();
  if (!normalizedQuery) return prompts;
  return prompts.filter(
    (prompt) =>
      (prompt.title || "").toLowerCase().includes(normalizedQuery) ||
      (prompt.category || "").toLowerCase().includes(normalizedQuery) ||
      (prompt.prompt || "").toLowerCase().includes(normalizedQuery),
  );
};

const theseusPromptPhaseInfo = function theseusPromptPhaseInfo(id) {
  const phaseId = String(id);
  const meta = window.theseusPromptPhaseMeta()[phaseId] || {};
  return {
    id: phaseId,
    label: meta.label || `Phase ${phaseId}`,
    pillClass: meta.pillClass || "bg-ink-800 text-slate-400 border-edge",
    accentClass: meta.accentClass || "accent-cyan",
  };
};

const theseusLoadPromptIntoComposer = function theseusLoadPromptIntoComposer(
  app,
  prompt,
  options = {},
) {
  const { closePicker = false, activateChat = false } = options;
  window.theseusLoadComposerText(app, prompt.prompt, {
    closePromptPicker: closePicker,
    activateChat,
    toastMessage: "Prompt loaded into composer",
  });
};

window.theseusPhaseLabel = function theseusPhaseLabel(id) {
  return theseusPromptPhaseInfo(id).label;
};

window.theseusPhasePillClass = function theseusPhasePillClass(id) {
  return theseusPromptPhaseInfo(id).pillClass;
};

window.theseusPromptPhases = function theseusPromptPhases(app) {
  const buckets = {};
  for (const prompt of window.theseusFilteredPrompts(app)) {
    const phase = String(prompt.phase || "?");
    (buckets[phase] = buckets[phase] || []).push(prompt);
  }
  return Object.keys(buckets)
    .sort()
    .map((id) => ({
      ...theseusPromptPhaseInfo(id),
      items: buckets[id],
    }));
};

window.theseusUsePrompt = function theseusUsePrompt(app, prompt) {
  theseusLoadPromptIntoComposer(app, prompt, { activateChat: true });
};

window.theseusCopyPrompt = async function theseusCopyPrompt(app, prompt) {
  await window.theseusCopyText(app, prompt.prompt, {
    success: "Prompt copied to clipboard",
    error: "Copy failed",
    kind: "info",
  });
};

window.theseusOpenPromptPicker = function theseusOpenPromptPicker(app) {
  app.promptPicker.open = true;
  app.promptPicker.query = "";
};

window.theseusUsePromptFromPicker = function theseusUsePromptFromPicker(
  app,
  prompt,
) {
  theseusLoadPromptIntoComposer(app, prompt, { closePicker: true });
};

window.theseusPickerPhases = function theseusPickerPhases(app) {
  const matched = theseusSearchPrompts(app.promptLibrary, app.promptPicker.query);
  const phases = [];
  const byId = {};
  for (const prompt of matched) {
    const id = String(prompt.phase || "?");
    if (!byId[id]) {
      byId[id] = {
        ...theseusPromptPhaseInfo(id),
        items: [],
      };
      phases.push(byId[id]);
    }
    byId[id].items.push(prompt);
  }
  phases.sort((left, right) => String(left.id).localeCompare(String(right.id)));
  return phases;
};

window.theseusPromptCategories = function theseusPromptCategories() {
  return [
    "Discovery",
    "Strategy",
    "Compliance",
    "Forensic",
    "Pricing",
    "Bypass",
    "Traceability",
    "Writing",
    "Risk",
    "Review",
    "Submission",
  ];
};

window.theseusPromptPlaceholders = function theseusPromptPlaceholders() {
  return [
    "{topic}",
    "{focus}",
    "{section_or_task}",
    "{capability}",
    "{requirement_id}",
    "{external_topic}",
    "{company}",
    "{volume_or_section}",
  ];
};

window.theseusApplyPromptLibraryResponse = function theseusApplyPromptLibraryResponse(
  app,
  response,
) {
  app.promptLibrary = response.prompts || [];
  app.promptLibraryMeta = {
    customized: Boolean(response.customized),
    workspace: response.workspace || app.stats.workspace || "",
  };
};

window.theseusLoadPromptLibrary = async function theseusLoadPromptLibrary(app) {
  try {
    const response = await app.api("/api/ui/prompt-library");
    window.theseusApplyPromptLibraryResponse(app, response);
  } catch {
    app.promptLibrary = [];
    app.promptLibraryMeta = { customized: false, workspace: "" };
  }
};

window.theseusFilteredPrompts = function theseusFilteredPrompts(app) {
  let prompts = theseusSearchPrompts(app.promptLibrary, app.promptFilter);
  if (app.promptFilterMine) {
    prompts = prompts.filter((prompt) => prompt.source === "user");
  }
  return prompts;
};

window.theseusOpenPromptEditor = function theseusOpenPromptEditor(app, prompt = null) {
  if (prompt) {
    app.promptEditor.isNew = false;
    app.promptEditor.draft = {
      id: prompt.id,
      phase: String(prompt.phase || "4"),
      category: prompt.category || "Discovery",
      title: prompt.title || "",
      prompt: prompt.prompt || "",
      source: prompt.source || "shipped",
    };
  } else {
    app.promptEditor.isNew = true;
    app.promptEditor.draft = {
      id: "",
      phase: "4",
      category: "Discovery",
      title: "",
      prompt: "",
      source: "user",
    };
  }
  app.promptEditor.open = true;
  app.promptEditor.saving = false;
  app.promptEditor.refining = false;
  window.theseusAfterRender(app);
};

window.theseusClosePromptEditor = function theseusClosePromptEditor(app) {
  app.promptEditor.open = false;
};

window.theseusSavePromptEditor = async function theseusSavePromptEditor(app) {
  const draft = app.promptEditor.draft;
  const body = {
    phase: String(draft.phase || "4").trim(),
    category: (draft.category || "").trim(),
    title: (draft.title || "").trim(),
    prompt: (draft.prompt || "").trim(),
  };
  if (!body.title || !body.prompt || !body.category) {
    app.toast("Title, category, and prompt are required", "error");
    return;
  }

  app.promptEditor.saving = true;
  try {
    const response = app.promptEditor.isNew
      ? await app.api("/api/ui/prompt-library", {
          method: "POST",
          body: JSON.stringify(body),
        })
      : await app.api(`/api/ui/prompt-library/${draft.id}`, {
          method: "PUT",
          body: JSON.stringify(body),
        });
    window.theseusApplyPromptLibraryResponse(app, response);
    app.promptEditor.open = false;
    app.toast(app.promptEditor.isNew ? "Prompt added" : "Prompt saved");
  } catch (error) {
    app.toast("Save failed: " + error.message, "error");
  } finally {
    app.promptEditor.saving = false;
  }
};

window.theseusDeletePromptEntry = async function theseusDeletePromptEntry(
  app,
  prompt,
) {
  const label =
    prompt.source === "user"
      ? `Delete "${prompt.title}"?`
      : `Hide shipped prompt "${prompt.title}" from this workspace?`;
  if (!confirm(label)) return;
  try {
    const response = await app.api(`/api/ui/prompt-library/${prompt.id}`, {
      method: "DELETE",
    });
    window.theseusApplyPromptLibraryResponse(app, response);
    if (app.promptEditor.open && app.promptEditor.draft.id === prompt.id) {
      app.promptEditor.open = false;
    }
    app.toast(prompt.source === "user" ? "Prompt deleted" : "Prompt hidden");
  } catch (error) {
    app.toast("Delete failed: " + error.message, "error");
  }
};

window.theseusDuplicatePromptEntry = async function theseusDuplicatePromptEntry(
  app,
  prompt,
) {
  try {
    const response = await app.api(
      `/api/ui/prompt-library/${prompt.id}/duplicate`,
      { method: "POST" },
    );
    window.theseusApplyPromptLibraryResponse(app, response);
    const created = response.entry;
    if (created) window.theseusOpenPromptEditor(app, created);
    app.toast("Editable copy created");
  } catch (error) {
    app.toast("Duplicate failed: " + error.message, "error");
  }
};

window.theseusResetPromptLibrary = async function theseusResetPromptLibrary(app) {
  if (
    !confirm(
      "Restore shipped default prompts for this workspace?\n\nYour custom prompts and edits will be removed.",
    )
  ) {
    return;
  }
  try {
    const response = await app.api("/api/ui/prompt-library/reset", {
      method: "POST",
    });
    window.theseusApplyPromptLibraryResponse(app, response);
    app.toast("Prompt library reset to defaults");
  } catch (error) {
    app.toast("Reset failed: " + error.message, "error");
  }
};

window.theseusImportPromptLibrary = async function theseusImportPromptLibrary(
  app,
  file,
) {
  if (!file) return;
  try {
    const text = await file.text();
    const parsed = JSON.parse(text);
    const prompts = Array.isArray(parsed) ? parsed : parsed.prompts;
    if (!Array.isArray(prompts) || !prompts.length) {
      throw new Error("JSON must be an array of prompts or { prompts: [...] }");
    }
    const response = await app.api("/api/ui/prompt-library/import", {
      method: "POST",
      body: JSON.stringify({ prompts }),
    });
    window.theseusApplyPromptLibraryResponse(app, response);
    app.toast(`Imported ${response.imported?.length || prompts.length} prompt(s)`);
  } catch (error) {
    app.toast("Import failed: " + error.message, "error");
  }
};

window.theseusRefinePromptDraft = async function theseusRefinePromptDraft(
  app,
  action,
) {
  const text = (app.promptEditor.draft.prompt || "").trim();
  if (!text) {
    app.toast("Enter prompt text to refine", "info");
    return;
  }
  app.promptEditor.refining = true;
  try {
    const response = await app.api("/api/ui/prompt-library/refine", {
      method: "POST",
      body: JSON.stringify({ prompt: text, action }),
    });
    app.promptEditor.draft.prompt = response.prompt || text;
    app.toast("Prompt refined — review before saving");
  } catch (error) {
    app.toast("Refine failed: " + error.message, "error");
  } finally {
    app.promptEditor.refining = false;
  }
};

window.theseusExportPromptLibrary = function theseusExportPromptLibrary(app) {
  const payload = {
    workspace: app.promptLibraryMeta.workspace || app.stats.workspace,
    exported_at: new Date().toISOString(),
    prompts: (app.promptLibrary || []).map((prompt) => ({
      phase: prompt.phase,
      category: prompt.category,
      title: prompt.title,
      prompt: prompt.prompt,
      source: prompt.source,
    })),
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: "application/json",
  });
  const href = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = href;
  anchor.download = `theseus-prompts-${payload.workspace || "workspace"}.json`;
  anchor.click();
  URL.revokeObjectURL(href);
  app.toast("Prompt library exported");
};
