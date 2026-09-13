"use client";

import { useCallback, useEffect, useState } from "react";
import { Logo } from "@/components/Logo";
import {
  approveDiscount,
  createProduct,
  dashboardLogin,
  fetchCapacity,
  fetchInbox,
  fetchLeads,
  fetchProducts,
  fetchTasks,
  isDashboardAuthError,
  isRateLimitError,
  type CapacitySnapshot,
  type EscalationRecord,
  type LeadRecord,
  type ProductDraft,
  type ProductListing,
  type TaskRecord,
} from "@/lib/api";
import {
  DoodleSpark,
  DoodleWave,
  DoodleCircle,
  DoodleArrow,
  DoodleUnderline,
  DoodleLoop,
  DoodleCheck,
  DoodleDivider,
} from "@/components/Doodles";

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

  // null = still checking on first mount; false = no valid session cookie
  // yet - show the gate instead of the dashboard; true = past the gate,
  // poll normally.
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [passwordInput, setPasswordInput] = useState("");
  const [checkingPassword, setCheckingPassword] = useState(false);
  const [authErrorMessage, setAuthErrorMessage] = useState<string | null>(null);

  const load = useCallback(async (): Promise<boolean> => {
    // allSettled, not all - one source failing (e.g. EspoCRM rejecting the
    // products entity) must not blank the four sections that loaded fine.
    const [cap, leadRows, inboxRows, productRows, taskRows] = await Promise.allSettled([
      fetchCapacity(),
      fetchLeads(),
      fetchInbox(),
      fetchProducts(),
      fetchTasks(),
    ]);

    const failed = [cap, leadRows, inboxRows, productRows, taskRows].find((r) => r.status === "rejected") as
      | PromiseRejectedResult
      | undefined;

    if (failed && isDashboardAuthError(failed.reason)) {
      setAuthed(false);
      return false;
    }

    if (cap.status === "fulfilled") setCapacity(cap.value);
    if (leadRows.status === "fulfilled") setLeads(leadRows.value);
    if (inboxRows.status === "fulfilled") setInbox(inboxRows.value);
    if (productRows.status === "fulfilled") setProducts(productRows.value);
    if (taskRows.status === "fulfilled") setTasks(taskRows.value);
    setLoadError(failed ? (failed.reason instanceof Error ? failed.reason.message : String(failed.reason)) : null);
    setAuthed(true);
    return true;
  }, []);

  const submitPassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setCheckingPassword(true);
    setAuthErrorMessage(null);
    try {
      await dashboardLogin(passwordInput);
      await load();
    } catch (err) {
      setAuthed(false);
      setAuthErrorMessage(isRateLimitError(err) ? "Too many attempts — wait a few minutes." : "Wrong password.");
    } finally {
      setCheckingPassword(false);
    }
  };

  // First check on mount - a fresh checkout with no DASHBOARD_PASSWORD set
  // sails through this with authed=true immediately, same as before.
  useEffect(() => {
    void load();
  }, [load]);

  // Poll only once past the gate - a wrong/missing password shouldn't spam
  // fetches every 5s while the login form is sitting there.
  useEffect(() => {
    if (!authed) return;
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [authed, load]);

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
    <div className="app" style={{ position: "relative" }}>
      <DoodleLoop
        className="doodle faint"
        size={72}
        style={{ position: "absolute", right: 24, bottom: 24, pointerEvents: "none" }}
      />
      <header className="top">
        <div className="brand">
          <Logo size={24} />
          <span>Aria</span>
          <span className="sub">Dashboard</span>
          <DoodleUnderline className="doodle faint" width={40} />
        </div>
        <div className="actions">
          <a href="/" className="ghost">
            Console
          </a>
        </div>
      </header>

      <main className="stage" style={{ display: "block", padding: "24px 28px", maxWidth: 1100, margin: "0 auto" }}>
        {authed !== true ? (
          <section className="card" style={{ maxWidth: 380, margin: "80px auto 0" }}>
            <h3>Dashboard password</h3>
            <form onSubmit={submitPassword} className="edit-fields" style={{ gridTemplateColumns: "1fr" }}>
              <div>
                <label htmlFor="dash-password">Password</label>
                <input
                  id="dash-password"
                  type="password"
                  autoFocus
                  value={passwordInput}
                  onChange={(e) => setPasswordInput(e.target.value)}
                />
              </div>
            </form>
            <div className="edit-actions">
              <button className="primary small" onClick={submitPassword} disabled={checkingPassword || !passwordInput}>
                {checkingPassword ? "Checking…" : "Unlock"}
              </button>
              {authErrorMessage && <span className="tone-bad">{authErrorMessage}</span>}
            </div>
          </section>
        ) : (
          <>
        {loadError && (
          <p className="tone-bad" style={{ marginBottom: 16 }}>
            {loadError}
          </p>
        )}

        <section className="card" style={{ marginBottom: 20 }}>
          <h3>
            Capacity
            <DoodleWave className="doodle" width={30} />
          </h3>
          <div className="stats">
            <div className="stat">
              <div className="k">
                Calls total <DoodleCheck className="doodle faint" size={12} style={{ verticalAlign: "middle" }} />
              </div>
              <div className="v">{capacity?.calls_total ?? "—"}</div>
            </div>
            <div className="stat">
              <div className="k">
                Live now <DoodleSpark className="doodle warm" size={12} style={{ verticalAlign: "middle" }} />
              </div>
              <div className="v">{capacity?.calls_live_now ?? "—"}</div>
            </div>
            <div className="stat">
              <div className="k">
                Peak concurrent <DoodleLoop className="doodle faint" size={16} style={{ verticalAlign: "middle" }} />
              </div>
              <div className="v">{capacity?.peak_concurrent_calls ?? "—"}</div>
            </div>
            <div className="stat">
              <div className="k">
                Meetings booked <DoodleCheck className="doodle" size={12} style={{ verticalAlign: "middle" }} />
              </div>
              <div className="v">{capacity?.meetings_booked ?? "—"}</div>
            </div>
          </div>
        </section>

        <section className="card" style={{ marginBottom: 20 }}>
          <h3>
            Leads
            <DoodleCircle className="doodle faint" size={18} />
          </h3>
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
          <DoodleDivider className="doodle faint" width={70} style={{ margin: "0 0 10px" }} />
          <div className="list">
            {leads.length === 0 ? (
              <p className="empty"><DoodleSpark className="doodle faint" size={16} />No leads yet.</p>
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
          <h3>
            Open escalations
            <DoodleArrow className="doodle warm" size={26} />
          </h3>
          <div className="list risk">
            {openEscalations.length === 0 ? (
              <p className="empty"><DoodleSpark className="doodle faint" size={16} />Nothing waiting on a person right now.</p>
            ) : (
              <ul>
                {openEscalations.map((esc, i) => (
                  <li key={esc.id}>
                    {esc.brief.issue} — {esc.reason}
                    <span className="pill warn" style={{ marginLeft: 8 }}>
                      {esc.kind === "deal_approval" ? "Approval needed" : "Handoff"}
                    </span>
                    {i === 0 && (
                      <DoodleCheck
                        className="doodle warm"
                        size={13}
                        style={{ marginLeft: 6, verticalAlign: "middle" }}
                      />
                    )}
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
          <h3>
            Follow-ups
            <DoodleUnderline className="doodle faint" width={34} />
          </h3>
          <div className="list">
            {tasks.length === 0 ? (
              <p className="empty"><DoodleSpark className="doodle faint" size={16} />Nothing scheduled for later.</p>
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
          <h3>
            Products
            <DoodleSpark className="doodle" size={16} />
          </h3>
          <div className="story-pill-row">
            {products.map((p, i) => (
              <span className="pill info" key={p.name}>
                {p.name}
                {p.price_usd != null ? ` — $${p.price_usd}` : ""}
                {p.stock_qty != null ? ` · ${p.stock_qty} in stock` : ""}
                {(i === 0 || i === 3) && (
                  <DoodleSpark className="doodle faint" size={11} style={{ marginLeft: 2 }} />
                )}
              </span>
            ))}
          </div>
        </section>

        <section className="card">
          <h3>
            <span style={{ display: "inline-flex", alignItems: "center" }}>
              Add a product
              <DoodleWave className="doodle faint" width={26} style={{ marginLeft: 8 }} />
            </span>
            {savedName && <span className="tone-good">{savedName} added</span>}
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
              <DoodleCheck className="doodle" size={14} />
              {saveError && <span className="tone-bad">{saveError}</span>}
            </div>
          </form>
        </section>
          </>
        )}
      </main>
    </div>
  );
}
