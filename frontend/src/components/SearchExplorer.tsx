import { useState } from "react";
import { api } from "../services/api";
import type { SearchHit, SearchResponse } from "../types";

export function SearchExplorer() {
  const [query, setQuery] = useState("");
  const mode = "hybrid" as const;
  const [approvedOnly, setApprovedOnly] = useState(true);
  const [excludeInjection, setExcludeInjection] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [expandedChunkId, setExpandedChunkId] = useState<string | null>(null);

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    setError(null);
    try {
      const res = await api.search(query.trim(), {
        mode,
        filters: {
          approved_only: approvedOnly,
          exclude_injection_flagged: excludeInjection,
        },
      });
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="search-explorer">
      <div className="stage-head">
        <div>
          <h2>Find a passage</h2>
        </div>
      </div>

      <form onSubmit={handleSearch} className="search-form">
        <div className="search-input-row">
          <input
            type="text"
            className="search-input"
            placeholder="SLA clause, SKU conflict, upgrade path…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <button type="submit" className="primary" disabled={loading || !query.trim()}>
            {loading ? "Searching…" : "Search"}
          </button>
        </div>

        <div className="search-controls">
          <div className="control-group filters">
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={approvedOnly}
                onChange={(e) => setApprovedOnly(e.target.checked)}
              />
              Ready sources only
            </label>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={excludeInjection}
                onChange={(e) => setExcludeInjection(e.target.checked)}
              />
              Skip sources that look like instructions
            </label>
          </div>
        </div>
      </form>

      {error && <div className="banner error">{error}</div>}

      {!result && !error && (
        <div className="empty-desk">
          <p className="kicker">Index</p>
          <h3>Pull passages from the live index.</h3>
          <p>
            Approved-only is on by default — as it should be on a live deal. Expand a hit for the
            the passage and where it came from.
          </p>
        </div>
      )}

      {result && (
        <div className="search-results">
          <div className="search-stats">
            <span>
              {result.candidate_count} candidates · top {result.hits.length} shown
            </span>
            <div className="timing-badges">
              <span className="timing-tag">Total {result.timings_ms.total_ms}ms</span>
              {result.timings_ms.vector_ms !== undefined && (
                <span className="timing-tag">Vector {result.timings_ms.vector_ms}ms</span>
              )}
              {result.timings_ms.keyword_ms !== undefined && (
                <span className="timing-tag">Keyword {result.timings_ms.keyword_ms}ms</span>
              )}
              <span className="timing-tag">RRF fuse {result.timings_ms.fuse_ms}ms</span>
            </div>
          </div>

          {result.hits.length === 0 ? (
            <div className="empty-desk">
              <p className="kicker">No match</p>
              <h3>No passages survived the filter set.</h3>
              <p>Widen the query, or drop approved-only if you are hunting drafts — knowing they are drafts.</p>
            </div>
          ) : (
            <div className="hits-list">
              {result.hits.map((hit: SearchHit, idx: number) => {
                const isExpanded = expandedChunkId === hit.chunk_id;
                return (
                  <div
                    key={hit.chunk_id}
                    className={`hit-card ${isExpanded ? "expanded" : ""}`}
                    onClick={() => setExpandedChunkId(isExpanded ? null : hit.chunk_id)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        setExpandedChunkId(isExpanded ? null : hit.chunk_id);
                      }
                    }}
                    role="button"
                    tabIndex={0}
                  >
                    <div className="hit-header">
                      <div className="hit-title">
                        <span className="rank-num">#{String(idx + 1).padStart(2, "0")}</span>
                        <strong>{hit.document_title || hit.original_filename}</strong>
                        <span className="citation-badge">{hit.citation}</span>
                      </div>
                      <div className="hit-scores">
                        <span className="score-pill">RRF {hit.rrf_score.toFixed(4)}</span>
                        {hit.ranks?.vector !== undefined && (
                          <span className="rank-pill">Vec #{hit.ranks.vector} ({hit.branch_scores?.vector !== undefined ? hit.branch_scores.vector.toFixed(3) : ""})</span>
                        )}
                        {hit.ranks?.keyword !== undefined && (
                          <span className="rank-pill">Key #{hit.ranks.keyword} ({hit.branch_scores?.keyword !== undefined ? hit.branch_scores.keyword.toFixed(3) : ""})</span>
                        )}
                      </div>
                    </div>

                    <div className="hit-provenance">
                      {hit.vendor && <span className="prov-tag">Vendor {hit.vendor}</span>}
                      {hit.approval_state && (
                        <span className={`prov-tag ${hit.approval_state}`}>{hit.approval_state}</span>
                      )}
                      {hit.is_stale ? (
                        <span className="prov-tag stale">Stale</span>
                      ) : (
                        <span className="prov-tag fresh">Fresh</span>
                      )}
                      {hit.file_type && <span className="prov-tag">{hit.file_type}</span>}
                      {hit.sensitivity && <span className="prov-tag">{hit.sensitivity}</span>}
                    </div>

                    <p className={`hit-snippet ${isExpanded ? "full" : ""}`}>{hit.text}</p>
                    <div className="expand-hint">{isExpanded ? "Collapse passage" : "Expand passage"}</div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
