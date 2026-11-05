"""Chat with the Advisor in the terminal (handy before the UI exists).

Run from the backend folder:   python -m app.advisor.cli        (add --hi for Hindi, --rules to skip Gemini)
"""
from __future__ import annotations

import sys

from app.advisor.dialogue import AdvisorState, greeting, handle_message
from app.advisor.llm import get_llm


def main() -> None:
    lang = "hi" if "--hi" in sys.argv else "en"
    llm = None if "--rules" in sys.argv else get_llm()
    print(f"[understanding: {llm.name if llm else 'rules'}]  (type 'quit' to exit)\n")
    st = AdvisorState(session_id="cli", language=lang)
    r = greeting(st)
    while True:
        print("apnaSaathi:", r.text)
        if r.chips:
            print("   options:", " | ".join(c.label for c in r.chips))
        if r.recommendation:
            rec, q = r.recommendation, r.recommendation.quote
            if r.summary:
                print("\n  ", r.summary)
            print()
            for l in rec.lines:
                print(f"  + {l.product_name} x{l.qty}  (₹{l.list_monthly_inr}/month)  — {l.why}")
            for e in rec.excluded:
                print(f"  - {e.product_name}: {e.message}")
            if rec.addons:
                print("  Optional add-ons:", ", ".join(f"{a.product_name} (+₹{a.list_monthly_inr})" for a in rec.addons))
            print(f"\n  Monthly: ₹{q.monthly_subtotal_inr} + GST ₹{q.monthly_gst_inr} = ₹{q.monthly_total_inr}"
                  f"   One-time: ₹{q.one_time_total_inr}   Contract: {q.contract_months} months")
            print(f"  [segment={rec.segment}, tier={rec.profile.city_tier}]")
            break
        if r.handoff:
            break
        text = input("\nYou: ").strip()
        if text.lower() in ("quit", "exit"):
            break
        r = handle_message(st, text, llm=llm, use_default_llm=False)
        print(f"   [understood by {r.understood_by}; known: "
              f"{ {k: v for k, v in r.slots.model_dump().items() if v is not None and v != [] and k != 'needs_confirmed'} }]")


if __name__ == "__main__":
    main()
