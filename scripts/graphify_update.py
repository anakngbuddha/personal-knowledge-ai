"""
Graphify automatic update script.
Re-extracts AST nodes and edges across code files and updates graphify-out/.
Supports standalone execution and Antigravity PostToolUse hook contract (emits {} on stdout).
"""
import sys
import subprocess
from pathlib import Path

def run_update():
    workspace_dir = Path(__file__).resolve().parent.parent
    try:
        cmd = [sys.executable, "-m", "graphify", "update", "."]
        result = subprocess.run(
            cmd,
            cwd=str(workspace_dir),
            capture_output=True,
            text=True,
            check=False
        )
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)

def main():
    is_hook = "--hook" in sys.argv or not sys.stdin.isatty()
    success, stdout, stderr = run_update()
    
    if is_hook:
        # Antigravity PostToolUse hook requires an empty JSON object on stdout
        sys.stdout.write("{}\n")
        sys.stdout.flush()
        if not success and stderr:
            sys.stderr.write(f"[graphify-update] Warning: {stderr}\n")
    else:
        if success:
            print("[graphify-update] Successfully updated graphify knowledge graph.")
            if stdout.strip():
                print(stdout.strip())
        else:
            print(f"[graphify-update] Update failed: {stderr}")
            sys.exit(1)

if __name__ == "__main__":
    main()
