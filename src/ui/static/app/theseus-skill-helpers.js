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