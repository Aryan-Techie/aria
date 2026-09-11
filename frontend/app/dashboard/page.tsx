"use client";

import { useCallback, useEffect, useState } from "react";
import { Logo } from "@/components/Logo";
import {
  approveDiscount,
  createProduct,
  fetchCapacity,
  fetchInbox,
  fetchLeads,
  fetchProducts,
  fetchTasks,
  type CapacitySnapshot,
  type EscalationRecord,
  type LeadRecord,
  type ProductDraft,
  type ProductListing,
  type TaskRecord,
} from "@/lib/api";

const emptyDraft: ProductDraft = { name: "", category: "", price_usd: 0, description: "", stock_qty: 0 };

/** The dashboard's own copy of DealCard's approval control - same
 * .approve-row/.pct vocabulary, since this signs off the same escalation
 * the console's DealCard would, just from the other surface. */
function ApproveDiscountRow({ escalationId, onApproved }: { escalationId: string; onApproved: () => void }) {
  const [pct, setPct] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const approve = async () => {
    const value = Number(pct);
    if (!pct || Number.isNaN(value)) return;
    setSubmitting(true);
    setError(null);
    try {
      await approveDiscount(escalationId, value);
      onApproved();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="approve-row" style={{ marginTop: 6 }}>
      <input
        className="pct"
        type="number"
        min={0}
        max={18}
        step={0.5}
        placeholder="%"
        value={pct}
        onChange={(e) => setPct(e.target.value)}
        aria-label="Discount percent to approve"
      />
      <button className="primary small" onClick={approve} disabled={submitting}>
        {submitting ? "Signing…" : "Approve"}
      </button>
      {error && (
        <span className="tone-bad" style={{ marginLeft: 8 }}>
          {error}
        </span>
      )}
    </div>
  );
}

export default function DashboardPage() {
  const [capacity, setCapacity] = useState<CapacitySnapshot | null>(null);
  const [leads, setLeads] = useState<LeadRecord[]>([]);
  const [inbox, setInbox] = useState<EscalationRecord[]>([]);
  const [products, setProducts] = useState<ProductListing[]>([]);
  const [tasks, setTasks] = useState<TaskRecord[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [draft, setDraft] = useState<ProductDraft>(emptyDraft);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [savedName, setSavedName] = useState<string | null>(null);

  const [leadSearch, setLeadSearch] = useState("");
  const [leadStatus, setLeadStatus] = useState("all");

  const load = useCallback(async () => {
    // allSettled, not all - one source failing (e.g. EspoCRM rejecting the
    // products entity) must not blank the four sections that loaded fine.
    const [cap, leadRows, inboxRows, productRows, taskRows] = await Promise.allSettled([
      fetchCapacity(),
      fetchLeads(),
      fetchInbox(),
      fetchProducts(),
      fetchTasks(),
    ]);
    if (cap.status === "fulfilled") setCapacity(cap.value);
    if (leadRows.status === "fulfilled") setLeads(leadRows.value);
    if (inboxRows.status === "fulfilled") setInbox(inboxRows.value);
    if (productRows.status === "fulfilled") setProducts(productRows.value);
    if (taskRows.status === "fulfilled") setTasks(taskRows.value);

    const failed = [cap, leadRows, inboxRows, productRows, taskRows].find((r) => r.status === "rejected") as
      | PromiseRejectedResult
      | undefined;
    setLoadError(failed ? (failed.reason instanceof Error ? failed.reason.message : String(failed.reason)) : null);
  }, []);

  useEffect(() => {
    void load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [load]);

  const openEscalations = inbox.filter((e) => !e.resolved_at);

  const leadStatuses = Array.from(new Set(leads.map((l) => l.status))).sort();
  const filteredLeads = leads.filter((lead) => {
    if (leadStatus !== "all" && lead.status !== leadStatus) return false;
    if (leadSearch) {
      const q = leadSearch.toLowerCase();
      const hay = `${lead.name ?? ""} ${lead.company ?? ""}`.toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });

  const submitProduct = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!draft.name || !draft.price_usd) return;
    setSaving(true);
    setSaveError(null);
    try {
      const saved = await createProduct(draft);
      setSavedName(saved.name);
      setDraft(emptyDraft);
      await load();
      setTimeout(() => setSavedName(null), 3000);
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="app">
      <header className="top">
        <div className="brand">
          <Logo size={24} />
          <span>Aria</span>
          <span className="sub">Dashboard</span>
        </div>
        <div className="actions">
          <a href="/" className="ghost">
            Console
          </a>
        </div>
      </header>

      <main className="stage" style={{ display: "block", padding: "24px 28px", maxWidth: 1100, margin: "0 auto" }}>
        {loadError && (
          <p className="tone-bad" style={{ marginBottom: 16 }}>
            {loadError}
          </p>
        )}

        <section className="card" style={{ marginBottom: 20 }}>
          <h3>Capacity</h3>
          <div className="stats">
            <div className="stat">
              <div className="k">Calls total</div>
              <div className="v">{capacity?.calls_total ?? "—"}</div>
            </div>
            <div className="stat">
              <div className="k">Live now</div>
              <div className="v">{capacity?.calls_live_now ?? "—"}</div>
            </div>
            <div className="stat">
              <div className="k">Peak concurrent</div>
              <div className="v">{capacity?.peak_concurrent_calls ?? "—"}</div>
            </div>
            <div className="stat">
              <div className="k">Meetings booked</div>
              <div className="v">{capacity?.meetings_booked ?? "—"}</div>
            </div>
          </div>
        </section>

        <section className="card" style={{ marginBottom: 20 }}>
          <h3>Leads</h3>
          <div style={{ display: "flex", gap: 8, marginBottom: 10, flexWrap: "wrap" }}>
            <input
              placeholder="Search name or company…"
              value={leadSearch}
              onChange={(e) => setLeadSearch(e.target.value)}
              style={{ flex: "1 1 200px" }}
              aria-label="Search leads"
            />
            <select value={leadStatus} onChange={(e) => setLeadStatus(e.target.value)} aria-label="Filter by status">
              <option value="all">All statuses</option>
              {leadStatuses.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
          <div className="list">
            {leads.length === 0 ? (
              <p className="empty">No leads yet.</p>
            ) : filteredLeads.length === 0 ? (
              <p className="empty">No leads match that filter.</p>
            ) : (
              <ul>
                {filteredLeads.map((lead) => (
                  <li key={lead.id}>
                    {lead.name ?? "Unnamed"}
                    {lead.company ? ` · ${lead.company}` : ""}
                    {" · "}
                    <span className="pill info">{lead.status}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>

        <section className="card" style={{ marginBottom: 20 }}>
          <h3>Open escalations</h3>
          <div className="list risk">
            {openEscalations.length === 0 ? (
              <p className="empty">Nothing waiting on a person right now.</p>
            ) : (
              <ul>
                {openEscalations.map((esc) => (
                  <li key={esc.id}>
                    {esc.brief.issue} — {esc.reason}
                    <span className="pill warn" style={{ marginLeft: 8 }}>
                      {esc.kind === "deal_approval" ? "Approval needed" : "Handoff"}
                    </span>
                    {esc.kind === "deal_approval" && (
                      <ApproveDiscountRow escalationId={esc.id} onApproved={() => void load()} />
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>

        <section className="card" style={{ marginBottom: 20 }}>
          <h3>Follow-ups</h3>
          <div className="list">
            {tasks.length === 0 ? (
              <p className="empty">Nothing scheduled for later.</p>
            ) : (
              <ul>
                {tasks.map((t) => (
                  <li key={t.id}>
                    {t.note}
                    {t.due ? ` · due ${t.due}` : ""}
                    {t.completed && (
                      <span className="pill good" style={{ marginLeft: 8 }}>
                        Done
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>

        <section className="card" style={{ marginBottom: 20 }}>
          <h3>Products</h3>
          <div className="story-pill-row">
            {products.map((p) => (
              <span className="pill info" key={p.name}>
                {p.name}
                {p.price_usd != null ? ` — $${p.price_usd}` : ""}
                {p.stock_qty != null ? ` · ${p.stock_qty} in stock` : ""}
              </span>
            ))}
          </div>
        </section>

        <section className="card">
          <h3>
            Add a product
            {savedName && <span className="tone-good" style={{ marginLeft: 8 }}>{savedName} added</span>}
          </h3>
          <form onSubmit={submitProduct}>
            <div className="edit-fields">
              <div>
                <label htmlFor="p-name">Name</label>
                <input
                  id="p-name"
                  value={draft.name}
                  onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))}
                  required
                />
              </div>
              <div>
                <label htmlFor="p-category">Category</label>
                <input
                  id="p-category"
                  value={draft.category ?? ""}
                  onChange={(e) => setDraft((d) => ({ ...d, category: e.target.value }))}
                />
              </div>
              <div>
                <label htmlFor="p-price">Price (USD)</label>
                <input
                  id="p-price"
                  type="number"
                  min={0}
                  value={draft.price_usd || ""}
                  onChange={(e) => setDraft((d) => ({ ...d, price_usd: Number(e.target.value) }))}
                  required
                />
              </div>
              <div>
                <label htmlFor="p-stock">Stock qty</label>
                <input
                  id="p-stock"
                  type="number"
                  min={0}
                  value={draft.stock_qty ?? 0}
                  onChange={(e) => setDraft((d) => ({ ...d, stock_qty: Number(e.target.value) }))}
                />
              </div>
              <div>
                <label htmlFor="p-desc">Description</label>
                <input
                  id="p-desc"
                  value={draft.description ?? ""}
                  onChange={(e) => setDraft((d) => ({ ...d, description: e.target.value }))}
                />
              </div>
            </div>
            <div className="edit-actions">
              <button className="primary small" type="submit" disabled={saving}>
                {saving ? "Adding…" : "Add product"}
              </button>
              {saveError && <span className="tone-bad">{saveError}</span>}
            </div>
          </form>
        </section>
      </main>
    </div>
  );
}
