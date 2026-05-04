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

window.theseusFilteredPrompts = function theseusFilteredPrompts(app) {
  const query = (app.promptFilter || "").trim().toLowerCase();
  if (!query) return app.promptLibrary;
  return app.promptLibrary.filter(
    (prompt) =>
      (prompt.title || "").toLowerCase().includes(query) ||
      (prompt.category || "").toLowerCase().includes(query) ||
      (prompt.prompt || "").toLowerCase().includes(query),
  );
};

window.theseusPhaseLabel = function theseusPhaseLabel(id) {
  return window.theseusPromptPhaseMeta()[String(id)]?.label || `Phase ${id}`;
};

window.theseusPhasePillClass = function theseusPhasePillClass(id) {
  return (
    window.theseusPromptPhaseMeta()[String(id)]?.pillClass ||
    "bg-ink-800 text-slate-400 border-edge"
  );
};

window.theseusPromptPhases = function theseusPromptPhases(app) {
  const meta = window.theseusPromptPhaseMeta();
  const buckets = {};
  for (const prompt of window.theseusFilteredPrompts(app)) {
    const phase = String(prompt.phase || "?");
    (buckets[phase] = buckets[phase] || []).push(prompt);
  }
  return Object.keys(buckets)
    .sort()
    .map((id) => ({
      id,
      label: meta[id]?.label || `Phase ${id}`,
      pillClass: meta[id]?.pillClass || "bg-ink-800 text-slate-400 border-edge",
      accentClass: meta[id]?.accentClass || "accent-cyan",
      items: buckets[id],
    }));
};

window.theseusFocusComposer = function theseusFocusComposer(app) {
  app.$nextTick(() => {
    if (app.$refs.composer) app.$refs.composer.focus();
  });
};

window.theseusUsePrompt = function theseusUsePrompt(app, prompt) {
  app.composer = prompt.prompt;
  app.active = "chat";
  window.theseusFocusComposer(app);
  app.toast("Prompt loaded into composer", "info");
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
  app.composer = prompt.prompt;
  app.promptPicker.open = false;
  window.theseusFocusComposer(app);
  app.toast("Prompt loaded into composer", "info");
};

window.theseusPickerPhases = function theseusPickerPhases(app) {
  const query = (app.promptPicker.query || "").toLowerCase().trim();
  const matched = !query
    ? app.promptLibrary
    : app.promptLibrary.filter(
        (prompt) =>
          (prompt.title || "").toLowerCase().includes(query) ||
          (prompt.category || "").toLowerCase().includes(query) ||
          (prompt.prompt || "").toLowerCase().includes(query),
      );
  const phases = [];
  const byId = {};
  for (const prompt of matched) {
    const id = String(prompt.phase || "?");
    if (!byId[id]) {
      byId[id] = {
        id,
        label: window.theseusPhaseLabel(id),
        pillClass: window.theseusPhasePillClass(id),
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
