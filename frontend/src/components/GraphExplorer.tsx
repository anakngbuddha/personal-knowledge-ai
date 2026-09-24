import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  catalogApi,
  type GraphNode,
  type GraphLink,
  type PortfolioGraphOut,
  type GraphQueryOut,
  type IntegrityReportOut,
  type CoverageReportOut,
  type ProductEdgeOut,
  type NeighborhoodOut,
} from "../services/catalog";

/* ── Colour Palette ──────────────────────────────────────────────────── */
const EDGE_COLORS: Record<string, string> = {
  requires: "#d4a056",
  integrates_with: "#4f8a62",
  conflicts_with: "#d64532",
  replaces: "#c4b89d",
  bundles_with: "#8a8170",
  alternative_to: "#7a9e8a",
  migrates_to: "#c47a3a",
};

const OWNERSHIP_COLORS: Record<string, string> = {
  own: "#c9a227",
  resold: "#4f8a62",
};

/* ── Force-simulation helpers ────────────────────────────────────────── */
interface SimNode extends GraphNode {
  x: number;
  y: number;
  vx: number;
  vy: number;
  fx: number | null;
  fy: number | null;
}

function initSim(nodes: GraphNode[], width: number, height: number): SimNode[] {
  return nodes.map((n, i) => ({
    ...n,
    x: width / 2 + (Math.random() - 0.5) * width * 0.6,
    y: height / 2 + (Math.random() - 0.5) * height * 0.6,
    vx: 0,
    vy: 0,
    fx: null,
    fy: null,
  }));
}

function tick(
  simNodes: SimNode[],
  edges: GraphLink[],
  width: number,
  height: number,
  alpha: number
): void {
  const idxById: Record<string, number> = {};
  simNodes.forEach((n, i) => (idxById[n.id] = i));

  // Center gravity
  for (const n of simNodes) {
    n.vx += (width / 2 - n.x) * 0.002 * alpha;
    n.vy += (height / 2 - n.y) * 0.002 * alpha;
  }

  // Repulsion (O(n²) – fine for ≤50 nodes)
  for (let i = 0; i < simNodes.length; i++) {
    for (let j = i + 1; j < simNodes.length; j++) {
      let dx = simNodes[j].x - simNodes[i].x;
      let dy = simNodes[j].y - simNodes[i].y;
      let d2 = dx * dx + dy * dy;
      if (d2 < 1) d2 = 1;
      const force = (800 * alpha) / d2;
      const fx = dx * force;
      const fy = dy * force;
      simNodes[i].vx -= fx;
      simNodes[i].vy -= fy;
      simNodes[j].vx += fx;
      simNodes[j].vy += fy;
    }
  }

  // Edge attraction
  for (const e of edges) {
    const si = idxById[e.source];
    const ti = idxById[e.target];
    if (si === undefined || ti === undefined) continue;
    const s = simNodes[si];
    const t = simNodes[ti];
    const dx = t.x - s.x;
    const dy = t.y - s.y;
    const d = Math.sqrt(dx * dx + dy * dy) || 1;
    const targetDist = 140;
    const force = ((d - targetDist) / d) * 0.03 * alpha;
    const fx = dx * force;
    const fy = dy * force;
    s.vx += fx;
    s.vy += fy;
    t.vx -= fx;
    t.vy -= fy;
  }

  // Integrate + dampen + boundary clamp
  for (const n of simNodes) {
    if (n.fx !== null) {
      n.x = n.fx;
      n.vx = 0;
    } else {
      n.vx *= 0.6;
      n.x += n.vx;
    }
    if (n.fy !== null) {
      n.y = n.fy;
      n.vy = 0;
    } else {
      n.vy *= 0.6;
      n.y += n.vy;
    }
    n.x = Math.max(40, Math.min(width - 40, n.x));
    n.y = Math.max(40, Math.min(height - 40, n.y));
  }
}

