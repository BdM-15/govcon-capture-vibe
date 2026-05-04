window.theseusLoadWorkspaceList = async function theseusLoadWorkspaceList(
  app,
  silent = true,
) {
  try {
    const response = await app.api("/api/ui/workspaces");
    app.wsModal.items = response.workspaces || [];
  } catch (error) {
    if (!silent) {
      app.toast("Could not list workspaces: " + error.message, "error");
    }
  }
};

window.theseusOpenWorkspaceModal = async function theseusOpenWorkspaceModal(
  app,
) {
  app.wsModal.open = true;
  app.wsModal.newName = "";
  await app.loadWorkspaceList(false);
};

window.theseusPollRestart = function theseusPollRestart(app) {
  const target = app.restartTarget;
  const startedAt = Date.now();
  const maxWaitMs = 60_000;
  const tick = async () => {
    if (!app.restarting) return;
    if (Date.now() - startedAt > maxWaitMs) {
      app.restartStuck = true;
      return;
    }
    try {
      const response = await fetch("/api/ui/stats", { cache: "no-store" });
      if (response.ok) {
        const payload = await response.json();
        if (payload.workspace === target) {
          window.location.reload();
          return;
        }
      }
    } catch {}
    setTimeout(tick, 1000);
  };
  setTimeout(tick, 1500);
};

window.theseusSwitchWorkspace = async function theseusSwitchWorkspace(
  app,
  name,
  create = false,
) {
  if (!name || app.wsModal.switching) return;
  if (name === app.stats.workspace) {
    app.wsModal.open = false;
    return;
  }
  if (!confirm(`Switch to workspace "${name}"? The server will restart.`)) {
    return;
  }
  app.wsModal.switching = true;
  try {
    await app.api("/api/ui/workspaces/switch", {
      method: "POST",
      body: JSON.stringify({ name, create }),
    });
    app.wsModal.open = false;
    app.restartTarget = name;
    app.restartStuck = false;
    app.restarting = true;
    app.pollRestart();
  } catch (error) {
    app.toast("Switch failed: " + error.message, "error");
  } finally {
    app.wsModal.switching = false;
  }
};

window.theseusRestartServer = async function theseusRestartServer(app) {
  if (
    !confirm(
      "Restart the server now? Active uploads or in-flight queries will be interrupted.",
    )
  ) {
    return;
  }
  try {
    await app.api("/api/ui/restart", { method: "POST" });
    app.restartTarget = app.stats.workspace || "server";
    app.restartStuck = false;
    app.restarting = true;
    app.pollRestart();
  } catch (error) {
    app.toast("Restart failed: " + error.message, "error");
  }
};

window.theseusLoadWorkspaceInventory =
  async function theseusLoadWorkspaceInventory(app) {
    app.dangerZone.loading = true;
    try {
      const response = await app.api("/api/ui/workspaces/inventory");
      app.dangerZone.workspaces = response.workspaces || [];
      app.dangerZone.neo4jAvailable = !!response.neo4j_available;
      app.dangerZone.loaded = true;
      app.$nextTick(() => lucide.createIcons());
    } catch (error) {
      app.toast("Inventory failed: " + error.message, "error");
    } finally {
      app.dangerZone.loading = false;
    }
  };

window.theseusOpenDeleteModal = function theseusOpenDeleteModal(
  app,
  workspace,
) {
  if (workspace.is_active) {
    app.toast("Switch to another workspace before deleting this one.", "error");
    return;
  }
  app.deleteModal.target = workspace;
  app.deleteModal.scope = {
    neo4j: workspace.neo4j_nodes > 0,
    rag_storage: workspace.storage_mb !== null,
    inputs: false,
  };
  app.deleteModal.confirmText = "";
  app.deleteModal.busy = false;
  app.deleteModal.open = true;
  app.$nextTick(() => lucide.createIcons());
};

window.theseusCloseDeleteModal = function theseusCloseDeleteModal(app) {
  if (app.deleteModal.busy) return;
  app.deleteModal.open = false;
  app.deleteModal.target = null;
  app.deleteModal.confirmText = "";
};

