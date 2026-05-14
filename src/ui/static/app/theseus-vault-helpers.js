window.theseusLoadVaultNotes = async function theseusLoadVaultNotes(app) {
  app.vaultNotesLoading = true;
  try {
    const params = new URLSearchParams();
    if (app.vaultSearch) params.set("q", app.vaultSearch);
    if (app.vaultFilterStatus) params.set("status", app.vaultFilterStatus);
    if (app.vaultActiveTier) params.set("tier", app.vaultActiveTier);
    const qs = params.toString() ? "?" + params.toString() : "";
    const data = await app.api("/api/ui/vault/notes" + qs);
    app.vaultNotes = data.notes || [];
    app.vaultActiveTopic = ""; // reset topic selection on tier reload
  } catch (error) {
    app.toast("Failed to load vault notes: " + error.message, "error");
  } finally {
    app.vaultNotesLoading = false;
  }
};

window.theseusVaultSetTier = async function theseusVaultSetTier(app, tier) {
  app.vaultActiveTier = tier;
  await window.theseusLoadVaultNotes(app);
};

window.theseusVaultSelectNote = async function theseusVaultSelectNote(
  app,
  note,
) {
  try {
    // Fetch full note (includes body)
    const full = await app.api("/api/ui/vault/notes/" + note.id);
    app.vaultActiveNote = { ...full };
    app.vaultEditorMode = "editor";
  } catch (error) {
    app.toast("Failed to load note: " + error.message, "error");
  }
};

window.theseusVaultNewNote = async function theseusVaultNewNote(app) {
  try {
    const resp = await fetch("/api/ui/vault/notes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: "New Note",
        body: "",
        note_type: "raw",
        topic: "",
        source: "manual",
      }),
    });
    if (!resp.ok) throw new Error("Create failed");
    const note = await resp.json();
    app.vaultActiveNote = { ...note };
    app.vaultEditorMode = "editor";
    await window.theseusLoadVaultNotes(app);
  } catch (error) {
    app.toast("Failed to create note: " + error.message, "error");
  }
};

window.theseusVaultSaveNote = async function theseusVaultSaveNote(app) {
  if (!app.vaultActiveNote) return;
  try {
    const resp = await fetch("/api/ui/vault/notes/" + app.vaultActiveNote.id, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: app.vaultActiveNote.title,
        body: app.vaultActiveNote.body,
        note_type: app.vaultActiveNote.type,
        topic: app.vaultActiveNote.topic || "",
        source: app.vaultActiveNote.source || "manual",
        status: app.vaultActiveNote.status || "raw",
        pursuit: app.vaultActiveNote.pursuit || null,
        tags: app.vaultActiveNote.tags || [],
        tier: app.vaultActiveNote.tier || null,
      }),
    });
    if (!resp.ok) throw new Error("Save failed");
    const updated = await resp.json();
    app.vaultActiveNote = { ...updated };
    await window.theseusLoadVaultNotes(app);
  } catch (error) {
    app.toast("Auto-save failed: " + error.message, "error");
  }
};

window.theseusVaultScheduleSave = function theseusVaultScheduleSave(app) {
  if (app.vaultAutoSaveTimer) clearTimeout(app.vaultAutoSaveTimer);
  app.vaultAutoSaveTimer = setTimeout(
    () => window.theseusVaultSaveNote(app),
    2000,
  );
};

window.theseusDeleteVaultNote = async function theseusDeleteVaultNote(app, id) {
  try {
    const resp = await fetch("/api/ui/vault/notes/" + id, { method: "DELETE" });
    if (!resp.ok) throw new Error("Delete failed");
    await window.theseusLoadVaultNotes(app);
  } catch (error) {
    app.toast("Failed to delete note: " + error.message, "error");
  }
};

window.theseusPolishVaultNote = async function theseusPolishVaultNote(app, id) {
  try {
    const resp = await fetch("/api/ui/vault/notes/" + id + "/polish", {
      method: "POST",
    });
    if (resp.status === 503) {
      app.toast(
        "Polish requires Ollama — start Ollama and restart Theseus.",
        "error",
      );
      return;
    }
    if (!resp.ok) throw new Error("Polish failed");
    await window.theseusLoadVaultNotes(app);
    app.toast("Note polished", "success");
  } catch (error) {
    app.toast("Failed to polish note: " + error.message, "error");
  }
};

