import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from Fast_Swarm.Main import app


def check_routes():
    print("Verifying FastAPI Application Routes...")

    expected_routes = [
        "/agents/",
        "/patterns/",
        "/trades/",
        "/evolution/monitor/cycles",
        "/governance/committees",
        "/market_data/candles",
        "/exchanges/status",
    ]

    registered_routes = [route.path for route in app.routes]

    for route in expected_routes:
        if route in registered_routes:
            print(f"[OK] Found route: {route}")
        else:
            print(f"[ERROR] Missing route: {route}")

    # Print total count
    print(f"\nTotal Routes Registered: {len(registered_routes)}")

    # Try a simple health check (implied by startup)
    print("\nApplication startup check passed (imported successfully).")


if __name__ == "__main__":
    check_routes()
