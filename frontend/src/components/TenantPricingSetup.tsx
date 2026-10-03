import { useCallback, useEffect, useState } from "react";
import { salesSetupApi, providerNames } from "../services/salesSetup";
import type { HuaweiSpec, PricingAccess, PricingProduct, PricingProvider, SkuMapping } from "../services/salesSetup";
import { salesQuotesApi } from "../services/salesQuotes";
import type { SalesPolicy } from "../services/salesQuotes";

const providers: PricingProvider[] = ["azure", "aws", "huawei", "gcp"];
const errorText = (err: unknown) => err instanceof Error ? err.message : "The request failed. Try again.";
const textField = (data: FormData, name: string) => String(data.get(name) ?? "").trim();

function ProviderAccessForm({ provider, access, onSaved }: {
  provider: PricingProvider; access?: PricingAccess; onSaved: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [secret, setSecret] = useState("");
  const [keyId, setKeyId] = useState("");
  const [sessionToken, setSessionToken] = useState("");

  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (provider === "azure") return;
    const value = provider === "aws" ? JSON.stringify({ access_key_id: keyId.trim(), secret_access_key: secret,
      ...(sessionToken.trim() ? { session_token: sessionToken.trim() } : {}) }) : secret.trim();
    setSecret(""); setKeyId(""); setSessionToken("");
    setBusy(true); setError(null); setMessage(null);
    try {
      await salesSetupApi.configureAccess(provider, { enabled: true, secret: value });
      await onSaved();
      setMessage("Credentials saved. Capture a price below to verify live access.");
    } catch (err) { setError(errorText(err)); }
    finally { setBusy(false); }
  }

  async function toggle() {
    if (provider === "azure") return;
    setBusy(true); setError(null); setMessage(null);
    try {
      await salesSetupApi.configureAccess(provider, { enabled: !access?.enabled });
      await onSaved();
      setMessage(access?.enabled ? "Pricing access disabled." : "Pricing access enabled. Capture a price to verify live access.");
    } catch (err) { setError(errorText(err)); }
    finally { setBusy(false); }
  }

  return <div className="pricing-access-form">
    <h3>{providerNames[provider]} access</h3>
    {error && <div className="banner error" role="alert">{error}</div>}
    {message && <p role="status">{message}</p>}
    {provider === "azure" ? <p>Azure public retail pricing needs no tenant credentials. Create and approve an exact SKU and meter mapping, then capture its price.</p> : <>
      <p>{access?.has_secret ? (access.enabled ? "Credentials saved · access enabled" : "Credentials saved · access disabled") : "Credentials not configured"}</p>
      <form className="opportunities-form" onSubmit={save}>
        {provider === "aws" && <><label htmlFor="pricing-key-id">AWS access key ID</label>
          <input id="pricing-key-id" value={keyId} onChange={(event) => setKeyId(event.target.value)} minLength={16} maxLength={128} autoComplete="off" required />
          <p className="muted">Use tenant credentials with Price List Query access. Temporary credentials also need a session token.</p></>}
        {provider === "gcp" && <p className="muted">Paste the tenant service-account JSON with Cloud Billing API access.</p>}
        {provider === "huawei" && <p className="muted">Use a tenant IAM token for price inquiry. Replace the token before it expires.</p>}
        <label htmlFor="pricing-secret">{provider === "aws" ? "AWS secret access key" : provider === "gcp" ? "Google Cloud service-account JSON" : "Huawei IAM token"}</label>
        {provider === "gcp" ? <textarea id="pricing-secret" value={secret} onChange={(event) => setSecret(event.target.value)} maxLength={16384} autoComplete="off" spellCheck={false} required />
          : <input id="pricing-secret" type="password" value={secret} onChange={(event) => setSecret(event.target.value)} minLength={provider === "aws" ? 16 : 1} maxLength={provider === "aws" ? 256 : 8192} autoComplete="new-password" required />}
        {provider === "aws" && <><label htmlFor="pricing-session-token">AWS session token (optional)</label>
          <input id="pricing-session-token" type="password" value={sessionToken} onChange={(event) => setSessionToken(event.target.value)} maxLength={8192} autoComplete="new-password" /></>}
        <p className="muted">Credentials are encrypted for this tenant. Saved secrets cannot be viewed here.</p>
        <button type="submit" disabled={busy || !secret.trim() || (provider === "aws" && !keyId.trim())}>{busy ? "Saving…" : access?.has_secret ? "Replace credentials" : "Save credentials"}</button>
      </form>
      {access?.has_secret && <button className="battle-secondary" type="button" disabled={busy} onClick={toggle}>{access.enabled ? "Disable pricing access" : "Enable pricing access"}</button>}
    </>}
  </div>;
}