window.theseusVaultPromoteNote = async function theseusVaultPromoteNote(
  app,
  id,
) {
  try {
    const resp = await fetch("/api/ui/vault/notes/" + id + "/promote", {
      method: "POST",
    });
    if (!resp.ok) throw new Error("Promote failed");
    const updated = await resp.json();
    if (app.vaultActiveNote && app.vaultActiveNote.id === id) {
      app.vaultActiveNote = { ...updated };
    }
    await window.theseusLoadVaultNotes(app);
    app.toast("Note promoted to " + updated.status, "success");
  } catch (error) {
    app.toast("Failed to promote note: " + error.message, "error");
  }
};

window.theseusVaultAskTheseus = async function theseusVaultAskTheseus(app, id) {
  if (!id) return;
  app.vaultAskLoading = true;
  app.vaultAskAnswer = "";
  app.vaultAskSources = [];
  try {
    const resp = await fetch("/api/ui/vault/notes/" + id + "/ask-theseus", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        workspace: app.stats ? app.stats.workspace : null,
      }),
    });
    if (!resp.ok) throw new Error("Ask Theseus failed (" + resp.status + ")");
    const data = await resp.json();
    app.vaultAskAnswer = data.answer || "";
    app.vaultAskSources = data.sources || [];
  } catch (error) {
    app.toast("Ask Theseus error: " + error.message, "error");
  } finally {
    app.vaultAskLoading = false;
  }
};

window.theseusVaultSaveAsNote = async function theseusVaultSaveAsNote(app) {
  if (!app.vaultAskAnswer || !app.vaultActiveNote) return;
  try {
    const resp = await fetch(
      "/api/ui/vault/notes/" + app.vaultActiveNote.id + "/ask-theseus/save",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          answer: app.vaultAskAnswer,
          source_title: app.vaultActiveNote.title || "",
        }),
      },
    );
    if (!resp.ok) throw new Error("Save as Note failed (" + resp.status + ")");
    await window.theseusLoadVaultNotes(app);
    app.toast("Insight saved to vault", "success");
  } catch (error) {
    app.toast("Save as Note error: " + error.message, "error");
  }
};

window.theseusVaultLoadRecommendations =
  async function theseusVaultLoadRecommendations(app) {
    const workspace =
      app.stats && app.stats.workspace ? app.stats.workspace : null;
    if (!workspace) {
      app.vaultRecommendations = [];
      return;
    }
    app.vaultRecommendLoading = true;
    try {
      const data = await app.api(
        "/api/ui/vault/recommend?workspace=" +
          encodeURIComponent(workspace) +
          "&limit=5",
      );
      app.vaultRecommendations = data.recommendations || [];
    } catch (error) {
      app.toast("Failed to load recommendations: " + error.message, "error");
      app.vaultRecommendations = [];
    } finally {
      app.vaultRecommendLoading = false;
    }
  };

window.theseusVaultFeedToWorkspace = async function theseusVaultFeedToWorkspace(
  app,
  id,
) {
  const workspace =
    app.stats && app.stats.workspace ? app.stats.workspace : null;
  if (!workspace || !id) return;
  try {
    const resp = await fetch("/api/ui/vault/notes/" + id + "/feed", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workspace }),
    });
    if (!resp.ok) throw new Error("Feed failed (" + resp.status + ")");
    app.toast("Note fed to workspace", "success");
    await window.theseusVaultLoadRecommendations(app);
  } catch (error) {
    app.toast("Feed to workspace error: " + error.message, "error");
  }
};

/**
 * Preview polish for a vault note. Calls POST /polish without accept=true,
 * stores the diff result and opens the diff overlay.
 */
