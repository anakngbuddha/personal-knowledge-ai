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
import {
  ActivityIcon,
  BookOpenIcon,
  CheckIcon,
  DatabaseIcon,
  FileTextIcon,
  FilterIcon,
  InfoIcon,
  LayersVectorIcon,
  MaximizeIcon,
  NetworkIcon,
  PlusIcon,
  RefreshCwIcon,
  SearchIcon,
  ShieldCheckIcon,
  SparklesIcon,
  UploadCloudIcon,
  ZapIcon,
  ZoomInIcon,
  ZoomOutIcon,
} from "./Icons";
import { MapEditor } from "./MapEditor";
import { ProductImport } from "./ProductImport";

/* ── Edge & Ownership Colors ────────────────────────────────────────── */
const EDGE_COLORS: Record<string, string> = {
  requires: "#d97706",
  integrates_with: "#10b981",
  conflicts_with: "#ef4444",
  replaces: "#8b5cf6",
  bundles_with: "#06b6d4",
  alternative_to: "#3b82f6",
  migrates_to: "#f97316",
};

const OWNERSHIP_COLORS: Record<string, string> = {
  own: "#d97706",
  resold: "#10b981",
};

/* ── Force Simulation Node ──────────────────────────────────────────── */
interface SimNode extends GraphNode {
  x: number;
  y: number;
  vx: number;
  vy: number;
  fx: number | null;
  fy: number | null;
}

function initSim(nodes: GraphNode[], width: number, height: number): SimNode[] {
  const cx = width / 2;
  const cy = height / 2;
  const radius = Math.min(width, height) * 0.35;
  const count = nodes.length || 1;

  return nodes.map((n, i) => {
    const angle = (i / count) * 2 * Math.PI;
    const r = radius * (0.4 + 0.6 * Math.random());
    return {
      ...n,
      x: cx + Math.cos(angle) * r,
      y: cy + Math.sin(angle) * r,
      vx: 0,
      vy: 0,
      fx: null,
      fy: null,
    };
  });
}

