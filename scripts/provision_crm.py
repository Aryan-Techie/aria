"""Mint the API user Aria authenticates as, and print its key.

EspoCRM's documented path for this is clicking through Administration > API
Users, which is no good for a stack that has to be reproducible on a strange
laptop the morning of a demo. An admin can create the same record over the
REST API with Basic auth, so this does the whole thing headlessly: role,
API user, key.

Idempotent - re-running finds the existing role/user rather than duplicating
them. It cannot recover an existing key, though: EspoCRM returns `apiKey`
only in the response that creates the user. If the key is lost, pass
--recreate to delete the user and mint a fresh one.

    python scripts/provision_crm.py [--recreate]

Writes nothing. Prints the two lines to paste into the root .env.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from base64 import b64encode

BASE_URL = "http://localhost:8080"
ADMIN_USER = "admin"
ADMIN_PASSWORD = "aria-demo-admin"

ROLE_NAME = "Aria Voice Agent"
API_USER_NAME = "aria-agent"
# A Meeting requires an assignedUser and an api-type user cannot BE one,
# so bookings need a regular user to hang off. Also makes the calendar in
# the CRM UI read as a real rep's diary rather than a service account's.
REP_USER_NAME = "aria"

# Creating a custom field does NOT put it on any layout - the field exists and
# holds data, but the Lead page simply does not show it, so a live demo of
# "watch the CRM fill in" shows nothing. This layout adds an "Aria
# Qualification" panel carrying all seven.
#
# It is installed by copying the file into the container rather than over the
# REST API: this EspoCRM build answers 405 on PUT Layout/{scope}/{name} and
# parses PUT Admin/layout/... with "Admin" as the scope ("Admin is not
# customizable"). The file path is the stable interface.
CONTAINER = "aria-espocrm"
LAYOUT_ROOT = pathlib.Path(__file__).resolve().parent.parent / "crm" / "layouts"
LAYOUT_DEST_ROOT = "/var/www/html/custom/Espo/Custom/Resources/layouts"

# Qualification state has no home among EspoCRM's stock Lead fields, and
# stuffing it into `description` as prose makes the live-update demo
# unreadable. These are created through the Field Manager API and then show up
# as real, typed fields on the Lead detail view.
#
# NOTE the name you write with is NOT the name you create with: EspoCRM
# prefixes every custom field with "c", so creating "ariaUserCount" yields a
# field addressed as "cAriaUserCount". Writing the unprefixed name is silently
# accepted and silently dropped - it does not error, the value just never
# appears. Hence CUSTOM_FIELD_PREFIX and the mapping in crm/espo_store.py.
CUSTOM_FIELDS = [
    {"name": "ariaUserCount", "type": "int", "label": "Device Count", "min": 0, "max": 1000000},
    {"name": "ariaBudgetRange", "type": "varchar", "label": "Budget Range", "maxLength": 100},
    {"name": "ariaTimeline", "type": "varchar", "label": "Rollout Timeline", "maxLength": 100},
    {
        "name": "ariaDecisionStage",
        "type": "enum",
        "label": "Decision Stage",
        "options": ["", "discovery", "evaluating", "ready_to_buy", "not_a_fit"],
    },
    {"name": "ariaPainPoints", "type": "text", "label": "Pain Points"},
    {"name": "ariaOutcome", "type": "varchar", "label": "Call Outcome", "maxLength": 100},
    # The join key back to our own session state. Indexed lookups on it are
    # how a mid-call update finds the row it created two turns earlier.
    {"name": "ariaSessionId", "type": "varchar", "label": "Aria Session", "maxLength": 64},
]

# Live stock, as a real entity in the CRM rather than another document in the
# RAG corpus. Pricing and features are prose and belong in app/rag/docs; how
# many units are on the shelf is a number that has to be right at the moment
# it is asked, and a keyword search over documents is how an agent ends up
# confidently quoting yesterday's figure.
#
# Putting it in EspoCRM buys the editing UI for free, and the websocket
# container already running means a change made in the browser is live for the
# next question she is asked - no restart, no re-ingest.
#
# NOTE EspoCRM prefixes custom ENTITIES with "C" as well as custom fields, so
# creating "AriaProduct" yields a scope addressed as "CAriaProduct". Confirmed
# against this build: the create call is POST EntityManager/action/createEntity
# (Admin/entityManager/createEntity 404s here), and removeEntity wants the
# prefixed name back or answers 403.
INVENTORY_ENTITY = "AriaProduct"
INVENTORY_SCOPE = "CAriaProduct"

# `name` comes with every Base entity, so only the stock-specific columns are
# created here. NOTE these are NOT c-prefixed: the "c" prefix applies to custom
# fields added to a STOCK entity (Lead -> cStockQty), but a field created on a
# custom entity keeps the name it was given. Verified against this build's
# Metadata: entityDefs.CAriaProduct.fields has `sku`, not `cSku`. Filtering on
# the prefixed name answers 400 "Not existing attribute 'cSku' in where."
INVENTORY_FIELDS = [
    {"name": "sku", "type": "varchar", "label": "SKU", "maxLength": 40},
    {"name": "stockQty", "type": "int", "label": "Units in stock", "min": 0, "max": 1000000},
    {"name": "priceUsd", "type": "float", "label": "Unit price (USD)", "min": 0},
    {"name": "leadTimeDays", "type": "int", "label": "Lead time (days)", "min": 0, "max": 365},
    {
        "name": "status",
        "type": "enum",
        "label": "Availability",
        "options": ["", "in_stock", "low_stock", "out_of_stock", "discontinued"],
    },
]

# Enough rows to hold a conversation about. Matched to the device lineup in
# app/rag/docs/pricing.json so she cannot quote a price for something that has
# no stock record, or stock for something with no price.
SEED_PRODUCTS = [
    {"name": "iPad 10th gen", "sku": "IPAD-10", "stockQty": 240, "priceUsd": 349.0, "leadTimeDays": 3},
    {"name": "iPad Pro M4 11-inch", "sku": "IPADPRO-M4-11", "stockQty": 60, "priceUsd": 999.0, "leadTimeDays": 7},
    {"name": "MacBook Air M3 13-inch", "sku": "MBA-M3-13", "stockQty": 85, "priceUsd": 1099.0, "leadTimeDays": 5},
    {"name": "iPhone 15", "sku": "IPHONE-15", "stockQty": 0, "priceUsd": 799.0, "leadTimeDays": 21},
]

# Only what the tool loop actually touches. Lead and Meeting are the two
# entities Aria writes to; Account/Contact are readable so a lookup against an
# existing customer works, but she has no business deleting anything.
ROLE_DATA = {
    "name": ROLE_NAME,
    "assignmentPermission": "all",
    "exportPermission": "no",
    "massUpdatePermission": "no",
    "data": {
        "Lead": {"create": "yes", "read": "all", "edit": "all", "delete": "no", "stream": "all"},
        "Meeting": {"create": "yes", "read": "all", "edit": "all", "delete": "no", "stream": "all"},
        "Account": {"create": "no", "read": "all", "edit": "no", "delete": "no", "stream": "no"},
        "Contact": {"create": "no", "read": "all", "edit": "no", "delete": "no", "stream": "no"},
        # read:all, not own - assigning a Meeting to the rep user is a link
        # operation, and Espo refuses it ("No foreign record access for link
        # operation") unless the API user can read that User record.
        "User": {"create": "no", "read": "all", "edit": "no", "delete": "no", "stream": "no"},
        # Read-only on purpose. Stock is changed by a person in the CRM, or by
        # whatever system owns it — never by the agent mid-call.
        INVENTORY_SCOPE: {"create": "no", "read": "all", "edit": "no", "delete": "no", "stream": "no"},
    },
    "fieldData": {},
}


def _request(method: str, path: str, payload: dict | None = None, params: dict | None = None):
    url = f"{BASE_URL}/api/v1/{path}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"

    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=body, method=method)
    token = b64encode(f"{ADMIN_USER}:{ADMIN_PASSWORD}".encode()).decode()
    req.add_header("Authorization", f"Basic {token}")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()[:400]
        raise SystemExit(
            f"EspoCRM {method} {path} failed: {exc.code} {exc.reason}\n{detail}\n\n"
            "Is the stack up?  docker compose -f crm/docker-compose.yml ps"
        ) from exc
    except urllib.error.URLError as exc:
        raise SystemExit(
            f"Could not reach EspoCRM at {BASE_URL}: {exc.reason}\n"
            "Start it with:  docker compose -f crm/docker-compose.yml up -d"
        ) from exc


def _find_one(entity: str, field: str, value: str) -> dict | None:
    """EspoCRM's list filter syntax is `where[0][...]` query params, not a
    JSON body - passing a body to a GET here silently returns everything."""
    result = _request(
        "GET",
        entity,
        params={
            "maxSize": 1,
            "where[0][type]": "equals",
            "where[0][attribute]": field,
            "where[0][value]": value,
        },
    )
    rows = (result or {}).get("list") or []
    return rows[0] if rows else None



def _install_layout() -> None:
    """Copy every layout under crm/layouts/<Scope>/ into the container.

    A custom entity gets no layouts of its own: EspoCRM falls back to a default
    that shows `name` and nothing else, so the stock columns exist in the API
    and are invisible - and therefore uneditable - in the browser. Verified on
    this build: before these files, CAriaProduct's detail view listed only
    Name / Assigned User / Teams / Created.
    """
    dirs = sorted(d for d in LAYOUT_ROOT.iterdir() if d.is_dir()) if LAYOUT_ROOT.exists() else []
    if not dirs:
        print(f"layout    : SKIPPED, no layouts under {LAYOUT_ROOT}")
        return

    def docker(*args: str) -> bool:
        result = subprocess.run(
            ["docker", *args], capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0:
            print(f"layout    : docker {' '.join(args[:2])} failed: {result.stderr.strip()[:160]}")
            return False
        return True

    ok = True
    for scope_dir in dirs:
        dest = f"{LAYOUT_DEST_ROOT}/{scope_dir.name}"
        files = sorted(scope_dir.glob("*.json"))
        if not files:
            continue
        scope_ok = docker("exec", CONTAINER, "mkdir", "-p", dest)
        for src in files:
            scope_ok = scope_ok and docker("cp", str(src), f"{CONTAINER}:{dest}/{src.name}")
        scope_ok = scope_ok and docker("exec", CONTAINER, "chown", "-R", "www-data:www-data", dest)
        print(
            f"layout    : {scope_dir.name} {', '.join(f.stem for f in files)}"
            if scope_ok
            else f"layout    : {scope_dir.name} FAILED"
        )
        ok = ok and scope_ok

    # Layouts are cached; without this the panels do not appear until something
    # else happens to invalidate the cache.
    ok = docker("exec", CONTAINER, "php", "/var/www/html/clear_cache.php") and ok
    if not ok:
        print("layout    : one or more layouts failed to install")


def _ensure_inventory(metadata: dict) -> None:
    """Create the stock entity, its columns and its seed rows, idempotently.

    Split from the Lead fields because it needs its own rebuild: the entity has
    to exist in the schema before fields can be hung off it, and the fields
    have to be in the database before a row can be written.
    """
    scopes = metadata.get("scopes", {})
    if INVENTORY_SCOPE in scopes:
        print(f"inventory : reusing {INVENTORY_SCOPE}")
    else:
        _request(
            "POST",
            "EntityManager/action/createEntity",
            {
                "name": INVENTORY_ENTITY,
                "type": "Base",
                "labelSingular": "Product",
                "labelPlural": "Products",
                "stream": False,
                "disabled": False,
            },
        )
        print(f"inventory : created {INVENTORY_SCOPE}")

    existing = (
        _request("GET", "Metadata").get("entityDefs", {}).get(INVENTORY_SCOPE, {}).get("fields", {})
    )
    created_any = False
    for field in INVENTORY_FIELDS:
        if field["name"] in existing:
            print(f"inventory : reusing {field['name']}")
            continue
        _request("POST", f"Admin/fieldManager/{INVENTORY_SCOPE}", field)
        created_any = True
        print(f"inventory : created {field['name']} ({field['type']})")

    if created_any:
        print("rebuild   : applying inventory schema...")
        _request("POST", "Admin/rebuild")

    # Seeded by SKU so re-running never duplicates, and so a stock figure
    # someone has edited by hand is left exactly as they left it.
    for product in SEED_PRODUCTS:
        if _find_one(INVENTORY_SCOPE, "sku", product["sku"]):
            print(f"inventory : reusing {product['sku']}")
            continue
        _request(
            "POST",
            INVENTORY_SCOPE,
            {
                "name": product["name"],
                "sku": product["sku"],
                "stockQty": product["stockQty"],
                "priceUsd": product["priceUsd"],
                "leadTimeDays": product["leadTimeDays"],
                "status": "out_of_stock" if product["stockQty"] == 0 else "in_stock",
            },
        )
        print(f"inventory : seeded {product['sku']} ({product['stockQty']} units)")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="delete the existing API user first (the only way to get a new key)",
    )
    args = parser.parse_args()

    # There is no GET on Admin/fieldManager/{scope} - it 404s. The existing
    # field list has to come out of the metadata tree instead.
    metadata = _request("GET", "Metadata") or {}
    existing_fields = metadata.get("entityDefs", {}).get("Lead", {}).get("fields", {})
    created_any = False
    for field in CUSTOM_FIELDS:
        prefixed = "c" + field["name"][0].upper() + field["name"][1:]
        if prefixed in existing_fields:
            print(f"field     : reusing {prefixed}")
            continue
        _request("POST", "Admin/fieldManager/Lead", field)
        created_any = True
        print(f"field     : created {prefixed} ({field['type']})")

    if created_any:
        # Without this the columns exist in metadata but not in the database,
        # and every write of them is accepted and dropped.
        print("rebuild   : applying schema (this takes a few seconds)...")
        _request("POST", "Admin/rebuild")

    _install_layout()
    _ensure_inventory(metadata)

    # After _ensure_inventory: a role that lists a scope Espo does not know
    # yet is rejected with "Bad data. Scope CAriaProduct is not allowed."
    role = _find_one("Role", "name", ROLE_NAME)
    if role:
        # `name` is omitted - Espo answers 400 when it is sent back on a PUT.
        _request("PUT", f"Role/{role['id']}",
                 {k: v for k, v in ROLE_DATA.items() if k != "name"})
        print(f"role      : updated {ROLE_NAME} ({role['id']})")
    else:
        role = _request("POST", "Role", ROLE_DATA)
        print(f"role      : created {ROLE_NAME} ({role['id']})")

    rep = _find_one("User", "userName", REP_USER_NAME)
    if rep:
        print(f"rep user  : reusing {REP_USER_NAME} ({rep['id']})")
    else:
        rep = _request(
            "POST",
            "User",
            {
                "userName": REP_USER_NAME,
                "firstName": "Aria",
                "lastName": "Voice Agent",
                "type": "regular",
                "isActive": True,
                "emailAddress": "aria@example.com",
            },
        )
        print(f"rep user  : created {REP_USER_NAME} ({rep['id']})")

    existing = _find_one("User", "userName", API_USER_NAME)
    if existing and args.recreate:
        _request("DELETE", f"User/{existing['id']}")
        print(f"api user  : deleted old {API_USER_NAME} ({existing['id']})")
        existing = None
    elif existing:
        print(
            f"api user  : {API_USER_NAME} already exists ({existing['id']}) - kept.\n"
            "            EspoCRM returns apiKey only in the response that CREATES\n"
            "            the user, so an existing key cannot be read back. If you\n"
            "            no longer have it, re-run with --recreate.\n"
            f"\nESPOCRM_ASSIGNED_USER_ID={rep['id']}"
        )
        return 0

    user = _request(
        "POST",
        "User",
        {
            "userName": API_USER_NAME,
            "type": "api",
            "authMethod": "ApiKey",
            "isActive": True,
            "rolesIds": [role["id"]],
        },
    )

    api_key = user.get("apiKey")
    if not api_key:
        raise SystemExit(f"User created ({user.get('id')}) but no apiKey came back: {user}")

    print(f"api user  : created {API_USER_NAME} ({user['id']})")


    print()
    print("Add these to the ROOT .env, then restart the backend")
    print("(settings are cached with lru_cache - editing alone does nothing):")
    print()
    print("CRM_BACKEND=espocrm")
    print(f"ESPOCRM_BASE_URL={BASE_URL}")
    print(f"ESPOCRM_API_KEY={api_key}")
    print(f"ESPOCRM_ASSIGNED_USER_ID={rep['id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
