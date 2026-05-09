# Future Features Roadmap

## Phase 1: API Stability (Current)
*   [x] Core Agent/Pattern Read Access.
*   [x] Basic Action Triggers (Spawn, Cull, Backtest).
*   [x] Trade History Access.

## Phase 2: Live Trading & Exchanges
*   **Exchanges Domain**: Implement specific adapters for:
    *   Binance
    *   Bybit
    *   Coinbase
*   **Execution Engine**: Move from "Paper Trading/Backtest" DB logging to real API execution.
*   **Key Management**: Secure handling of API keys (Vault/Encrypted Environment Variables).

## Phase 3: Real-Time Data (Websockets)
*   **Market Data Stream**: Replace static "Candle Loading" with a Websocket Service (`Fast_Swarm/MarketData`) to stream live prices.
*   **Agent Tick Loop**: Agents should process ticks in real-time rather than batch backtests.
*   **WebSocket API**: Push notifications to the UI when trades occur.

## Phase 4: User Interface (The Control Room)
*   **Dashboard**: A React/Next.js frontend to visualize the Swarm.
    *   Real-time PnL graph.
    *   "Genealogy Tree" visualization of Agent evolution.
    *   Manual Override buttons ("Kill Switch").

## Phase 5: AI Memory System Integration
*   **Replace Legacy Three-Tier Memory**: Migrate from `EpisodicMemory → SemanticMemory → WisdomMemory` to the typed AI memory system in `local_agents/core/memory.py`.
*   **Typed Memory Categories**:
    *   `observation`: Neutral pattern noticed (weight 0.1-0.5)
    *   `opinion`: Belief + confidence (weight 0.3-0.8)
    *   `lesson`: Actionable takeaway (weight 0.5-0.9)
    *   `counterfactual`: What-if analysis (weight 0.2-0.6)
    *   `regret`: Decision to not repeat (weight 0.6-1.0)
    *   `affirmation`: Decision to repeat (weight 0.6-1.0)
*   **Memory Lifecycle**: Implement conflict detection (60% Jaccard similarity), inheritance selection, and weight decay.
*   **Daemon Integration**: Replace temporary stub classes in `evolution_daemon.py` with full AI memory system calls.
*   **LLM Memory Review**: Surface weak memories (< 0.15 weight) for LLM review on triggers (session_end, every 50 backtests, etc.).

## Phase 6: Distributed Swarm
*   **Kubernetes / Cloudflare**: Deploy agents as independent micro-services or Workers (refer to `v3/cloudflare-agents/`).
*   **Shared Memory**: Redis integration for high-speed inter-agent communication.