window.theseusVaultPreviewPolish = async function theseusVaultPreviewPolish(
  app,
  id,
) {
  if (!id) return;
  app.vaultPolishLoading = true;
  app.vaultDiffOpen = false;
  app.vaultDiffResult = null;
  try {
    const resp = await fetch("/api/ui/vault/notes/" + id + "/polish", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: app.vaultPolishModel || "qwen",
        accept: false,
      }),
    });
    if (!resp.ok)
      throw new Error("Polish preview failed (" + resp.status + ")");
    app.vaultDiffResult = await resp.json();
    app.vaultDiffOpen = true;
  } catch (error) {
    app.toast("Polish preview error: " + error.message, "error");
  } finally {
    app.vaultPolishLoading = false;
  }
};

/**
 * Accept the current polish diff and persist the rewritten body to the store.
 * Closes the diff overlay and refreshes the active note.
 */
window.theseusVaultAcceptPolish = async function theseusVaultAcceptPolish(
  app,
  id,
) {
  if (!id) return;
  app.vaultPolishLoading = true;
  try {
    const resp = await fetch("/api/ui/vault/notes/" + id + "/polish", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: app.vaultPolishModel || "qwen",
        accept: true,
      }),
    });
    if (!resp.ok) throw new Error("Accept polish failed (" + resp.status + ")");
    const updated = await resp.json();
    app.vaultDiffOpen = false;
    app.vaultDiffResult = null;
    app.vaultActiveNote = updated;
    app.toast("Note polished and saved", "success");
    if (window.theseusLoadVaultNotes) await window.theseusLoadVaultNotes(app);
  } catch (error) {
    app.toast("Accept polish error: " + error.message, "error");
  } finally {
    app.vaultPolishLoading = false;
  }
};

/**
 * Extract govcon entities from the active vault note.
 * Results are stored in app.vaultEntityProposals (each proposal has a _selected flag).
 */
window.theseusVaultExtractEntities = async function theseusVaultExtractEntities(
  app,
  id,
) {
  if (!id) return;
  app.vaultEntityLoading = true;
  app.vaultEntityProposals = [];
  try {
    const body =
      app.stats && app.stats.workspace
        ? JSON.stringify({ workspace: app.stats.workspace })
        : "{}";
    const resp = await fetch(
      "/api/ui/vault/notes/" + id + "/extract-entities",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
      },
    );
    if (!resp.ok)
      throw new Error("Entity extraction failed (" + resp.status + ")");
    const data = await resp.json();
    app.vaultEntityProposals = (data.proposals || []).map((p) => ({
      ...p,
      _selected: !p.already_in_kg,
    }));
  } catch (error) {
    app.toast("Entity extraction error: " + error.message, "error");
  } finally {
    app.vaultEntityLoading = false;
  }
};

/**
 * Commit selected entity proposals to the active workspace KG.
 * Requires an active workspace; disabled in UI if none is set.
 */
window.theseusVaultAcceptEntities = async function theseusVaultAcceptEntities(
  app,
  id,
) {
  if (!id) return;
  const workspace = app.stats && app.stats.workspace;
  if (!workspace) {
    app.toast("Select a workspace to commit entities", "warning");
    return;
  }
  const selected = (app.vaultEntityProposals || []).filter((p) => p._selected);
  if (!selected.length) {
    app.toast("No entities selected", "warning");
    return;
  }
  try {
    const resp = await fetch("/api/ui/vault/notes/" + id + "/accept-entities", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        workspace,
        proposals: selected.map(({ _selected, ...rest }) => rest),
      }),
    });
    if (!resp.ok)
      throw new Error("Accept entities failed (" + resp.status + ")");
    const data = await resp.json();
    app.toast(
      `${data.accepted} entit${data.accepted === 1 ? "y" : "ies"} committed to KG`,
      "success",
    );
    app.vaultEntityProposals = [];
  } catch (error) {
    app.toast("Accept entities error: " + error.message, "error");
  }
};

// ---------------------------------------------------------------------------
// Intel Feed — Zettelkasten swimlanes
// ---------------------------------------------------------------------------

/**
 * Load all vault notes into app.intelFeedNotes for the Intel Feed kanban.
 */
