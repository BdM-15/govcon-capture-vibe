window.createTheseusNavGroups = function createTheseusNavGroups() {
  return [
    {
      id: "capture",
      label: "CAPTURE",
      accent: "cyan",
      items: [
        {
          id: "dashboard",
          label: "Dashboard",
          icon: "layout-dashboard",
          accent: "cyan",
        },
        {
          id: "documents",
          label: "Documents",
          icon: "file-text",
          accent: "magenta",
        },
        {
          id: "intel",
          label: "RFP Intelligence",
          icon: "shield-check",
          accent: "amber",
        },
        {
          id: "studio",
          label: "Studio",
          icon: "folder-open",
          accent: "lime",
        },
      ],
    },
    {
      id: "tools",
      label: "TOOLS",
      accent: "magenta",
      items: [
        {
          id: "graph",
          label: "Knowledge Graph",
          icon: "git-fork",
          accent: "lime",
        },
        {
          id: "chat",
          label: "Capture Chat",
          icon: "message-square",
          accent: "cyan",
        },
        {
          id: "prompts",
          label: "Prompt Library",
          icon: "library",
          accent: "magenta",
        },
        {
          id: "skills",
          label: "Agent Skills",
          icon: "wand-2",
          accent: "magenta",
        },
        {
          id: "activity",
          label: "Activity Log",
          icon: "activity",
          accent: "amber",
        },
      ],
    },
    {
      id: "system",
      label: "SYSTEM",
      accent: "lime",
      items: [
        {
          id: "settings",
          label: "Settings",
          icon: "settings",
          accent: "amber",
        },
      ],
    },
  ];
};

window.createTheseusIntelTabs = function createTheseusIntelTabs() {
  return [
    {
      id: "lm",
      label: "Instructions ↔ Evaluation",
      icon: "arrow-left-right",
    },
    { id: "trace", label: "Traceability", icon: "list-tree" },
    { id: "coverage", label: "Coverage", icon: "shield-check" },
    { id: "gaps", label: "Gaps", icon: "alert-triangle" },
  ];
};