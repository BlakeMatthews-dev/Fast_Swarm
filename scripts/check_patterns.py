#!/usr/bin/env python3
"""Check Postgres connectivity and pattern counts."""

import asyncio

from Fast_Swarm.Database import async_session_maker
from Fast_Swarm.Patterns.Models.pattern_models import Pattern
from sqlmodel import select


async def main():
    async with async_session_maker() as session:
        result = await session.exec(select(Pattern).where(Pattern.is_active == True))
        patterns = result.all()
        print(f"Found {len(patterns)} active patterns")
        if patterns:
            sample = patterns[:3]
            for p in sample:
                print(f" - {p.pattern_id} | {p.name} | fitness={p.fitness_score}")


if __name__ == "__main__":
    asyncio.run(main())
