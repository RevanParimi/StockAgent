"""EOD digest → human-readable text. Single renderer shared by the API's
?format=text mode so the Inbox shows the same content notifications describe."""
from __future__ import annotations


def render_digest_text(digest: dict) -> str:
    lines = [f"EOD digest — {digest.get('date', '')}"]
    pv = digest.get("portfolio_value")
    pnl = digest.get("total_pnl_pct")
    if pv is not None:
        row = f"Portfolio value: ₹{pv:,.0f}"
        if pnl is not None:
            row += f" ({pnl:+.1f}% total P&L)"
        lines.append(row)
    for h in digest.get("holdings", []):
        row = f"{h.get('verdict', '?')}: {h.get('symbol', '?')}"
        if h.get("reason"):
            row += f" — {h['reason']}"
        lines.append(row)
    esc = digest.get("escalations") or []
    if esc:
        lines.append("Escalations: " + ", ".join(esc))
    return "\n".join(lines)
