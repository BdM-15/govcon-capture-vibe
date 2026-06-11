window.THESEUS_INTEL_CONTEXT_TOOLTIP_DEFAULT =
  "Optional first-run notes appended to this briefing's prompt as " +
  "User-supplied context. High impact for facts the KG may not encode: " +
  "incumbent name, partner URLs (web_fetch), teaming focus, or constraints " +
  "like 'no company capability mapping'. Leave empty for the catalog prompt only.";

window.theseusIntelContextTooltip = function theseusIntelContextTooltip(
  sliceOrRel,
) {
  const text = String(sliceOrRel?.context_tooltip || "").trim();
  return text || window.THESEUS_INTEL_CONTEXT_TOOLTIP_DEFAULT;
};

window.theseusOpenIntelBriefingGuide = function theseusOpenIntelBriefingGuide(
  app,
  slice,
  related,
) {
  app.intel.briefingGuide.slice = slice || null;
  app.intel.briefingGuide.related = related || null;
  app.intel.briefingGuide.open = true;
  window.theseusAfterRender(app);
};

window.theseusCloseIntelBriefingGuide = function theseusCloseIntelBriefingGuide(
  app,
) {
  app.intel.briefingGuide.open = false;
  app.intel.briefingGuide.slice = null;
  app.intel.briefingGuide.related = null;
  window.theseusAfterRender(app);
};

window.theseusIntelBriefingGuideTarget = function theseusIntelBriefingGuideTarget(
  app,
) {
  if (app.intel.briefingGuide.related) {
    return app.intel.briefingGuide.related;
  }
  return app.intel.briefingGuide.slice;
};

window.theseusLoadIntel = async function theseusLoadIntel(app) {
  app.intel.loading = true;
  app.intel.slicesLoading = true;
  try {
    const [summary, slicesPayload] = await Promise.all([
      app.api("/api/ui/intel/summary"),
      app.api("/api/ui/intel/slices"),
    ]);
    app.intel.data = summary;
    app.intel.slices = slicesPayload.slices || [];
  } catch (error) {
    app.toast("Intel compute failed: " + error.message, "error");
  } finally {
    app.intel.loading = false;
    app.intel.slicesLoading = false;
    window.theseusAfterRender(app);
  }
};

window.theseusIntelSliceContextKey = function theseusIntelSliceContextKey(
  sliceId,
  relatedSkill,
) {
  if (relatedSkill) return String(sliceId) + ":" + String(relatedSkill);
  return String(sliceId || "");
};

window.theseusIntelSliceContextText = function theseusIntelSliceContextText(
  app,
  contextKey,
) {
  const key = String(contextKey || "");
  if (!key) return "";
  if (!app.intel.sliceContext || typeof app.intel.sliceContext !== "object") {
    app.intel.sliceContext = {};
  }
  return String(app.intel.sliceContext[key] || "");
};

window.theseusRunIntelChatSlice = function theseusRunIntelChatSlice(
  app,
  slice,
  contextKey,
) {
  if (!slice?.prompt) return;
  const extra = window.theseusIntelSliceContextText(
    app,
    contextKey || slice.id,
  ).trim();
  const prompt = extra
    ? slice.prompt + "\n\nUser-supplied context:\n" + extra
    : slice.prompt;
  window.theseusStartChatWithComposer(app, prompt);
};

window.theseusInvokeIntelSkill = async function theseusInvokeIntelSkill(
  app,
  skillName,
  prompt,
  runningKey,
  contextKey,
) {
  if (!skillName) return;
  app.intel.sliceRunning = runningKey || skillName;
  const userAddendum = window
    .theseusIntelSliceContextText(app, contextKey || runningKey)
    .trim();
  try {
    const response = await app.api(
      "/api/ui/skills/" + encodeURIComponent(skillName) + "/invoke",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: prompt || "",
          user_addendum: userAddendum,
        }),
      },
    );
    if (response.run_id) {
      app.toast("Briefing run saved: " + response.run_id, "ok");
    } else {
      app.toast("Skill run completed", "ok");
    }
    const slicesPayload = await app.api("/api/ui/intel/slices");
    app.intel.slices = slicesPayload.slices || [];
    window.theseusAfterRender(app);
  } catch (error) {
    app.toast("Skill run failed: " + (error.message || error), "error");
  } finally {
    app.intel.sliceRunning = null;
  }
};

window.theseusOpenIntelSliceInStudio = function theseusOpenIntelSliceInStudio(
  app,
  run,
) {
  if (!run?.run_id || !run?.skill) return;
  app.active = "studio";
  app.$nextTick(() => {
    if (typeof app.loadStudio === "function") {
      app.loadStudio().then(() => window.theseusAfterRender(app));
    }
  });
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
  window.theseusStartChatWithComposer(app, prompt);
};