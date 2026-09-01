def resolve_tier(claims: dict) -> tuple[str, str]:
    """Resolve data tier from validated JWT claims.

    Returns (decision, tier) where:
      decision ∈ {"ALLOW", "DENY"}
      tier     ∈ {"REALTIME", "DELAYED", "NONE"}

    Logic (decision matrix):
      BROKER + MARKET_DATA_REALTIME in entitlements → ALLOW / REALTIME
      RETAIL                                        → ALLOW / DELAYED
      anything else                                 → DENY  / NONE

    The only input is the validated claims dict from validate_jwt().
    The caller's request parameters are never consulted.

    reason_code implied by tier:
      REALTIME → ENTITLEMENT_CONFIRMED
      DELAYED  → RETAIL_DELAY_APPLIED
      NONE     → ENTITLEMENT_MISSING
    """
    role = claims.get("role", "")
    entitlements = claims.get("entitlements", [])

    if role == "BROKER" and "MARKET_DATA_REALTIME" in entitlements:
        return ("ALLOW", "REALTIME")
    if role == "RETAIL":
        return ("ALLOW", "DELAYED")
    return ("DENY", "NONE")


REASON_CODES: dict[str, str] = {
    "REALTIME": "ENTITLEMENT_CONFIRMED",
    "DELAYED":  "RETAIL_DELAY_APPLIED",
    "NONE":     "ENTITLEMENT_MISSING",
}
