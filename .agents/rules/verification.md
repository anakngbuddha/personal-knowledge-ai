---
trigger: always_on
description: Always run validation and verification tests on every modification or feature update to guarantee working code.
---

# Code Modification & Feature Verification Rules

Every code modification, bug fix, or feature update must be verified with tests and syntax validations before declaring completion.

## Verification Standards

1. **Mandatory Test Execution**:
   - Whenever backend code is modified, run the test suite:
     ```bash
     python -m pytest backend/tests
     ```
   - If tests do not exist for the modified functionality, add regression unit tests in `backend/tests/` to cover new behaviors and edge cases.
   - For complete project verification across Python syntax, backend tests, and frontend build, run:
     ```bash
     python scripts/verify_project.py
     ```

2. **Compilation & Syntax Integrity**:
   - Ensure all modified Python files compile cleanly (`python -m py_compile <file>`).
   - If frontend files (`frontend/src/`) are modified, run `tsc -b` or `npm run build` inside `frontend/` to ensure no TypeScript compilation or type errors.

3. **No Unverified Claims**:
   - Never report that a feature is working or a bug is resolved without executing verification tests and inspecting output logs.
   - If an error or regression occurs during test execution, diagnose and resolve it before completing the turn.
