"""
Delete patterns from database that contain unresolvable indicators.

These indicators were hallucinated by the LLM during pattern generation
and have no corresponding computation in calculate_indicators_fast()
or any alias mapping. They will always fail during backtesting.

Unresolvable indicators (alias='None'):
- dpo_14: Detrended Price Oscillator - not computed
- trix_30: TRIX with period 30 - we compute TRIX (period 15), not 30
- trix_signal: TRIX signal line - not computed
- chop_14: Choppiness Index - not computed
- month: Calendar month - not a technical indicator
- pvi_ema: Positive Volume Index EMA - not computed
- ui_14: Ulcer Index - not computed
"""

import sys
sys.path.insert(0, r"c:\fast_swarm\src")

if sys.platform == "win32":
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from sqlalchemy import text, bindparam, create_engine
from sqlalchemy.orm import Session
from Fast_Swarm.Database import SYNC_DATABASE_URL

UNRESOLVABLE_INDICATORS = [
    "dpo_14",
    "trix_30",
    "trix_signal",
    "chop_14",
    "month",
    "pvi_ema",
    "ui_14",
]

def main():
    engine = create_engine(SYNC_DATABASE_URL)

    # Build the SQL query using jsonb_array_elements to check entry_conditions
    # Each entry_condition is a list of dicts like: [{"indicator": "rsi_14", ...}, ...]
    # We want patterns where ANY condition has an indicator in the unresolvable list

    # Also check exit_conditions
    placeholders = ", ".join(f"'{ind}'" for ind in UNRESOLVABLE_INDICATORS)

    find_query = text(f"""
        SELECT DISTINCT p.pattern_id, p.name, p.status, p.symbol, p.timeframe
        FROM patterns p,
             jsonb_array_elements(p.entry_conditions) AS cond
        WHERE lower(cond->>'indicator') IN ({placeholders})

        UNION

        SELECT DISTINCT p.pattern_id, p.name, p.status, p.symbol, p.timeframe
        FROM patterns p,
             jsonb_array_elements(p.exit_conditions) AS cond
        WHERE lower(cond->>'indicator') IN ({placeholders})

        ORDER BY pattern_id
    """)

    with Session(engine) as session:
        # First, find matching patterns
        result = session.execute(find_query)
        patterns = result.fetchall()

        if not patterns:
            print("[DELETE] No patterns found with unresolvable indicators.")
            return

        print(f"[DELETE] Found {len(patterns)} patterns with unresolvable indicators:")
        print("-" * 80)
        for p in patterns:
            print(f"  {p.pattern_id[:12]}  {p.status:<10} {p.symbol or 'any':<12} {p.timeframe or '?':<5} {p.name[:50]}")
        print("-" * 80)

        # Delete them
        pattern_ids = [p.pattern_id for p in patterns]

        # Delete from child tables first (FK constraints)
        del_embeddings = text(
            "DELETE FROM pattern_embeddings WHERE pattern_id IN :ids"
        ).bindparams(bindparam("ids", expanding=True))
        r1 = session.execute(del_embeddings, {"ids": pattern_ids})
        print(f"\n[DELETE] Removed {r1.rowcount} pattern_embeddings rows")

        del_backtests = text(
            "DELETE FROM backtest_results WHERE pattern_id IN :ids"
        ).bindparams(bindparam("ids", expanding=True))
        r2 = session.execute(del_backtests, {"ids": pattern_ids})
        print(f"[DELETE] Removed {r2.rowcount} backtest_results rows")

        # Now delete the patterns themselves
        del_patterns = text(
            "DELETE FROM patterns WHERE pattern_id IN :ids"
        ).bindparams(bindparam("ids", expanding=True))
        r3 = session.execute(del_patterns, {"ids": pattern_ids})
        session.commit()

        print(f"[DELETE] Removed {r3.rowcount} patterns")
        print("[DELETE] Indicators purged: " + ", ".join(UNRESOLVABLE_INDICATORS))


if __name__ == "__main__":
    main()
