"""
Graphify PreInvocation hook script.
Executed by Antigravity prior to model invocation to ensure graphify context
is triggered on every incoming prompt.
Outputs JSON conforming to the PreInvocation lifecycle contract.
"""
import sys
import json
from pathlib import Path

def get_graph_stats(workspace_dir: Path):
    graph_path = workspace_dir / "graphify-out" / "graph.json"
    if not graph_path.exists():
        return None
    try:
        data = json.loads(graph_path.read_text(encoding="utf-8"))
        nodes = len(data.get("nodes", []))
        edges = len(data.get("edges", []))
        return nodes, edges
    except Exception:
        return None

def main():
    workspace_dir = Path(__file__).resolve().parent.parent
    stats = get_graph_stats(workspace_dir)
    
    if stats:
        nodes, edges = stats
        message = (
            f"[Graphify Active] Codebase knowledge graph loaded ({nodes} nodes, {edges} edges). "
            f"On this prompt, consult Graphify before answering or modifying code: "
            f"run `python -m graphify query \"<question>\"` or inspect `graphify-out/graph.json` / `graphify-out/GRAPH_REPORT.md`."
        )
    else:
        message = (
            "[Graphify Active] Knowledge graph is initialized. Consult Graphify or run "
            "`python -m graphify update .` to index new components before modifying code."
        )
        
    payload = {
        "injectSteps": [
            {
                "ephemeralMessage": message
            }
        ]
    }
    
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()

if __name__ == "__main__":
    main()
