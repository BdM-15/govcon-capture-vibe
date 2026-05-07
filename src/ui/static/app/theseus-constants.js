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
          id: "chains",
          label: "Skill Chains",
          icon: "workflow",
          accent: "cyan",
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

window.createTheseusSkillPersonaConfig =
  function createTheseusSkillPersonaConfig() {
    return [
      { id: "capture_manager", label: "Capture Managers" },
      { id: "proposal_manager", label: "Proposal Managers" },
      { id: "proposal_writer", label: "Proposal Writers" },
      { id: "cost_estimator", label: "Cost Estimators" },
      { id: "contracts_manager", label: "Contracts Managers" },
      { id: "technical_sme", label: "Technical SMEs" },
      { id: "legal_compliance", label: "Legal / Compliance" },
      { id: "program_manager", label: "Program Managers" },
      { id: "none", label: "Utility & Meta" },
    ];
  };

window.createTheseusSkillPersonaFilterConfig =
  function createTheseusSkillPersonaFilterConfig() {
    return [
      {
        id: "capture",
        label: "Capture",
        personas: ["capture_manager"],
      },
      { id: "writer", label: "Writer", personas: ["proposal_writer"] },
      {
        id: "operations",
        label: "Operations",
        personas: ["technical_sme", "program_manager"],
      },
      { id: "cost", label: "Cost", personas: ["cost_estimator"] },
      {
        id: "contracts",
        label: "Contracts",
        personas: ["contracts_manager"],
      },
      { id: "legal", label: "Legal", personas: ["legal_compliance"] },
    ];
  };

window.createTheseusSkillPhaseConfig =
  function createTheseusSkillPhaseConfig() {
    return [
      { id: "pursuit", label: "Pursuit" },
      { id: "capture", label: "Capture" },
      { id: "strategy", label: "Strategy" },
      { id: "proposal_development", label: "Proposal Dev" },
      { id: "negotiation", label: "Negotiation" },
      { id: "post_award", label: "Post-Award" },
    ];
  };

window.createTheseusSkillCapabilityConfig =
  function createTheseusSkillCapabilityConfig() {
    return [
      { id: "research", label: "Research" },
      { id: "analyze", label: "Analyze" },
      { id: "draft", label: "Draft" },
      { id: "audit", label: "Audit" },
      { id: "estimate", label: "Estimate" },
      { id: "render", label: "Render" },
      { id: "meta", label: "Meta" },
    ];
  };
