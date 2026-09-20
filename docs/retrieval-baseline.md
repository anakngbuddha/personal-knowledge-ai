# Retrieval Baseline (Offline)

Recorded 2026-09-20 10:06 UTC. **Offline mode: fake embeddings, SQLite, substring matching.**

> [!NOTE]
> This baseline measures plumbing correctness, not retrieval quality.
> Fake embeddings produce hash vectors with no semantic meaning.
> A quality baseline requires PostgreSQL with real embeddings (`run_eval.py`).

## Pinned Configuration

| Setting | Value |
|---|---|
| Embedding model | `fake-deterministic` |
| Embedding dimensions | 768 |
| Chunk size / overlap | 1200 / 150 |
| Corpus | Phase 4 seed catalog (20 synthetic datasheets) |
| Question set | docs/eval/questions.json |
| top_k | 10 |

## Results

| Configuration | Questions | hit@1 | hit@5 | hit@10 | MRR |
|---|---|---|---|---|---|
| offline-fake-cosine | 46 | 0.04 | 0.17 | 0.54 | 0.135 |

## Label Verification

- **Labels verified** (correct passage exists in corpus): 46
- **Labels unverified** (expected passage not found): 0
- **Negative questions** (no expected document, skipped): 8

## Interpretation

- Hash-based fake vectors have **no semantic relationship** to text content.
  Any non-zero hit rate comes from lucky hash collisions, not retrieval quality.
- The purpose of this baseline is to validate the evaluation pipeline,
  question labels, and scoring logic work end-to-end.
- **Label verification** confirms that every labeled question has a matching
  passage somewhere in the seeded corpus. A label-verified count below the
  total signals a labeling error or a missing seed document.
- The quality target is set **after** running `run_eval.py` against PostgreSQL
  with real Gemini embeddings, not before.
