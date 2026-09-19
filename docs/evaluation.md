# Evaluation Strategy (Phase 4)

Not implemented yet. Recorded here so the shape is fixed before the measurements start.

## Labeled set

20-30 questions in the `evaluation_questions` table, each with:
expected document, expected page (when available), expected chunk, and a note on why that
passage is the correct evidence.

Use safe material only: public lecture PDFs, public documentation, open educational
material, or documents written specifically for testing.

## Metrics

```text
Top-5 Retrieval Hit Rate = questions with the correct chunk in top 5 / all questions
Citation accuracy        = answers citing the correct document + page/section
```

## Experiments

| ID | Configuration |
|---|---|
| A | Vector only |
| B | Keyword only |
| C | Hybrid + RRF |
| D | Hybrid + reranker (only if C hits a ceiling) |

One variable at a time. Pin `GEMINI_GENERATION_MODEL` and `GEMINI_EMBEDDING_MODEL` for the
duration of a comparison. Provider rate limits are logged as provider failures, not
retrieval failures.

The quality target gets chosen after the first baseline run, not invented before it.
