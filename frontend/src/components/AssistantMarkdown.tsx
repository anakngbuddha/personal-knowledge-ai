import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";
import type { SourceMetadata } from "../types";

function prepare(text: string): string {
  return text.replace(/\[source_(\d+)\]/g, "[$1](#cite-$1)");
}

export function AssistantMarkdown({
  text,
  citations,
  onSelect,
}: {
  text: string;
  citations: SourceMetadata[];
  onSelect: (source: SourceMetadata) => void;
}) {
  return (
    <div className="message-body markdown-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeSanitize]}
        components={{
          a: ({ href, children }: { href?: string; children?: React.ReactNode }) => {
            if (href?.startsWith("#cite-")) {
              const n = Number(href.slice(6));
              const src = citations[n - 1];
              return (
                <button
                  type="button"
                  className="cite-chip"
                  title={src?.citation || `Source ${n}`}
                  onClick={() => src && onSelect(src)}
                >
                  {n}
                </button>
              );
            }
            return (
              <a href={href} target="_blank" rel="noreferrer">
                {children}
              </a>
            );
          },
        }}
      >
        {prepare(text)}
      </ReactMarkdown>
    </div>
  );
}
