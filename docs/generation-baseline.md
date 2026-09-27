# Generation baseline

**No live baseline has been recorded yet.**

The numbers previously published here (100% refusal / adversarial) came from `fake-llm-v1` on five cases per set. They are plumbing checks, not quality results: the fake provider refuses whenever context is empty. Keep them as pipeline regression tests.

To record a real baseline:

1. Point `DATABASE_URL` at PostgreSQL with pgvector; set `LLM_PROVIDER=gemini`, `EMBEDDING_PROVIDER=gemini`, `GEMINI_API_KEY`.
2. Retrieval: `cd backend && python ../scripts/run_eval.py --out ../docs/retrieval-baseline-live.md` (defaults to production `TOP_K`).
3. Generation: run the eval sets against the live provider; record refusal rate, adversarial safety, citation precision, and per-citation `support_score` from `app/generation/claim_support.py`.
4. Commit the report with prompt version (`4.3.0`), model id and date. Grow refusal/adversarial sets well past five cases first.
5. Pick release thresholds after this first measurement, then gate releases on them.
