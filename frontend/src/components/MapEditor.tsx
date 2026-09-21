import { useCallback, useEffect, useMemo, useState } from "react";
import { catalogApi, type ProductOut } from "../services/catalog";
import {
  mapApi,
  type MapContext,
  type MapContextLink,
  type RelationWord,
  type ReviewQueue,
} from "../services/mapEdit";

/**
 * 3.4 Edit the map.
 *
 * Everything the map draws can be added, corrected and removed here: products, the
 * relationships between them, the use cases / room types / platforms they are sold
 * against, and the pile of suggestions a source read left behind. No Swagger, no
 * relation names in the UI: every relationship is offered in the words it reads as.
 */

const KINDS: { value: string; label: string }[] = [
  { value: "use_case", label: "Use case" },
  { value: "room_type", label: "Room type" },
  { value: "platform", label: "Platform" },
];

type Draft = { name: string; vendor: string; category: string };

export function MapEditor({ onChanged }: { onChanged?: () => void }) {
  const [products, setProducts] = useState<ProductOut[]>([]);
  const [contexts, setContexts] = useState<MapContext[]>([]);
  const [links, setLinks] = useState<MapContextLink[]>([]);
  const [words, setWords] = useState<RelationWord[]>([]);
  const [queue, setQueue] = useState<ReviewQueue | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const [productDraft, setProductDraft] = useState<Draft>({ name: "", vendor: "", category: "" });
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState<Draft>({ name: "", vendor: "", category: "" });
  const [contextDraft, setContextDraft] = useState({ name: "", kind: "use_case" });
  const [relation, setRelation] = useState({
    source: "",
    target: "",
    relation_type: "integrates_with",
    evidence: "",
  });

  const productWords = useMemo(() => words.filter((w) => w.about === "product"), [words]);
  const contextWords = useMemo(() => words.filter((w) => w.about === "context"), [words]);
  const targetIsContext = useMemo(
    () => contextWords.some((w) => w.relation_type === relation.relation_type),
    [contextWords, relation.relation_type]
  );

  const reload = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const [productList, contextList, linkList, queueOut] = await Promise.all([
        catalogApi.listProducts(),
        mapApi.listContexts(),
        mapApi.listContextLinks(),
        mapApi.reviewQueue(),
      ]);
      setProducts(productList);
      setContexts(contextList);
      setLinks(linkList);
      setQueue(queueOut);
    } catch (e: any) {
      setError(e?.message ?? "The map could not be loaded.");
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    reload();
    mapApi
      .relationWords()
      .then(setWords)
      .catch(() => setWords([]));
  }, [reload]);

  const run = useCallback(
    async (action: () => Promise<unknown>, message?: string) => {
      setBusy(true);
      setError(null);
      setNote(null);
      try {
        await action();
        if (message) setNote(message);
        await reload();
        onChanged?.();
      } catch (e: any) {
        setError(e?.message ?? "That did not go through.");
      } finally {
        setBusy(false);
      }
    },
    [reload, onChanged]
  );

  const addProduct = () => {
    const { name, vendor, category } = productDraft;
    if (name.trim().length < 2) {
      setError("Give the product a name first.");
      return;
    }
    run(
      () =>
        mapApi.createProduct({
          name: name.trim(),
          vendor: vendor.trim() || "Unspecified",
          category: category.trim() || "other",
        }),
      `${name.trim()} is on the map.`
    ).then(() => setProductDraft({ name: "", vendor: "", category: "" }));
  };

  const addContext = () => {
    if (contextDraft.name.trim().length < 2) {
      setError("Give it a name first.");
      return;
    }
    run(
      () => mapApi.createContext({ name: contextDraft.name.trim(), kind: contextDraft.kind }),
      `${contextDraft.name.trim()} is on the map.`
    ).then(() => setContextDraft({ name: "", kind: contextDraft.kind }));
  };

  const addRelation = () => {
    if (!relation.source || !relation.target) {
      setError("Pick both ends of the relationship.");
      return;
    }
    if (relation.evidence.trim().length < 3) {
      setError("Say why, in a sentence. A relationship nobody can check is not worth having.");
      return;
    }
    const evidence = relation.evidence.trim();
    const action = targetIsContext
      ? () =>
          mapApi.createContextLink({
            product_id: relation.source,
            context_id: relation.target,
            relation_type: relation.relation_type,
            evidence,
          })
      : () =>
          mapApi.createEdge({
            source_product_id: relation.source,
            target_product_id: relation.target,
            relation_type: relation.relation_type,
            evidence,
          });
    run(action, "Relationship added.").then(() =>
      setRelation({ ...relation, target: "", evidence: "" })
    );
  };

  const startEdit = (product: ProductOut) => {
    setEditingId(product.id);
    setEditDraft({ name: product.name, vendor: product.vendor, category: product.category });
  };

  const saveEdit = () => {
    if (!editingId) return;
    run(() => mapApi.updateProduct(editingId, editDraft), "Saved.").then(() => setEditingId(null));
  };

  const waiting = queue?.suggestions ?? [];

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <p className="kicker">The map</p>
          <h2>Edit the map</h2>
        </div>
        <button type="button" disabled={busy} onClick={reload}>
          Refresh
        </button>
      </div>

      {error && <div className="banner error">{error}</div>}
      {note && <div className="banner">{note}</div>}

      {/* Waiting on a person ------------------------------------------------ */}
      {waiting.length > 0 && (
        <div className="curation-list">
          <div className="panel-head">
            <h3>Waiting on you ({waiting.length})</h3>
            <button
              type="button"
              disabled={busy}
              onClick={() =>
                run(() => mapApi.acceptHighConfidence(), "Accepted everything we were sure about.")
              }
            >
              Accept all we are confident about
            </button>
          </div>
          {waiting.slice(0, 20).map((item) => (
            <div key={item.id} className="curation-card">
              <div className="curation-relation">
                <span className="curation-source">{item.source_name}</span>
                <span className="curation-arrow"> {item.reads_as} </span>
                <span className="curation-target">{item.target_name}</span>
              </div>
              <p className="curation-evidence">{item.evidence}</p>
              <div className="curation-meta">
                <span className="confidence-pill">{Math.round(item.confidence * 100)}% sure</span>
                {item.from_source && <span className="muted"> from {item.from_source}</span>}
                {item.page_number ? <span className="muted"> page {item.page_number}</span> : null}
              </div>
              <div className="curation-btns">
                <button
                  className="approve-btn"
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    run(
                      () =>
                        item.kind === "context"
                          ? mapApi.approveContextLink(item.id)
                          : mapApi.approveEdge(item.id),
                      "Added to the map."
                    )
                  }
                >
                  Add to map
                </button>
                <button
                  className="reject-btn"
                  type="button"
                  disabled={busy}
                  onClick={() =>
                    run(
                      () =>
                        item.kind === "context"
                          ? mapApi.rejectContextLink(item.id, "Not right for our map")
                          : mapApi.rejectEdge(item.id, "Not right for our map"),
                      "Left off the map."
                    )
                  }
                >
                  Not this one
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Products ----------------------------------------------------------- */}
      <h3>Products ({products.length})</h3>
      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.75rem" }}>
        <input
          placeholder="Product name"
          value={productDraft.name}
          onChange={(e) => setProductDraft({ ...productDraft, name: e.target.value })}
        />
        <input
          placeholder="Brand"
          value={productDraft.vendor}
          onChange={(e) => setProductDraft({ ...productDraft, vendor: e.target.value })}
        />
        <input
          placeholder="What it is"
          value={productDraft.category}
          onChange={(e) => setProductDraft({ ...productDraft, category: e.target.value })}
        />
        <button className="primary" type="button" disabled={busy} onClick={addProduct}>
          Add product
        </button>
      </div>

      {products.length === 0 ? (
        <p className="muted">
          Nothing here yet. Import your product list above, or add the first one by hand.
        </p>
      ) : (
        <ul className="map-products">
          {products.map((product) => (
            <li key={product.id} style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
              {editingId === product.id ? (
                <>
                  <input
                    value={editDraft.name}
                    onChange={(e) => setEditDraft({ ...editDraft, name: e.target.value })}
                  />
                  <input
                    value={editDraft.vendor}
                    onChange={(e) => setEditDraft({ ...editDraft, vendor: e.target.value })}
                  />
                  <input
                    value={editDraft.category}
                    onChange={(e) => setEditDraft({ ...editDraft, category: e.target.value })}
                  />
                  <button type="button" className="primary" disabled={busy} onClick={saveEdit}>
                    Save
                  </button>
                  <button type="button" disabled={busy} onClick={() => setEditingId(null)}>
                    Cancel
                  </button>
                </>
              ) : (
                <>
                  <strong>{product.name}</strong>
                  <span className="muted">
                    {product.vendor} · {product.category}
                  </span>
                  <button type="button" disabled={busy} onClick={() => startEdit(product)}>
                    Edit
                  </button>
                  <button
                    type="button"
                    className="reject-btn"
                    disabled={busy}
                    onClick={() => {
                      if (!window.confirm(`Remove ${product.name} and its relationships?`)) return;
                      run(() => mapApi.deleteProduct(product.id), `${product.name} removed.`);
                    }}
                  >
                    Remove
                  </button>
                </>
              )}
            </li>
          ))}
        </ul>
      )}

      {/* Relationships ------------------------------------------------------ */}
      <h3>Add a relationship</h3>
      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", alignItems: "center" }}>
        <select
          value={relation.source}
          onChange={(e) => setRelation({ ...relation, source: e.target.value })}
        >
          <option value="">Pick a product</option>
          {products.map((product) => (
            <option key={product.id} value={product.id}>
              {product.name}
            </option>
          ))}
        </select>
        <select
          value={relation.relation_type}
          onChange={(e) => setRelation({ ...relation, relation_type: e.target.value, target: "" })}
        >
          {productWords.map((word) => (
            <option key={word.relation_type} value={word.relation_type}>
              {word.reads_as}
            </option>
          ))}
          {contextWords.map((word) => (
            <option key={word.relation_type} value={word.relation_type}>
              {word.reads_as}
            </option>
          ))}
        </select>
        <select
          value={relation.target}
          onChange={(e) => setRelation({ ...relation, target: e.target.value })}
        >
          <option value="">{targetIsContext ? "Pick a use case or platform" : "Pick a product"}</option>
          {(targetIsContext ? contexts : products).map((item: any) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </select>
        <input
          style={{ minWidth: "16rem" }}
          placeholder="Why do we know this?"
          value={relation.evidence}
          onChange={(e) => setRelation({ ...relation, evidence: e.target.value })}
        />
        <button className="primary" type="button" disabled={busy} onClick={addRelation}>
          Add
        </button>
      </div>

      {/* Use cases, room types, platforms ----------------------------------- */}
      <h3>Use cases, room types and platforms ({contexts.length})</h3>
      <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.5rem" }}>
        <input
          placeholder="Name"
          value={contextDraft.name}
          onChange={(e) => setContextDraft({ ...contextDraft, name: e.target.value })}
        />
        <select
          value={contextDraft.kind}
          onChange={(e) => setContextDraft({ ...contextDraft, kind: e.target.value })}
        >
          {KINDS.map((kind) => (
            <option key={kind.value} value={kind.value}>
              {kind.label}
            </option>
          ))}
        </select>
        <button className="primary" type="button" disabled={busy} onClick={addContext}>
          Add
        </button>
      </div>
      {contexts.length === 0 ? (
        <p className="muted">
          None yet. These are the things you sell against: huddle rooms, contact centre,
          Microsoft Teams.
        </p>
      ) : (
        <ul>
          {contexts.map((context) => (
            <li key={context.id} style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
              <strong>{context.name}</strong>
              <span className="muted">
                {context.reads_as} · {context.link_count} linked
              </span>
              <button
                type="button"
                disabled={busy}
                onClick={() => {
                  const next = window.prompt("Rename to", context.name);
                  if (!next || next === context.name) return;
                  run(() => mapApi.updateContext(context.id, { name: next }), "Renamed.");
                }}
              >
                Rename
              </button>
              <button
                type="button"
                className="reject-btn"
                disabled={busy}
                onClick={() => {
                  if (!window.confirm(`Remove ${context.name}?`)) return;
                  run(() => mapApi.deleteContext(context.id), `${context.name} removed.`);
                }}
              >
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}

      {links.length > 0 && (
        <>
          <h3>What suits what ({links.length})</h3>
          <ul>
            {links.map((link) => (
              <li key={link.id} style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                <span>
                  <strong>{link.product_name}</strong> {link.reads_as}{" "}
                  <strong>{link.context_name}</strong>
                </span>
                {link.status !== "approved" && <span className="muted">waiting on you</span>}
                <button
                  type="button"
                  className="reject-btn"
                  disabled={busy}
                  onClick={() => run(() => mapApi.deleteContextLink(link.id), "Removed.")}
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
