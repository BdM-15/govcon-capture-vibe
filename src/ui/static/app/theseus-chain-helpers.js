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

window.theseusOpenChain = async function theseusOpenChain(app, chainId) {
  if (!chainId) return;
  app.chains.loadingDetail = true;
  app.chains.error = null;
  try {
    const response = await app.api(
      "/api/ui/skill-chains/" + encodeURIComponent(chainId),
    );
    app.chains.current = response;
    app.active = "chains";
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
  return !!window.theseusChainResumeStepId(chain);
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
  const chain = app.chains.current?.chain_id === chainId ? app.chains.current : null;
  const fromStepId = window.theseusChainResumeStepId(chain);
  app.chains.resuming = chainId;
  try {
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
  await app.openSkill(step.skill);
  await app.loadSkillRun(step.skill, step.run_id);
};
