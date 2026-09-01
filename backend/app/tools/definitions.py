"""Tool schemas in Anthropic's `tools` format (input_schema = JSON Schema).

These are executed entirely inside our own backend (see executor.py) rather
than delegated to Agora's `llm.mcp_servers` — see the plan's tradeoff note:
tool execution must also mutate session/CRM state and emit RTM events, so
keeping the whole loop in one process is simpler to build and debug.
"""

TOOLS: list[dict] = [
    {
        "name": "search_pricing_rag",
        "description": (
            "Search Aria's product, pricing, feature, and competitor-comparison "
            "knowledge base. Always use this instead of guessing at prices, "
            "features, or competitor comparisons."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The customer's question, in natural language."},
                "top_k": {"type": "integer", "description": "Number of results to return.", "default": 4},
            },
            "required": ["query"],
        },
    },
    {
        "name": "crm_upsert_lead",
        "description": (
            "Create or update the qualification record for this call. Only pass "
            "fields the customer actually stated or changed — omitted fields are "
            "left untouched, so this is safe to call repeatedly as new details "
            "come up (including corrections, e.g. user count changing). Capture "
            "WHO you are speaking to as well as what they need: a caller who "
            "opens with 'this is Priya from Northwind Logistics' has just given "
            "you both name and company, and a record without them is of no use "
            "to the rep who picks this lead up afterwards."
        ),
        "input_schema": {
            "type": "object",
            # Every property carries its own description. Without them the
            # model reliably filled in the numeric qualification fields and
            # left name/company empty, even when the caller had stated both in
            # their opening sentence - confirmed twice on scripted runs.
            "properties": {
                "company": {
                    "type": "string",
                    "description": "The customer's company/organisation name, e.g. 'Northwind Logistics'.",
                },
                "user_count": {
                    "type": "integer",
                    "description": "How many devices or employees the deployment covers.",
                },
                "budget_range": {
                    "type": "string",
                    "description": "Budget as stated, e.g. 'around 60 thousand'.",
                },
                "timeline": {
                    "type": "string",
                    "description": "When they need the devices, e.g. 'end of October'.",
                },
                "pain_points": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "What is driving the change, in their words.",
                },
                "decision_stage": {
                    "type": "string",
                    "enum": ["discovery", "evaluating", "ready_to_buy", "not_a_fit"],
                    "description": "How close they are to a decision, on your read of the call.",
                },
                "name": {
                    "type": "string",
                    "description": "The name of the person on the call, e.g. 'Priya'.",
                },
                "email": {"type": "string", "description": "Their email address, if given."},
                "phone": {"type": "string", "description": "Their phone number, if given."},
            },
        },
    },
    {
        "name": "crm_qualify_lead",
        "description": "Mark the lead for this call as qualified or disqualified, with a short reason.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["qualified", "disqualified"]},
                "reason": {"type": "string"},
            },
            "required": ["status", "reason"],
        },
    },
    {
        "name": "calendar_check_availability",
        "description": "Check available meeting slots, optionally within a date range (ISO 8601 datetimes).",
        "input_schema": {
            "type": "object",
            "properties": {
                "date_range_start": {"type": "string", "description": "ISO 8601 datetime, optional."},
                "date_range_end": {"type": "string", "description": "ISO 8601 datetime, optional."},
            },
        },
    },
    {
        "name": "calendar_book_meeting",
        "description": "Book a specific meeting slot by its slot_id (from calendar_check_availability).",
        "input_schema": {
            "type": "object",
            "properties": {"slot_id": {"type": "string"}},
            "required": ["slot_id"],
        },
    },
    {
        "name": "escalate_to_human",
        "description": (
            "Hand this call off to a human specialist with full context. Use when "
            "the customer explicitly asks for a person, or you genuinely can't "
            "resolve something after real effort."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"reason": {"type": "string"}},
            "required": ["reason"],
        },
    },
    {
        "name": "log_objection",
        "description": (
            "Record a pricing, trust, or product objection the customer raised. "
            "Call again with resolved=true once you've addressed it."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "enum": ["pricing", "trust", "product"]},
                "raised_text": {"type": "string", "description": "What the customer said, briefly."},
                "resolved": {"type": "boolean", "default": False},
                "resolution_text": {"type": "string"},
            },
            "required": ["topic", "raised_text"],
        },
    },
    {
        "name": "ask_solutions_engineer",
        "description": (
            "Put a technical question to a deployment engineer - compatibility, "
            "migration, MDM, security, integration, rollout logistics. Use this "
            "whenever search_pricing_rag does not settle a technical question, "
            "INSTEAD of escalating and instead of guessing. It reads everything "
            "we have and tells you precisely what is supported and what is "
            "genuinely still open, which is an answer a customer can act on. "
            "Not for pricing or discounts - that is negotiate_deal."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The technical question, in the customer's own terms.",
                },
                "their_setup": {
                    "type": "string",
                    "description": (
                        "Anything they have said about their current environment - "
                        "software, existing fleet, IT tooling. Helps the engineer be specific."
                    ),
                },
            },
            "required": ["question"],
        },
    },
    {
        "name": "negotiate_deal",
        "description": (
            "Work out what you are actually allowed to offer when the customer "
            "pushes on price - a discount request, a target number, a competing "
            "quote, or 'what's your best price'. This consults the deal desk and "
            "returns a priced, authorised offer. You must call this before "
            "putting ANY discount, target price, or trade-in figure to the "
            "customer: a number you worked out yourself is not an offer the "
            "business has agreed to, and quoting one you cannot honour is worse "
            "than saying no. Call it again each time they push again - the desk "
            "tracks what has already been conceded."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_ask": {
                    "type": "string",
                    "description": "What they asked for, in their own words.",
                },
                "requested_discount_pct": {
                    "type": "number",
                    "description": "Only if they named a percentage, e.g. 15 for 'fifteen percent off'.",
                },
                "target_total_price": {
                    "type": "number",
                    "description": "Only if they named a total they need to hit, e.g. 90000.",
                },
                "target_unit_price": {
                    "type": "number",
                    "description": "Only if they named a per-device price they need, e.g. 850.",
                },
                "competitor_quote": {
                    "type": "string",
                    "description": "The competing quote they are holding over you, if any.",
                },
                "device_mix": {
                    "type": "array",
                    "description": (
                        "The fleet, when they have specified models. Omit it and "
                        "the whole fleet is priced as MacBook Airs."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "model": {"type": "string"},
                            "quantity": {"type": "integer"},
                        },
                        "required": ["model", "quantity"],
                    },
                },
                "trade_in_devices": {
                    "type": "integer",
                    "description": "How many devices they would trade in, if they have said.",
                },
                "financing": {
                    "type": "boolean",
                    "description": "True if the blocker is cash flow rather than total cost.",
                },
            },
            "required": ["customer_ask"],
        },
    },
    {
        "name": "update_sentiment",
        "description": "Record a noticeable shift in the customer's tone.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sentiment": {
                    "type": "string",
                    "enum": ["positive", "neutral", "skeptical", "frustrated"],
                }
            },
            "required": ["sentiment"],
        },
    },
]