window.theseusIntelFeedLoad = async function theseusIntelFeedLoad(app) {
  app.intelFeedLoading = true;
  try {
    const resp = await fetch("/api/ui/vault/notes");
    if (!resp.ok) throw new Error("Failed to load notes (" + resp.status + ")");
    const data = await resp.json();
    app.intelFeedNotes = data.notes || [];
  } catch (e) {
    console.error("intel feed load failed", e);
    app.intelFeedNotes = [];
  } finally {
    app.intelFeedLoading = false;
  }
};

/**
 * Move a note to a new swimlane status (optimistic update + PUT persist).
 */
window.theseusIntelDrop = async function theseusIntelDrop(
  app,
  noteId,
  newStatus,
) {
  if (!noteId) return;
  const note = app.intelFeedNotes.find((n) => n.id === noteId);
  if (!note || note.status === newStatus) return;
  // Optimistic update
  note.status = newStatus;
  try {
    const resp = await fetch("/api/ui/vault/notes/" + noteId, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: newStatus }),
    });
    if (!resp.ok) throw new Error("status update failed (" + resp.status + ")");
    const updated = await resp.json();
    const idx = app.intelFeedNotes.findIndex((n) => n.id === noteId);
    if (idx !== -1) app.intelFeedNotes[idx] = updated;
  } catch (e) {
    app.toast("Failed to move note: " + e.message, "error");
    await window.theseusIntelFeedLoad(app); // revert
  }
};

/**
 * Bulk-polish all fleeting (raw) notes in sequence.
 * Sets per-note progress in intelBulkProgress: 'polishing' | 'done' | 'error'.
 */
window.theseusIntelBulkPolish = async function theseusIntelBulkPolish(app) {
  const rawNotes = app.intelFeedNotes.filter(
    (n) => (n.status || "raw") === "raw",
  );
  if (!rawNotes.length) return;
  app.intelBulkPolishing = true;
  app.intelBulkProgress = {};
  for (const note of rawNotes) {
    app.intelBulkProgress = {
      ...app.intelBulkProgress,
      [note.id]: "polishing",
    };
    try {
      const resp = await fetch("/api/ui/vault/notes/" + note.id + "/polish", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ accept: true }),
      });
      if (!resp.ok) throw new Error("polish failed (" + resp.status + ")");
      const updated = await resp.json();
      const idx = app.intelFeedNotes.findIndex((n) => n.id === note.id);
      if (idx !== -1) app.intelFeedNotes[idx] = updated;
      app.intelBulkProgress = { ...app.intelBulkProgress, [note.id]: "done" };
    } catch (e) {
      app.intelBulkProgress = { ...app.intelBulkProgress, [note.id]: "error" };
    }
  }
  app.intelBulkPolishing = false;
};

// ---------------------------------------------------------------------------
// Vault KG Graph — D3 force-directed note relationship view
// ---------------------------------------------------------------------------

const _VAULT_TIER_COLOR = {
  doctrine: "#00f0ff", // neon-cyan
  intelligence: "#ff2bd6", // neon-magenta
  pursuit: "#ffb020", // neon-amber
};

function _vaultNodeColor(node) {
  return _VAULT_TIER_COLOR[node.tier] || "#64748b";
}

