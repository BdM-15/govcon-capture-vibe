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
  app.composer = prompt.prompt;
  if (closePicker) app.promptPicker.open = false;
  if (activateChat) app.active = "chat";
  window.theseusFocusComposer(app);
  app.toast("Prompt loaded into composer", "info");
};

window.theseusFilteredPrompts = function theseusFilteredPrompts(app) {
  return theseusSearchPrompts(app.promptLibrary, app.promptFilter);
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

window.theseusFocusComposer = function theseusFocusComposer(app) {
  app.$nextTick(() => {
    if (app.$refs.composer) app.$refs.composer.focus();
  });
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

window.theseusLoadPromptLibrary = async function theseusLoadPromptLibrary(app) {
  try {
    const response = await app.api("/api/ui/prompt-library");
    app.promptLibrary = response.prompts || [];
  } catch {
    app.promptLibrary = [];
  }
};
