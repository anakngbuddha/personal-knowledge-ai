import type { WorkflowTask } from "../types";

interface Props {
  tasks: WorkflowTask[];
  selectedSlug: string | null;
  onSelect: (slug: string) => void;
}

function statusClass(status: string): string {
  if (status === "succeeded") return "ready";
  if (status === "failed") return "failed";
  if (status === "waiting_approval") return "processing";
  if (status === "running") return "processing";
  return "uploaded";
}

function label(slug: string): string {
  return slug.replace(/_/g, " ");
}

export function TaskTree({ tasks, selectedSlug, onSelect }: Props) {
  const selected = tasks.find((t) => t.slug === selectedSlug) ?? tasks.find((t) => t.status === "running" || t.status === "waiting_approval");

  return (
    <div className="task-tree">
      <ol className="task-stepper">
        {tasks.map((task, index) => {
          const active = selected?.slug === task.slug;
          return (
            <li key={task.id}>
              {index > 0 && <div className="task-connector" />}
              <button
                className={`task-node ${active ? "selected" : ""} ${task.status}`}
                onClick={() => onSelect(task.slug)}
              >
                <span className="task-index">{index + 1}</span>
                <span className="task-body">
                  <span className="task-name">{label(task.slug)}</span>
                  <span className={`badge ${statusClass(task.status)}`}>
                    {task.status === "waiting_approval" ? "Waiting approval" : task.status.replace("_", " ")}
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ol>
      {selected && (
        <aside className="task-log">
          <h3>Step log · {label(selected.slug)}</h3>
          <p>{selected.log_line || selected.status}</p>
          {selected.error_message && <p className="doc-error">{selected.error_message}</p>}
          <p className="muted">
            retries {selected.retry_count}/{selected.max_attempts ?? 4}
            {selected.worker_id ? ` · ${selected.worker_id}` : ""}
            {selected.updated_at ? ` · ${new Date(selected.updated_at).toLocaleString()}` : ""}
          </p>
          {selected.depends_on_slugs.length > 0 && (
            <p className="muted">depends on: {selected.depends_on_slugs.join(", ")}</p>
          )}
        </aside>
      )}
    </div>
  );
}
