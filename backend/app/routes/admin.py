"""Demo/debug endpoints — for showing judges the CRM record, calendar slot,
and escalation inbox that a live call actually produced.
"""
import hashlib
import hmac
import json
import logging
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from app.calendar import service as calendar_service
from app.config import get_settings
from app.crm import service as crm_service
from app.escalation.inbox import inbox
from app.handoff import service as handoff_service
from app.inventory.models import InventoryUnavailable, Product
from app.inventory.store import product_store
from app.metrics import capacity
from app.rag import retriever
from app.rag.ingest import DOCS_DIR
from app.rtm.publisher import default_rtm_publisher
from app.sessions.store import session_store
from app.tasks import service as tasks_service

router = APIRouter()
logger = logging.getLogger("aria")

_CUSTOM_PRODUCTS_DOC = DOCS_DIR / "custom_products.md"
_CATALOG_JSON = DOCS_DIR / "pricing.json"

# ---------------------------------------------------------------------------
# Dashboard auth: a signed, expiring HttpOnly cookie rather than replaying the
# raw password on every request. The signing key is random-per-process, not
# config - a backend restart naturally invalidates every session, the same
# way live call state already resets on restart elsewhere in this app.
# ---------------------------------------------------------------------------
_DASHBOARD_COOKIE = "aria_dashboard_session"
_SESSION_TTL_SECONDS = 12 * 60 * 60  # a demo-day session, not a "remember me"
_SIGNING_KEY = secrets.token_bytes(32)

# Per-IP failed-attempt tracking, in-process - consistent with how session
# state already lives in memory elsewhere in this app (sessions/store.py).
# Not for a multi-worker deployment (this backend already runs --workers 1
# by design, see deploy/README.md), but exactly right for this one.
_RATE_LIMIT_WINDOW_SECONDS = 5 * 60
_RATE_LIMIT_MAX_ATTEMPTS = 5
_failed_attempts: dict[str, list[float]] = {}


def _sign(expiry: int) -> str:
    return hmac.new(_SIGNING_KEY, f"dashboard:{expiry}".encode(), hashlib.sha256).hexdigest()


def _make_session_token() -> str:
    expiry = int(time.time()) + _SESSION_TTL_SECONDS
    return f"{expiry}.{_sign(expiry)}"


def _session_token_is_valid(token: str) -> bool:
    try:
        expiry_str, signature = token.split(".", 1)
        expiry = int(expiry_str)
    except (ValueError, AttributeError):
        return False
    if expiry < time.time():
        return False
    return hmac.compare_digest(signature, _sign(expiry))


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _too_many_recent_failures(key: str) -> bool:
    cutoff = time.time() - _RATE_LIMIT_WINDOW_SECONDS
    attempts = [t for t in _failed_attempts.get(key, []) if t > cutoff]
    _failed_attempts[key] = attempts
    return len(attempts) >= _RATE_LIMIT_MAX_ATTEMPTS


def _record_failure(key: str) -> None:
    _failed_attempts.setdefault(key, []).append(time.time())


class DashboardLogin(BaseModel):
    password: str


@router.post("/api/dashboard/login")
def dashboard_login(body: DashboardLogin, request: Request, response: Response) -> dict:
    settings = get_settings()
    if not settings.dashboard_password:
        return {"ok": True}

    key = _client_key(request)
    if _too_many_recent_failures(key):
        raise HTTPException(status_code=429, detail="Too many attempts — wait a few minutes")

    if not hmac.compare_digest(body.password, settings.dashboard_password):
        _record_failure(key)
        raise HTTPException(status_code=401, detail="Wrong dashboard password")

    _failed_attempts.pop(key, None)
    response.set_cookie(
        _DASHBOARD_COOKIE,
        _make_session_token(),
        max_age=_SESSION_TTL_SECONDS,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
    )
    return {"ok": True}


