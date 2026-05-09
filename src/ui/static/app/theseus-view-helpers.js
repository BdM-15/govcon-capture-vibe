const THESEUS_VIEW_META = {
  dashboard: {
    title: "Ariadne's Thread",
    subtitle: "global capture command center",
  },
  documents: {
    title: "Documents",
    subtitle: "ingest · MinerU · multimodal extraction",
  },
  graph: {
    title: "Knowledge Graph",
    subtitle: (stats) => {
      const { entityTypeCount, relationshipTypeCount } =
        theseusOntologyCounts(stats);
      return `${entityTypeCount} entity types · ${relationshipTypeCount} relationship types`;
    },
  },
  chat: {
    title: "Capture Chat",
    subtitle: "shipley mentor · RAG over the workspace",
  },
  intel: {
    title: "RFP Intelligence",
    subtitle: "instructions ↔ evaluation · traceability · coverage · gaps",
  },
  studio: {
    title: "Studio",
    subtitle: "capture products · rendered final deliverables only",
  },
  chains: {
    title: "Skill Chains",
    subtitle: "multi-skill runs · handoffs · resume",
  },
  settings: {
    title: "Settings",
    subtitle: "workspace · storage · models",
  },
};

const theseusOntologyCounts = function theseusOntologyCounts(stats) {
  return {
    entityTypeCount: stats.ontology?.entity_type_count ?? 32,
    relationshipTypeCount: stats.ontology?.relationship_type_count ?? 26,
  };
};

const theseusViewMetaFor = function theseusViewMetaFor(active) {
  return THESEUS_VIEW_META[active] || null;
};

const THESEUS_METRIC_META = [
  {
    label: "Documents",
    icon: "file-text",
    hint: () => "Processed in this workspace",
    value: (stats) => stats.documents ?? "—",
    go: "documents",
    accent: "cyan",
    color: "text-neon-cyan",
  },
  {
    label: "Entities",
    icon: "sparkles",
    hint: (_stats, counts) => `${counts.entityTypeCount} govcon types`,
    value: (stats) => stats.entities ?? "—",
    go: "graph",
    accent: "magenta",
    color: "text-neon-magenta",
  },
  {
    label: "Relationships",
    icon: "link",
    hint: (_stats, counts) => `${counts.relationshipTypeCount} canonical types`,
    value: (stats) => stats.relationships ?? "—",
    go: "graph",
    accent: "lime",
    color: "text-neon-lime",
  },
  {
    label: "Chats",
    icon: "messages-square",
    hint: () => "Saved sessions",
    value: (stats) => stats.chats ?? 0,
    go: "chat",
    accent: "amber",
    color: "text-neon-amber",
  },
];

window.theseusNavTitle = function theseusNavTitle(active) {
  return theseusViewMetaFor(active)?.title || "";
};

window.theseusNavIcon = function theseusNavIcon(navGroups, active) {
  const flat = navGroups.flatMap((group) => group.items);
  return flat.find((item) => item.id === active)?.icon || "circle";
};

window.theseusNavSubtitle = function theseusNavSubtitle(active, stats) {
  const subtitle = theseusViewMetaFor(active)?.subtitle;
  return typeof subtitle === "function" ? subtitle(stats) : subtitle || "";
};

window.theseusGreeting = function theseusGreeting() {
  const hour = new Date().getHours();
  const part =
    hour < 5
      ? "Working late"
      : hour < 12
        ? "Good morning"
        : hour < 17
          ? "Good afternoon"
          : "Good evening";
  return `${part}, Ben`;
};

window.theseusMetrics = function theseusMetrics(stats) {
  const counts = theseusOntologyCounts(stats);
  return THESEUS_METRIC_META.map((metric) => ({
    label: metric.label,
    value: metric.value(stats, counts),
    icon: metric.icon,
    hint: metric.hint(stats, counts),
    go: metric.go,
    accent: metric.accent,
    color: metric.color,
  }));
};