/* ── Component ───────────────────────────────────────────────────────── */
export function GraphExplorer() {
  /* Shared state */
  const [graph, setGraph] = useState<PortfolioGraphOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  /* Filters */
  const [vendorFilter, setVendorFilter] = useState("");
  const [ownershipFilter, setOwnershipFilter] = useState("");
  const [edgeTypeFilter, setEdgeTypeFilter] = useState<Set<string>>(new Set());

  /* Selection & detail */
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [neighborhood, setNeighborhood] = useState<NeighborhoodOut | null>(null);
  const [impactResult, setImpactResult] = useState<GraphQueryOut | null>(null);

  /* Modals */
  const [integrity, setIntegrity] = useState<IntegrityReportOut | null>(null);
  const [coverage, setCoverage] = useState<CoverageReportOut | null>(null);
  const [showHealth, setShowHealth] = useState(false);

  /* Curation */
  const [pendingEdges, setPendingEdges] = useState<ProductEdgeOut[]>([]);
  const [showCuration, setShowCuration] = useState(false);
  const [autoGraphNote, setAutoGraphNote] = useState<string | null>(null);
  const [autoGraphBusy, setAutoGraphBusy] = useState(false);

  /* Canvas */
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const simNodesRef = useRef<SimNode[]>([]);
  const animRef = useRef<number>(0);
  const alphaRef = useRef(1);
  const draggingRef = useRef<number | null>(null);
  const panRef = useRef({ x: 0, y: 0, startX: 0, startY: 0, panning: false });
  const zoomRef = useRef(1);

  /* ── Fetch ─────────────────────────────────────────────────────────── */
  const fetchGraph = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await catalogApi.getPortfolioGraph();
      setGraph(data);
    } catch (e: any) {
      setError(e.message ?? "Failed to load graph");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchGraph();
  }, [fetchGraph]);

  /* ── Load pending edges ────────────────────────────────────────────── */
  const loadPending = useCallback(async () => {
    try {
      const edges = await catalogApi.listEdges({ status: "pending_review" });
      setPendingEdges(edges);
    } catch {
      /* swallow */
    }
  }, []);

  useEffect(() => {
    loadPending();
  }, [loadPending]);

  /* ── Filtered graph ────────────────────────────────────────────────── */
  const filtered = useMemo(() => {
    if (!graph) return { nodes: [], edges: [] };
    let nodes = graph.nodes;
    if (vendorFilter) nodes = nodes.filter((n) => n.vendor === vendorFilter);
    if (ownershipFilter) nodes = nodes.filter((n) => n.ownership === ownershipFilter);
    const nodeIds = new Set(nodes.map((n) => n.id));
    let edges = graph.edges.filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target));
    if (edgeTypeFilter.size > 0) edges = edges.filter((e) => edgeTypeFilter.has(e.relation_type));
    return { nodes, edges };
  }, [graph, vendorFilter, ownershipFilter, edgeTypeFilter]);

  /* ── Canvas simulation ─────────────────────────────────────────────── */
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || filtered.nodes.length === 0) return;
    const W = canvas.width;
    const H = canvas.height;
    simNodesRef.current = initSim(filtered.nodes, W, H);
    alphaRef.current = 1;

    const ctx = canvas.getContext("2d")!;

    function draw() {
      const sim = simNodesRef.current;
      if (alphaRef.current > 0.005) {
        tick(sim, filtered.edges, W, H, alphaRef.current);
        alphaRef.current *= 0.992;
      }

      const z = zoomRef.current;
      const px = panRef.current.x;
      const py = panRef.current.y;
      ctx.save();
      ctx.fillStyle = "#0c0a07";
      ctx.fillRect(0, 0, W, H);
      ctx.translate(px, py);
      ctx.scale(z, z);

      // Edges
      const idxById: Record<string, number> = {};
      sim.forEach((n, i) => (idxById[n.id] = i));
      for (const e of filtered.edges) {
        const si = idxById[e.source];
        const ti = idxById[e.target];
        if (si === undefined || ti === undefined) continue;
        const s = sim[si];
        const t = sim[ti];
        ctx.beginPath();
        ctx.moveTo(s.x, s.y);
        ctx.lineTo(t.x, t.y);
        ctx.strokeStyle = EDGE_COLORS[e.relation_type] ?? "#555";
        ctx.globalAlpha = e.status === "approved" ? 0.6 : 0.25;
        if (e.relation_type === "conflicts_with") ctx.setLineDash([6, 4]);
        else ctx.setLineDash([]);
        ctx.lineWidth = 1.5;
        ctx.stroke();
        ctx.globalAlpha = 1;
        ctx.setLineDash([]);

        // Arrow
        const angle = Math.atan2(t.y - s.y, t.x - s.x);
        const arrLen = 8;
        const mx = (s.x + t.x) / 2;
        const my = (s.y + t.y) / 2;
        ctx.beginPath();
        ctx.moveTo(mx, my);
        ctx.lineTo(mx - arrLen * Math.cos(angle - 0.4), my - arrLen * Math.sin(angle - 0.4));
        ctx.moveTo(mx, my);
        ctx.lineTo(mx - arrLen * Math.cos(angle + 0.4), my - arrLen * Math.sin(angle + 0.4));
        ctx.strokeStyle = EDGE_COLORS[e.relation_type] ?? "#555";
        ctx.lineWidth = 1.2;
        ctx.stroke();
      }

      // Nodes — square stamps, not bubbles
      for (const n of sim) {
        const isSelected = n.id === selectedNodeId;
        const radius = isSelected ? 16 : 11;
        const color = OWNERSHIP_COLORS[n.ownership] ?? "#c9a227";

        if (isSelected) {
          ctx.strokeStyle = "#ece4d4";
          ctx.lineWidth = 1;
          ctx.strokeRect(n.x - radius - 4, n.y - radius - 4, (radius + 4) * 2, (radius + 4) * 2);
        }

        ctx.fillStyle = color;
        ctx.fillRect(n.x - radius, n.y - radius, radius * 2, radius * 2);
        ctx.strokeStyle = isSelected ? "#ece4d4" : "#0e0c09";
        ctx.lineWidth = 1;
        ctx.strokeRect(n.x - radius, n.y - radius, radius * 2, radius * 2);

        ctx.fillStyle = "#ece4d4";
        ctx.font = `${isSelected ? "500 " : "400 "}${isSelected ? 11 : 9}px "IBM Plex Mono", ui-monospace, monospace`;
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        const label = n.name.length > 18 ? n.name.slice(0, 16) + "…" : n.name;
        ctx.fillText(label, n.x, n.y + radius + 5);

        if (n.ownership === "resold") {
          ctx.fillStyle = "#0e0c09";
          const bw = 36;
          const bh = 11;
          ctx.fillRect(n.x - bw / 2, n.y - radius - 14, bw, bh);
          ctx.strokeStyle = "#4f8a62";
          ctx.strokeRect(n.x - bw / 2, n.y - radius - 14, bw, bh);
          ctx.fillStyle = "#4f8a62";
          ctx.font = "500 8px \"IBM Plex Mono\", ui-monospace, monospace";
          ctx.textBaseline = "middle";
          ctx.fillText("RESOLD", n.x, n.y - radius - 8);
        }
      }

      ctx.restore();
      animRef.current = requestAnimationFrame(draw);
    }

    animRef.current = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(animRef.current);
  }, [filtered, selectedNodeId]);

  /* ── Mouse events ──────────────────────────────────────────────────── */
  const handleCanvasMouseDown = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      const z = zoomRef.current;
      const mx = (e.clientX - rect.left - panRef.current.x) / z;
      const my = (e.clientY - rect.top - panRef.current.y) / z;

      // Check node hit
      for (let i = 0; i < simNodesRef.current.length; i++) {
        const n = simNodesRef.current[i];
        const dx = n.x - mx;
        const dy = n.y - my;
        if (dx * dx + dy * dy < 20 * 20) {
          draggingRef.current = i;
          n.fx = n.x;
          n.fy = n.y;
          alphaRef.current = 0.3;
          return;
        }
      }
      // Pan
      panRef.current.panning = true;
      panRef.current.startX = e.clientX - panRef.current.x;
      panRef.current.startY = e.clientY - panRef.current.y;
    },
    []
  );

  const handleCanvasMouseMove = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      if (draggingRef.current !== null) {
        const canvas = canvasRef.current!;
        const rect = canvas.getBoundingClientRect();
        const z = zoomRef.current;
        const n = simNodesRef.current[draggingRef.current];
        n.fx = (e.clientX - rect.left - panRef.current.x) / z;
        n.fy = (e.clientY - rect.top - panRef.current.y) / z;
      } else if (panRef.current.panning) {
        panRef.current.x = e.clientX - panRef.current.startX;
        panRef.current.y = e.clientY - panRef.current.startY;
      }
    },
    []
  );

  const handleCanvasMouseUp = useCallback(() => {
    if (draggingRef.current !== null) {
      const n = simNodesRef.current[draggingRef.current];
      setSelectedNodeId(n.id);
      n.fx = null;
      n.fy = null;
      draggingRef.current = null;
    }
    panRef.current.panning = false;
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      zoomRef.current = Math.max(0.3, Math.min(3, zoomRef.current - event.deltaY * 0.001));
    };
    canvas.addEventListener("wheel", onWheel, { passive: false });
    return () => canvas.removeEventListener("wheel", onWheel);
  }, [loading, error]);

  /* ── Fetch detail on select ────────────────────────────────────────── */
  useEffect(() => {
    if (!selectedNodeId) {
      setNeighborhood(null);
      setImpactResult(null);
      return;
    }
    catalogApi.getNeighborhood(selectedNodeId).then(setNeighborhood).catch(() => {});
  }, [selectedNodeId]);

  /* ── Health check ──────────────────────────────────────────────────── */
  const runHealthCheck = useCallback(async () => {
    setShowHealth(true);
    try {
      const [integ, cov] = await Promise.all([catalogApi.getIntegrity(), catalogApi.getCoverage()]);
      setIntegrity(integ);
      setCoverage(cov);
    } catch {
      /* swallow */
    }
  }, []);

  /* ── Impact query ──────────────────────────────────────────────────── */
  const runImpactQuery = useCallback(async (productId: string) => {
    try {
      const res = await catalogApi.queryImpact(productId);
      setImpactResult(res);
    } catch {
      /* swallow */
    }
  }, []);

  /* ── Curation actions ──────────────────────────────────────────────── */
  const approveEdge = useCallback(
    async (id: string) => {
      try {
        await catalogApi.approveEdge(id);
        setPendingEdges((prev) => prev.filter((e) => e.id !== id));
        fetchGraph();
      } catch {
        /* swallow */
      }
    },
    [fetchGraph]
  );

  const rejectEdge = useCallback(async (id: string) => {
    const reason = window.prompt("Rejection reason:");
    if (!reason) return;
    try {
      await catalogApi.rejectEdge(id, reason);
      setPendingEdges((prev) => prev.filter((e) => e.id !== id));
    } catch {
      /* swallow */
    }
  }, []);

  const triggerSuggest = useCallback(async () => {
    try {
      const newEdges = await catalogApi.suggestEdges();
      setPendingEdges((prev) => [...prev, ...newEdges]);
    } catch {
      /* swallow */
    }
  }, []);

  const triggerAutoGraph = useCallback(async () => {
    setAutoGraphBusy(true);
    setAutoGraphNote(null);
    try {
      const result = await catalogApi.autoGraph();
      const waiting = result.edges.filter((edge) => edge.status === "pending_review");
      setPendingEdges((prev) => {
        const seen = new Set(prev.map((edge) => edge.id));
        return [...prev, ...waiting.filter((edge) => !seen.has(edge.id))];
      });
      setShowCuration(true);
      setAutoGraphNote(
        result.proposed === 0
          ? "No new relationships. The list needs at least two products, or these pairs are already on the map."
          : `Proposed ${result.proposed} relationship${result.proposed === 1 ? "" : "s"}. Review them before they guide a sale.`
      );
      await fetchGraph();
      await loadPending();
    } catch (e: unknown) {
      setAutoGraphNote(e instanceof Error ? e.message : "Auto-graph failed.");
    } finally {
      setAutoGraphBusy(false);
    }
  }, [fetchGraph, loadPending]);

  /* ── Edge toggle ────────────────────────────────────────────────────── */
  const toggleEdgeType = (type: string) => {
    setEdgeTypeFilter((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  };

  /* ── Render ─────────────────────────────────────────────────────────── */
  if (loading) {
    return (
      <div className="graph-loading">
        <div className="graph-spinner" />
        <p>Loading your map…</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="graph-error">
        <div className="empty-desk">
          <h3>The map could not be loaded.</h3>
          <p>{error}</p>
        </div>
        <button className="primary" onClick={fetchGraph}>
          Retry
        </button>
      </div>
    );
  }

  const selectedNode = graph?.nodes.find((n) => n.id === selectedNodeId);

  return (
    <div className="graph-explorer">
      {/* ── Toolbar ──────────────────────────────────────────────────── */}
      <div className="graph-toolbar">
        <div className="toolbar-filters">
          <select value={vendorFilter} onChange={(e) => setVendorFilter(e.target.value)}>
            <option value="">All Vendors</option>
            {graph?.vendors.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>

          <select value={ownershipFilter} onChange={(e) => setOwnershipFilter(e.target.value)}>
            <option value="">All Ownership</option>
            <option value="own">Own Products</option>
            <option value="resold">Resold Products</option>
          </select>

          <div className="edge-toggles">
            {Object.entries(EDGE_COLORS).map(([type, color]) => (
              <button
                key={type}
                className={`edge-toggle ${edgeTypeFilter.size === 0 || edgeTypeFilter.has(type) ? "active" : ""}`}
                style={{ borderColor: color, color: edgeTypeFilter.has(type) ? "#fff" : color }}
                onClick={() => toggleEdgeType(type)}
              >
                <span className="edge-dot" style={{ background: color }} />
                {type.replace(/_/g, " ")}
              </button>
            ))}
          </div>
        </div>

        <div className="toolbar-actions">
          <button type="button" className="primary" onClick={triggerAutoGraph} disabled={autoGraphBusy}>
            {autoGraphBusy ? "Graphing…" : "Auto-graph"}
          </button>
          <button type="button" onClick={runHealthCheck}>
            Integrity check
          </button>
          <button type="button" onClick={() => setShowCuration(!showCuration)}>
            Curation queue ({pendingEdges.length})
          </button>
        </div>
      </div>
      {autoGraphNote && <p className="graph-note">{autoGraphNote}</p>}

      {/* ── Main Area ────────────────────────────────────────────────── */}
      <div className="graph-main">
        {/* Canvas */}
        <div className="graph-canvas-wrap">
          <canvas
            ref={canvasRef}
            width={1200}
            height={700}
            className="graph-canvas"
            onMouseDown={handleCanvasMouseDown}
            onMouseMove={handleCanvasMouseMove}
            onMouseUp={handleCanvasMouseUp}
            onMouseLeave={handleCanvasMouseUp}
          />
          <div className="graph-legend">
            <span className="legend-title">Key</span>
            <span className="legend-item">
              <span className="legend-circle" style={{ background: OWNERSHIP_COLORS.own }} /> Own
            </span>
            <span className="legend-item">
              <span className="legend-circle" style={{ background: OWNERSHIP_COLORS.resold }} /> Resold
            </span>
            <span className="legend-sep">|</span>
            {Object.entries(EDGE_COLORS).map(([type, color]) => (
              <span key={type} className="legend-item">
                <span className="legend-line" style={{ background: color }} />
                {type.replace(/_/g, " ")}
              </span>
            ))}
          </div>
          <div className="graph-stats">
            {graph && (
              <>
                <span>{graph.nodes.length} products</span>
                <span className="stats-sep">·</span>
                <span>{graph.edges.length} edges</span>
                <span className="stats-sep">·</span>
                <span>{graph.categories.length} categories</span>
              </>
            )}
          </div>
        </div>

        {/* Detail drawer */}
        {selectedNode && (
          <aside className="graph-drawer">
            <div className="drawer-header">
              <div>
                <h3>{selectedNode.name}</h3>
                <span className={`ownership-badge ${selectedNode.ownership}`}>
                  {selectedNode.ownership}
                </span>
              </div>
              <button className="drawer-close" onClick={() => setSelectedNodeId(null)}>
                ✕
              </button>
            </div>

            <div className="drawer-section">
              <div className="detail-grid">
                <div className="detail-item">
                  <span className="detail-label">Vendor</span>
                  <span>{selectedNode.vendor}</span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">Category</span>
                  <span>{selectedNode.category}</span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">Tier</span>
                  <span>{selectedNode.tier}</span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">Deployment</span>
                  <span>{selectedNode.deployment_model}</span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">Lifecycle</span>
                  <span className={`lifecycle-tag ${selectedNode.lifecycle_status.toLowerCase()}`}>
                    {selectedNode.lifecycle_status}
                  </span>
                </div>
                <div className="detail-item">
                  <span className="detail-label">Capabilities</span>
                  <span>{selectedNode.capability_count}</span>
                </div>
              </div>
            </div>

            {/* Neighborhood summary */}
            {neighborhood && (
              <div className="drawer-section">
                <h4>Neighborhood</h4>
                {neighborhood.upstream_requires.length > 0 && (
                  <div className="nb-group">
                    <span className="nb-label" style={{ color: EDGE_COLORS.requires }}>
                      Requires ({neighborhood.upstream_requires.length})
                    </span>
                    {neighborhood.upstream_requires.map((e) => (
                      <span key={e.id} className="nb-tag">
                        {e.target_product_name}
                      </span>
                    ))}
                  </div>
                )}
                {neighborhood.conflicts.length > 0 && (
                  <div className="nb-group">
                    <span className="nb-label" style={{ color: EDGE_COLORS.conflicts_with }}>
                      Conflicts ({neighborhood.conflicts.length})
                    </span>
                    {neighborhood.conflicts.map((e) => (
                      <span key={e.id} className="nb-tag conflict">
                        {e.source_product_id === selectedNodeId
                          ? e.target_product_name
                          : e.source_product_name}
                      </span>
                    ))}
                  </div>
                )}
                {neighborhood.integrations.length > 0 && (
                  <div className="nb-group">
                    <span className="nb-label" style={{ color: EDGE_COLORS.integrates_with }}>
                      Integrations ({neighborhood.integrations.length})
                    </span>
                    {neighborhood.integrations.map((e) => (
                      <span key={e.id} className="nb-tag">
                        {e.source_product_id === selectedNodeId
                          ? e.target_product_name
                          : e.source_product_name}
                      </span>
                    ))}
                  </div>
                )}
                {neighborhood.downstream_required_by.length > 0 && (
                  <div className="nb-group">
                    <span className="nb-label" style={{ color: "#fbbf24" }}>
                      Required By ({neighborhood.downstream_required_by.length})
                    </span>
                    {neighborhood.downstream_required_by.map((e) => (
                      <span key={e.id} className="nb-tag">
                        {e.source_product_name}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}

            <div className="drawer-section">
              <button className="primary" onClick={() => runImpactQuery(selectedNodeId!)}>
                Trace impact
              </button>
            </div>

            {/* Impact result */}
            {impactResult && impactResult.product_id === selectedNodeId && (
              <div className="drawer-section impact-result">
                <h4>Impact Analysis</h4>
                {impactResult.all_prerequisites.length > 0 && (
                  <div className="impact-group">
                    <span className="impact-label prereq">
                      Prerequisites ({impactResult.all_prerequisites.length})
                    </span>
                    {impactResult.all_prerequisites.map((p, i) => (
                      <div key={i} className="impact-item">
                        <span className="impact-name">{p.name}</span>
                        <span className="impact-depth">depth {p.depth}</span>
                        <span className="impact-path">{p.path.join(" → ")}</span>
                      </div>
                    ))}
                  </div>
                )}
                {impactResult.all_incompatibilities.length > 0 && (
                  <div className="impact-group">
                    <span className="impact-label conflict">
                      Breaks ({impactResult.all_incompatibilities.length})
                    </span>
                    {impactResult.all_incompatibilities.map((c, i) => (
                      <div key={i} className="impact-item conflict">
                        <span className="impact-name">{c.conflicted_product_name}</span>
                        <span className="impact-reason">{c.reason}</span>
                      </div>
                    ))}
                  </div>
                )}
                {impactResult.all_prerequisites.length === 0 &&
                  impactResult.all_incompatibilities.length === 0 && (
                    <p className="impact-clean">No dependencies or conflicts found.</p>
                  )}
              </div>
            )}
          </aside>
        )}
      </div>

      {/* ── Health Modal ─────────────────────────────────────────────── */}
      {showHealth && (
        <div className="modal-backdrop" onClick={() => setShowHealth(false)}>
          <div className="modal-card health-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Graph integrity</h3>
              <button className="drawer-close" onClick={() => setShowHealth(false)}>
                ✕
              </button>
            </div>
            {integrity && (
              <div className="health-section">
                <h4>
                  Integrity{" "}
                  <span className={`health-badge ${integrity.is_valid ? "pass" : "fail"}`}>
                    {integrity.is_valid ? "Valid" : "Issues found"}
                  </span>
                </h4>
                {integrity.cycle_detected && (
                  <div className="health-alert danger">
                    <strong>Cycles detected:</strong>
                    {integrity.cycles.map((c, i) => (
                      <div key={i} className="cycle-path">
                        {c.join(" → ")}
                      </div>
                    ))}
                  </div>
                )}
                {integrity.contradictions_detected && (
                  <div className="health-alert danger">
                    <strong>Contradictions:</strong>
                    {integrity.contradictions.map((c: any, i: number) => (
                      <div key={i} className="contradiction-item">
                        {c.description}
                      </div>
                    ))}
                  </div>
                )}
                {integrity.is_valid && (
                  <div className="health-alert success">No cycles or contradictions detected.</div>
                )}
              </div>
            )}
            {coverage && (
              <div className="health-section">
                <h4>Coverage</h4>
                <div className="coverage-bar-wrap">
                  <div className="coverage-bar" style={{ width: `${coverage.coverage_percentage}%` }} />
                  <span className="coverage-pct">{coverage.coverage_percentage}%</span>
                </div>
                <div className="coverage-stats">
                  <span>Products: {coverage.total_products}</span>
                  <span>With Capability: {coverage.products_with_capability}</span>
                  <span>With Document: {coverage.products_with_document}</span>
                  <span>With Edge: {coverage.products_with_edge}</span>
                  <span>Fully Covered: {coverage.fully_covered_products}</span>
                </div>
                {coverage.orphan_capabilities.length > 0 && (
                  <div className="health-alert warning">
                    <strong>Orphan capabilities:</strong>{" "}
                    {coverage.orphan_capabilities.map((c: any) => c.name).join(", ")}
                  </div>
                )}
                <div className={`exit-badge ${coverage.exit_criteria_met ? "met" : ""}`}>
                  Exit criteria: {coverage.exit_criteria_met ? "Met" : "Not met"}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Curation Drawer ──────────────────────────────────────────── */}
      {showCuration && (
        <div className="curation-drawer">
          <div className="curation-header">
            <h3>Edge curation</h3>
            <div className="curation-actions">
              <button onClick={triggerSuggest}>Suggest Edges</button>
              <button className="drawer-close" onClick={() => setShowCuration(false)}>
                ✕
              </button>
            </div>
          </div>
          {pendingEdges.length === 0 ? (
            <p className="curation-empty">No edges waiting a stamp. Suggest from catalog evidence, then approve or reject.</p>
          ) : (
            <div className="curation-list">
              {pendingEdges.map((edge) => (
                <div key={edge.id} className="curation-card">
                  <div className="curation-relation">
                    <span className="curation-source">{edge.source_product_name}</span>
                    <span className="curation-arrow" style={{ color: EDGE_COLORS[edge.relation_type] ?? "#888" }}>
                      → {edge.relation_type.replace(/_/g, " ")} →
                    </span>
                    <span className="curation-target">{edge.target_product_name}</span>
                  </div>
                  <p className="curation-evidence">{edge.evidence}</p>
                  <div className="curation-meta">
                    <span className="confidence-pill">
                      Confidence: {(edge.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className="curation-btns">
                    <button className="approve-btn" onClick={() => approveEdge(edge.id)}>
                      Approve
                    </button>
                    <button className="reject-btn" onClick={() => rejectEdge(edge.id)}>
                      Reject
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
