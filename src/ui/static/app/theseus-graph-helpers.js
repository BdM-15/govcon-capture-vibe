window.theseusSearchLabels = async function theseusSearchLabels(app) {
  const query = (app.graph.labelQuery || "").trim();
  if (!query) {
    app.graph.labelOptions = [];
    return;
  }
  try {
    const response = await fetch(
      `/graph/label/search?q=${encodeURIComponent(query)}&limit=30`,
    );
    if (!response.ok) return;
    const data = await response.json();
    app.graph.labelOptions = Array.isArray(data)
      ? data
      : data.labels || data.results || [];
  } catch {
    app.graph.labelOptions = [];
  }
};

const theseusGraphNodeType = function theseusGraphNodeType(node) {
  const props = node.properties || {};
  return (
    props.entity_type ||
    (node.labels && node.labels[0]) ||
    "concept"
  )
    .toString()
    .toLowerCase();
};

const theseusGraphElements = function theseusGraphElements(data) {
  const nodes = (data.nodes || []).map((node) => {
    const props = node.properties || {};
    return {
      data: {
        id: String(node.id),
        label: (props.entity_id || node.id).toString().replace(/^"|"$/g, ""),
        type: theseusGraphNodeType(node),
        description: props.description || "",
        raw: props,
        degree: 0,
      },
    };
  });

  const nodeIds = new Set(nodes.map((node) => node.data.id));
  const edges = (data.edges || [])
    .filter(
      (edge) =>
        nodeIds.has(String(edge.source)) && nodeIds.has(String(edge.target)),
    )
    .map((edge) => {
      const props = edge.properties || {};
      return {
        data: {
          id: String(edge.id),
          source: String(edge.source),
          target: String(edge.target),
          label: edge.type || props.keywords || "RELATED_TO",
          weight: parseFloat(props.weight ?? 1) || 1,
          confidence: parseFloat(props.confidence ?? 1) || 1,
          raw: props,
        },
      };
    });

  return { nodes, edges };
};

const theseusApplyGraphDegrees = function theseusApplyGraphDegrees(nodes, edges) {
  const degrees = {};
  edges.forEach((edge) => {
    degrees[edge.data.source] = (degrees[edge.data.source] || 0) + 1;
    degrees[edge.data.target] = (degrees[edge.data.target] || 0) + 1;
  });
  nodes.forEach((node) => {
    node.data.degree = degrees[node.data.id] || 0;
  });
};

const theseusGraphTypeCounts = function theseusGraphTypeCounts(nodes) {
  const counts = {};
  nodes.forEach((node) => {
    counts[node.data.type] = (counts[node.data.type] || 0) + 1;
  });
  return Object.entries(counts).sort((left, right) => right[1] - left[1]);
};

window.theseusLoadGraph = async function theseusLoadGraph(app) {
  const label = (app.graph.label || "*").trim() || "*";
  app.graph.loading = true;
  app.graph.selected = null;
  try {
    const isWildcard = !label || label === "*";
    const params = new URLSearchParams({
      max_nodes: String(app.graph.maxNodes),
    });
    if (!isWildcard) params.set("entity_type", label);
    const url = `/api/ui/graph?${params.toString()}`;
    const response = await fetch(url);
    if (!response.ok)
      throw new Error(`${response.status} ${response.statusText}`);
    const data = await response.json();

    const { nodes, edges } = theseusGraphElements(data);
    theseusApplyGraphDegrees(nodes, edges);
    app.graph.typeCounts = theseusGraphTypeCounts(nodes);
    app.graph.stats = {
      nodes: nodes.length,
      edges: edges.length,
      visibleNodes: nodes.length,
      visibleEdges: edges.length,
      truncated: !!data.is_truncated,
    };
    window.theseusRenderGraph(app, nodes, edges);
  } catch (error) {
    app.toast("Graph load failed: " + error.message, "error");
  } finally {
    app.graph.loading = false;
  }
};

window.theseusLoadGraphFromNode = function theseusLoadGraphFromNode(app, id) {
  app.graph.label = id;
  app.graph.labelQuery = id;
  app.loadGraph();
};

