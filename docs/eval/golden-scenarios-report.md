# Golden scenario report

- Generated: 2026-09-20T10:52:30.246830+00:00
- Catalog source: **backend/app/catalog/seeds.py** (placeholder until real product graph is curated)
- Pass rate: **20/20**

## Path to a real Phase 6.5 sign-off

1. Replace seed data with the real product line (`POST /catalog/seed` or a new seed module).
2. Run `POST /graph/suggest-edges` and **human-approve** edges (`POST /graph/edges/{id}/approve`).
3. Generate a new `docs/eval/golden-scenarios.json` from the approved graph.
4. Re-run this script. The scorer in `backend/app/eval/golden.py` does not change.

## Results

| ID | Passed | Coverage | Hallucinated | Ungrounded | Conflicts | Constraints |
|---|---|---|---|---|---|---|
| gs-01 | True | 1.00 | 0 | 0 | 0 | 0 |
| gs-02 | True | 1.00 | 0 | 0 | 0 | 0 |
| gs-03 | True | 1.00 | 0 | 0 | 0 | 0 |
| gs-04 | True | 1.00 | 0 | 0 | 0 | 0 |
| gs-05 | True | 1.00 | 0 | 0 | 0 | 0 |
| gs-06 | True | 1.00 | 0 | 0 | 0 | 0 |
| gs-07 | True | 1.00 | 0 | 0 | 0 | 0 |
| gs-08 | True | 1.00 | 0 | 0 | 0 | 0 |
| gs-09 | True | 1.00 | 0 | 0 | 0 | 0 |
| gs-10 | True | 1.00 | 0 | 0 | 0 | 0 |
| gs-11 | True | 1.00 | 0 | 0 | 0 | 0 |
| gs-12 | True | 1.00 | 0 | 0 | 0 | 0 |
| gs-13 | True | 1.00 | 0 | 0 | 0 | 0 |
| gs-14 | True | 1.00 | 0 | 0 | 0 | 0 |
| gs-15 | True | 1.00 | 0 | 0 | 0 | 0 |
| gs-16 | True | 1.00 | 0 | 0 | 0 | 0 |
| gs-17 | True | 1.00 | 0 | 0 | 0 | 0 |
| gs-18 | True | 1.00 | 0 | 0 | 0 | 0 |
| gs-19 | True | 1.00 | 0 | 0 | 0 | 0 |
| gs-20 | True | 1.00 | 0 | 0 | 0 | 0 |

All placeholder scenarios passed the deterministic scorer.