function tickSim(
  simNodes: SimNode[],
  edges: GraphLink[],
  width: number,
  height: number,
  alpha: number
): void {
  const idxById: Record<string, number> = {};
  simNodes.forEach((n, i) => (idxById[n.id] = i));

  // Center gravity
  const cx = width / 2;
  const cy = height / 2;
  for (const n of simNodes) {
    n.vx += (cx - n.x) * 0.0025 * alpha;
    n.vy += (cy - n.y) * 0.0025 * alpha;
  }

  // Repulsion between nodes
  for (let i = 0; i < simNodes.length; i++) {
    for (let j = i + 1; j < simNodes.length; j++) {
      const dx = simNodes[j].x - simNodes[i].x;
      const dy = simNodes[j].y - simNodes[i].y;
      const d2 = dx * dx + dy * dy || 1;
      const dist = Math.sqrt(d2);
      const minSpacing = 160;
      if (dist < minSpacing) {
        const force = ((minSpacing - dist) / minSpacing) * 45 * alpha;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;
        simNodes[i].vx -= fx;
        simNodes[i].vy -= fy;
        simNodes[j].vx += fx;
        simNodes[j].vy += fy;
      }
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
    const targetDist = 180;
    const force = ((d - targetDist) / d) * 0.035 * alpha;
    const fx = dx * force;
    const fy = dy * force;
    s.vx += fx;
    s.vy += fy;
    t.vx -= fx;
    t.vy -= fy;
  }

  // Integration & dampening
  for (const n of simNodes) {
    if (n.fx !== null) {
      n.x = n.fx;
      n.vx = 0;
    } else {
      n.vx *= 0.65;
      n.x += n.vx;
    }
    if (n.fy !== null) {
      n.y = n.fy;
      n.vy = 0;
    } else {
      n.vy *= 0.65;
      n.y += n.vy;
    }
    n.x = Math.max(60, Math.min(width - 60, n.x));
    n.y = Math.max(60, Math.min(height - 60, n.y));
  }
}

/* ── Props ───────────────────────────────────────────────────────────── */
export interface TabItem {
  id: string;
  name: string;
  icon: React.ComponentType<{ size?: number }>;
  badge?: string;
}

interface Props {
  sourceCount?: number;
  tabs?: TabItem[];
  activeTab?: string;
  onTabChange?: (tab: any) => void;
  onNavigate?: (tab: "sources" | "map" | "ask" | "notes") => void;
  onMapChanged?: () => void;
}

/* ── Component ───────────────────────────────────────────────────────── */
export function GraphExplorer({
  sourceCount = 0,
  tabs,
  activeTab = "map",
  onTabChange,
  onNavigate,
  onMapChanged,
}: Props) {
  /* View mode */
  const [viewMode, setViewMode] = useState<"map" | "editor" | "import">("map");

  /* Graph data */
  const [graph, setGraph] = useState<PortfolioGraphOut | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  /* Filters */
  const [searchQuery, setSearchQuery] = useState("");
  const [vendorFilter, setVendorFilter] = useState("");
  const [ownershipFilter, setOwnershipFilter] = useState("");
  const [edgeTypeFilter, setEdgeTypeFilter] = useState<Set<string>>(new Set());

  /* Selection & hover */
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const [neighborhood, setNeighborhood] = useState<NeighborhoodOut | null>(null);
  const [impactResult, setImpactResult] = useState<GraphQueryOut | null>(null);
  const [impactLoading, setImpactLoading] = useState(false);

  /* Health & integrity */
  const [integrity, setIntegrity] = useState<IntegrityReportOut | null>(null);
  const [coverage, setCoverage] = useState<CoverageReportOut | null>(null);
  const [showHealth, setShowHealth] = useState(false);
  const [healthLoading, setHealthLoading] = useState(false);

  /* Curation */
  const [pendingEdges, setPendingEdges] = useState<ProductEdgeOut[]>([]);
  const [showCuration, setShowCuration] = useState(false);
  const [autoGraphNote, setAutoGraphNote] = useState<string | null>(null);
  const [autoGraphBusy, setAutoGraphBusy] = useState(false);

  /* Canvas viewport */
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const simNodesRef = useRef<SimNode[]>([]);
  const animRef = useRef<number>(0);
  const alphaRef = useRef(1);
  const draggingRef = useRef<number | null>(null);
  const panRef = useRef({ x: 0, y: 0, startX: 0, startY: 0, panning: false });
  const zoomRef = useRef(1);
  const [viewportZoom, setViewportZoom] = useState(100);

  /* ── Fetch Graph ───────────────────────────────────────────────────── */
  const fetchGraph = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await catalogApi.getPortfolioGraph();
      setGraph(data);
    } catch (e: any) {
      setError(e?.message ?? "Failed to load knowledge map.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchGraph();
  }, [fetchGraph]);

  /* ── Load Pending Edges ────────────────────────────────────────────── */
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

  /* ── Filtered Graph ────────────────────────────────────────────────── */
  const filtered = useMemo(() => {
    if (!graph) return { nodes: [], edges: [] };
    let nodes = graph.nodes;
    if (vendorFilter) nodes = nodes.filter((n) => n.vendor === vendorFilter);
    if (ownershipFilter) nodes = nodes.filter((n) => n.ownership === ownershipFilter);

    const nodeIds = new Set(nodes.map((n) => n.id));
    let edges = graph.edges.filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target));
    if (edgeTypeFilter.size > 0) {
      edges = edges.filter((e) => edgeTypeFilter.has(e.relation_type));
    }
    return { nodes, edges };
  }, [graph, vendorFilter, ownershipFilter, edgeTypeFilter]);

  /* Set of node IDs matching search */
  const searchMatchedIds = useMemo(() => {
    if (!searchQuery.trim()) return null;
    const q = searchQuery.toLowerCase().trim();
    const set = new Set<string>();
    filtered.nodes.forEach((n) => {
      if (
        n.name.toLowerCase().includes(q) ||
        n.vendor.toLowerCase().includes(q) ||
        n.category.toLowerCase().includes(q)
      ) {
        set.add(n.id);
      }
    });
    return set;
  }, [filtered.nodes, searchQuery]);

  /* Selected or hovered connected IDs */
  const activeFocusIds = useMemo(() => {
    const activeId = hoveredNodeId || selectedNodeId;
    if (!activeId) return null;
    const ids = new Set<string>([activeId]);
    filtered.edges.forEach((e) => {
      if (e.source === activeId) ids.add(e.target);
      if (e.target === activeId) ids.add(e.source);
    });
    return ids;
  }, [hoveredNodeId, selectedNodeId, filtered.edges]);

  /* ── Fetch Detail on Node Selection ────────────────────────────────── */
  useEffect(() => {
    if (!selectedNodeId) {
      setNeighborhood(null);
      setImpactResult(null);
      return;
    }
    catalogApi.getNeighborhood(selectedNodeId).then(setNeighborhood).catch(() => {});
  }, [selectedNodeId]);

  /* ── Auto-fit / Center Viewport ─────────────────────────────────────── */
  const fitView = useCallback(() => {
    const canvas = canvasRef.current;
    const sim = simNodesRef.current;
    if (!canvas || sim.length === 0) return;

    let minX = Infinity,
      maxX = -Infinity,
      minY = Infinity,
      maxY = -Infinity;
    sim.forEach((n) => {
      minX = Math.min(minX, n.x);
      maxX = Math.max(maxX, n.x);
      minY = Math.min(minY, n.y);
      maxY = Math.max(maxY, n.y);
    });

    const w = canvas.clientWidth || 1000;
    const h = canvas.clientHeight || 650;
    const graphW = Math.max(maxX - minX + 240, 300);
    const graphH = Math.max(maxY - minY + 160, 300);

    const scaleX = w / graphW;
    const scaleY = h / graphH;
    const targetZoom = Math.max(0.4, Math.min(1.2, Math.min(scaleX, scaleY)));

    const graphCenterX = (minX + maxX) / 2;
    const graphCenterY = (minY + maxY) / 2;

    panRef.current.x = w / 2 - graphCenterX * targetZoom;
    panRef.current.y = h / 2 - graphCenterY * targetZoom;
    zoomRef.current = targetZoom;
    setViewportZoom(Math.round(targetZoom * 100));
  }, []);

  const handleZoom = (delta: number) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    const oldZoom = zoomRef.current;
    const newZoom = Math.max(0.3, Math.min(2.5, oldZoom + delta));
    // zoom towards center
    const cx = w / 2;
    const cy = h / 2;
    panRef.current.x = cx - (cx - panRef.current.x) * (newZoom / oldZoom);
    panRef.current.y = cy - (cy - panRef.current.y) * (newZoom / oldZoom);
    zoomRef.current = newZoom;
    setViewportZoom(Math.round(newZoom * 100));
  };

  const handleReheat = () => {
    alphaRef.current = 1;
  };

  /* ── Canvas Simulation & High-DPI Loop ─────────────────────────────── */
  useEffect(() => {
    if (viewMode !== "map") return;
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;

    // Responsive size with Device Pixel Ratio
    const updateSize = () => {
      const rect = container.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      const w = Math.max(rect.width, 300);
      const h = Math.max(rect.height, 300);

      canvas.width = Math.floor(w * dpr);
      canvas.height = Math.floor(h * dpr);
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;

      if (simNodesRef.current.length === 0 && filtered.nodes.length > 0) {
        simNodesRef.current = initSim(filtered.nodes, w, h);
        fitView();
      }
    };

    updateSize();
    const observer = new ResizeObserver(() => updateSize());
    observer.observe(container);

    return () => observer.disconnect();
  }, [viewMode, filtered.nodes, fitView]);

  /* Reset simulation when node list changes */
  useEffect(() => {
    if (viewMode !== "map") return;
    const canvas = canvasRef.current;
    if (!canvas || filtered.nodes.length === 0) return;
    const w = canvas.clientWidth || 1000;
    const h = canvas.clientHeight || 650;

    const existingById = new Map(simNodesRef.current.map((n) => [n.id, n]));
    simNodesRef.current = filtered.nodes.map((n, i) => {
      const existing = existingById.get(n.id);
      if (existing) {
        return { ...n, x: existing.x, y: existing.y, vx: 0, vy: 0, fx: null, fy: null };
      }
      const angle = (i / filtered.nodes.length) * 2 * Math.PI;
      const r = Math.min(w, h) * 0.35 * (0.5 + 0.5 * Math.random());
      return {
        ...n,
        x: w / 2 + Math.cos(angle) * r,
        y: h / 2 + Math.sin(angle) * r,
        vx: 0,
        vy: 0,
        fx: null,
        fy: null,
      };
    });
    alphaRef.current = 1;
  }, [filtered.nodes, viewMode]);

  /* Main Animation Draw Loop */
  useEffect(() => {
    if (viewMode !== "map") return;
    const canvas = canvasRef.current;
    let active = true;

    function renderFrame() {
      if (!active || !canvas) return;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      const dpr = window.devicePixelRatio || 1;
      const W = canvas.clientWidth;
      const H = canvas.clientHeight;
      const sim = simNodesRef.current;

      // Physics tick
      if (alphaRef.current > 0.003) {
        tickSim(sim, filtered.edges, W, H, alphaRef.current);
        alphaRef.current *= 0.991;
      }

      ctx.save();
      ctx.scale(dpr, dpr);

      // Check current theme
      const isDark = document.documentElement.getAttribute("data-theme") === "dark";

      // Background
      ctx.fillStyle = isDark ? "#090d16" : "#f8fafc";
      ctx.fillRect(0, 0, W, H);

      // Soft Grid Dots (Apple style subtle canvas texture)
      const z = zoomRef.current;
      const px = panRef.current.x;
      const py = panRef.current.y;
      const dotSpacing = 32 * z;
      if (dotSpacing >= 14) {
        ctx.fillStyle = isDark ? "rgba(255, 255, 255, 0.07)" : "rgba(148, 163, 184, 0.32)";
        const startX = (px % dotSpacing + dotSpacing) % dotSpacing;
        const startY = (py % dotSpacing + dotSpacing) % dotSpacing;
        for (let x = startX; x < W; x += dotSpacing) {
          for (let y = startY; y < H; y += dotSpacing) {
            ctx.beginPath();
            ctx.arc(x, y, 1.2, 0, Math.PI * 2);
            ctx.fill();
          }
        }
      }

      // Camera Transform
      ctx.save();
      ctx.translate(px, py);
      ctx.scale(z, z);

      const idxById: Record<string, number> = {};
      sim.forEach((n, i) => (idxById[n.id] = i));

      // Draw Edges
      for (const e of filtered.edges) {
        const si = idxById[e.source];
        const ti = idxById[e.target];
        if (si === undefined || ti === undefined) continue;
        const s = sim[si];
        const t = sim[ti];

        const isHighlighted =
          (activeFocusIds && (activeFocusIds.has(e.source) && activeFocusIds.has(e.target))) ||
          (selectedNodeId && (e.source === selectedNodeId || e.target === selectedNodeId));

        const isDimmed =
          (activeFocusIds && !isHighlighted) ||
          (searchMatchedIds && (!searchMatchedIds.has(e.source) || !searchMatchedIds.has(e.target)));

        ctx.save();
        ctx.beginPath();
        ctx.moveTo(s.x, s.y);
        ctx.lineTo(t.x, t.y);

        const edgeColor = EDGE_COLORS[e.relation_type] ?? (isDark ? "#94a3b8" : "#64748b");
        ctx.strokeStyle = edgeColor;
        ctx.lineWidth = isHighlighted ? 2.5 : 1.4;

        if (isHighlighted) {
          ctx.globalAlpha = 0.95;
          ctx.shadowColor = edgeColor;
          ctx.shadowBlur = 6;
        } else if (isDimmed) {
          ctx.globalAlpha = 0.12;
        } else {
          ctx.globalAlpha = e.status === "approved" ? (isDark ? 0.65 : 0.55) : 0.25;
        }

        if (e.relation_type === "conflicts_with") {
          ctx.setLineDash([6, 5]);
        } else {
          ctx.setLineDash([]);
        }
        ctx.stroke();

        // Directional Arrowhead
        const angle = Math.atan2(t.y - s.y, t.x - s.x);
        const cardW = 126;
        const cardH = 46;
        // Position arrow slightly before target node border
        const offset = Math.min(cardW, cardH) * 0.75;
        const ax = t.x - Math.cos(angle) * offset;
        const ay = t.y - Math.sin(angle) * offset;
        const arrLen = isHighlighted ? 10 : 8;

        ctx.beginPath();
        ctx.moveTo(ax, ay);
        ctx.lineTo(ax - arrLen * Math.cos(angle - 0.42), ay - arrLen * Math.sin(angle - 0.42));
        ctx.moveTo(ax, ay);
        ctx.lineTo(ax - arrLen * Math.cos(angle + 0.42), ay - arrLen * Math.sin(angle + 0.42));
        ctx.stroke();

        ctx.restore();
      }

      // Draw Nodes (Apple squircle cards)
      const CARD_W = 132;
      const CARD_H = 48;
      const CARD_R = 10;

      for (const n of sim) {
        const isSelected = n.id === selectedNodeId;
        const isHovered = n.id === hoveredNodeId;
        const isInFocus = !activeFocusIds || activeFocusIds.has(n.id);
        const isSearchMatch = !searchMatchedIds || searchMatchedIds.has(n.id);
        const isDimmed = !isInFocus || !isSearchMatch;

        ctx.save();
        ctx.translate(n.x, n.y);

        if (isDimmed) {
          ctx.globalAlpha = 0.22;
        } else {
          ctx.globalAlpha = 1;
        }

        const left = -CARD_W / 2;
        const top = -CARD_H / 2;

        // Shadow
        if (!isDimmed) {
          ctx.shadowColor = isSelected
            ? isDark
              ? "rgba(99, 102, 241, 0.5)"
              : "rgba(79, 70, 229, 0.35)"
            : isHovered
            ? isDark
              ? "rgba(0, 0, 0, 0.5)"
              : "rgba(15, 23, 42, 0.12)"
            : isDark
            ? "rgba(0, 0, 0, 0.35)"
            : "rgba(15, 23, 42, 0.05)";
          ctx.shadowBlur = isSelected ? 16 : isHovered ? 12 : 6;
          ctx.shadowOffsetY = isSelected ? 4 : isHovered ? 3 : 2;
        }

        // Card Body
        ctx.beginPath();
        ctx.roundRect(left, top, CARD_W, CARD_H, CARD_R);
        ctx.fillStyle = isDark ? "#131b2e" : "#ffffff";
        ctx.fill();

        // Specular 1px Border
        ctx.shadowColor = "transparent";
        ctx.lineWidth = isSelected ? 2 : 1;
        ctx.strokeStyle = isSelected
          ? isDark
            ? "#818cf8"
            : "#4f46e5"
          : isHovered
          ? isDark
            ? "#3b82f6"
            : "#6366f1"
          : isDark
          ? "rgba(255, 255, 255, 0.12)"
          : "rgba(226, 232, 240, 0.9)";
        ctx.stroke();

        // Active selection outer halo ring
        if (isSelected) {
          ctx.beginPath();
          ctx.roundRect(left - 4, top - 4, CARD_W + 8, CARD_H + 8, CARD_R + 3);
          ctx.lineWidth = 1.5;
          ctx.strokeStyle = isDark ? "rgba(129, 140, 248, 0.4)" : "rgba(79, 70, 229, 0.3)";
          ctx.stroke();
        }

        // Ownership accent tag pill on left edge
        const ownColor = OWNERSHIP_COLORS[n.ownership] ?? "#d97706";
        ctx.beginPath();
        ctx.roundRect(left + 3, top + 5, 4, CARD_H - 10, 2);
        ctx.fillStyle = ownColor;
        ctx.fill();

        // Node Title
        ctx.font = '600 11px system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
        ctx.textAlign = "left";
        ctx.textBaseline = "top";
        ctx.fillStyle = isDark ? "#f8fafc" : "#0f172a";

        const maxChars = 14;
        const displayName =
          n.name.length > maxChars ? `${n.name.slice(0, maxChars - 1)}…` : n.name;
        ctx.fillText(displayName, left + 14, top + 9);

        // Vendor / Category Subtitle
        ctx.font = '500 9px system-ui, -apple-system, sans-serif';
        ctx.fillStyle = isDark ? "#94a3b8" : "#64748b";
        const subText = `${n.vendor} · ${n.category}`;
        const subDisplay = subText.length > 20 ? `${subText.slice(0, 18)}…` : subText;
        ctx.fillText(subDisplay, left + 14, top + 25);

        // Resold badge pill if resold
        if (n.ownership === "resold") {
          const badgeW = 34;
          const badgeH = 12;
          const bx = left + CARD_W - badgeW - 6;
          const by = top + 8;
          ctx.beginPath();
          ctx.roundRect(bx, by, badgeW, badgeH, 3);
          ctx.fillStyle = isDark ? "rgba(16, 185, 129, 0.2)" : "#ecfdf5";
          ctx.fill();
          ctx.strokeStyle = isDark ? "rgba(16, 185, 129, 0.4)" : "rgba(16, 185, 129, 0.3)";
          ctx.lineWidth = 0.75;
          ctx.stroke();

          ctx.font = '700 7.5px "IBM Plex Mono", ui-monospace, monospace';
          ctx.textAlign = "center";
          ctx.textBaseline = "middle";
          ctx.fillStyle = "#10b981";
          ctx.fillText("RESOLD", bx + badgeW / 2, by + badgeH / 2);
        }

        ctx.restore();
      }

      ctx.restore(); // Camera transform
      ctx.restore(); // DPI scale

      animRef.current = requestAnimationFrame(renderFrame);
    }

    animRef.current = requestAnimationFrame(renderFrame);
    return () => {
      active = false;
      cancelAnimationFrame(animRef.current);
    };
  }, [filtered, selectedNodeId, hoveredNodeId, activeFocusIds, searchMatchedIds, viewMode]);

  /* ── Canvas Mouse Events ───────────────────────────────────────────── */
  const handleCanvasMouseDown = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      const z = zoomRef.current;
      const mx = (e.clientX - rect.left - panRef.current.x) / z;
      const my = (e.clientY - rect.top - panRef.current.y) / z;

      const CARD_W = 132;
      const CARD_H = 48;

      // Check node hit
      for (let i = simNodesRef.current.length - 1; i >= 0; i--) {
        const n = simNodesRef.current[i];
        if (
          mx >= n.x - CARD_W / 2 &&
          mx <= n.x + CARD_W / 2 &&
          my >= n.y - CARD_H / 2 &&
          my <= n.y + CARD_H / 2
        ) {
          draggingRef.current = i;
          n.fx = n.x;
          n.fy = n.y;
          alphaRef.current = 0.35;
          return;
        }
      }

      // Canvas pan
      panRef.current.panning = true;
      panRef.current.startX = e.clientX - panRef.current.x;
      panRef.current.startY = e.clientY - panRef.current.y;
    },
    []
  );

  const handleCanvasMouseMove = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      const z = zoomRef.current;
      const mx = (e.clientX - rect.left - panRef.current.x) / z;
      const my = (e.clientY - rect.top - panRef.current.y) / z;

      if (draggingRef.current !== null) {
        const n = simNodesRef.current[draggingRef.current];
        n.fx = mx;
        n.fy = my;
        return;
      }

      if (panRef.current.panning) {
        panRef.current.x = e.clientX - panRef.current.startX;
        panRef.current.y = e.clientY - panRef.current.startY;
        return;
      }

      // Check hover
      const CARD_W = 132;
      const CARD_H = 48;
      let found: string | null = null;
      for (let i = simNodesRef.current.length - 1; i >= 0; i--) {
        const n = simNodesRef.current[i];
        if (
          mx >= n.x - CARD_W / 2 &&
          mx <= n.x + CARD_W / 2 &&
          my >= n.y - CARD_H / 2 &&
          my <= n.y + CARD_H / 2
        ) {
          found = n.id;
          break;
        }
      }
      setHoveredNodeId(found);
    },
    []
  );

  const handleCanvasMouseUp = useCallback(
    (e: React.MouseEvent<HTMLCanvasElement>) => {
      const canvas = canvasRef.current;
      if (!canvas) return;

      if (draggingRef.current !== null) {
        const n = simNodesRef.current[draggingRef.current];
        setSelectedNodeId(n.id);
        n.fx = null;
        n.fy = null;
        draggingRef.current = null;
        return;
      }

      if (panRef.current.panning) {
        // If it was a click without substantial pan, check if hit empty canvas to deselect
        const dx = Math.abs(e.clientX - (panRef.current.startX + panRef.current.x));
        const dy = Math.abs(e.clientY - (panRef.current.startY + panRef.current.y));
        if (dx < 4 && dy < 4 && !hoveredNodeId) {
          setSelectedNodeId(null);
        }
        panRef.current.panning = false;
      }
    },
    [hoveredNodeId]
  );

  // Wheel zoom
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const oldZoom = zoomRef.current;
      const zoomFactor = e.deltaY < 0 ? 1.1 : 0.9;
      const newZoom = Math.max(0.3, Math.min(2.5, oldZoom * zoomFactor));

      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;

      panRef.current.x = mouseX - (mouseX - panRef.current.x) * (newZoom / oldZoom);
      panRef.current.y = mouseY - (mouseY - panRef.current.y) * (newZoom / oldZoom);
      zoomRef.current = newZoom;
      setViewportZoom(Math.round(newZoom * 100));
    };

    canvas.addEventListener("wheel", onWheel, { passive: false });
    return () => canvas.removeEventListener("wheel", onWheel);
  }, [viewMode]);

  /* ── Health Check ──────────────────────────────────────────────────── */
  const runHealthCheck = useCallback(async () => {
    setShowHealth(true);
    setHealthLoading(true);
    try {
      const [integ, cov] = await Promise.all([catalogApi.getIntegrity(), catalogApi.getCoverage()]);
      setIntegrity(integ);
      setCoverage(cov);
    } catch {
      /* swallow */
    } finally {
      setHealthLoading(false);
    }
  }, []);

  /* ── Impact Query ──────────────────────────────────────────────────── */
  const runImpactQuery = useCallback(async (productId: string) => {
    setImpactLoading(true);
    try {
      const res = await catalogApi.queryImpact(productId);
      setImpactResult(res);
    } catch {
      /* swallow */
    } finally {
      setImpactLoading(false);
    }
  }, []);

  /* ── Edge Curation ─────────────────────────────────────────────────── */
  const approveEdge = useCallback(
    async (id: string) => {
      try {
        await catalogApi.approveEdge(id);
        setPendingEdges((prev) => prev.filter((e) => e.id !== id));
        await fetchGraph();
        onMapChanged?.();
      } catch {
        /* swallow */
      }
    },
    [fetchGraph, onMapChanged]
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
          : `Proposed ${result.proposed} relationship${
              result.proposed === 1 ? "" : "s"
            }. Review them before they guide a sale.`
      );
      await fetchGraph();
      await loadPending();
      onMapChanged?.();
    } catch (e: unknown) {
      setAutoGraphNote(e instanceof Error ? e.message : "Auto-graph failed.");
    } finally {
      setAutoGraphBusy(false);
    }
  }, [fetchGraph, loadPending, onMapChanged]);

  const toggleEdgeType = (type: string) => {
    setEdgeTypeFilter((prev) => {
      const next = new Set(prev);
      if (next.has(type)) next.delete(type);
      else next.add(type);
      return next;
    });
  };

  /* ── Selection Helpers ─────────────────────────────────────────────── */
  const selectedNode = useMemo(() => {
    if (!selectedNodeId || !graph) return null;
    return graph.nodes.find((n) => n.id === selectedNodeId) ?? null;
  }, [selectedNodeId, graph]);

  const jumpToNode = useCallback(
    (id: string) => {
      setSelectedNodeId(id);
      const target = simNodesRef.current.find((n) => n.id === id);
      const canvas = canvasRef.current;
      if (target && canvas) {
        const w = canvas.clientWidth;
        const h = canvas.clientHeight;
        const z = zoomRef.current;
        panRef.current.x = w / 2 - target.x * z;
        panRef.current.y = h / 2 - target.y * z;
      }
    },
    []
  );

  /* ── Render Loading & Error States ─────────────────────────────────── */
  if (loading && !graph) {
    return (
      <div className="map-desk">
        <div className="map-loading-screen">
          <div className="graph-spinner" />
          <p className="loading-title">Loading Knowledge Map</p>
          <span className="loading-sub">Indexing nodes, relationships &amp; citations…</span>
        </div>
      </div>
    );
  }

  if (error && !graph) {
    return (
      <div className="map-desk">
        <div className="map-error-card">
          <InfoIcon size={28} />
          <h3>Knowledge map could not be loaded</h3>
          <p>{error}</p>
          <button className="primary" onClick={fetchGraph}>
            Retry Loading
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="map-desk">
      {/* ── Left Column: Workspace Navigation & Map Filters ────────────── */}
      <aside className="map-sources">
        {/* Workspace Tab Navigation (Matching Ask Intelligence) */}
        {tabs && onTabChange && (
          <div className="sidebar-workspace-nav">
            <div className="sidebar-section-title">WORKSPACE</div>
            <div className="workspace-tabs-list">
              {tabs.map((tab) => {
                const Icon = tab.icon;
                const isActive = activeTab === tab.id;
                return (
                  <button
                    key={tab.id}
                    type="button"
                    className={`workspace-tab-btn ${isActive ? "active" : ""}`}
                    onClick={() => onTabChange(tab.id)}
                  >
                    <span className="tab-btn-icon">
                      <Icon size={17} />
                    </span>
                    <span className="tab-btn-name">{tab.name}</span>
                    {tab.badge && (
                      <span
                        className={`tab-btn-badge ${
                          tab.badge === "Live" ? "live" : tab.badge === "AI" ? "ai" : ""
                        }`}
                      >
                        {tab.badge}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* View Mode Segmented Controller */}
        <div className="map-view-segment-card">
          <div className="sidebar-section-title">PERSPECTIVE</div>
          <div className="segmented-control">
            <button
              type="button"
              className={`segmented-item ${viewMode === "map" ? "active" : ""}`}
              onClick={() => setViewMode("map")}
              title="Interactive 2D Knowledge Graph"
            >
              <NetworkIcon size={15} />
              <span>Map</span>
            </button>
            <button
              type="button"
              className={`segmented-item ${viewMode === "editor" ? "active" : ""}`}
              onClick={() => setViewMode("editor")}
              title="Edit Catalog & Context Relationships"
            >
              <BookOpenIcon size={15} />
              <span>Editor</span>
            </button>
            <button
              type="button"
              className={`segmented-item ${viewMode === "import" ? "active" : ""}`}
              onClick={() => setViewMode("import")}
              title="Import spreadsheet products"
            >
              <UploadCloudIcon size={15} />
              <span>Import</span>
            </button>
          </div>
        </div>

        {/* Catalog Filters */}
        <div className="sources-setup-card map-filters-card">
          <div className="sources-setup-header">CATALOG FILTERS</div>

          {/* Vendor Filter */}
          <div className="filter-group">
            <label className="filter-label">Vendor</label>
            <div className="notebook-select-wrap">
              <select
                className="notebook-select"
                value={vendorFilter}
                onChange={(e) => setVendorFilter(e.target.value)}
              >
                <option value="">All Vendors ({graph?.vendors.length || 0})</option>
                {graph?.vendors.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
              <span className="notebook-select-chevron">▾</span>
            </div>
          </div>

          {/* Ownership Filter */}
          <div className="filter-group">
            <label className="filter-label">Ownership</label>
            <div className="notebook-select-wrap">
              <select
                className="notebook-select"
                value={ownershipFilter}
                onChange={(e) => setOwnershipFilter(e.target.value)}
              >
                <option value="">All Ownership Types</option>
                <option value="own">Own Products</option>
                <option value="resold">Resold Products</option>
              </select>
              <span className="notebook-select-chevron">▾</span>
            </div>
          </div>

          {/* Edge Types Toggles */}
          <div className="filter-group">
            <label className="filter-label">Relationships</label>
            <div className="edge-toggles-grid">
              {Object.entries(EDGE_COLORS).map(([type, color]) => {
                const isActive = edgeTypeFilter.size === 0 || edgeTypeFilter.has(type);
                return (
                  <button
                    key={type}
                    type="button"
                    className={`edge-pill-toggle ${isActive ? "active" : ""}`}
                    onClick={() => toggleEdgeType(type)}
                    style={{
                      borderColor: isActive ? color : "var(--rule-strong)",
                    }}
                  >
                    <span className="edge-dot-circle" style={{ background: color }} />
                    <span className="edge-pill-text">{type.replace(/_/g, " ")}</span>
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* Graph AI & Ops Card */}
        <div className="sources-setup-card map-actions-card">
          <div className="sources-setup-header">GRAPH INTELLIGENCE</div>
          <div className="map-action-buttons">
            <button
              type="button"
              className="map-action-btn primary"
              onClick={triggerAutoGraph}
              disabled={autoGraphBusy}
            >
              <SparklesIcon size={14} />
              <span>{autoGraphBusy ? "Analyzing Catalog…" : "Auto-graph"}</span>
            </button>
            <button type="button" className="map-action-btn" onClick={runHealthCheck}>
              <ShieldCheckIcon size={14} />
              <span>Integrity Check</span>
            </button>
            <button
              type="button"
              className="map-action-btn"
              onClick={() => setShowCuration(!showCuration)}
            >
              <ActivityIcon size={14} />
              <span>Curation Queue</span>
              {pendingEdges.length > 0 && (
                <span className="pill-badge">{pendingEdges.length}</span>
              )}
            </button>
          </div>
          {autoGraphNote && <p className="auto-graph-note">{autoGraphNote}</p>}
        </div>

        {/* Vector Memory & Catalog Telemetry Card (Matching Ask Intelligence) */}
        <div className="vector-memory-card">
          <div className="vector-memory-row">
            <div className="vector-memory-icon-wrap">
              <LayersVectorIcon size={16} />
            </div>
            <div className="vector-memory-info">
              <div className="vector-memory-title-row">
                <span className="vector-memory-title">Catalog Memory</span>
                <span className="vector-memory-hnsw">HNSW</span>
              </div>
              <div className="vector-memory-meta">
                {graph?.nodes.length || 0} products &bull; {graph?.edges.length || 0} edges
              </div>
            </div>
          </div>
        </div>
      </aside>

      {/* ── Center Column: Interactive Canvas or Editor Stage ─────────── */}
      <main className="map-stage-center">
        {/* Top Header Bar */}
        <header className="map-center-header">
          <div className="header-left">
            <div className="header-breadcrumbs">
              <span className="crumb-main">Knowledge Map</span>
              <span className="crumb-sep">/</span>
              <span className="crumb-sub">
                {viewMode === "map"
                  ? "Interactive Portfolio Topology"
                  : viewMode === "editor"
                  ? "Catalog & Relationship Editor"
                  : "Product List Importer"}
              </span>
            </div>
          </div>

          <div className="header-center">
            {/* Quick Product Search Input */}
            <div className="map-search-bar">
              <SearchIcon size={14} />
              <input
                type="text"
                placeholder="Filter or search products in map…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
              {searchQuery && (
                <button
                  type="button"
                  className="search-clear-btn"
                  onClick={() => setSearchQuery("")}
                >
                  ✕
                </button>
              )}
            </div>
          </div>

          <div className="header-right">
            {/* Quick View Controls */}
            {viewMode === "map" && (
              <div className="canvas-hud-controls">
                <button
                  type="button"
                  className="hud-icon-btn"
                  onClick={() => handleZoom(0.2)}
                  title="Zoom In"
                >
                  <ZoomInIcon size={15} />
                </button>
                <span className="zoom-label">{viewportZoom}%</span>
                <button
                  type="button"
                  className="hud-icon-btn"
                  onClick={() => handleZoom(-0.2)}
                  title="Zoom Out"
                >
                  <ZoomOutIcon size={15} />
                </button>
                <div className="hud-sep" />
                <button
                  type="button"
                  className="hud-icon-btn"
                  onClick={fitView}
                  title="Fit Map to Viewport"
                >
                  <MaximizeIcon size={14} />
                </button>
                <button
                  type="button"
                  className="hud-icon-btn"
                  onClick={handleReheat}
                  title="Re-heat Simulation"
                >
                  <RefreshCwIcon size={14} />
                </button>
              </div>
            )}
          </div>
        </header>

        {/* Center Workspace Body */}
        <div className="map-stage-viewport">
          {viewMode === "map" && (
            <div ref={containerRef} className="map-canvas-container">
              <canvas
                ref={canvasRef}
                className="map-interactive-canvas"
                onMouseDown={handleCanvasMouseDown}
                onMouseMove={handleCanvasMouseMove}
                onMouseUp={handleCanvasMouseUp}
                onMouseLeave={handleCanvasMouseUp}
              />

              {/* Floating Bottom HUD: Legend */}
              <div className="map-floating-legend">
                <div className="legend-section">
                  <span className="legend-title">OWNERSHIP</span>
                  <span className="legend-item">
                    <span
                      className="legend-dot"
                      style={{ background: OWNERSHIP_COLORS.own }}
                    />
                    <span>Own</span>
                  </span>
                  <span className="legend-item">
                    <span
                      className="legend-dot"
                      style={{ background: OWNERSHIP_COLORS.resold }}
                    />
                    <span>Resold</span>
                  </span>
                </div>
                <div className="legend-vdivider" />
                <div className="legend-section">
                  <span className="legend-title">RELATIONS</span>
                  {Object.entries(EDGE_COLORS).map(([type, color]) => (
                    <span key={type} className="legend-item">
                      <span className="legend-line" style={{ background: color }} />
                      <span>{type.replace(/_/g, " ")}</span>
                    </span>
                  ))}
                </div>
              </div>

              {/* Floating Bottom-Right HUD: Stats */}
              <div className="map-floating-stats">
                <span>{filtered.nodes.length} products</span>
                <span className="stat-bullet">&bull;</span>
                <span>{filtered.edges.length} edges</span>
                <span className="stat-bullet">&bull;</span>
                <span>{graph?.categories.length || 0} categories</span>
              </div>
            </div>
          )}

          {viewMode === "editor" && (
            <div className="map-embedded-editor">
              <MapEditor
                onChanged={() => {
                  fetchGraph();
                  onMapChanged?.();
                }}
              />
            </div>
          )}

          {viewMode === "import" && (
            <div className="map-embedded-import">
              <ProductImport
                onImported={() => {
                  fetchGraph();
                  onMapChanged?.();
                  setViewMode("map");
                }}
              />
            </div>
          )}
        </div>
      </main>

      {/* ── Right Column: Node Inspector & Impact Analyzer ───────────── */}
      <aside className="map-side">
        <div className="side-section">
          <div className="side-section-header">
            <span className="side-title">NODE INSPECTOR</span>
            <span className="side-meta-mono">Live Inspector</span>
          </div>

          {selectedNode ? (
            <div className="node-inspector-active">
              {/* Product Header Card */}
              <div className="inspector-card-header">
                <div className="inspector-title-row">
                  <div className="node-squircle-icon">
                    <NetworkIcon size={18} />
                  </div>
                  <div className="node-title-wrap">
                    <h3 className="node-name">{selectedNode.name}</h3>
                    <span className="node-vendor">{selectedNode.vendor}</span>
                  </div>
                </div>

                <div className="inspector-badges-row">
                  <span className={`ownership-chip ${selectedNode.ownership}`}>
                    {selectedNode.ownership === "own" ? "Own Product" : "Resold"}
                  </span>
                  <span className="category-chip">{selectedNode.category}</span>
                  <span className="lifecycle-chip">{selectedNode.lifecycle_status}</span>
                </div>
              </div>

              {/* Attributes Grid */}
              <div className="inspector-meta-grid">
                <div className="meta-cell">
                  <span className="meta-label">Tier</span>
                  <span className="meta-val">{selectedNode.tier}</span>
                </div>
                <div className="meta-cell">
                  <span className="meta-label">Deployment</span>
                  <span className="meta-val">{selectedNode.deployment_model}</span>
                </div>
                <div className="meta-cell">
                  <span className="meta-label">Capabilities</span>
                  <span className="meta-val">{selectedNode.capability_count} verified</span>
                </div>
              </div>

              {/* Neighborhood Connections */}
              {neighborhood && (
                <div className="inspector-neighborhood-section">
                  <div className="nb-header">CONNECTED TOPOLOGY</div>

                  {neighborhood.upstream_requires.length > 0 && (
                    <div className="nb-block">
                      <div className="nb-title" style={{ color: EDGE_COLORS.requires }}>
                        Requires ({neighborhood.upstream_requires.length})
                      </div>
                      <div className="nb-tags-wrap">
                        {neighborhood.upstream_requires.map((e) => (
                          <button
                            key={e.id}
                            type="button"
                            className="nb-jump-tag"
                            onClick={() => jumpToNode(e.target_product_id)}
                            title="Jump to product"
                          >
                            <span>{e.target_product_name}</span>
                            <span className="tag-arrow">↗</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  {neighborhood.conflicts.length > 0 && (
                    <div className="nb-block conflict">
                      <div className="nb-title" style={{ color: EDGE_COLORS.conflicts_with }}>
                        Conflicts With ({neighborhood.conflicts.length})
                      </div>
                      <div className="nb-tags-wrap">
                        {neighborhood.conflicts.map((e) => {
                          const conflictTargetId =
                            e.source_product_id === selectedNode.id
                              ? e.target_product_id
                              : e.source_product_id;
                          const conflictTargetName =
                            e.source_product_id === selectedNode.id
                              ? e.target_product_name
                              : e.source_product_name;
                          return (
                            <button
                              key={e.id}
                              type="button"
                              className="nb-jump-tag conflict"
                              onClick={() => jumpToNode(conflictTargetId)}
                              title="Jump to conflict"
                            >
                              <span>{conflictTargetName}</span>
                              <span className="tag-arrow">⚠</span>
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {neighborhood.integrations.length > 0 && (
                    <div className="nb-block">
                      <div className="nb-title" style={{ color: EDGE_COLORS.integrates_with }}>
                        Integrations ({neighborhood.integrations.length})
                      </div>
                      <div className="nb-tags-wrap">
                        {neighborhood.integrations.map((e) => {
                          const integId =
                            e.source_product_id === selectedNode.id
                              ? e.target_product_id
                              : e.source_product_id;
                          const integName =
                            e.source_product_id === selectedNode.id
                              ? e.target_product_name
                              : e.source_product_name;
                          return (
                            <button
                              key={e.id}
                              type="button"
                              className="nb-jump-tag"
                              onClick={() => jumpToNode(integId)}
                              title="Jump to integrated product"
                            >
                              <span>{integName}</span>
                              <span className="tag-arrow">↗</span>
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {neighborhood.downstream_required_by.length > 0 && (
                    <div className="nb-block">
                      <div className="nb-title" style={{ color: "#f59e0b" }}>
                        Required By ({neighborhood.downstream_required_by.length})
                      </div>
                      <div className="nb-tags-wrap">
                        {neighborhood.downstream_required_by.map((e) => (
                          <button
                            key={e.id}
                            type="button"
                            className="nb-jump-tag"
                            onClick={() => jumpToNode(e.source_product_id)}
                            title="Jump to dependent product"
                          >
                            <span>{e.source_product_name}</span>
                            <span className="tag-arrow">↗</span>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Impact Query Button */}
              <div className="inspector-actions-row">
                <button
                  type="button"
                  className="trace-impact-btn"
                  onClick={() => runImpactQuery(selectedNode.id)}
                  disabled={impactLoading}
                >
                  <ActivityIcon size={14} />
                  <span>{impactLoading ? "Tracing impact…" : "Trace Architectural Impact"}</span>
                </button>
              </div>

              {/* Impact Query Results */}
              {impactResult && impactResult.product_id === selectedNode.id && (
                <div className="impact-results-card">
                  <div className="impact-results-title">IMPACT ANALYSIS</div>
                  {impactResult.all_prerequisites.length > 0 && (
                    <div className="impact-group">
                      <span className="impact-header-tag prereq">
                        Prerequisites ({impactResult.all_prerequisites.length})
                      </span>
                      {impactResult.all_prerequisites.map((p, i) => (
                        <div key={i} className="impact-node-row">
                          <span className="node-p-name">{p.name}</span>
                          <span className="node-p-depth">depth {p.depth}</span>
                          <span className="node-p-path">{p.path.join(" → ")}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {impactResult.all_incompatibilities.length > 0 && (
                    <div className="impact-group">
                      <span className="impact-header-tag conflict">
                        Incompatibilities ({impactResult.all_incompatibilities.length})
                      </span>
                      {impactResult.all_incompatibilities.map((c, i) => (
                        <div key={i} className="impact-node-row conflict">
                          <span className="node-p-name">{c.conflicted_product_name}</span>
                          <span className="node-p-reason">{c.reason}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {impactResult.all_prerequisites.length === 0 &&
                    impactResult.all_incompatibilities.length === 0 && (
                      <p className="clean-impact-text">
                        No dependencies or conflict issues found for this node.
                      </p>
                    )}
                </div>
              )}

              <button
                type="button"
                className="citation-clear-btn"
                onClick={() => setSelectedNodeId(null)}
              >
                Close inspector
              </button>
            </div>
          ) : (
            /* Apple-Style Empty State */
            <div className="citation-inspector-empty">
              <div className="citation-icon-squircle">
                <NetworkIcon size={20} />
              </div>
              <p className="citation-empty-text">Select a node on the map to inspect.</p>
              <p className="empty-subtext">
                Click any product node to explore prerequisites, integrations, and conflicts.
              </p>

              {/* Quick Jump Suggestions */}
              {filtered.nodes.length > 0 && (
                <div className="quick-inspect-list">
                  <span className="quick-inspect-title">POPULAR PRODUCTS</span>
                  <div className="quick-tags-wrap">
                    {filtered.nodes.slice(0, 6).map((n) => (
                      <button
                        key={n.id}
                        type="button"
                        className="quick-node-tag"
                        onClick={() => jumpToNode(n.id)}
                      >
                        {n.name}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </aside>

      {/* ── Health & Integrity Modal ──────────────────────────────────── */}
      {showHealth && (
        <div className="modal-backdrop" onClick={() => setShowHealth(false)}>
          <div className="modal-card health-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div className="modal-title-wrap">
                <ShieldCheckIcon size={20} />
                <h3>Graph Integrity &amp; Coverage</h3>
              </div>
              <button
                type="button"
                className="drawer-close"
                onClick={() => setShowHealth(false)}
              >
                ✕
              </button>
            </div>

            {healthLoading ? (
              <div className="health-loading-box">
                <div className="graph-spinner" />
                <span>Auditing graph cycles and orphan capabilities…</span>
              </div>
            ) : (
              <>
                {integrity && (
                  <div className="health-section">
                    <div className="health-header-row">
                      <h4>Cycle &amp; Contradiction Audit</h4>
                      <span
                        className={`health-badge ${integrity.is_valid ? "pass" : "fail"}`}
                      >
                        {integrity.is_valid ? "Valid" : "Issues Found"}
                      </span>
                    </div>

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
                      <div className="health-alert success">
                        No circular dependencies or conflicting edges found in portfolio.
                      </div>
                    )}
                  </div>
                )}

                {coverage && (
                  <div className="health-section">
                    <h4>Portfolio Coverage</h4>
                    <div className="coverage-bar-wrap">
                      <div
                        className="coverage-bar"
                        style={{ width: `${coverage.coverage_percentage}%` }}
                      />
                      <span className="coverage-pct">{coverage.coverage_percentage}%</span>
                    </div>
                    <div className="coverage-stats">
                      <span>Total Products: {coverage.total_products}</span>
                      <span>With Capability: {coverage.products_with_capability}</span>
                      <span>With Document: {coverage.products_with_document}</span>
                      <span>With Edges: {coverage.products_with_edge}</span>
                      <span>Fully Grounded: {coverage.fully_covered_products}</span>
                    </div>

                    {coverage.orphan_capabilities.length > 0 && (
                      <div className="health-alert warning">
                        <strong>Orphan capabilities:</strong>{" "}
                        {coverage.orphan_capabilities.map((c: any) => c.name).join(", ")}
                      </div>
                    )}

                    <div
                      className={`exit-badge ${
                        coverage.exit_criteria_met ? "met" : ""
                      }`}
                    >
                      Exit criteria: {coverage.exit_criteria_met ? "Met" : "Not met"}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}

      {/* ── Curation Queue Modal/Drawer ───────────────────────────────── */}
      {showCuration && (
        <div className="modal-backdrop" onClick={() => setShowCuration(false)}>
          <div className="curation-sheet-card" onClick={(e) => e.stopPropagation()}>
            <div className="curation-header">
              <div className="curation-title-wrap">
                <SparklesIcon size={18} />
                <h3>Edge Curation Queue ({pendingEdges.length})</h3>
              </div>
              <div className="curation-actions">
                <button type="button" className="btn-suggest" onClick={triggerSuggest}>
                  Suggest Edges
                </button>
                <button
                  type="button"
                  className="drawer-close"
                  onClick={() => setShowCuration(false)}
                >
                  ✕
                </button>
              </div>
            </div>

            <p className="curation-lead">
              AI-extracted and evidence-backed relationships waiting for human verification
              before grounding sales.
            </p>

            {pendingEdges.length === 0 ? (
              <div className="curation-empty-card">
                <CheckIcon size={28} />
                <p>All catalog relationships are reviewed and approved.</p>
                <button type="button" onClick={triggerSuggest}>
                  Run Discovery on Sources
                </button>
              </div>
            ) : (
              <div className="curation-list-scroll">
                {pendingEdges.map((edge) => (
                  <div key={edge.id} className="curation-card">
                    <div className="curation-relation">
                      <span className="curation-source">{edge.source_product_name}</span>
                      <span
                        className="curation-arrow"
                        style={{ color: EDGE_COLORS[edge.relation_type] ?? "#888" }}
                      >
                        → {edge.relation_type.replace(/_/g, " ")} →
                      </span>
                      <span className="curation-target">{edge.target_product_name}</span>
                    </div>

                    <p className="curation-evidence">"{edge.evidence}"</p>

                    <div className="curation-meta">
                      <span className="confidence-pill">
                        Confidence: {(edge.confidence * 100).toFixed(0)}%
                      </span>
                      {edge.is_ai_suggested && (
                        <span className="ai-pill">AI Suggested</span>
                      )}
                    </div>

                    <div className="curation-btns">
                      <button
                        type="button"
                        className="approve-btn"
                        onClick={() => approveEdge(edge.id)}
                      >
                        Approve
                      </button>
                      <button
                        type="button"
                        className="reject-btn"
                        onClick={() => rejectEdge(edge.id)}
                      >
                        Reject
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
