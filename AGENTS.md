# AGENTS.md — Secure Market Gateway (Synthetic Demo)

## Status
SYNTHETIC DEMONSTRATION — non-production.
No real market data, no ADX systems, no production credentials.
All instruments, prices and users are fictional.

---

## Purpose
This project demonstrates how IBM Bob extends an existing FastAPI
market-data service to enforce broker entitlements, rate limiting,
and audit logging across REST and MCP channels.

A licensed broker receives synthetic real-time prices.
A retail user receives delayed prices (quote_as_of = 15 min behind served_at).
Unauthorised or over-limit access fails closed.
Every decision is auditable.

---

## Current Structure

financial-data/
├── main.py                          — FastAPI app entry point, routing, auth stub
├── src/
│   ├── api/ticker.py                — Data fetching logic
│   ├── common/fastapi_util.py       — Shared utilities, exception handler
│   ├── common/synthetic_market_data.py — Synthetic instrument prices
│   ├── common/synthetic_users.py    — Synthetic user personas
│   └── models/                      — Pydantic data models
├── json/                            — Static JSON fixture files
├── demo/tokens.json                 — Fixture JWT tokens (5 personas)
├── docs/plan/                       — Implementation plans (Bob writes here)
├── test.py                          — Existing test file
├── AGENTS.md                        — This file
└── .bobignore

---

## Canonical Commands

Start:  uvicorn main:app --reload
Stop:   Ctrl+C in terminal
Test:   pytest test.py
Lint:   ruff check .
Health: http://localhost:8000/docs

---

## Synthetic Instruments

| Symbol  | Company Name               | Sector      | Approx base (AED) |
|---------|----------------------------|-------------|-------------------|
| AURORA  | Aurora Mobility PJSC       | Mobility    | 24.80             |
| NEXUS   | Nexus Digital Holdings     | Technology  | 71.25             |
| OASIS   | Oasis Utilities Group      | Utilities   |  9.42             |
| FALCON  | Falcon Logistics Co.       | Logistics   | 36.10             |
| CEDAR   | Cedar Healthcare Ltd.      | Healthcare  | 18.65             |
| HORIZON | Horizon Industrial Systems | Industrials | 52.30             |
| SYN1    | Aster Gulf Logistics       | Logistics   | 42.25             |
| SYN2    | North Harbor Energy        | Energy      | 58.40             |
| SYN3    | Verdant Terrace Foods      | Food        | 91.30             |

All 9 instruments are defined in SYNTHETIC_MARKET_DATA with 4 daily
price rows each (2026-08-01 to 2026-08-04). No sector or base_price_aed
field exists in the data dict itself — the table above is documentation only.
No real market data is used or fetched.

## Synthetic User Personas

| Token alias         | Role   | Entitlement           | Expected decision |
|---------------------|--------|-----------------------|-------------------|
| retail-user         | RETAIL | none                  | ALLOW / DELAYED   |
| broker-entitled     | BROKER | MARKET_DATA_REALTIME  | ALLOW / REALTIME  |
| broker-no-entitle   | BROKER | none                  | DENY              |
| expired-token       | —      | —                     | DENY (401)        |
| wrong-audience      | —      | —                     | DENY (403)        |

---

## Decision Matrix

| Identity                    | Channel      | Decision | Tier     | Reason code            |
|-----------------------------|--------------|----------|----------|------------------------|
| Valid retail                | REST or MCP  | ALLOW    | DELAYED  | RETAIL_DELAY_APPLIED   |
| Valid broker + entitlement  | REST or MCP  | ALLOW    | REALTIME | ENTITLEMENT_CONFIRMED  |
| Valid broker, no entitlement| REST or MCP  | DENY     | none     | ENTITLEMENT_MISSING    |
| Expired token               | REST or MCP  | DENY     | none     | TOKEN_EXPIRED          |
| Invalid audience            | REST or MCP  | DENY     | none     | TOKEN_AUDIENCE_INVALID |
| Policy service unavailable  | REST or MCP  | DENY     | none     | POLICY_UNAVAILABLE     |
| Rate limit exceeded         | REST or MCP  | THROTTLE | none     | RATE_LIMIT_EXCEEDED    |

---

## Business Rules

- The caller CANNOT select or override their data tier. Tier is determined
  server-side from the validated identity and entitlement only.
- DELAYED: quote_as_of = served_at minus 15 minutes.
- REALTIME: quote_as_of = served_at.
- If the policy service is unreachable or times out, DENY the request.
  Do not default to allow. Do not cache a previous decision.
- Rate limits: RETAIL = 5 req/min, BROKER = 20 req/min.
  Limits are configurable via environment variables.
- JWT claims required: sub, role, entitlements, exp, aud.
- Accepted audience value: adx-demo-gateway

---

## Security Rules

- Never hard-code or print credentials, tokens, private keys
  or Authorization headers.
- REST and MCP must use the same authorization policy service.
- Authorization failures must fail closed.
- Do not permit the caller to select or override its market-data tier.
- Validate all identifiers against an allow-listed format.
- Use structured audit events — no secrets, no personal data in logs.
- Add positive, negative and dependency-failure tests for every
  security-sensitive change.
- Do not add external network dependencies or production endpoints.
- Redact Authorization headers from all log output.

---

## Audit Event Schema

Every request — allowed, denied or throttled — must produce one event:

event_id        — UUID
timestamp_utc   — ISO-8601 UTC
request_id      — Correlation ID
actor_id        — Synthetic subject identifier (sub claim). No token, no name.
channel         — REST or MCP
action          — GET_QUOTE, LIST_INSTRUMENTS, VIEW_AUDIT
resource        — Instrument symbol or endpoint path
decision        — ALLOW, DENY, THROTTLE
reason_code     — Exact code from decision matrix above
latency_ms      — End-to-end measured latency

---
## JWT Fixture Configuration
Algorithm: HS256
Audience:  adx-demo-gateway
Issuer:    adx-demo-idp
Secret:    demo-secret-key-not-for-production
Note:      This secret is synthetic and non-production. 
           Never use in a real environment.

## Authentication Requirements

- All requests to REST and MCP endpoints must be authenticated.
- No path may bypass authentication, including /mcp and /sse routes.
- Tokens must be validated as JWT using HS256.
- Validation must check: signature, expiry, audience (adx-demo-gateway), issuer.
- Role and entitlements must be extracted from validated claims only.
- A plain string token comparison is not acceptable.

## Change Constraints

- Do not modify synthetic_market_data.py or synthetic_users.py 
  instrument prices or user definitions unless explicitly instructed.
- Do not add calls to external APIs, Yahoo Finance, or any live data source.
- Preserve the existing public API response shape. Add fields; do not
  remove or rename existing ones.
- Do not expose internal identifiers (database IDs, internal user keys)
  in any API response.
- Every change must include at minimum: one positive test, one negative
  test, one dependency-failure test.

---

## Definition of Done

A task is complete when:
1. All seven decision matrix rows return the correct HTTP status,
   tier, and reason_code.
2. The same policy applies to both REST and MCP paths.
3. The audit log records an event for every request.
4. No secrets or Authorization headers appear in any log output.
5. All tests pass: pytest test.py
6. uvicorn main:app --reload starts cleanly from a fresh clone.