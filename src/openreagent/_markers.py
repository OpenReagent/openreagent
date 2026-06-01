"""Built-in marker vocabularies for the slot recipes.

A *marker* is a lowercase token or substring whose presence in a function body
is evidence that a given element is implemented. The slot recipes use these to
decide presence/absence; a signature may always override or extend them via its
slots (see docs/conventions.md). These tables are intentionally small, public,
and editable — they encode no measurement, only conventional vocabulary.
"""
from __future__ import annotations

# operation token -> markers that indicate the element IS present.
REQUIRED_ELEMENT_MARKERS: dict[str, list[str]] = {
    "access_control": ["onlyowner", "onlyrole", "_checkrole", "hasrole",
                        "onlyadmin", "onlygovernance", "authorized", "_authorized"],
    "authorization": ["onlyowner", "onlyrole", "_checkrole", "hasrole",
                      "onlyadmin", "authorized"],
    "zero_address_check": ["address(0)", "!= address(0)", "zeroaddress", "notzeroaddress"],
    "reentrancy_guard": ["nonreentrant", "reentrancyguard", "_noreentrant", "mutex"],
    "deadline_check": ["deadline", "block.timestamp", "expiry", "expired"],
    "slippage_check": ["minamountout", "amountoutmin", "slippage", "minout",
                       "minreturn", "mintokensout"],
    "pause_check": ["whennotpaused", "paused"],
    "input_validation": ["require(", "assert("],
    "supply_update": ["totalsupply", "_totalsupply"],
}

# operation token -> markers for keyed (per-account) state.
KEYED_STATE_MARKERS: dict[str, list[str]] = {
    "balance": ["balances[", "balanceof[", "_balances["],
    "shares": ["shares[", "_shares["],
    "deposits": ["deposits[", "deposited["],
}

# operation token -> markers for aggregated (global) state.
AGGREGATE_STATE_MARKERS: dict[str, list[str]] = {
    "total_supply": ["totalsupply", "_totalsupply"],
    "total_shares": ["totalshares", "_totalshares"],
    "total_deposits": ["totaldeposits", "totaldeposited"],
}


def normalize(token) -> str:
    if token is None:
        return ""
    if isinstance(token, dict):
        token = token.get("value") or token.get("kind") or token.get("name") or ""
    return str(token).strip().lower().replace("-", "_").replace(" ", "_")
