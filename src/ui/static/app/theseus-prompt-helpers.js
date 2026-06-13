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

const theseusGroupPromptsByCategory = function theseusGroupPromptsByCategory(
  prompts,
) {
  const buckets = new Map();
  for (const prompt of prompts) {
    const label = String(prompt.category || "Other").trim() || "Other";
    if (!buckets.has(label)) buckets.set(label, []);
    buckets.get(label).push(prompt);
  }
  return Array.from(buckets.entries())
    .sort((left, right) => left[0].localeCompare(right[0]))
    .map(([label, items]) => ({
      id: label,
      label,
      items,
    }));
};

window.theseusPromptCollectionFilters = function theseusPromptCollectionFilters() {
  return [
    { id: "all", label: "All" },
    { id: "chat", label: "Capture Chat" },
    { id: "briefing", label: "RFP Briefings" },
  ];
};

window.theseusPromptDestinationMeta = function theseusPromptDestinationMeta(
  prompt,
) {
  const channel = window.theseusPromptChannel(prompt);
  const title = String(prompt.label || prompt.title || "Prompt").trim();
  if (channel === "briefing_chat") {
    return {
      line: "RFP Intelligence",
      detail: title,
      icon: "shield-check",
    };
  }
  if (channel === "briefing_skill") {
    return {
      line: "RFP Intelligence",
      detail: title,
      icon: "target",
      skill: String(prompt.skill || "").trim(),
    };
  }
  if (channel === "briefing_related") {
    return {
      line: "RFP Intelligence",
      detail: title,
      icon: "link-2",
      skill: String(prompt.skill || "").trim(),
    };
  }
  if (channel === "skill_default") {
    return {
      line: "Agent Skills",
      detail: String(prompt.skill || title).trim(),
      icon: "wand-2",
      skill: String(prompt.skill || "").trim(),
    };
  }
  return {
    line: "Capture Chat",
    detail: String(prompt.category || "Starter").trim(),
    icon: "message-square",
  };
};

window.theseusPromptPrimaryAction = function theseusPromptPrimaryAction(prompt) {
  const channel = window.theseusPromptChannel(prompt);
  if (
    channel === "briefing_chat"
    || channel === "briefing_skill"
    || channel === "briefing_related"
  ) {
    return {
      id: "open_intel",
      label: "Open in Intelligence",
      icon: "shield-check",
    };
  }
  if (channel === "skill_default") {
    return {
      id: "open_skill",
      label: "Open skill",
      icon: "wand-2",
    };
  }
  return {
    id: "use_chat",
    label: "Use in Capture Chat",
    icon: "message-square",
  };
};

window.theseusUsePromptInChat = function theseusUsePromptInChat(app, prompt) {
  theseusLoadPromptIntoComposer(app, prompt, { activateChat: true });
};

window.theseusUsePrompt = function theseusUsePrompt(app, prompt) {
  window.theseusUsePromptInChat(app, prompt);
};

window.theseusRunPromptPrimaryAction = async function theseusRunPromptPrimaryAction(
  app,
  prompt,
) {
  const action = window.theseusPromptPrimaryAction(prompt);
  if (action.id === "use_chat") {
    window.theseusUsePromptInChat(app, prompt);
    return;
  }
  if (action.id === "open_intel") {
    app.active = "intel";
    app.intel.tab = "briefings";
    if (!app.intel.slices?.length && typeof app.loadIntel === "function") {
      await app.loadIntel();
    } else {
      window.theseusAfterRender(app);
    }
    const meta = window.theseusPromptDestinationMeta(prompt);
    app.toast(
      "RFP Intelligence → Briefings · " + (meta.detail || meta.line),
      "ok",
    );
    return;
  }
  if (action.id === "open_skill") {
    const skill = String(prompt.skill || "").trim();
    if (!skill) {
      app.toast("No skill binding on this prompt", "error");
      return;
    }
    app.active = "skills";
    if (typeof app.openSkill === "function") {
      await app.openSkill(skill);
    }
  }
};

