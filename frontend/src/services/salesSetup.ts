import { request } from "./http";

export type PricingProvider = "azure" | "aws" | "gcp" | "huawei";
export const providerNames: Record<PricingProvider, string> = {
  azure: "Azure", aws: "AWS", gcp: "Google Cloud", huawei: "Huawei Cloud",
};
export interface PricingAccess {
  provider: PricingProvider;
  enabled: boolean;
  has_secret: boolean;
  requires_credentials: boolean;
}
export interface PricingProduct { id: string; name: string; vendor: string; }
export interface SkuMappingInput {
  product_id: string;
  provider: PricingProvider;
  service: string;
  sku: string;
  meter: string | null;
  region: string;
  billing_mode: "pay_per_use";
}
export interface SkuMapping extends SkuMappingInput { id: string; status: "draft" | "approved"; }
export interface HuaweiSpec {
  market: "intl" | "eu";
  project_id: string;
  cloud_service_type: string;
  resource_type: string;
  resource_spec: string;
  region: string;
  usage_factor: string;
  usage_measure_id: number;
  unit: string;
  available_zone?: string;
  resource_size?: string;
  size_measure_id?: number;
}

const json = (body: unknown) => ({ headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
export const salesSetupApi = {
  access: () => request<{ items: PricingAccess[] }>("/api/sales/pricing-credentials"),
  configureAccess: (provider: Exclude<PricingProvider, "azure">, body: { enabled: boolean; secret?: string }) =>
    request<PricingAccess>(`/api/sales/pricing-credentials/${provider}`, { method: "PUT", ...json(body) }),
  products: (offset = 0) => request<{ items: PricingProduct[] }>(`/api/sales/pricing-products?limit=50&offset=${offset}`),
  mappings: (status: "draft" | "approved", offset = 0) =>
    request<{ items: SkuMapping[] }>(`/api/sales/sku-maps?status=${status}&limit=50&offset=${offset}`),
  createMapping: (body: SkuMappingInput) => request<SkuMapping>("/api/sales/sku-maps", { method: "POST", ...json(body) }),
  approveMapping: (id: string) => request<SkuMapping>(`/api/sales/sku-maps/${id}/approve`, { method: "POST" }),
  capture: (id: string, huawei_spec?: HuaweiSpec) =>
    request<{ id: string }>(`/api/sales/sku-maps/${id}/capture-price`, { method: "POST", ...json(huawei_spec ? { huawei_spec } : {}) }),
  createPolicy: (version: string, currency: string) =>
    request<{ id: string }>("/api/sales/policies", { method: "POST", ...json({ version, currency }) }),
};