window.theseusRenderGraph = function theseusRenderGraph(app, nodes, edges) {
  const container = app.$refs.cy;
  if (!container) return;
  if (app.cy) {
    try {
      app.cy.destroy();
    } catch {}
    app.cy = null;
  }
  app.cy = cytoscape({
    container,
    elements: [...nodes, ...edges],
    wheelSensitivity: 0.3,
    style: [
      {
        selector: "node",
        style: {
          "background-color": (ele) =>
            window.theseusEntityColor(ele.data("type")),
          "border-color": "#0a0e1a",
          "border-width": 1.5,
          label: "data(label)",
          "font-size": 9,
          color: "#cbd5e1",
          "font-family": "JetBrains Mono, monospace",
          "text-valign": "bottom",
          "text-margin-y": 4,
          "text-outline-width": 2,
          "text-outline-color": "#05070d",
          width: (ele) =>
            Math.max(14, Math.min(46, 14 + (ele.data("degree") || 0) * 2)),
          height: (ele) =>
            Math.max(14, Math.min(46, 14 + (ele.data("degree") || 0) * 2)),
          "min-zoomed-font-size": 8,
        },
      },
      {
        selector: "node:selected",
        style: {
          "border-color": "#00f0ff",
          "border-width": 3,
          "overlay-color": "#00f0ff",
          "overlay-opacity": 0.15,
        },
      },
      {
        selector: "edge",
        style: {
          "curve-style": "bezier",
          width: (ele) => Math.max(0.6, Math.min(3, ele.data("weight") || 1)),
          "line-color": "#2c3a5e",
          "target-arrow-color": "#2c3a5e",
          "target-arrow-shape": "triangle",
          "arrow-scale": 0.8,
          opacity: 0.55,
          label: "data(label)",
          "font-size": 7,
          color: "#64748b",
          "font-family": "JetBrains Mono, monospace",
          "text-rotation": "autorotate",
          "text-background-color": "#05070d",
          "text-background-opacity": 0.7,
          "text-background-padding": 1,
          "min-zoomed-font-size": 9,
        },
      },
      {
        selector: "edge:selected",
        style: {
          "line-color": "#ff2bd6",
          "target-arrow-color": "#ff2bd6",
          opacity: 1,
          width: 2.5,
        },
      },
      { selector: ".dimmed", style: { opacity: 0.08 } },
      { selector: ".highlight", style: { opacity: 1 } },
    ],
    layout: window.theseusGraphLayoutOptions(app),
  });

  app.cy.on("tap", "node", (evt) =>
    window.theseusSelectGraphNode(app, evt.target),
  );
  app.cy.on("tap", (evt) => {
    if (evt.target === app.cy) {
      app.graph.selected = null;
      app.cy.elements().removeClass("dimmed highlight");
    }
  });
  window.theseusApplyGraphFilters(app);
};

window.theseusGraphLayoutOptions = function theseusGraphLayoutOptions(app) {
  const base = { animate: false, fit: true, padding: 30 };
  if (app.graph.layout === "fcose") {
    return {
      name: "fcose",
      quality: "default",
      randomize: true,
      nodeRepulsion: 4500,
      idealEdgeLength: 80,
      ...base,
    };
  }
  if (app.graph.layout === "concentric") {
    return {
      name: "concentric",
      concentric: (node) => node.degree(),
      levelWidth: () => 2,
      ...base,
    };
  }
  return { name: app.graph.layout, ...base };
};

window.theseusRelayoutGraph = function theseusRelayoutGraph(app) {
  if (!app.cy) return;
  app.cy.layout(window.theseusGraphLayoutOptions(app)).run();
};

window.theseusFitGraph = function theseusFitGraph(app) {
  if (app.cy) app.cy.fit(undefined, 30);
};

window.theseusExportGraphPng = function theseusExportGraphPng(app) {
  if (!app.cy) return;
  const png = app.cy.png({ full: true, scale: 2, bg: "#05070d" });
  const anchor = document.createElement("a");
  anchor.href = png;
  anchor.download = `theseus-graph-${Date.now()}.png`;
  anchor.click();
};

window.theseusToggleGraphTypeFilter = function theseusToggleGraphTypeFilter(
  app,
  type,
) {
  const idx = app.graph.hiddenTypes.indexOf(type);
  if (idx >= 0) app.graph.hiddenTypes.splice(idx, 1);
  else app.graph.hiddenTypes.push(type);
  window.theseusApplyGraphFilters(app);
};

window.theseusApplyGraphFilters = function theseusApplyGraphFilters(app) {
  if (!app.cy) return;
  const hidden = new Set(app.graph.hiddenTypes);
  const minConfidence = app.graph.minConfidence;
  let visibleNodes = 0;
  let visibleEdges = 0;
  app.cy.batch(() => {
    app.cy.nodes().forEach((node) => {
      const show = !hidden.has(node.data("type"));
      node.style("display", show ? "element" : "none");
      if (show) visibleNodes++;
    });
    app.cy.edges().forEach((edge) => {
      const srcOk = edge.source().style("display") !== "none";
      const tgtOk = edge.target().style("display") !== "none";
      const confOk = (edge.data("confidence") ?? 1) >= minConfidence;
      const show = srcOk && tgtOk && confOk;
      edge.style("display", show ? "element" : "none");
      if (show) visibleEdges++;
    });
  });
  app.graph.stats.visibleNodes = visibleNodes;
  app.graph.stats.visibleEdges = visibleEdges;
};

window.theseusSelectGraphNode = async function theseusSelectGraphNode(
  app,
  node,
) {
  const data = node.data();
  const skip = new Set(["id", "label", "type", "description", "raw", "degree"]);
  const props = Object.entries(data.raw || {}).filter(
    ([key]) => !skip.has(key),
  );
  props.unshift(["degree", String(data.degree)]);
  app.graph.selected = {
    id: data.label,
    type: data.type,
    description: data.description,
  };
  app.graph.selectedProps = props.map(([key, value]) => [
    key,
    typeof value === "string" ? value : JSON.stringify(value),
  ]);

  app.cy.elements().addClass("dimmed").removeClass("highlight");
  const hood = node.closedNeighborhood();
  hood.removeClass("dimmed").addClass("highlight");

  app.graph.chunksLoading = true;
  app.graph.chunks = [];
  try {
    const response = await app.api(
      `/api/ui/entity/${encodeURIComponent(data.label)}/chunks?limit=5`,
    );
    app.graph.chunks = response.chunks || [];
  } catch {
  } finally {
    app.graph.chunksLoading = false;
  }
};

window.theseusAskAboutEntity = function theseusAskAboutEntity(app, entity) {
  window.theseusStartChatWithComposer(
    app,
    `Tell me everything about "${entity.id}" (${entity.type}). Cite source chunks.`,
    entity.id,
  );
};
