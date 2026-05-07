window.theseusLoadChains = async function theseusLoadChains(app) {
  app.chains.loading = true;
  app.chains.error = null;
  try {
    const response = await app.api("/api/ui/skill-chains?limit=100");
    app.chains.items = response.chains || [];
    app.chains.loaded = true;
    if (app.chains.current?.chain_id) {
      const current = app.chains.items.find(
        (chain) => chain.chain_id === app.chains.current.chain_id,
      );
      if (!current) app.chains.current = null;
    }
  } catch (error) {
    app.chains.error = "Chain load failed: " + (error?.message || error);
    app.chains.items = [];
  } finally {
    app.chains.loading = false;
    window.theseusAfterRender(app);
  }
};

window.theseusOpenChain = async function theseusOpenChain(
  app,
  chainId,
  options = {},
) {
  if (!chainId) return;
  app.chains.loadingDetail = true;
  app.chains.error = null;
  try {
    const response = await app.api(
      "/api/ui/skill-chains/" + encodeURIComponent(chainId),
    );
    app.chains.current = response;
    if (options.activate !== false) app.active = "chains";
  } catch (error) {
    app.toast("Chain load failed: " + (error?.message || error), "error");
  } finally {
    app.chains.loadingDetail = false;
    window.theseusAfterRender(app);
  }
};

window.theseusChainSteps = function theseusChainSteps(chain) {
  if (!chain) return [];
  const runs = chain.steps || {};
  const specSteps = chain.spec?.steps || [];
  const ordered = specSteps
    .map((step) => runs[step.id] || { id: step.id, skill: step.skill })
    .filter(Boolean);
  const seen = new Set(ordered.map((step) => step.id));
  Object.values(runs).forEach((step) => {
    if (!seen.has(step.id)) ordered.push(step);
  });
  return ordered;
};

window.theseusChainStatusClass = function theseusChainStatusClass(status) {
  if (status === "completed") return "text-neon-lime border-neon-lime/40 bg-neon-lime/10";
  if (status === "running") return "text-neon-cyan border-neon-cyan/40 bg-neon-cyan/10";
  if (status === "failed") return "text-neon-red border-neon-red/40 bg-neon-red/10";
  if (status === "skipped") return "text-neon-amber border-neon-amber/40 bg-neon-amber/10";
  return "text-slate-400 border-edge bg-ink-800";
};

window.theseusChainArtifactCount = function theseusChainArtifactCount(chain) {
  return window
    .theseusChainSteps(chain)
    .reduce((total, step) => total + ((step.artifacts || []).length || 0), 0);
};

window.theseusChainResumeStepId = function theseusChainResumeStepId(chain) {
  const step = window
    .theseusChainSteps(chain)
    .find((item) => ["failed", "skipped", "pending", "running"].includes(item.status));
  return step?.id || "";
};

window.theseusChainCanResume = function theseusChainCanResume(chain) {
  if (!chain || chain.status === "running" || chain.status === "completed") return false;
  if (chain.resume_step_id) return true;
  if (chain.can_resume === false) return false;
  return !!window.theseusChainResumeStepId(chain);
};

window.theseusPrimaryChain = function theseusPrimaryChain(deliverable) {
  return deliverable?.chain || (deliverable?.chains || [])[0] || null;
};

window.theseusStudioHasChain = function theseusStudioHasChain(deliverable) {
  return !!window.theseusPrimaryChain(deliverable);
};

window.theseusOpenStudioChainTrace = async function theseusOpenStudioChainTrace(
  app,
  deliverable,
) {
  const chain = window.theseusPrimaryChain(deliverable);
  if (!chain?.chain_id) return;
  app.studio.chainTraceOpen = true;
  await window.theseusOpenChain(app, chain.chain_id, { activate: false });
};

window.theseusCloseStudioChainTrace = function theseusCloseStudioChainTrace(app) {
  app.studio.chainTraceOpen = false;
};

window.theseusRerunStudioChain = async function theseusRerunStudioChain(
  app,
  deliverable,
) {
  const chain = window.theseusPrimaryChain(deliverable);
  if (!chain?.chain_id) return;
  app.studio.chainTraceOpen = true;
  await window.theseusRerunChain(app, chain.chain_id);
};

window.theseusResumeStudioChain = async function theseusResumeStudioChain(
  app,
  deliverable,
) {
  const chain = window.theseusPrimaryChain(deliverable);
  if (!chain?.chain_id) return;
  app.studio.chainTraceOpen = true;
  await window.theseusResumeChain(app, chain.chain_id);
};

