window.theseusNavTitle = function theseusNavTitle(active) {
  const titles = {
    dashboard: "Dashboard",
    documents: "Documents",
    graph: "Knowledge Graph",
    chat: "Capture Chat",
    intel: "RFP Intelligence",
    studio: "Studio",
    settings: "Settings",
  };
  return titles[active] || "";
};

window.theseusNavIcon = function theseusNavIcon(navGroups, active) {
  const flat = navGroups.flatMap((group) => group.items);
  return flat.find((item) => item.id === active)?.icon || "circle";
};

window.theseusNavSubtitle = function theseusNavSubtitle(active, stats) {
  const entityTypeCount = stats.ontology?.entity_type_count ?? 32;
  const relationshipTypeCount = stats.ontology?.relationship_type_count ?? 26;
  const subtitles = {
    dashboard: "capture command overview",
    documents: "ingest · MinerU · multimodal extraction",
    graph: `${entityTypeCount} entity types · ${relationshipTypeCount} relationship types`,
    chat: "shipley mentor · RAG over the workspace",
    intel: "instructions ↔ evaluation · traceability · coverage · gaps",
    studio: "capture products · every artifact every skill produced",
    settings: "workspace · storage · models",
  };
  return subtitles[active] || "";
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
  return [
    {
      label: "Documents",
      value: stats.documents ?? "—",
      icon: "file-text",
      hint: "Processed in this workspace",
      go: "documents",
      accent: "cyan",
      color: "text-neon-cyan",
    },
    {
      label: "Entities",
      value: stats.entities ?? "—",
      icon: "sparkles",
      hint: `${stats.ontology?.entity_type_count ?? 32} govcon types`,
      go: "graph",
      accent: "magenta",
      color: "text-neon-magenta",
    },
    {
      label: "Relationships",
      value: stats.relationships ?? "—",
      icon: "link",
      hint: `${stats.ontology?.relationship_type_count ?? 26} canonical types`,
      go: "graph",
      accent: "lime",
      color: "text-neon-lime",
    },
    {
      label: "Chats",
      value: stats.chats ?? 0,
      icon: "messages-square",
      hint: "Saved sessions",
      go: "chat",
      accent: "amber",
      color: "text-neon-amber",
    },
  ];
};