window.theseusPromptLibrarySections = function theseusPromptLibrarySections(app) {
  const collection = String(app.promptCollectionFilter || "all");
  const prompts = window.theseusFilteredPrompts(app);
  const sections = [];

  const briefingPrompts = prompts.filter((prompt) =>
    window.theseusIsBriefingPrompt(prompt),
  );
  if (
    briefingPrompts.length
    && (collection === "all" || collection === "briefing")
  ) {
    const orientation = briefingPrompts.filter(
      (prompt) => window.theseusPromptChannel(prompt) === "briefing_chat",
    );
    const skills = briefingPrompts.filter(
      (prompt) => window.theseusPromptChannel(prompt) === "briefing_skill",
    );
    const related = briefingPrompts.filter(
      (prompt) => window.theseusPromptChannel(prompt) === "briefing_related",
    );
    const groups = [
      { id: "orientation", label: "Chat orientation", items: orientation },
      { id: "skills", label: "Skill briefings", items: skills },
      { id: "related", label: "Related forensic", items: related },
    ].filter((group) => group.items.length);
    sections.push({
      id: "briefings",
      label: "RFP Intelligence Briefings",
      hint: "Packaged prompts for the Intelligence → Briefings tab",
      accent: "amber",
      defaultOpen: true,
      groups,
    });
  }

  if (collection === "all" || collection === "chat") {
    for (const phaseId of ["4", "5", "6"]) {
      const phasePrompts = prompts.filter((prompt) => {
        if (window.theseusIsBriefingPrompt(prompt)) return false;
        return String(prompt.phase || "") === phaseId;
      });
      if (!phasePrompts.length) continue;
      const phaseInfo = theseusPromptPhaseInfo(phaseId);
      sections.push({
        id: "phase-" + phaseId,
        label: "Capture Chat · " + phaseInfo.label,
        hint: "Shipley-aligned starters seeded into the chat composer",
        accent: phaseInfo.accentClass.replace("accent-", ""),
        pillClass: phaseInfo.pillClass,
        defaultOpen: phaseId === "4",
        groups: theseusGroupPromptsByCategory(phasePrompts),
      });
    }
  }

  return sections;
};

window.theseusPromptsExpandAll = function theseusPromptsExpandAll() {
  document
    .querySelectorAll("[data-prompt-sections] details.acc")
    .forEach((detail) => {
      detail.open = true;
    });
};

window.theseusPromptsCollapseAll = function theseusPromptsCollapseAll() {
  document
    .querySelectorAll("[data-prompt-sections] details.acc")
    .forEach((detail) => {
      detail.open = false;
    });
};

window.theseusPromptSectionCount = function theseusPromptSectionCount(section) {
  return (section?.groups || []).reduce(
    (total, group) => total + (group.items?.length || 0),
    0,
  );
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
    window.theseusAfterRender(app);
  } catch {
    app.promptLibrary = [];
    app.promptLibraryMeta = { customized: false, workspace: "" };
  }
};

window.theseusPromptChannel = function theseusPromptChannel(prompt) {
  return String(prompt?.channel || "chat").trim() || "chat";
};

window.theseusIsBriefingPrompt = function theseusIsBriefingPrompt(prompt) {
  const channel = window.theseusPromptChannel(prompt);
  return channel === "briefing_chat"
    || channel === "briefing_skill"
    || channel === "briefing_related"
    || channel === "skill_default";
};

window.theseusPromptChannelLabel = function theseusPromptChannelLabel(prompt) {
  const channel = window.theseusPromptChannel(prompt);
  if (channel === "briefing_chat") return "RFP briefing · chat";
  if (channel === "briefing_skill") return "RFP briefing · skill";
  if (channel === "briefing_related") return "RFP briefing · related";
  if (channel === "skill_default") return "Skill default";
  return "Capture chat";
};

window.theseusFilteredPrompts = function theseusFilteredPrompts(app) {
  let prompts = theseusSearchPrompts(app.promptLibrary, app.promptFilter);
  if (app.promptFilterMine) {
    prompts = prompts.filter((prompt) => prompt.source === "user");
  }
  const channelFilter = String(
    app.promptCollectionFilter || app.promptChannelFilter || "all",
  );
  if (channelFilter === "chat") {
    prompts = prompts.filter(
      (prompt) => !window.theseusIsBriefingPrompt(prompt),
    );
  } else if (channelFilter === "briefing") {
    prompts = prompts.filter((prompt) =>
      window.theseusIsBriefingPrompt(prompt),
    );
  }
  return prompts;
};

window.theseusFindPromptLibraryEntry = function theseusFindPromptLibraryEntry(
  app,
  entryId,
) {
  const id = String(entryId || "").trim();
  if (!id) return null;
  return (app.promptLibrary || []).find((prompt) => prompt.id === id) || null;
};

window.theseusEnsurePromptLibraryLoaded =
  async function theseusEnsurePromptLibraryLoaded(app) {
    if ((app.promptLibrary || []).length) return;
    await window.theseusLoadPromptLibrary(app);
  };

window.theseusResolveSkillDefaultPrompt =
  function theseusResolveSkillDefaultPrompt(app, skillName) {
    const name = String(skillName || "").trim();
    if (!name) return "";
    const matches = (app.promptLibrary || []).filter((prompt) => {
      const channel = window.theseusPromptChannel(prompt);
      return (
        String(prompt.skill || "").trim() === name
        && (channel === "briefing_skill" || channel === "skill_default")
      );
    });
    if (!matches.length) return "";
    matches.sort(
      (left, right) =>
        Number(left.sort_order || 0) - Number(right.sort_order || 0),
    );
    return String(matches[0].prompt || "").trim();
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
    const saved = response.entry || draft;
    if (
      window.theseusIsBriefingPrompt(saved)
      && typeof app.loadIntel === "function"
    ) {
      app.loadIntel();
    }
    if (
      saved.skill
      && app.skills?.current?.name === saved.skill
      && String(saved.prompt || "").trim()
    ) {
      app.skills.invokePrompt = String(saved.prompt).trim();
    }
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
