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
        if h.get("top_up_skipped"):
            row += f" ({h['top_up_skipped']})"
        lines.append(row)
    esc = digest.get("escalations") or []
    if esc:
        lines.append("Escalations: " + ", ".join(esc))
    dep = digest.get("deployment")
    if dep and dep.get("error"):
        lines.append(f"Idle cash: nothing bought; {dep['error']}")
    elif dep:
        # SA-049: what idle cash bought, and why any of it stayed idle.
        bought = ", ".join(dep.get("bought") or []) or "nothing"
        lines.append(f"Idle cash: bought {bought}; invested "
                     f"{dep.get('invested_before_pct', 0):.1f}% → "
                     f"{dep.get('invested_after_pct', 0):.1f}% against a target of "
                     f"{dep.get('target_pct', 0):.1f}% ({dep.get('regime') or 'no regime'}). "
                     + "; ".join(dep.get("reasons") or []))
    return "\n".join(lines)
