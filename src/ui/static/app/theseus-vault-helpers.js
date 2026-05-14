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







// Vault KG Graph — D3 force-directed note relationship view
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

  } catch (err) {
    app.toast("Graph load failed: " + err.message, "error");
  } finally {
    app.vaultGraphLoading = false;
  }
};
