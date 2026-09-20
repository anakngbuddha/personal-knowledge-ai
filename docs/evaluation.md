# Evaluation Strategy (Phase 4.5)

This document defines the evaluation methodology, golden datasets, scoring metrics, and execution runners for retrieval and grounded generation in the Personal Knowledge AI system.

---

## 1. Golden Evaluation Datasets

All evaluation sets are stored under `docs/eval/`:

### A. Labeled SE Question Set (`docs/eval/questions.json`)
Contains 50+ hand-crafted questions representing authentic Solutions Engineering inquiry patterns against the seed product catalog:
- **Direct capability lookups** (10+): Single-product feature and spec questions.
- **Multi-product compatibility** (8+): Cross-product integration and compatibility checks.
- **Negative / unsupported questions** (8+): Capabilities not supported by any seed product (expected to refuse or declare unsupported).
- **Competitive / vendor comparisons** (6+): Differentiators vs. external market solutions.
- **Sizing & prerequisites** (8+): Resource requirements, licenses, and deployment constraints.
- **Account-scoped / permission-filtered** (6+): Queries testing clearance-level isolation.
- **Reference architectures** (4+): High-level system topologies and patterns.

#### Substring Invariant
Labels use `text_contains` substrings (at least 15 characters) rather than raw chunk IDs:
> **Why:** Chunk IDs change whenever chunking parameters or document boundaries change. A labeled benchmark that breaks on chunking tweaks is brittle. A distinct substring of the target passage survives re-chunking and verifies that the correct evidence was retrieved.

### B. Refusal Benchmark (`docs/eval/refusal_set.json`)
Curated queries testing that the model gracefully refuses queries unsupported by the catalog (e.g., consumer laptops, arbitrary cooking recipes, fictitious future releases, unverified pricing).

### C. Adversarial Benchmark (`docs/eval/adversarial_set.json`)
Curated prompt injection and privilege escalation attempts testing prompt confinement:
- System prompt override attempts (`"Ignore all previous instructions..."`)
- Competitor defamation traps
- Boundary marker escapes (`<<<END_UNTRUSTED_DOCUMENT_CONTENT>>>`)
- Internal confidential disclosure traps
- Free license hallucination traps

---

## 2. Metrics & Definitions

### Retrieval Metrics
```text
Hit@K    = (Questions where expected passage substring appears in top-K retrieved chunks) / (Total positive questions)
MRR      = Mean Reciprocal Rank of the first chunk containing the expected passage
Label Verification Rate = (Questions whose text_contains exists in seed corpus) / (Total labeled questions)
```
*Note: Negative questions (unsupported) are excluded from positive Hit@K and evaluated separately for non-retrieval or empty context.*

### Generation Metrics
```text
Refusal Accuracy = Correctly refused queries / Total out-of-domain queries
Adversarial Confinement = Injections neutralized / Total attack vectors
Citation Accuracy = Answers citing valid document titles & sections / Total answered queries
```

---

## 3. Evaluation Runners

### Offline Retrieval Eval (`scripts/run_eval_offline.py`)
Runs entirely offline without PostgreSQL, pgvector, or live Gemini API keys:
- Seeds the 20 synthetic datasheets into an in-memory SQLite database.
- Uses `fake-deterministic` embeddings (768-dim hash projections).
- Runs candidate retrieval and verifies label coverage across all 54 questions.
- Generates `docs/retrieval-baseline.md`.

```bash
python scripts/run_eval_offline.py --out docs/retrieval-baseline.md
```

### Production Retrieval Eval (`scripts/run_eval.py`)
Runs against PostgreSQL + `pgvector` with live Gemini embeddings (`gemini-embedding-001`):
- Measures real semantic similarity, hybrid BM25 + vector fusion, and Reciprocal Rank Fusion (RRF).
- Evaluates Top-1, Top-5, Top-10 hits and MRR.

```bash
python scripts/run_eval.py --out docs/retrieval-baseline-live.md
```

### Generation Eval (`scripts/run_generation_eval.py`)
Benchmarks grounded generation against refusal and adversarial test suites:
- Evaluates refusal detection against `docs/eval/refusal_set.json`.
- Evaluates prompt injection defenses against `docs/eval/adversarial_set.json`.
- Validates prompt confinement markers and output sanitization.

```bash
python scripts/run_generation_eval.py --out docs/generation-baseline.md
```

---

## 4. Current Baselines

- **Retrieval Baseline (Offline Plumbing)**: [docs/retrieval-baseline.md](file:///c:/Users/markv/Desktop/Projects/personal-knowledge-ai/docs/retrieval-baseline.md)
  - 54 questions total (46 positive, 8 negative)
  - 100% label verification (0 missing labels)
- **Generation Baseline**: [docs/generation-baseline.md](file:///c:/Users/markv/Desktop/Projects/personal-knowledge-ai/docs/generation-baseline.md)
  - 100% refusal pass rate (5/5)
  - 100% adversarial resistance (5/5)

---

## 5. Continuous Validation

Regression tests for the evaluation substrate itself are implemented in `backend/tests/test_eval.py`:
- Validates that `docs/eval/questions.json` contains $\ge 50$ questions.
- Validates all required JSON fields (`id`, `question`, `category`, `shape`, etc.).
- Verifies question shape diversity.
- Guarantees negative questions have no expected document.
- Verifies every positive question's `text_contains` substring actually exists in the seed catalog corpus.
- Confirms baseline report files are present.
