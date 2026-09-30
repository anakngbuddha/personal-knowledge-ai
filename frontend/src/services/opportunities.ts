import { request } from "./http";

export interface Opportunity {
  id: string;
  account_id: string | null;
  workspace_id: string;
  owner_id: string | null;
  title: string;
  stage: string;
  currency: string;
  version: number;
  created_at: string;
}

export interface Requirement {
  id: string;
  opportunity_id: string;
  original_text: string;
  acceptance_criterion: string | null;
  priority: "must" | "should" | "could";
  coverage_state: "unreviewed" | "covered" | "partial" | "gap" | "excluded";
  coverage_note: string | null;
  reviewer_id: string | null;
  version: number;
}

export interface Coverage {
  opportunity_id: string;
  requirements: Requirement[];
  total: number;
  limit: number;
  offset: number;
  mandatory_total: number;
  mandatory_covered: number;
  ready_for_quote: boolean;
}

const jsonHeaders = { "Content-Type": "application/json" };

export const opportunityApi = {
  list: (offset = 0) => request<{ items: Opportunity[]; limit: number; offset: number }>(
    `/api/opportunities?limit=50&offset=${offset}`
  ),
  create: (title: string, currency: string) => request<Opportunity>("/api/opportunities", {
    method: "POST", headers: jsonHeaders, body: JSON.stringify({ title, currency }),
  }),
  coverage: (id: string, offset = 0) => request<Coverage>(
    `/api/opportunities/${id}/coverage?limit=50&offset=${offset}`
  ),
  addRequirement: (id: string, text: string, priority: Requirement["priority"]) =>
    request<Requirement>(`/api/opportunities/${id}/requirements`, {
      method: "POST", headers: jsonHeaders,
      body: JSON.stringify({ original_text: text, priority }),
    }),
  importRequirements: (id: string, text: string) =>
    request<{ created: number; requirements: Requirement[] }>(
      `/api/opportunities/${id}/requirements/import`, {
        method: "POST", headers: jsonHeaders, body: JSON.stringify({ text }),
      }
    ),
  reviewRequirement: (
    id: string, requirement: Requirement, state: Requirement["coverage_state"], note: string,
  ) => request<Requirement>(
    `/api/opportunities/${id}/requirements/${requirement.id}`, {
      method: "PATCH", headers: jsonHeaders,
      body: JSON.stringify({
        version: requirement.version, acceptance_criterion: requirement.acceptance_criterion,
        coverage_state: state, coverage_note: note,
      }),
    }
  ),
};
