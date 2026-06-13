const _SKILL_FAMILY_ORDER = [
  "readiness-frame",
  "capture-intel",
  "pricing",
  "proposal-pipeline",
  "compliance",
];

window.theseusSkillViewModes = function theseusSkillViewModes() {
  return [
    { id: "families", label: "Families" },
    { id: "orchestrators", label: "Orchestrators" },
    { id: "flat", label: "All flat" },
  ];
};

window.theseusSkillSectionAccent = function theseusSkillSectionAccent(accent) {
  const styles = {
    cyan: {
      border: "border-neon-cyan/40",
      icon: "sparkles",
      iconColor: "text-neon-cyan",
      pill: "text-neon-cyan border-neon-cyan/40",
      card: "accent-cyan",
      heading: "text-neon-cyan/70",
      rule: "bg-neon-cyan/20",
    },
    magenta: {
      border: "border-neon-magenta/30",
      icon: "wand-2",
      iconColor: "text-neon-magenta",
      pill: "text-neon-magenta border-neon-magenta/40",
      card: "accent-magenta",
      heading: "text-neon-magenta/70",
      rule: "bg-neon-magenta/20",
    },
    amber: {
      border: "border-amber-400/40",
      icon: "git-merge",
      iconColor: "text-amber-400",
      pill: "text-amber-400 border-amber-400/40",
      card: "accent-amber",
      heading: "text-amber-400/80",
      rule: "bg-amber-400/20",
    },
  };
  return styles[accent] || styles.magenta;
};

window.theseusSkillRoleLabel = function theseusSkillRoleLabel(role) {
  const labels = {
    orchestrator: "orchestrator",
    slice: "slice",
    standalone: "standalone",
  };
  return labels[role] || "";
};

window.theseusSortSkillsByName = function theseusSortSkillsByName(skills) {
  return skills.slice().sort((left, right) => left.name.localeCompare(right.name));
};

window.theseusSkillsFamilyRank = function theseusSkillsFamilyRank(family) {
  const index = _SKILL_FAMILY_ORDER.indexOf(family);
  return index >= 0 ? index : 100;
};

window.theseusSkillsGroupedSections = function theseusSkillsGroupedSections(app) {
  const filtered = window.theseusSkillsFiltered(app);
  const view = app.skills.viewMode || "families";

  if (view === "flat") {
    const meta = window.theseusSortSkillsByName(
      filtered.filter((skill) => window.theseusIsMetaSkill(skill)),
    );
    const domain = window.theseusSortSkillsByName(
      filtered.filter((skill) => !window.theseusIsMetaSkill(skill)),
    );
    const sections = [];
    if (meta.length) {
      sections.push({
        id: "utility",
        label: "Utility & Infrastructure",
        skills: meta,
        accent: "cyan",
        defaultOpen: false,
        hint: "Rendering, ontology, and skill authoring utilities.",
      });
    }
    if (domain.length) {
      sections.push({
        id: "domain-flat",
        label: "Domain Skills",
        skills: domain,
        accent: "magenta",
        defaultOpen: true,
      });
    }
    return sections;
  }

  const orchestrators = window.theseusSortSkillsByName(
    filtered.filter((skill) => skill.skill_role === "orchestrator"),
  );
  const utility = window.theseusSortSkillsByName(
    filtered.filter((skill) => window.theseusIsMetaSkill(skill)),
  );
  const domain = filtered.filter(
    (skill) =>
      !window.theseusIsMetaSkill(skill) && skill.skill_role !== "orchestrator",
  );

  const familyMap = new Map();
  const standalone = [];
  for (const skill of domain) {
    const family = skill.skill_family || "";
    if (family) {
      if (!familyMap.has(family)) familyMap.set(family, []);
      familyMap.get(family).push(skill);
    } else {
      standalone.push(skill);
    }
  }

  const familySections = Array.from(familyMap.entries())
    .sort(
      (left, right) =>
        window.theseusSkillsFamilyRank(left[0]) -
          window.theseusSkillsFamilyRank(right[0]) ||
        left[0].localeCompare(right[0]),
    )
    .map(([family, skills]) => ({
      id: `family-${family}`,
      label: skills[0]?.skill_family_label || family.replace(/-/g, " "),
      family,
      skills: window.theseusSortSkillsByName(skills),
      accent: "magenta",
      defaultOpen: false,
    }));

  const sections = [];

  if (utility.length) {
    sections.push({
      id: "utility",
      label: "Utility & Infrastructure",
      skills: utility,
      accent: "cyan",
      defaultOpen: false,
      hint: "Rendering, ontology, and skill authoring utilities.",
    });
  }

  if ((view === "families" || view === "orchestrators") && orchestrators.length) {
    sections.push({
      id: "orchestrators",
      label: "Orchestrators",
      skills: orchestrators,
      accent: "amber",
      defaultOpen: true,
      hint: "Compile handoffs from one or more skill families into deliverables.",
    });
  }

  if (view === "families" || view === "orchestrators") {
    sections.push(...familySections);
    const sortedStandalone = window.theseusSortSkillsByName(standalone);
    if (sortedStandalone.length) {
      sections.push({
        id: "standalone",
        label: "Standalone Domain",
        skills: sortedStandalone,
        accent: "magenta",
        defaultOpen: false,
        hint: "Invoked directly — not part of a decomposed family.",
      });
    }
  }

  return sections;
};

window.theseusSkillsExpandAll = function theseusSkillsExpandAll() {
  document.querySelectorAll("[data-skills-sections] details.acc").forEach((detail) => {
    detail.open = true;
  });
};

window.theseusSkillsCollapseAll = function theseusSkillsCollapseAll() {
  document.querySelectorAll("[data-skills-sections] details.acc").forEach((detail) => {
    detail.open = false;
  });
};