def require_dashboard_session(request: Request) -> None:
    """Gates the dashboard-only endpoints - not /api/metrics/capacity or
    /api/calendar/slots, which the live console also depends on and must
    stay reachable with no password. A no-op until DASHBOARD_PASSWORD is
    set, matching this project's existing "off until configured" posture
    elsewhere (CRM_BACKEND, EMAIL_ENABLED) - a fresh checkout isn't locked
    out of its own dashboard by default."""
    settings = get_settings()
    if not settings.dashboard_password:
        return
    token = request.cookies.get(_DASHBOARD_COOKIE)
    if not token or not _session_token_is_valid(token):
        raise HTTPException(status_code=401, detail="Dashboard login required")


@router.get("/api/leads", dependencies=[Depends(require_dashboard_session)])
def list_leads() -> list[dict]:
    return [lead.model_dump(mode="json") for lead in crm_service.list_leads()]


@router.get("/api/calendar/slots")
def list_slots() -> list[dict]:
    return [slot.model_dump(mode="json") for slot in calendar_service.list_available()]


@router.get("/api/products", dependencies=[Depends(require_dashboard_session)])
def list_products() -> list[dict]:
    """The catalogue (app/rag/docs/pricing.json's device_lineup, plus
    anything added since via POST below) joined against live stock
    (CAriaProduct) where a SKU/name happens to match. Best-effort join -
    most catalogue entries have no matching stock row and that's fine,
    they just carry no stock fields."""
    catalog: list[dict] = []
    try:
        data = json.loads(_CATALOG_JSON.read_text(encoding="utf-8"))
        catalog = data.get("device_lineup", [])
    except (OSError, json.JSONDecodeError):
        pass

    # Degrade the same way EspoLeadStore.all() does - a live catalog with no
    # stock numbers is a working dashboard; a bare 500 blanking the whole
    # page over one down dependency is not.
    try:
        stock_by_name = {p.name.lower(): p for p in product_store.all()}
    except InventoryUnavailable as exc:
        logger.warning("Product list failed: %s", exc)
        stock_by_name = {}

    out: list[dict] = []
    for item in catalog:
        name = item.get("product", "")
        stock = stock_by_name.pop(name.lower(), None)
        out.append(
            {
                "name": name,
                "category": item.get("category"),
                "price_usd": item.get("starting_price"),
                "note": item.get("note"),
                "stock_qty": stock.stock_qty if stock else None,
                "status": stock.resolved_status() if stock else None,
            }
        )
    # Whatever's left in stock_by_name is admin-added (or seeded) and has no
    # catalog.json entry - still worth listing.
    for stock in stock_by_name.values():
        out.append(
            {
                "name": stock.name,
                "category": stock.category,
                "price_usd": stock.price_usd,
                "note": stock.description,
                "stock_qty": stock.stock_qty,
                "status": stock.resolved_status(),
            }
        )
    return out


class ProductCreate(BaseModel):
    name: str
    category: str | None = None
    price_usd: float
    description: str | None = None
    stock_qty: int = 0


@router.post("/api/products", dependencies=[Depends(require_dashboard_session)])
def create_product(body: ProductCreate) -> dict:
    """Backend-team product upload, without touching app/rag/docs' hand-
    authored files or waiting on a restart. Writes the stock row, appends a
    matching section to custom_products.md, then drops the cached RAG index
    so search_pricing_rag finds it on the very next question asked."""
    sku = "ADMIN-" + "".join(ch for ch in body.name.upper() if ch.isalnum())[:24] or "ADMIN-PRODUCT"

    product = Product(
        sku=sku,
        name=body.name,
        stock_qty=body.stock_qty,
        price_usd=body.price_usd,
        description=body.description,
        category=body.category,
    )
    try:
        saved = product_store.add(product)
    except Exception as exc:  # noqa: BLE001 - surfaced to the caller, not swallowed
        raise HTTPException(status_code=502, detail=f"Could not save product: {exc}")

    bits = [f"## {body.name}", f"Starting price: ${body.price_usd:.0f}."]
    if body.category:
        bits.append(f"Category: {body.category}.")
    if body.description:
        bits.append(body.description)
    bits.append(f"In stock: {body.stock_qty} units.")
    section = "\n\n" + "\n".join(bits) + "\n"

    try:
        with _CUSTOM_PRODUCTS_DOC.open("a", encoding="utf-8") as f:
            f.write(section)
    except OSError as exc:
        raise HTTPException(status_code=502, detail=f"Product saved but not yet searchable: {exc}")

    retriever.reset_index()

    return {"sku": saved.sku, "name": saved.name, "price_usd": saved.price_usd}


