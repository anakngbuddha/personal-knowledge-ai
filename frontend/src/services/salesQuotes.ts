import { request } from "./http";

export interface SalesPolicy {
  id: string;
  version: string;
  currency: string;
  max_discount_percent: string;
  min_margin_percent: string;
  tax_percent: string;
}

export interface PriceObservationSummary {
  id: string;
  sku_map_id: string;
  source_kind: string;
  observation: {
    provider: string;
    sku: string;
    region: string;
    unit: string;
    currency: string;
    unit_price: string | null;
    expires_at: string;
  };
}

export interface QuoteVersion {
  id: string;
  quote_id: string;
  number: number;
  status: "draft" | "review" | "approved" | "issued";
  snapshot_sha256: string;
  result: {
    currency: string;
    total: string;
    subtotal: string;
    tax_total: string;
    issueable: boolean;
    blockers: string[];
    lines: Array<{ sku: string; provider: string; total_amount: string; assumption: string }>;
  };
}

const headers = { "Content-Type": "application/json" };

export interface DealSignal { kind: string; message: string; quote_version_id?: string; }

export const salesQuotesApi = {
  signals: (opportunityId: string) => request<{ items: DealSignal[] }>(`/api/sales/opportunities/${opportunityId}/signals?limit=100`),
  policies: () => request<{ items: SalesPolicy[] }>("/api/sales/policies?limit=100"),
  observations: () => request<{ items: PriceObservationSummary[] }>("/api/sales/price-observations?limit=100"),
  quotes: (opportunityId: string) => request<{ items: QuoteVersion[] }>(
    `/api/sales/opportunities/${opportunityId}/quotes?limit=100`
  ),
  create: (opportunityId: string, policyId: string, lines: Array<{
    observation_id: string;
    resource_quantity: string;
    usage_per_resource: string;
    discount_percent: string;
    assumption: string;
  }>) => request<QuoteVersion>(`/api/sales/opportunities/${opportunityId}/quotes`, {
    method: "POST", headers, body: JSON.stringify({ policy_id: policyId, lines }),
  }),
  transition: (versionId: string, action: "submit" | "approve" | "issue") =>
    request<QuoteVersion>(`/api/sales/quote-versions/${versionId}/${action}`, { method: "POST" }),
  customerExport: (versionId: string) => request<Record<string, unknown>>(
    `/api/sales/quote-versions/${versionId}/customer-export`
  ),
  googleSheetsExport: (versionId: string) => request<{ export_id: string; spreadsheet_id: string; url: string }>(
    `/api/sales/quote-versions/${versionId}/export/google-sheets`, { method: "POST" }
  ),
};
