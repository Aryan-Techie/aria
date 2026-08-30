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
            "come up (including corrections, e.g. user count changing)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "company": {"type": "string"},
                "user_count": {"type": "integer"},
                "budget_range": {"type": "string"},
                "timeline": {"type": "string"},
                "pain_points": {"type": "array", "items": {"type": "string"}},
                "decision_stage": {
                    "type": "string",
                    "enum": ["discovery", "evaluating", "ready_to_buy", "not_a_fit"],
                },
                "name": {"type": "string"},
                "email": {"type": "string"},
                "phone": {"type": "string"},
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
