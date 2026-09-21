/**
 * 3.4 Writes for the Map screen.
 *
 * Kept apart from catalog.ts on purpose: that file is the read client the graph canvas
 * uses, and this one is everything that changes the map. Products, relationships, use
 * cases / room types / platforms, their links, and the queue of things a read proposed.
 */

import { request } from "./http";

export interface MapContext {
  id: string;
  kind: string;
  reads_as: string;
  name: string;
  slug: string;
  description: string | null;
  aliases: string[];
  curation_status: string;
  is_demo: boolean;
  link_count: number;
}

export interface MapContextLink {
  id: string;
  product_id: string;
  product_name: string;
  context_id: string;
  context_name: string;
  context_kind: string;
  relation_type: string;
  reads_as: string;
  evidence: string;
  confidence: number;
  status: string;
}

export interface RelationWord {
  relation_type: string;
  reads_as: string;
  about: "product" | "context";
}

export interface ReviewSuggestion {
  id: string;
  kind: string;
  source_name: string;
  target_name: string;
  relation_type: string;
  reads_as: string;
  evidence: string;
  confidence: number;
  page_number: number | null;
  from_source: string | null;
}

export interface SuggestedNode {
  id: string;
  name: string;
  kind: string;
  vendor: string | null;
  category: string | null;
  from_source: string | null;
}

export interface ReviewQueue {
  suggestions: ReviewSuggestion[];
  new_products: SuggestedNode[];
  total: number;
}

export interface AcceptResult {
  min_confidence: number;
  relationships_accepted: number;
  context_links_accepted: number;
  products_confirmed: number;
  contexts_confirmed: number;
}

const json = (body: unknown) => ({
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const mapApi = {
  relationWords: () => request<RelationWord[]>("/map/relation-words"),

  // Use cases, room types, platforms
  listContexts: () => request<MapContext[]>("/map/contexts"),
  createContext: (body: { name: string; kind: string; description?: string; aliases?: string[] }) =>
    request<MapContext>("/map/contexts", { method: "POST", ...json(body) }),
  updateContext: (id: string, body: { name?: string; description?: string; aliases?: string[] }) =>
    request<MapContext>(`/map/contexts/${id}`, { method: "PATCH", ...json(body) }),
  deleteContext: (id: string) =>
    request<{ deleted: boolean; links_removed: number }>(`/map/contexts/${id}`, { method: "DELETE" }),

  // Product to use case / room type / platform
  listContextLinks: (productId?: string) =>
    request<MapContextLink[]>(`/map/context-links${productId ? `?product_id=${productId}` : ""}`),
  createContextLink: (body: {
    product_id: string;
    context_id: string;
    relation_type: string;
    evidence: string;
  }) => request<MapContextLink>("/map/context-links", { method: "POST", ...json(body) }),
  deleteContextLink: (id: string) =>
    request<{ deleted: boolean }>(`/map/context-links/${id}`, { method: "DELETE" }),

  // Products
  createProduct: (body: {
    name: string;
    vendor: string;
    category: string;
    ownership?: string;
    lifecycle_status?: string;
    description?: string;
  }) => request<{ id: string; name: string }>("/catalog/products", { method: "POST", ...json(body) }),
  updateProduct: (
    id: string,
    body: { name?: string; vendor?: string; category?: string; lifecycle_status?: string }
  ) => request<{ id: string; name: string }>(`/catalog/products/${id}`, { method: "PATCH", ...json(body) }),
  deleteProduct: (id: string) =>
    request<{ deleted: boolean }>(`/catalog/products/${id}`, { method: "DELETE" }),

  // Relationships between two products
  createEdge: (body: {
    source_product_id: string;
    target_product_id: string;
    relation_type: string;
    evidence: string;
  }) =>
    request<{ id: string }>("/graph/edges", {
      method: "POST",
      ...json({ ...body, confidence: 1.0, status: "approved" }),
    }),
  deleteEdge: (id: string) => request<{ deleted: boolean }>(`/graph/edges/${id}`, { method: "DELETE" }),

  // What a read proposed and nobody has decided on yet
  reviewQueue: () => request<ReviewQueue>("/graph/review-queue"),
  acceptHighConfidence: () =>
    request<AcceptResult>("/graph/accept-high-confidence", { method: "POST", ...json({}) }),
  approveEdge: (id: string) => request<unknown>(`/graph/edges/${id}/approve`, { method: "POST" }),
  rejectEdge: (id: string, reason: string) =>
    request<unknown>(`/graph/edges/${id}/reject`, { method: "POST", ...json({ reason }) }),
  approveContextLink: (id: string) =>
    request<unknown>(`/graph/context-links/${id}/approve`, { method: "POST" }),
  rejectContextLink: (id: string, reason: string) =>
    request<unknown>(`/graph/context-links/${id}/reject`, { method: "POST", ...json({ reason }) }),
};
