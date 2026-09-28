import type { KnowledgeDocument } from "../types";

export type SourceSort = "modified" | "name";

export function sortKnowledgeDocuments(
  documents: KnowledgeDocument[],
  sort: SourceSort
): KnowledgeDocument[] {
  return [...documents].sort((a, b) => {
    if (sort === "name") {
      return (a.title || a.original_filename).localeCompare(b.title || b.original_filename);
    }
    const aDate = Date.parse(a.processed_at || a.uploaded_at || "") || 0;
    const bDate = Date.parse(b.processed_at || b.uploaded_at || "") || 0;
    return bDate - aDate;
  });
}
