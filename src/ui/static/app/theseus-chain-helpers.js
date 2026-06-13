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
    if (typeof app.chains.resumeDrafts?.[chainId] !== "string") {
      app.chains.resumeDrafts[chainId] = "";
    }
    if (response.status === "running") {
      window.theseusStartChainEventsPoll(app, chainId);
    } else {
      window.theseusStopChainEventsPoll(app);
      await window.theseusLoadChainEvents(app, chainId);
    }
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
  if (status === "completed")
    return "text-neon-lime border-neon-lime/40 bg-neon-lime/10";
  if (status === "partial")
    return "text-neon-amber border-neon-amber/40 bg-neon-amber/10";
  if (status === "running")
    return "text-neon-cyan border-neon-cyan/40 bg-neon-cyan/10";
  if (status === "failed")
    return "text-neon-red border-neon-red/40 bg-neon-red/10";
  if (status === "skipped")
    return "text-neon-amber border-neon-amber/40 bg-neon-amber/10";
  return "text-slate-400 border-edge bg-ink-800";
};

window.theseusChainArtifactCount = function theseusChainArtifactCount(chain) {
  return window
    .theseusChainSteps(chain)
    .reduce((total, step) => total + ((step.artifacts || []).length || 0), 0);
};

window.theseusChainResumeStepId = function theseusChainResumeStepId(chain) {
  const projected = (chain?.resume_step_id || "").trim();
  if (projected) return projected;
  const request = chain?.input_request || null;
  const requested = (request?.resume_step_id || request?.step_id || "").trim();
  if (requested) return requested;
  const step = window
    .theseusChainSteps(chain)
    .find((item) =>
      ["failed", "partial", "skipped", "pending", "running"].includes(
        item.status,
      ),
    );
  return step?.id || "";
};

window.theseusChainCanResume = function theseusChainCanResume(chain) {
  if (!chain || chain.status === "running" || chain.status === "completed")
    return false;
  if (typeof chain.can_resume === "boolean") return chain.can_resume;
  return !!window.theseusChainResumeStepId(chain);
};

window.theseusChainInputRequest = function theseusChainInputRequest(chain) {
  const request = chain?.input_request;
  return request && request.needed ? request : null;
};

window.theseusChainResumePlaceholder = function theseusChainResumePlaceholder(
  chain,
) {
  const request = window.theseusChainInputRequest(chain);
  const missing = (request?.missing_inputs || []).join("\n- ");
  if (!missing) {
    return "Add the missing facts you now have, then click Resume.";
  }
  return "Provide the missing facts to unblock this chain:\n- " + missing;
};