const theseusStudioChainGoalPayload = function theseusStudioChainGoalPayload(app) {
  return {
    prompt: app.studio.chainGoal || "",
    outcome: app.studio.chainOutcome || "",
    max_steps: 8,
    include_rendering: true,
  };
};

window.theseusPlanStudioChainGoal = async function theseusPlanStudioChainGoal(app) {
  if (!app.studio.chainGoal?.trim() || app.studio.chainPlanning) return;
  app.studio.chainPlanning = true;
  app.studio.chainPlanError = null;
  try {
    const response = await app.api("/api/ui/skill-chains/plan", {
      method: "POST",
      body: JSON.stringify(theseusStudioChainGoalPayload(app)),
    });
    app.studio.chainPlan = response.plan;
    app.toast("Chain planned: " + (response.plan?.spec?.name || "skill-chain"), "ok");
  } catch (error) {
    app.studio.chainPlan = null;
    app.studio.chainPlanError = error?.message || String(error);
    app.toast("Chain plan failed: " + app.studio.chainPlanError, "error");
  } finally {
    app.studio.chainPlanning = false;
    window.theseusAfterRender(app);
  }
};

window.theseusRunStudioChainGoal = async function theseusRunStudioChainGoal(app) {
  if (!app.studio.chainGoal?.trim() || app.studio.chainRunningGoal) return;
  app.studio.chainRunningGoal = true;
  app.studio.chainPlanError = null;
  try {
    const response = await app.api("/api/ui/skill-chains/invoke-planned", {
      method: "POST",
      body: JSON.stringify(theseusStudioChainGoalPayload(app)),
    });
    app.studio.chainPlan = response.plan;
    app.chains.current = response.chain;
    app.studio.chainTraceOpen = true;
    app.toast("Chain run saved: " + response.chain.chain_id, "ok");
    await app.loadStudio();
    if (app.chains.loaded) await app.loadChains();
  } catch (error) {
    app.studio.chainPlanError = error?.message || String(error);
    app.toast("Chain run failed: " + app.studio.chainPlanError, "error");
  } finally {
    app.studio.chainRunningGoal = false;
    window.theseusAfterRender(app);
  }
};

window.theseusStudioChainPlanSteps = function theseusStudioChainPlanSteps(app) {
  return app.studio.chainPlan?.spec?.steps || [];
};

window.theseusRerunChain = async function theseusRerunChain(app, chainId) {
  if (!chainId || app.chains.rerunning) return;
  app.chains.rerunning = chainId;
  try {
    const response = await app.api(
      "/api/ui/skill-chains/" + encodeURIComponent(chainId) + "/rerun",
      {
        method: "POST",
        body: JSON.stringify({}),
      },
    );
    app.chains.current = response.chain;
    app.toast("Chain rerun saved: " + response.chain.chain_id, "ok");
    await app.loadChains();
    if (app.studio?.loaded) await app.loadStudio();
  } catch (error) {
    app.toast("Chain rerun failed: " + (error?.message || error), "error");
  } finally {
    app.chains.rerunning = "";
    window.theseusAfterRender(app);
  }
};

window.theseusResumeChain = async function theseusResumeChain(app, chainId) {
  if (!chainId || app.chains.resuming) return;
  app.chains.resuming = chainId;
  try {
    let chain = app.chains.current?.chain_id === chainId ? app.chains.current : null;
    if (!chain) {
      chain = await app.api("/api/ui/skill-chains/" + encodeURIComponent(chainId));
      app.chains.current = chain;
    }
    const fromStepId = chain.resume_step_id || window.theseusChainResumeStepId(chain);
    const response = await app.api(
      "/api/ui/skill-chains/" + encodeURIComponent(chainId) + "/resume",
      {
        method: "POST",
        body: JSON.stringify({ from_step_id: fromStepId }),
      },
    );
    app.chains.current = response.chain;
    app.toast("Chain resumed: " + response.chain.chain_id, "ok");
    await app.loadChains();
    if (app.studio?.loaded) await app.loadStudio();
  } catch (error) {
    app.toast("Chain resume failed: " + (error?.message || error), "error");
  } finally {
    app.chains.resuming = "";
    window.theseusAfterRender(app);
  }
};

window.theseusOpenChainStepRun = async function theseusOpenChainStepRun(app, step) {
  if (!step?.skill || !step?.run_id) return;
  app.studio.chainTraceOpen = false;
  app.active = "skills";
  await app.openSkill(step.skill);
  await app.loadSkillRun(step.skill, step.run_id);
};
