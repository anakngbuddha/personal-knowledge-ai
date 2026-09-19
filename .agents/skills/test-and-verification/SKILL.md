---
name: test-and-verification
description: >-
  Use this skill to execute automated tests, syntax checks, typechecking, and regression validations
  on every codebase modification, bug fix, or feature update to guarantee that changes are working.
---

# Test and Verification Skill

This skill defines the end-to-end verification runbook to ensure that every code modification or feature implementation in the Personal Knowledge AI workspace is functionally working, syntactically sound, and regression-free.

## 1. When to Use
- Immediately following any code edit, feature addition, refactoring, or dependency update.
- Before reporting completion to the user.
- Whenever preparing an implementation walkthrough.

## 2. Verification Runbook

Follow these verification steps in order:

### Step 1: Run Unified Project Verification
Run the unified verification script from workspace root:
```bash
python scripts/verify_project.py
```
This executes:
1. Python AST syntax and compilation checks across all backend and script files.
2. Pytest suite in `backend/tests/`.
3. Frontend TypeScript configuration and build checks.
4. Graphify knowledge graph integrity check.

### Step 2: Backend Unit & Integration Tests
For targeted backend testing:
```bash
python -m pytest backend/tests -v
```
To run a specific test file or test function:
```bash
python -m pytest backend/tests/test_chunking.py -v
python -m pytest backend/tests/test_extraction.py -k "test_detect_file_type" -v
```

### Step 3: Frontend Typechecking and Production Build
If frontend files (`frontend/src/` or `frontend/package.json`) were altered:
```bash
# If node_modules exists:
cd frontend && npm run build
# Or directly via tsc:
cd frontend && npx tsc -b
```

### Step 4: Adding Tests for New Features
When adding a new feature (e.g. a new document parser, embedding provider, search filter, or API route):
1. Create or update a corresponding test file in `backend/tests/` (e.g., `test_<feature>.py`).
2. Add test cases covering:
   - Happy path: expected input producing expected output.
   - Boundary & edge cases: empty input, corrupted files, large payload chunks.
   - Error handling: expected exceptions raised when constraints are violated.
3. Re-run `python -m pytest backend/tests` until all assertions pass cleanly.

## 3. Verification Checklist Before Concluding
- [ ] No syntax errors (`py_compile` succeeded).
- [ ] All automated tests pass with 0 failures (`pytest` exited with code 0).
- [ ] Frontend build succeeds without TypeScript errors.
- [ ] Graphify updated and valid (`python scripts/graphify_update.py`).
