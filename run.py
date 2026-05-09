# Windows + psycopg3 launcher - sets event loop BEFORE uvicorn starts
import sys
from pathlib import Path

# Add parent directory to path so Fast_Swarm module is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

# MUST set policy before ANY asyncio imports
if sys.platform == "win32":
    import asyncio

    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn

if __name__ == "__main__":
    # Run with explicit loop_factory to ensure SelectorEventLoop
    if sys.platform == "win32":
        import asyncio
        import selectors

        config = uvicorn.Config(
            "Fast_Swarm.Main:app",
            host="127.0.0.1",
            port=8080,
            reload=False,
        )
        server = uvicorn.Server(config)

        # Create and run with SelectorEventLoop
        loop = asyncio.SelectorEventLoop(selectors.SelectSelector())
        asyncio.set_event_loop(loop)
        loop.run_until_complete(server.serve())
    else:
        uvicorn.run(
            "Fast_Swarm.Main:app",
            host="127.0.0.1",
            port=8080,
            reload=False,
        )