const mappingHints: Record<PricingProvider, { service: string; sku: string; meter: string; region: string }> = {
  azure: { service: "Exact service name", sku: "ARM SKU name", meter: "Exact meter name (required)", region: "ARM region name" },
  aws: { service: "AWS service code", sku: "Exact product SKU", meter: "Rate code (required for multiple dimensions)", region: "Product region code" },
  gcp: { service: "Cloud Billing service ID", sku: "Exact SKU ID", meter: "Leave empty for Google Cloud", region: "Service region code" },
  huawei: { service: "Cloud service type code", sku: "Resource specification code", meter: "Resource type code (required)", region: "Resource region code" },
};

export function TenantPricingSetup({ onChanged }: { onChanged: () => void }) {
  const [access, setAccess] = useState<PricingAccess[]>([]);
  const [provider, setProvider] = useState<PricingProvider>("azure");
  const [products, setProducts] = useState<PricingProduct[]>([]);
  const [productOffset, setProductOffset] = useState(0);
  const [mappings, setMappings] = useState<SkuMapping[]>([]);
  const [mappingStatus, setMappingStatus] = useState<"draft" | "approved">("draft");
  const [mappingOffset, setMappingOffset] = useState(0);
  const [policies, setPolicies] = useState<SalesPolicy[]>([]);
  const [policyOffset, setPolicyOffset] = useState(0);
  const [captureTarget, setCaptureTarget] = useState<SkuMapping | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [reload, setReload] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const reloadAccess = useCallback(async () => setAccess((await salesSetupApi.access()).items), []);
  const reloadMappings = useCallback(async () => setMappings((await salesSetupApi.mappings(mappingStatus, mappingOffset)).items), [mappingStatus, mappingOffset]);
  const reloadPolicies = useCallback(async () => setPolicies((await salesQuotesApi.policies(policyOffset)).items), [policyOffset]);

  useEffect(() => {
    let active = true;
    setLoading(true); setError(null);
    Promise.all([salesSetupApi.access(), salesSetupApi.products(productOffset), salesSetupApi.mappings(mappingStatus, mappingOffset), salesQuotesApi.policies(policyOffset)])
      .then(([a, p, m, c]) => { if (active) { setAccess(a.items); setProducts(p.items); setMappings(m.items); setPolicies(c.items); } })
      .catch((err: unknown) => { if (active) setError(errorText(err)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [productOffset, mappingStatus, mappingOffset, policyOffset, reload]);

  async function act(operation: () => Promise<void>) {
    setBusy(true); setError(null); setMessage(null);
    try { await operation(); onChanged(); }
    catch (err) { setError(errorText(err)); }
    finally { setBusy(false); }
  }

  function createMapping(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    void act(async () => {
      await salesSetupApi.createMapping({ product_id: textField(data, "product_id"), provider,
        service: textField(data, "service"), sku: textField(data, "sku"), meter: textField(data, "meter") || null,
        region: textField(data, "region"), billing_mode: "pay_per_use" });
      form.reset(); setMappingStatus("draft"); setMappingOffset(0);
      if (mappingStatus === "draft" && mappingOffset === 0) await reloadMappings();
      setMessage("Mapping saved as a draft. Review its dimensions below, then approve it before capturing a price.");
    });
  }

  function captureHuawei(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!captureTarget) return;
    const data = new FormData(event.currentTarget);
    const mapping = captureTarget;
    const size = textField(data, "resource_size");
    const spec: HuaweiSpec = {
      market: textField(data, "market") as "intl" | "eu", project_id: textField(data, "project_id"),
      cloud_service_type: mapping.service, resource_type: mapping.meter!, resource_spec: mapping.sku, region: mapping.region,
      usage_factor: textField(data, "usage_factor"), usage_measure_id: Number(data.get("usage_measure_id")), unit: textField(data, "unit"),
      ...(textField(data, "available_zone") ? { available_zone: textField(data, "available_zone") } : {}),
      ...(size ? { resource_size: size, size_measure_id: Number(data.get("size_measure_id")) } : {}),
    };
    if (Boolean(size) !== Boolean(textField(data, "size_measure_id"))) {
      setError("Enter resource size and size measure ID together, or leave both empty."); return;
    }
    void act(async () => { await salesSetupApi.capture(mapping.id, spec); setCaptureTarget(null); setMessage("Huawei Cloud public price captured. It is now available in Quotes for the matching currency."); });
  }

  return <section className="tenant-pricing-setup" aria-label="Tenant pricing setup">
    <p className="battle-intro">Configure pricing access for your organization, review cloud mappings, and capture the public prices used in quotations. Tenant administrators manage these settings.</p>
    {loading && <p role="status">Loading tenant setup…</p>}
    {error && <div className="banner error" role="alert">{error}<button type="button" className="battle-secondary" disabled={busy || loading} onClick={() => setReload((value) => value + 1)}>Reload tenant setup</button></div>}
    {message && <p className="battle-feedback" role="status">{message}</p>}
    <section className="battle-setup-section" aria-labelledby="tenant-access-title">
      <h2 id="tenant-access-title">Tenant access</h2>
      <p className="muted">Saved credentials indicate configuration only. A successful price capture confirms access for that resource.</p>
      <div className="battle-provider-list" aria-label="Cloud providers">
        {providers.map((item) => {
          const state = access.find((row) => row.provider === item);
          return <button type="button" key={item} aria-pressed={provider === item} onClick={() => setProvider(item)}>
            <strong>{providerNames[item]}</strong><span>{item === "azure" ? "Public pricing" : state ? state.has_secret ? state.enabled ? "Configured" : "Disabled" : "Needs credentials" : "Status unavailable"}</span>
          </button>;
        })}
      </div>
      <ProviderAccessForm key={provider} provider={provider} access={access.find((item) => item.provider === provider)} onSaved={reloadAccess} />
    </section>
    <section className="battle-setup-section" aria-labelledby="sku-setup-title">
      <h2 id="sku-setup-title">SKU mappings &amp; approval</h2>
      <p className="muted">Map a confirmed, generally available catalog product to an exact cloud resource. Only approved mappings can supply quote prices. Current adapters support public pay-per-use pricing.</p>
      <details className="battle-details"><summary>Add {providerNames[provider]} mapping</summary>
        <form key={`${provider}-${productOffset}`} className="opportunities-form" onSubmit={createMapping}>
          <label htmlFor="mapping-product">Catalog product</label>
          <select id="mapping-product" name="product_id" required defaultValue=""><option value="">Choose an approved product</option>{products.map((product) => <option key={product.id} value={product.id}>{product.name} · {product.vendor}</option>)}</select>
          {products.length === 0 && !loading && <p className="muted">No eligible products on this page. Confirm a generally available product in Knowledge Map before mapping it.</p>}
          <div className="battle-pagination"><button type="button" disabled={busy || loading || productOffset === 0} onClick={() => setProductOffset(Math.max(0, productOffset - 50))}>Previous products</button><button type="button" disabled={busy || loading || products.length < 50} onClick={() => setProductOffset(productOffset + 50)}>More products</button></div>
          {(["service", "sku", "meter", "region"] as const).map((field) => <div className="battle-field" key={field}>
            <label htmlFor={`mapping-${field}`}>{field === "sku" ? "SKU / specification" : field === "meter" ? "Meter / resource type" : field === "service" ? "Service" : "Region"}</label>
            <input id={`mapping-${field}`} name={field} placeholder={mappingHints[provider][field]} maxLength={field === "sku" || field === "meter" ? 255 : 128} required={field !== "meter" || provider === "azure" || provider === "huawei"} disabled={field === "meter" && provider === "gcp"} />
          </div>)}
          <button type="submit" disabled={busy || loading || !products.length}>Save draft mapping</button>
        </form>
      </details>
      <nav className="battle-switcher" aria-label="Mapping status">
        <button type="button" aria-pressed={mappingStatus === "draft"} disabled={busy} onClick={() => { setMappingStatus("draft"); setMappingOffset(0); setCaptureTarget(null); }}>Pending approval</button>
        <button type="button" aria-pressed={mappingStatus === "approved"} disabled={busy} onClick={() => { setMappingStatus("approved"); setMappingOffset(0); }}>Approved mappings</button>
      </nav>
      {!loading && mappings.length === 0 && <p className="muted">No {mappingStatus} mappings on this page.</p>}
      {mappings.map((mapping) => <article className="battle-mapping" key={mapping.id}>
        <div><strong>{providerNames[mapping.provider]} · {mapping.sku}</strong><p>{mapping.service} · {mapping.region} · {mapping.meter || "SKU rate"} · pay-per-use</p></div>
        {mapping.status === "draft" ? <button type="button" disabled={busy || loading} onClick={() => void act(async () => { await salesSetupApi.approveMapping(mapping.id); await reloadMappings(); setMessage("Mapping approved. Find it under Approved mappings to capture a price."); })}>Approve mapping</button>
          : <button type="button" disabled={busy || loading || (mapping.provider !== "azure" && !access.some((item) => item.provider === mapping.provider && item.enabled && item.has_secret))} onClick={() => {
            if (mapping.provider === "huawei") { setCaptureTarget(mapping); return; }
            void act(async () => { await salesSetupApi.capture(mapping.id); setMessage(`${providerNames[mapping.provider]} public price captured. It is now available in Quotes for the matching currency.`); });
          }}>Capture price</button>}
      </article>)}
      <div className="battle-pagination"><button type="button" disabled={busy || loading || mappingOffset === 0} onClick={() => { setMappingOffset(Math.max(0, mappingOffset - 50)); setCaptureTarget(null); }}>Previous mappings</button><button type="button" disabled={busy || loading || mappings.length < 50} onClick={() => { setMappingOffset(mappingOffset + 50); setCaptureTarget(null); }}>More mappings</button></div>
      {captureTarget && <form key={captureTarget.id} className="opportunities-form battle-huawei-capture" onSubmit={captureHuawei} aria-label="Huawei resource capture">
        <h3>Capture Huawei Cloud price</h3><p>{captureTarget.sku} · {captureTarget.region}. Resource codes use the approved mapping above.</p>
        <label htmlFor="huawei-market">Market</label><select id="huawei-market" name="market"><option value="intl">International</option><option value="eu">Europe</option></select>
        {(["project_id", "usage_factor", "usage_measure_id", "unit", "available_zone", "resource_size", "size_measure_id"] as const).map((field) => {
          const labels = { project_id: "Project ID", usage_factor: "Usage factor", usage_measure_id: "Usage measure ID", unit: "Price unit", available_zone: "Availability zone (optional)", resource_size: "Resource size (optional)", size_measure_id: "Size measure ID (with resource size)" };
          const numeric = field === "usage_measure_id" || field === "size_measure_id" || field === "resource_size";
          return <div className="battle-field" key={field}><label htmlFor={`huawei-${field}`}>{labels[field]}</label><input id={`huawei-${field}`} name={field} type={numeric ? "number" : "text"} min={field === "resource_size" ? "0.000001" : numeric ? "1" : undefined} max={field.includes("measure_id") ? "9999" : undefined} step={field === "resource_size" ? "any" : numeric ? "1" : undefined} maxLength={field === "project_id" || field === "unit" || field === "available_zone" ? 64 : 128} required={["project_id", "usage_factor", "usage_measure_id", "unit"].includes(field)} /></div>;
        })}
        <button type="submit" disabled={busy}>Capture Huawei price</button><button type="button" className="battle-secondary" disabled={busy} onClick={() => setCaptureTarget(null)}>Cancel capture</button>
      </form>}
    </section>
    <section className="battle-setup-section" aria-labelledby="pricing-policy-title">
      <h2 id="pricing-policy-title">List-price policies</h2><p className="muted">Create a policy in the same currency as the opportunity and captured prices. New policies use zero tax, discount, and margin adjustment.</p>
      <form className="opportunities-form" onSubmit={(event) => {
        event.preventDefault(); const form = event.currentTarget; const data = new FormData(form);
        void act(async () => { await salesSetupApi.createPolicy(textField(data, "version"), textField(data, "currency")); form.reset(); setPolicyOffset(0); if (policyOffset === 0) await reloadPolicies(); setMessage("List-price policy created. Select it in Quotes for the matching currency."); });
      }}>
        <label htmlFor="policy-version">Policy version</label><input id="policy-version" name="version" maxLength={64} placeholder="For example, list-price-v1" required />
        <label htmlFor="policy-currency">Policy currency</label><input id="policy-currency" name="currency" defaultValue="USD" pattern="[A-Z]{3}" maxLength={3} required />
        <button type="submit" disabled={busy || loading}>Create list-price policy</button>
      </form>
      <ul className="battle-policy-list">{policies.map((policy) => <li key={policy.id}>{policy.version} · {policy.currency}{Number(policy.tax_percent) || Number(policy.max_discount_percent) || Number(policy.min_margin_percent) ? " · incompatible with new list-price quotes" : " · list price"}</li>)}</ul>
      {!loading && policies.length === 0 && <p className="muted">No policies on this page.</p>}
      <div className="battle-pagination"><button type="button" disabled={busy || loading || policyOffset === 0} onClick={() => setPolicyOffset(Math.max(0, policyOffset - 100))}>Previous policies</button><button type="button" disabled={busy || loading || policies.length < 100} onClick={() => setPolicyOffset(policyOffset + 100)}>More policies</button></div>
    </section>
  </section>;
}