window.theseusVaultLoadGraph = async function theseusVaultLoadGraph(app, tier) {
  app.vaultGraphLoading = true;
  const svgEl = document.getElementById("vault-graph-svg");
  if (!svgEl) {
    app.vaultGraphLoading = false;
    return;
  }

  // Clear previous render
  d3.select(svgEl).selectAll("*").remove();

  try {
    const qs = tier ? "?tier=" + encodeURIComponent(tier) : "";
    const data = await app.api("/api/ui/vault/graph" + qs);
    const nodes = (data.nodes || []).map((n) => ({ ...n }));
    const links = (data.links || []).map((l) => ({ ...l }));

    if (!nodes.length) {
      d3.select(svgEl)
        .append("text")
        .attr("x", svgEl.clientWidth / 2 || 400)
        .attr("y", 200)
        .attr("text-anchor", "middle")
        .attr("fill", "#64748b")
        .attr("font-size", "13px")
        .text("No notes in this tier yet");
      app.vaultGraphLoading = false;
      return;
    }

    const W = svgEl.clientWidth || 800;
    const H = svgEl.clientHeight || 500;

    const svg = d3
      .select(svgEl)
      .attr("viewBox", `0 0 ${W} ${H}`)
      .style("background", "transparent");

    // Zoom + pan
    const g = svg.append("g");
    svg.call(
      d3
        .zoom()
        .scaleExtent([0.3, 4])
        .on("zoom", (e) => g.attr("transform", e.transform)),
    );

    // Arrow marker
    svg
      .append("defs")
      .append("marker")
      .attr("id", "vault-arrow")
      .attr("viewBox", "0 -4 8 8")
      .attr("refX", 14)
      .attr("refY", 0)
      .attr("markerWidth", 6)
      .attr("markerHeight", 6)
      .attr("orient", "auto")
      .append("path")
      .attr("d", "M0,-4L8,0L0,4")
      .attr("fill", "#2c3a5e");

    const sim = d3
      .forceSimulation(nodes)
      .force(
        "link",
        d3
          .forceLink(links)
          .id((d) => d.id)
          .distance((d) => (d.kind === "topic" ? 60 : 100))
          .strength((d) => (d.kind === "topic" ? 0.8 : 0.4)),
      )
      .force("charge", d3.forceManyBody().strength(-180))
      .force("center", d3.forceCenter(W / 2, H / 2))
      .force("collision", d3.forceCollide(20));

    // Links
    const link = g
      .append("g")
      .selectAll("line")
      .data(links)
      .enter()
      .append("line")
      .attr("stroke", (d) =>
        d.kind === "wikilink" ? "rgba(0,240,255,0.4)" : "rgba(255,176,32,0.25)",
      )
      .attr("stroke-width", (d) => (d.kind === "wikilink" ? 1.5 : 0.8))
      .attr("stroke-dasharray", (d) => (d.kind === "topic" ? "3,3" : null))
      .attr("marker-end", "url(#vault-arrow)");

    // Node circles
    const nodeG = g
      .append("g")
      .selectAll("g")
      .data(nodes)
      .enter()
      .append("g")
      .attr("cursor", "pointer")
      .call(
        d3
          .drag()
          .on("start", (event, d) => {
            if (!event.active) sim.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
          })
          .on("drag", (event, d) => {
            d.fx = event.x;
            d.fy = event.y;
          })
          .on("end", (event, d) => {
            if (!event.active) sim.alphaTarget(0);
            d.fx = null;
            d.fy = null;
          }),
      )
      .on("click", (event, d) => {
        event.stopPropagation();
        app.vaultGraphHovered = d;
        // #157: when drawer is the host, focus the matching capture card.
        if (app.vaultGraphDrawerOpen && typeof window.theseusVaultFocusCaptureCard === "function") {
          window.theseusVaultFocusCaptureCard(app, d);
        }
      });

    nodeG
      .append("circle")
      .attr("r", (d) =>
        d.status === "evergreen" ? 9 : d.status === "polished" ? 7 : 5,
      )
      .attr("fill", (d) => _vaultNodeColor(d) + "33")
      .attr("stroke", (d) => _vaultNodeColor(d))
      .attr("stroke-width", 1.5);

    nodeG
      .append("text")
      .attr("dy", "0.32em")
      .attr("dx", 11)
      .attr("font-size", "10px")
      .attr("fill", "#94a3b8")
      .text((d) => (d.title || d.id).slice(0, 28));

    // Tick
    sim.on("tick", () => {
      link
        .attr("x1", (d) => d.source.x)
        .attr("y1", (d) => d.source.y)
        .attr("x2", (d) => d.target.x)
        .attr("y2", (d) => d.target.y);
      nodeG.attr("transform", (d) => `translate(${d.x},${d.y})`);
    });

    // Click canvas to deselect
    svg.on("click", () => {
      app.vaultGraphHovered = null;
    });
  } catch (err) {
    app.toast("Graph load failed: " + err.message, "error");
  } finally {
    app.vaultGraphLoading = false;
  }
};