@router.get("/api/inbox", dependencies=[Depends(require_dashboard_session)])
def list_inbox() -> list[dict]:
    return [record.model_dump(mode="json") for record in inbox.all()]


@router.get("/api/tasks", dependencies=[Depends(require_dashboard_session)])
def list_tasks() -> list[dict]:
    """Follow-ups written by the schedule_followup tool - for a rep to work
    later, not a meeting and not a line buried in a transcript."""
    return [task.model_dump(mode="json") for task in tasks_service.list_tasks()]


@router.get("/api/metrics/capacity")
def capacity_metrics() -> dict:
    """How many conversations this has actually handled, and what that stood
    in for. Every assumption behind the derived figures is returned alongside
    them — see app/metrics/capacity.py."""
    return capacity.snapshot(session_store.all())


@router.get("/api/summaries")
def list_summaries() -> list[dict]:
    """The wrap-up produced when each call ended - what the rep was told."""
    return [summary.model_dump(mode="json") for summary in handoff_service.all_summaries()]


@router.get("/api/summaries/{session_id}")
def get_summary(session_id: str) -> dict:
    summary = handoff_service.get(session_id)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"No wrap-up for session: {session_id}")
    return summary.model_dump(mode="json")


class ApprovalRequest(BaseModel):
    approved_pct: float
    approved_by: str = "sales manager"


@router.post("/api/inbox/{escalation_id}/approve", dependencies=[Depends(require_dashboard_session)])
def approve_discount(escalation_id: str, body: ApprovalRequest) -> dict:
    """Layer 3, answering while the call is still running.

    The whole point of separating a discount approval from a handoff is that
    this does not take the call away from Aria — a person answers one question
    about margin and the conversation carries on. So this writes the approved
    figure onto the live session, and the next system prompt renders it
    (pipeline.py::_render_negotiation): she can lead her very next sentence
    with the number a human just signed, seconds after they clicked.

    It deliberately does not push anything at the model. There is no way to
    interrupt a turn that is already generating, and a mid-sentence injection
    would be heard as her talking over herself. Picking it up on the next turn
    is both simpler and what a rep being handed a note would do.
    """
    record = inbox.get(escalation_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"No such escalation: {escalation_id}")
    if record.kind != "deal_approval":
        raise HTTPException(
            status_code=400,
            detail="That escalation is a handoff, not a discount approval — there is nothing to approve.",
        )

    inbox.resolve_approval(escalation_id, body.approved_pct, body.approved_by)

    session = session_store.get(record.session_id)
    if session is not None:
        negotiation = session.negotiation
        negotiation.human_approved_pct = body.approved_pct
        negotiation.human_approved_by = body.approved_by
        negotiation.pending_human_approval = False
        session_store.save(session)
        default_rtm_publisher().publish(
            record.session_id,
            "deal_approval_granted",
            {
                "escalation_id": escalation_id,
                "approved_pct": body.approved_pct,
                "approved_by": body.approved_by,
            },
        )

    return {
        "escalation_id": escalation_id,
        "session_id": record.session_id,
        "approved_pct": body.approved_pct,
        "approved_by": body.approved_by,
        # False when the call has already ended, or the backend restarted
        # since — the answer is still recorded on the inbox record either way.
        "applied_to_live_call": session is not None,
    }
