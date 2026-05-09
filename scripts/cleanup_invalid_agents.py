"""Delete agents without valid pattern conditions."""

from sqlalchemy import create_engine, text

engine = create_engine("postgresql://coinswarm:coinswarm_dev_2024@localhost:5432/coinswarm")

with engine.connect() as conn:
    # Delete agents whose base patterns don't have entry_conditions
    result = conn.execute(
        text("""
        DELETE FROM agents
        WHERE is_active = true
        AND NOT EXISTS (
            SELECT 1 FROM jsonb_array_elements(assigned_patterns->'base') AS p
            WHERE p->'entry_conditions' IS NOT NULL
        )
        RETURNING agent_id
    """)
    )
    deleted = result.fetchall()
    conn.commit()
    print(f"Deleted {len(deleted)} agents without entry_conditions")

    # Check remaining
    result = conn.execute(text("SELECT COUNT(*) FROM agents WHERE is_active = true"))
    remaining = result.scalar()
    print(f"Remaining active agents: {remaining}")
