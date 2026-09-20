/**
 * Phase 4: Catalog & Graph API client.
 *
 * Provides typed fetch wrappers for product catalog CRUD,
 * graph queries, integrity checks, and edge curation.
 */

import { request } from "./http";

// ── Types ─────────────────────────────────────────────────────────────────

export interface ProductOut {
  id: string;
  org_id: string;
  workspace_id: string;
  name: string;
  slug: string;
  vendor: string;
  ownership: string;
  category: string;
  tier: string;
  deployment_model: string;
  licensing_model: string;
  target_segment: string;
  lifecycle_status: string;
  prerequisites: string | null;
  support_path: string | null;
  description: string | null;
  collateral_document_ids: string[] | null;
  partner_tier: string | null;
  margin_band: string | null;
  support_owner: string | null;
  contract_constraints: string | null;
  source_of_truth_url: string | null;
  created_at: string;
  updated_at: string;
  capabilities: ProductCapabilityOut[];
  edge_count: number;
}

export interface ProductCapabilityOut {
  capability_id: string;
  name: string;
  slug: string;
  category: string;
  description: string | null;
  proficiency: string;
  notes: string | null;
}

export interface CapabilityOut {
  id: string;
  org_id: string;
  name: string;
  slug: string;
  category: string;
  description: string | null;
  created_at: string;
  product_count: number;
}

export interface ProductEdgeOut {
  id: string;
  org_id: string;
  workspace_id: string;
  source_product_id: string;
  source_product_name: string;
  target_product_id: string;
  target_product_name: string;
  relation_type: string;
  evidence: string;
  confidence: number;
  document_id: string | null;
  is_ai_suggested: boolean;
  status: string;
  rejection_reason: string | null;
  created_at: string;
}

export interface GraphNode {
  id: string;
  name: string;
  slug: string;
  vendor: string;
  ownership: string;
  category: string;
  tier: string;
  deployment_model: string;
  lifecycle_status: string;
  capability_count: number;
  collateral_count: number;
}

export interface GraphLink {
  id: string;
  source: string;
  target: string;
  relation_type: string;
  evidence: string;
  confidence: number;
  status: string;
  is_ai_suggested: boolean;
}

export interface PortfolioGraphOut {
  nodes: GraphNode[];
  edges: GraphLink[];
  categories: string[];
  vendors: string[];
  relation_types: string[];
}

export interface NeighborhoodOut {
  center_product: ProductOut;
  upstream_requires: ProductEdgeOut[];
  downstream_required_by: ProductEdgeOut[];
  conflicts: ProductEdgeOut[];
  integrations: ProductEdgeOut[];
  alternatives: ProductEdgeOut[];
  bundles: ProductEdgeOut[];
  replaces: ProductEdgeOut[];
  migrates_to: ProductEdgeOut[];
  reference_architectures: ReferenceArchitectureOut[];
}

export interface ImpactItem {
  product_id: string;
  name: string;
  vendor: string;
  ownership: string;
  depth: number;
  path: string[];
  evidence: string | null;
}

export interface ConflictItem {
  conflicted_product_id: string;
  conflicted_product_name: string;
  conflicted_product_vendor: string;
  reason: string;
  conflict_path: string[];
  evidence: string | null;
}

export interface GraphQueryOut {
  product_id: string;
  product_name: string;
  vendor: string;
  ownership: string;
  all_prerequisites: ImpactItem[];
  all_incompatibilities: ConflictItem[];
  direct_integrations: ImpactItem[];
  alternatives: ImpactItem[];
  reference_architectures: ReferenceArchitectureOut[];
}

export interface IntegrityReportOut {
  is_valid: boolean;
  cycle_detected: boolean;
  cycles: string[][];
  contradictions_detected: boolean;
  contradictions: Record<string, unknown>[];
}

export interface CoverageReportOut {
  total_products: number;
  products_with_capability: number;
  products_with_document: number;
  products_with_edge: number;
  fully_covered_products: number;
  coverage_percentage: number;
  orphan_capabilities: Record<string, unknown>[];
  uncovered_products: { id: string; name: string; vendor: string; ownership: string; missing: string[] }[];
  exit_criteria_met: boolean;
}

export interface ReferenceArchitectureProductOut {
  product_id: string;
  product_name: string;
  vendor: string;
  ownership: string;
  category: string;
  role: string;
  notes: string | null;
}

export interface ReferenceArchitectureOut {
  id: string;
  org_id: string;
  workspace_id: string;
  name: string;
  slug: string;
  description: string | null;
  architecture_overview: string | null;
  target_segment: string | null;
  created_at: string;
  products: ReferenceArchitectureProductOut[];
}

// ── API ───────────────────────────────────────────────────────────────────

export const catalogApi = {
  // Products
  listProducts: (params?: { vendor?: string; ownership?: string; search?: string }) => {
    const q = new URLSearchParams();
    if (params?.vendor) q.set("vendor", params.vendor);
    if (params?.ownership) q.set("ownership", params.ownership);
    if (params?.search) q.set("search", params.search);
    const qs = q.toString();
    return request<ProductOut[]>(`/catalog/products${qs ? `?${qs}` : ""}`);
  },

  getProduct: (id: string) => request<ProductOut>(`/catalog/products/${id}`),

  // Capabilities
  listCapabilities: () => request<CapabilityOut[]>("/catalog/capabilities"),

  // Reference Architectures
  listReferenceArchitectures: () => request<ReferenceArchitectureOut[]>("/catalog/reference-architectures"),
  getReferenceArchitecture: (id: string) => request<ReferenceArchitectureOut>(`/catalog/reference-architectures/${id}`),

  // Graph
  getPortfolioGraph: () => request<PortfolioGraphOut>("/graph/portfolio"),
  getNeighborhood: (productId: string) => request<NeighborhoodOut>(`/graph/neighborhood/${productId}`),
  queryImpact: (productId: string) => request<GraphQueryOut>(`/graph/query?product_id=${productId}`),
  getIntegrity: () => request<IntegrityReportOut>("/graph/integrity"),
  getCoverage: () => request<CoverageReportOut>("/graph/coverage"),

  // Edges
  listEdges: (params?: { status?: string }) => {
    const q = new URLSearchParams();
    if (params?.status) q.set("status", params.status);
    const qs = q.toString();
    return request<ProductEdgeOut[]>(`/graph/edges${qs ? `?${qs}` : ""}`);
  },

  suggestEdges: () =>
    request<ProductEdgeOut[]>("/graph/suggest-edges", { method: "POST" }),

  approveEdge: (id: string) =>
    request<ProductEdgeOut>(`/graph/edges/${id}/approve`, { method: "POST" }),

  rejectEdge: (id: string, reason: string) =>
    request<ProductEdgeOut>(`/graph/edges/${id}/reject`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason }),
    }),
};