window.theseusDeleteModalSelectAll = function theseusDeleteModalSelectAll(app) {
  const target = app.deleteModal.target;
  if (!target) return;
  app.deleteModal.scope = {
    neo4j: target.neo4j_nodes > 0,
    rag_storage: target.storage_mb !== null,
    inputs: target.inputs_files > 0 || target.inputs_mb > 0,
  };
};

window.theseusDeleteModalClearAll = function theseusDeleteModalClearAll(app) {
  app.deleteModal.scope = {
    neo4j: false,
    rag_storage: false,
    inputs: false,
  };
};

window.theseusCanSubmitDelete = function theseusCanSubmitDelete(app) {
  const modal = app.deleteModal;
  const anyScope =
    modal.scope.neo4j || modal.scope.rag_storage || modal.scope.inputs;
  const nameMatches =
    modal.target &&
    modal.confirmText === (modal.target.name || "").toUpperCase();
  return !!(anyScope && nameMatches);
};

window.theseusSubmitWorkspaceDelete =
  async function theseusSubmitWorkspaceDelete(app) {
    if (!window.theseusCanSubmitDelete(app) || app.deleteModal.busy) return;
    const target = app.deleteModal.target;
    app.deleteModal.busy = true;
    try {
      const response = await app.api(
        `/api/ui/workspaces/${encodeURIComponent(target.name)}/delete`,
        {
          method: "POST",
          body: JSON.stringify(app.deleteModal.scope),
        },
      );
      const parts = [];
      const deleted = response.deleted || {};
      if (deleted.neo4j_nodes != null) {
        parts.push(`${deleted.neo4j_nodes.toLocaleString()} Neo4j nodes`);
      }
      if (deleted.rag_storage) parts.push("rag_storage/");
      if (deleted.inputs_files)
        parts.push(`${deleted.inputs_files} input file(s)`);
      app.toast(
        `Deleted ${target.name}: ${parts.join(", ") || "(nothing)"}`,
        "success",
      );
      app.deleteModal.open = false;
      await app.loadWorkspaceInventory();
      await app.loadWorkspaceList(true);
    } catch (error) {
      app.toast("Delete failed: " + error.message, "error");
    } finally {
      app.deleteModal.busy = false;
    }
  };

window.theseusOpenWipeAllModal = function theseusOpenWipeAllModal(app) {
  app.wipeAllModal.scope = {
    neo4j: true,
    rag_storage: true,
    inputs: false,
  };
  app.wipeAllModal.confirmText = "";
  app.wipeAllModal.busy = false;
  app.wipeAllModal.open = true;
  app.$nextTick(() => lucide.createIcons());
};

window.theseusCloseWipeAllModal = function theseusCloseWipeAllModal(app) {
  if (app.wipeAllModal.busy) return;
  app.wipeAllModal.open = false;
  app.wipeAllModal.confirmText = "";
};

window.theseusCanSubmitWipeAll = function theseusCanSubmitWipeAll(app) {
  const modal = app.wipeAllModal;
  const anyScope =
    modal.scope.neo4j || modal.scope.rag_storage || modal.scope.inputs;
  return !!(anyScope && modal.confirmText === "DELETE ALL");
};

window.theseusSubmitWipeAll = async function theseusSubmitWipeAll(app) {
  if (!window.theseusCanSubmitWipeAll(app) || app.wipeAllModal.busy) return;
  app.wipeAllModal.busy = true;
  try {
    await app.api("/api/ui/workspaces/wipe-all", {
      method: "POST",
      body: JSON.stringify({
        ...app.wipeAllModal.scope,
        confirm: "DELETE ALL",
      }),
    });
    app.toast("Wipe complete. Restarting server…", "success");
    app.wipeAllModal.open = false;
    app.restartTarget = app.stats.workspace || "server";
    app.restartStuck = false;
    app.restarting = true;
    app.pollRestart();
  } catch (error) {
    app.toast("Wipe failed: " + error.message, "error");
  } finally {
    app.wipeAllModal.busy = false;
  }
};
