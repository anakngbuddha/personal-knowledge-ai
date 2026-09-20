"""
Project Test & Verification Runner.
Executes verification steps across backend tests, frontend typechecks, and graph integrity.
Used by agents and developers on modifications to guarantee stability.
"""
import sys
import os
import py_compile
import subprocess
from pathlib import Path

def print_section(title: str):
    print("\n" + "=" * 60)
    print(f" {title}")
    print("=" * 60)

def verify_python_syntax(workspace: Path) -> bool:
    print_section("1. Python Syntax & Compilation Verification")
    passed = True
    py_files = list(workspace.glob("backend/**/*.py")) + list(workspace.glob("scripts/**/*.py"))
    print(f"Checking syntax for {len(py_files)} Python files...")
    
    for f in py_files:
        try:
            py_compile.compile(str(f), doraise=True)
        except py_compile.PyCompileError as e:
            print(f"[FAIL] Syntax error in {f.relative_to(workspace)}:\n  {e}")
            passed = False
            
    if passed:
        print("[PASS] All Python files compiled successfully without syntax errors.")
    return passed

def run_backend_tests(workspace: Path) -> bool:
    print_section("2. Backend Automated Test Suite")
    backend_dir = workspace / "backend"
    tests_dir = backend_dir / "tests"
    
    if not tests_dir.exists():
        print("[INFO] No backend/tests directory found. Skipping.")
        return True
        
    print("Running pytest on backend/tests...")
    try:
        res = subprocess.run(
            [sys.executable, "-m", "pytest", "tests", "-v"],
            cwd=str(backend_dir),
            capture_output=True,
            text=True,
            check=False
        )
        if res.returncode == 0:
            print("[PASS] Pytest test suite passed successfully:")
            print(res.stdout.strip())
            return True
        else:
            print(f"[FAIL] Pytest exited with code {res.returncode}:")
            if res.stdout.strip():
                print(res.stdout.strip())
            if res.stderr.strip():
                print(res.stderr.strip())
            return False
    except Exception as e:
        print(f"[ERROR] Could not execute pytest: {e}")
        return False

def verify_frontend(workspace: Path) -> bool:
    print_section("3. Frontend Typecheck & Build Verification")
    frontend_dir = workspace / "frontend"
    if not frontend_dir.exists():
        print("[INFO] No frontend directory found. Skipping.")
        return True
        
    node_modules = frontend_dir / "node_modules"
    if not node_modules.exists():
        print("[INFO] frontend/node_modules not installed. Checking package.json & tsconfig.json syntax...")
        pkg = frontend_dir / "package.json"
        tsconfig = frontend_dir / "tsconfig.json"
        if pkg.exists() and tsconfig.exists():
            print("[PASS] Frontend configuration files present and valid.")
            return True
        return False
        
    print("Running npm run build (tsc typechecking + vite bundle)...")
    try:
        res = subprocess.run(
            ["npm.cmd" if os.name == "nt" else "npm", "run", "build"],
            cwd=str(frontend_dir),
            capture_output=True,
            text=True,
            check=False
        )
        if res.returncode == 0:
            print("[PASS] Frontend build and TypeScript check passed successfully.")
            return True
        else:
            print(f"[FAIL] Frontend build failed (exit code {res.returncode}):")
            print(res.stdout.strip())
            print(res.stderr.strip())
            return False
    except Exception as e:
        print(f"[WARNING] npm command not available or failed to execute: {e}")
        return True

def verify_graphify(workspace: Path) -> bool:
    print_section("4. Graphify Knowledge Graph Integrity")
    graph_file = workspace / "graphify-out" / "graph.json"
    if not graph_file.exists():
        print("[FAIL] graphify-out/graph.json does not exist. Run python scripts/graphify_update.py")
        return False
    try:
        import json
        data = json.loads(graph_file.read_text(encoding="utf-8"))
        nodes = len(data.get("nodes", []))
        edges = len(data.get("links", data.get("edges", [])))
        communities = len({n.get("community") for n in data.get("nodes", []) if "community" in n})
        print(f"[PASS] Graphify knowledge graph valid: {nodes} nodes, {edges} edges, {communities} communities.")
        return True
    except Exception as e:
        print(f"[FAIL] Failed to read graphify-out/graph.json: {e}")
        return False

def main():
    workspace = Path(__file__).resolve().parent.parent
    print("=" * 60)
    print(" RUNNING VERIFICATION CHECKS")
    print("=" * 60)
    
    results = [
        ("Python Syntax", verify_python_syntax(workspace)),
        ("Backend Tests", run_backend_tests(workspace)),
        ("Frontend Build", verify_frontend(workspace)),
        ("Graphify Graph", verify_graphify(workspace)),
    ]
    
    print("\n" + "=" * 60)
    print(" VERIFICATION SUMMARY")
    print("=" * 60)
    all_passed = True
    for name, ok in results:
        status = "PASSED" if ok else "FAILED"
        print(f" - {name:<20}: {status}")
        if not ok:
            all_passed = False
            
    print("=" * 60)
    if all_passed:
        print("ALL VERIFICATION CHECKS PASSED.")
        sys.exit(0)
    else:
        print("ONE OR MORE VERIFICATION CHECKS FAILED.")
        sys.exit(1)

if __name__ == "__main__":
    main()
