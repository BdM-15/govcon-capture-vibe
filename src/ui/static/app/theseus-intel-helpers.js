window.theseusLoadIntel = async function theseusLoadIntel(app) {
  app.intel.loading = true;
  try {
    app.intel.data = await app.api("/api/ui/intel/summary");
  } catch (error) {
    app.toast("Intel compute failed: " + error.message, "error");
  } finally {
    app.intel.loading = false;
  }
};

window.theseusFilteredLmRows = function theseusFilteredLmRows(app) {
  const rows = app.intel.data?.lm_matrix?.instructions || [];
  return rows.filter((row) =>
    row.covered ? app.intel.showCovered : app.intel.showGaps,
  );
};

window.theseusOrphanFactors = function theseusOrphanFactors(app) {
  const rows = app.intel.data?.lm_matrix?.factors || [];
  return rows.filter((row) => !row.covered);
};

window.theseusFilteredTrace = function theseusFilteredTrace(app) {
  const rows = app.intel.data?.traceability || [];
  const query = app.intel.traceFilter.trim().toLowerCase();
  if (!query) return rows;
  return rows.filter((row) => {
    const blob = [
      row.requirement.id,
      row.requirement.description,
      ...row.deliverables.map((deliverable) => deliverable.id),
      ...row.standards.map((standard) => standard.id),
      ...row.metrics.map((metric) => metric.id),
    ]
      .join(" ")
      .toLowerCase();
    return blob.includes(query);
  });
};

window.theseusCoverageBadgeClass = function theseusCoverageBadgeClass(score) {
  if (score >= 3) {
    return "bg-neon-lime/10 text-neon-lime border border-neon-lime/30";
  }
  if (score === 2) {
    return "bg-neon-cyan/10 text-neon-cyan border border-neon-cyan/30";
  }
  if (score === 1) {
    return "bg-neon-amber/10 text-neon-amber border border-neon-amber/30";
  }
  return "bg-neon-red/10 text-neon-red border border-neon-red/30";
};

window.theseusGapBuckets = function theseusGapBuckets(app) {
  const gaps = app.intel.data?.gaps || {};
  return [
    {
      id: "req",
      title: "Requirements without SATISFIED_BY",
      subtitle: "shall/will language with no satisfying deliverable.",
      items: gaps.requirements_no_satisfaction || [],
      askPrefix: "Identify candidate deliverables to satisfy requirement",
    },
    {
      id: "fact",
      title: "Evaluation factors with no proposal instruction hook",
      subtitle:
        "Evaluation factors (UCF Section M or equivalent) that no proposal_instruction (UCF Section L or equivalent) guides toward.",
      items: gaps.factors_no_instruction || [],
      askPrefix:
        "Recommend proposal_instruction entities (UCF Section L or equivalent) to add for evaluation factor",
    },
    {
      id: "del",
      title: "Deliverables without measure",
      subtitle: "Deliverables lacking MEASURED_BY or TRACKED_BY.",
      items: gaps.deliverables_no_measure || [],
      askPrefix: "Suggest performance standards or workload metrics for deliverable",
    },
  ];
};

window.theseusAskIntel = function theseusAskIntel(app, prompt) {
  app.composer = prompt;
  app.newChat();
};