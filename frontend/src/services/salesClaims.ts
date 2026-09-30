import { request } from "./http";

export interface SalesClaim {
  id: string; statement: string; competitor: string | null; source_document_id: string;
  source_anchor: string; source_version: number; source_content_hash: string; valid_until: string;
  status: "draft" | "approved" | "revoked"; version: number; review_reason: string | null;
}
export interface ClaimSource { id: string; title: string; approval_state: string; version: number; }
export interface BattleCardClaim { id: string; statement: string; source: { url: string | null; anchor: string; version: number }; }
const headers = { "Content-Type": "application/json" };
export const salesClaimsApi = {
  list: (id: string, offset = 0) => request<{ items: SalesClaim[] }>(`/api/sales/opportunities/${id}/claims?limit=50&offset=${offset}`),
  sources: (id: string, offset = 0) => request<{ items: ClaimSource[] }>(`/api/sales/opportunities/${id}/claim-sources?limit=50&offset=${offset}`),
  create: (id: string, body: { statement: string; competitor?: string; source_document_id: string; source_anchor: string; valid_until: string }) => request<SalesClaim>(`/api/sales/opportunities/${id}/claims`, { method: "POST", headers, body: JSON.stringify(body) }),
  decide: (id: string, action: "approve" | "revoke", version: number, reason: string) => request<unknown>(`/api/sales/claims/${id}/${action}`, { method: "POST", headers, body: JSON.stringify({ version, reason }) }),
  battleCard: (id: string, offset = 0) => request<{ items: BattleCardClaim[] }>(`/api/sales/opportunities/${id}/battle-card?limit=50&offset=${offset}`),
};