window.theseusMountChainInputPanel = function theseusMountChainInputPanel(
  app,
  host,
) {
  if (!host || host.dataset.chainInputMounted === "true") return;
  const template = document.getElementById(
    "chain-input-request-panel-template",
  );
  if (!template?.content) return;
  host.replaceChildren(template.content.cloneNode(true));
  host.dataset.chainInputMounted = "true";
  if (window.Alpine?.initTree) {
    window.Alpine.initTree(host);
  }
  if (window.lucide?.createIcons) {
    window.lucide.createIcons();
  }
  window.theseusAfterRender(app);
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

window.theseusCloseStudioChainTrace = function theseusCloseStudioChainTrace(
  app,
) {
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
  await window.theseusOpenChain(app, chain.chain_id, { activate: false });
  await window.theseusResumeChain(app, chain.chain_id);
};

const theseusStudioChainGoalPayload = function theseusStudioChainGoalPayload(
  app,
) {
  return {
    prompt: app.studio.chainGoal || "",
    outcome: app.studio.chainOutcome || "",
    max_steps: 8,
    include_rendering: true,
  };
};

window.theseusPlanStudioChainGoal = async function theseusPlanStudioChainGoal(
  app,
) {
  if (!app.studio.chainGoal?.trim() || app.studio.chainPlanning) return;
  app.studio.chainPlanning = true;
  app.studio.chainPlanError = null;
  try {
    const response = await app.api("/api/ui/skill-chains/plan", {
      method: "POST",
      body: JSON.stringify(theseusStudioChainGoalPayload(app)),
    });
    app.studio.chainPlan = response.plan;
    app.toast(
      "Chain planned: " + (response.plan?.spec?.name || "skill-chain"),
      "ok",
    );
  } catch (error) {
    app.studio.chainPlan = null;
    app.studio.chainPlanError = error?.message || String(error);
    app.toast("Chain plan failed: " + app.studio.chainPlanError, "error");
  } finally {
    app.studio.chainPlanning = false;
    window.theseusAfterRender(app);
  }
};

window.theseusRunStudioChainGoal = async function theseusRunStudioChainGoal(
  app,
) {
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
    let chain =
      app.chains.current?.chain_id === chainId ? app.chains.current : null;
    if (!chain) {
      chain = await app.api(
        "/api/ui/skill-chains/" + encodeURIComponent(chainId),
      );
      app.chains.current = chain;
    }
    const fromStepId =
      chain.resume_step_id || window.theseusChainResumeStepId(chain);
    const resumeNotes = (app.chains.resumeDrafts?.[chainId] || "").trim();
    if (window.theseusChainInputRequest(chain) && !resumeNotes) {
      app.toast(
        "Reply in the Missing Input composer, then click Resume.",
        "info",
      );
      return;
    }
    const response = await app.api(
      "/api/ui/skill-chains/" + encodeURIComponent(chainId) + "/resume",
      {
        method: "POST",
        body: JSON.stringify({
          from_step_id: fromStepId,
          user_addendum: resumeNotes,
        }),
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

window.theseusOpenChainStepRun = async function theseusOpenChainStepRun(
  app,
  step,
) {
  if (!step?.skill || !step?.run_id) return;
  app.studio.chainTraceOpen = false;
  app.active = "skills";
  await app.openSkill(step.skill);
  await app.loadSkillRun(step.skill, step.run_id);
};

window.theseusLoadPipelineLibrary = async function theseusLoadPipelineLibrary(
  app,
) {
  try {
    const response = await app.api("/api/ui/pipelines/library");
    app.chains.pipelines = response.pipelines || [];
    app.chains.studioUrl =
      response.studio_graph_url || response.studio_url || "";
    app.chains.pipelinesLoaded = true;
    app.chains.pipelinesError = response.studio_ready
      ? null
      : "LangGraph Studio is starting or unavailable — restart Theseus if this persists.";
  } catch (error) {
    app.chains.pipelinesError =
      "Pipeline library load failed: " + (error?.message || error);
    app.chains.pipelines = [];
  } finally {
    window.theseusAfterRender(app);
  }
};

window.theseusLoadChainEvents = async function theseusLoadChainEvents(
  app,
  chainId,
) {
  if (!chainId) return;
  try {
    const response = await app.api(
      "/api/ui/skill-chains/" + encodeURIComponent(chainId) + "/events?tail=120",
    );
    app.chains.events = response.events || [];
  } catch (_error) {
    app.chains.events = [];
  } finally {
    window.theseusAfterRender(app);
  }
};

window.theseusStartChainEventsPoll = function theseusStartChainEventsPoll(
  app,
  chainId,
) {
  window.theseusStopChainEventsPoll(app);
  if (!chainId) return;
  window.theseusLoadChainEvents(app, chainId);
  app.chains.eventsPolling = setInterval(() => {
    window.theseusLoadChainEvents(app, chainId);
  }, 2500);
};

window.theseusStopChainEventsPoll = function theseusStopChainEventsPoll(app) {
  if (app.chains.eventsPolling) {
    clearInterval(app.chains.eventsPolling);
    app.chains.eventsPolling = null;
  }
};

window.theseusChainEventClass = function theseusChainEventClass(event) {
  const status = String(event?.status || "").toLowerCase();
  if (status === "completed" || status === "running") {
    return status === "completed"
      ? "text-neon-lime border-neon-lime/30"
      : "text-neon-cyan border-neon-cyan/30";
  }
  if (status === "failed" || status === "partial") {
    return status === "failed"
      ? "text-neon-red border-neon-red/30"
      : "text-neon-amber border-neon-amber/30";
  }
  return "text-slate-400 border-edge";
};
