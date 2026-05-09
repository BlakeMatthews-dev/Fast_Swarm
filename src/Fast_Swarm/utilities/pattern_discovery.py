"""
Pattern Discovery Scheduler - Automated chaos → pattern discovery pipeline.

Ported from Coinswarm-1/local-utilities/daemon with improvements:
- Async-first using SQLAlchemy sessions (psycopg3 via SQLAlchemy)
- Integrated with Fast_Swarm Database module
- LLM provider support: Ollama (local) or Claude CLI
- No external APScheduler dependency - designed for use with asyncio

Pipeline:
1. Load chaos trades from PostgreSQL
2. Extract features using RandomForest
3. Build LLM prompt with top discriminating features
4. Call LLM (Ollama or Claude CLI)
5. Parse and insert discovered patterns
"""

import json
import os
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Try to import ML dependencies
try:
    import numpy as np
    from sklearn.ensemble import RandomForestClassifier

    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

try:
    import requests

    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


# Configuration — default to conductor for free cloud tokens
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "conductor")
CONDUCTOR_URL = os.getenv("CONDUCTOR_URL", "http://host.docker.internal:8100")
CONDUCTOR_KEY = os.getenv("CONDUCTOR_KEY", "sk-conductor-router-2026")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:0.5b")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "sonnet")

# Discovery settings
MIN_CHAOS_TRADES = 100  # Lowered from 500 - we need fewer trades to start discovering
WINNER_THRESHOLD = 0.5  # PnL > +0.5% = winner (lowered from 2% to capture more trades)
LOSER_THRESHOLD = -0.5  # PnL < -0.5% = loser (lowered from -2%)
TOP_FEATURES_COUNT = 20


@dataclass
class DiscoveryCycleResult:
    """Result of a discovery cycle."""

    success: bool
    chaos_trades_loaded: int = 0
    winners_count: int = 0
    losers_count: int = 0
    features_extracted: int = 0
    patterns_discovered: int = 0
    patterns_inserted: int = 0
    llm_provider: str = ""
    duration_seconds: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "chaos_trades_loaded": self.chaos_trades_loaded,
            "winners_count": self.winners_count,
            "losers_count": self.losers_count,
            "features_extracted": self.features_extracted,
            "patterns_discovered": self.patterns_discovered,
            "patterns_inserted": self.patterns_inserted,
            "patterns_created": self.patterns_inserted,  # Alias for compatibility
            "llm_provider": self.llm_provider,
            "duration_seconds": self.duration_seconds,
            "error": self.error,
        }


@dataclass
class FeatureImportance:
    """Feature with its importance score."""

    name: str
    importance: float
    winner_mean: float
    loser_mean: float
    separation: float


class PatternDiscoveryScheduler:
    """
    Automated pattern discovery from chaos trades.

    Use run_discovery_cycle() to execute a discovery cycle.
    """

    def __init__(
        self,
        interval_hours: int = 6,
        llm_provider: str = LLM_PROVIDER,
    ):
        self.interval_hours = interval_hours
        self.llm_provider = llm_provider
        print(f"[PatternDiscovery] Initialized with provider={llm_provider}")

    async def run_discovery_cycle(
        self,
        session: AsyncSession,
    ) -> DiscoveryCycleResult:
        """
        Run a complete discovery cycle.

        Args:
            session: Async database session

        Returns:
            DiscoveryCycleResult with cycle outcomes
        """
        start_time = time.time()
        print("[PatternDiscovery] === Starting discovery cycle ===")

        try:
            # Step 1: Load chaos trades
            winners, losers, indicator_cols = await self._load_chaos_trades(session)

            if len(winners) + len(losers) < MIN_CHAOS_TRADES:
                msg = f"Not enough chaos trades: {len(winners) + len(losers)} < {MIN_CHAOS_TRADES}"
                print(f"[PatternDiscovery] {msg}")
                return DiscoveryCycleResult(
                    success=False,
                    chaos_trades_loaded=len(winners) + len(losers),
                    winners_count=len(winners),
                    losers_count=len(losers),
                    error=msg,
                    duration_seconds=time.time() - start_time,
                )

            print(f"[PatternDiscovery] Loaded {len(winners)} winners, {len(losers)} losers")

            # Step 2: Extract features
            top_features = self._extract_features(winners, losers, indicator_cols)
            print(f"[PatternDiscovery] Extracted {len(top_features)} top features")

            if not top_features:
                return DiscoveryCycleResult(
                    success=False,
                    chaos_trades_loaded=len(winners) + len(losers),
                    winners_count=len(winners),
                    losers_count=len(losers),
                    error="Feature extraction failed (sklearn not installed?)",
                    duration_seconds=time.time() - start_time,
                )

            # Step 3: Build LLM prompt
            prompt = self._build_llm_prompt(winners, losers, top_features)

            # Step 4: Call LLM
            llm_response = await self._call_llm(prompt)
            if not llm_response:
                return DiscoveryCycleResult(
                    success=False,
                    chaos_trades_loaded=len(winners) + len(losers),
                    winners_count=len(winners),
                    losers_count=len(losers),
                    features_extracted=len(top_features),
                    llm_provider=self.llm_provider,
                    error="LLM call failed",
                    duration_seconds=time.time() - start_time,
                )

            # Step 5: Parse patterns
            patterns = self._parse_patterns(llm_response)
            print(f"[PatternDiscovery] Parsed {len(patterns)} patterns")

            # Step 6: Insert patterns
            inserted = await self._insert_patterns(session, patterns)
            print(f"[PatternDiscovery] Inserted {inserted} patterns")

            duration = time.time() - start_time
            print(f"[PatternDiscovery] === Cycle complete in {duration:.1f}s ===")

            return DiscoveryCycleResult(
                success=True,
                chaos_trades_loaded=len(winners) + len(losers),
                winners_count=len(winners),
                losers_count=len(losers),
                features_extracted=len(top_features),
                patterns_discovered=len(patterns),
                patterns_inserted=inserted,
                llm_provider=self.llm_provider,
                duration_seconds=duration,
            )

        except Exception as e:
            print(f"[PatternDiscovery] Cycle failed: {e}")
            import traceback

            traceback.print_exc()
            return DiscoveryCycleResult(
                success=False,
                error=str(e),
                duration_seconds=time.time() - start_time,
            )

    async def _load_chaos_trades(
        self,
        session: AsyncSession,
    ) -> tuple[list[dict], list[dict], list[str]]:
        """
        Load trades and generate 4 labeled variants per trade for learning.

        For each recorded trade, we generate:
        1. chaos/original - Actual entry → actual exit (original PnL)
        2. best_exit - Same entry → exit at MFE (best possible outcome)
        3. worst_exit - Same entry → exit at MAE (worst possible outcome)
        4. perfect - Better entry (local low before MFE) → exit at MFE

        This teaches the model what good vs bad entries/exits look like.
        """
        # Load all trades with MFE/MAE data
        try:
            result = await session.execute(
                text("""
                SELECT
                    COALESCE(net_pnl_pct, gross_pnl_pct, 0) as pnl_pct,
                    symbol,
                    timeframe,
                    entry_indicators,
                    entry_price,
                    exit_price,
                    mfe_pct,
                    mfe_price,
                    mae_pct,
                    mae_price,
                    side
                FROM backtest_trades_unified
                WHERE entry_indicators IS NOT NULL
                AND mfe_pct IS NOT NULL
                AND mae_pct IS NOT NULL
                ORDER BY entry_timestamp DESC
                LIMIT 2500
            """)
            )
            raw_trades = result.fetchall()
            print(f"[PatternDiscovery] Loaded {len(raw_trades)} trades with MFE/MAE data")
        except Exception as e:
            print(f"[PatternDiscovery] Trade query failed: {e}")
            raw_trades = []

        # Generate 4 variants per trade
        winners = []
        losers = []
        indicator_cols_set = set()

        for row in raw_trades:
            (pnl_pct, symbol, timeframe, entry_indicators,
             entry_price, exit_price, mfe_pct, mfe_price, mae_pct, mae_price, side) = row

            if not entry_indicators or not isinstance(entry_indicators, dict):
                continue

            # Extract indicators
            indicators = {}
            for k, v in entry_indicators.items():
                if isinstance(v, (int, float)) and v is not None:
                    indicators[k] = float(v)
                    indicator_cols_set.add(k)

            if not indicators:
                continue

            # Need at least entry_price and mfe_pct/mae_pct
            if not entry_price:
                continue

            entry_price = float(entry_price)
            mfe_pct = float(mfe_pct) if mfe_pct else 0
            mae_pct = float(mae_pct) if mae_pct else 0

            # Calculate prices from percentages if not provided
            if mfe_price:
                mfe_price = float(mfe_price)
            else:
                # Derive from entry_price and mfe_pct
                mfe_price = entry_price * (1 + mfe_pct / 100)

            if mae_price:
                mae_price = float(mae_price)
            else:
                # Derive from entry_price and mae_pct (mae_pct is negative)
                mae_price = entry_price * (1 + mae_pct / 100)

            # 1. CHAOS/ORIGINAL - actual trade
            chaos_trade = {
                "pnl_pct": float(pnl_pct),
                "symbol": symbol,
                "timeframe": timeframe,
                "trade_type": "chaos",
                **indicators
            }

            # 2. BEST_EXIT - same entry, exit at MFE
            # For long: MFE is the high, so pnl = mfe_pct
            # For short: MFE is the low, pnl = mfe_pct (already calculated correctly)
            best_exit_trade = {
                "pnl_pct": mfe_pct,
                "symbol": symbol,
                "timeframe": timeframe,
                "trade_type": "best_exit",
                **indicators
            }

            # 3. WORST_EXIT - same entry, exit at MAE
            # MAE is negative (adverse), so this is the worst outcome
            worst_exit_trade = {
                "pnl_pct": mae_pct,  # Already negative
                "symbol": symbol,
                "timeframe": timeframe,
                "trade_type": "worst_exit",
                **indicators
            }

            # 4. PERFECT - hypothetical better entry → MFE exit
            # Estimate: if we entered at MAE price instead, our MFE gain would be larger
            # Perfect PnL = distance from MAE to MFE (the full range we could have captured)
            if side == "long":
                # Long: buy at MAE (low), sell at MFE (high)
                perfect_pnl = ((mfe_price - mae_price) / mae_price) * 100 if mae_price > 0 else 0
            else:
                # Short: sell at MFE (high), buy back at MAE (low)
                perfect_pnl = ((mfe_price - mae_price) / mfe_price) * 100 if mfe_price > 0 else 0

            perfect_trade = {
                "pnl_pct": perfect_pnl,
                "symbol": symbol,
                "timeframe": timeframe,
                "trade_type": "perfect",
                **indicators
            }

            # Classify into winners/losers based on PnL threshold
            for trade in [chaos_trade, best_exit_trade, worst_exit_trade, perfect_trade]:
                if trade["pnl_pct"] > WINNER_THRESHOLD:
                    winners.append(trade)
                elif trade["pnl_pct"] < LOSER_THRESHOLD:
                    losers.append(trade)
                # Trades between thresholds are ignored (neutral zone)

        indicator_cols = list(indicator_cols_set)[:30]
        print(f"[PatternDiscovery] Generated {len(winners)} winners, {len(losers)} losers from {len(raw_trades)} base trades")
        print("[PatternDiscovery] Trade types: chaos, best_exit, worst_exit, perfect")
        print(f"[PatternDiscovery] Extracted {len(indicator_cols)} indicator columns")

        return winners, losers, indicator_cols

    def _extract_features(
        self,
        winners: list[dict],
        losers: list[dict],
        indicator_cols: list[str],
    ) -> list[FeatureImportance]:
        """Extract top features using RandomForest."""
        if not HAS_SKLEARN:
            print("[PatternDiscovery] sklearn not installed, skipping feature extraction")
            return []

        # Prepare data
        X_data = []
        y_labels = []

        for trade in winners:
            row = [float(trade.get(col, 0) or 0) for col in indicator_cols]
            X_data.append(row)
            y_labels.append(1)

        for trade in losers:
            row = [float(trade.get(col, 0) or 0) for col in indicator_cols]
            X_data.append(row)
            y_labels.append(0)

        if len(X_data) < 100:
            return []

        X = np.array(X_data, dtype=np.float64)
        y = np.array(y_labels)

        # Handle NaN/Inf
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

        # Train RandomForest
        rf = RandomForestClassifier(n_estimators=50, max_depth=8, random_state=42, n_jobs=-1)
        rf.fit(X, y)

        importances = rf.feature_importances_

        # Calculate mean values
        winner_X = X[y == 1]
        loser_X = X[y == 0]

        features = []
        for i, col in enumerate(indicator_cols):
            winner_mean = float(np.mean(winner_X[:, i])) if len(winner_X) > 0 else 0
            loser_mean = float(np.mean(loser_X[:, i])) if len(loser_X) > 0 else 0
            separation = abs(winner_mean - loser_mean)

            features.append(
                FeatureImportance(
                    name=col,
                    importance=float(importances[i]),
                    winner_mean=winner_mean,
                    loser_mean=loser_mean,
                    separation=separation,
                )
            )

        features.sort(key=lambda x: x.importance, reverse=True)
        return features[:TOP_FEATURES_COUNT]

    def _build_llm_prompt(
        self,
        winners: list[dict],
        losers: list[dict],
        top_features: list[FeatureImportance],
    ) -> str:
        """Build the LLM prompt for pattern discovery."""
        avg_winner_pnl = sum(w["pnl_pct"] for w in winners) / len(winners) if winners else 0
        avg_loser_pnl = sum(l["pnl_pct"] for l in losers) / len(losers) if losers else 0
        win_rate = len(winners) / (len(winners) + len(losers)) * 100 if (winners or losers) else 0

        feature_analysis = []
        for f in top_features:
            direction = "higher in winners" if f.winner_mean > f.loser_mean else "higher in losers"
            feature_analysis.append(
                f"- {f.name}: importance={f.importance:.4f}, "
                f"winners={f.winner_mean:.4f}, losers={f.loser_mean:.4f} ({direction})"
            )

        prompt = f"""## Pattern Discovery Task

Analyze chaos trades to discover profitable trading patterns.

### Summary
- Winners: {len(winners)} (avg PnL: {avg_winner_pnl:+.2f}%)
- Losers: {len(losers)} (avg PnL: {avg_loser_pnl:+.2f}%)
- Win Rate: {win_rate:.1f}%

### Top Discriminating Features
{chr(10).join(feature_analysis)}

### Task
Create 3-5 actionable trading patterns using these features.

For each pattern provide:
1. A descriptive name
2. Entry conditions (indicator + operator + value)
3. Exit conditions (trailing stop or indicator-based)
4. Brief description

Output ONLY valid JSON:
{{
  "patterns": [
    {{
      "name": "Pattern Name",
      "entry_conditions": [
        {{"indicator": "rsi", "operator": "<", "value": 30}}
      ],
      "exit_conditions": [
        {{"type": "trailing_stop", "atr_multiplier": 2.0}}
      ],
      "description": "Why this works..."
    }}
  ]
}}
"""
        return prompt

    async def _call_llm(self, prompt: str) -> str | None:
        """Call the LLM provider. Conductor → Ollama → Claude fallback chain."""
        if self.llm_provider == "conductor":
            result = self._call_conductor(prompt)
            if result:
                return result
            print("[PatternDiscovery] Conductor failed, falling back to Ollama")
            return self._call_ollama(prompt)
        elif self.llm_provider == "claude":
            return self._call_claude_cli(prompt)
        else:
            return self._call_ollama(prompt)

    def _call_conductor(self, prompt: str) -> str | None:
        """Call Conductor Router (OpenAI-compatible). Uses free cloud tokens."""
        if not HAS_REQUESTS:
            return None
        try:
            response = requests.post(
                f"{CONDUCTOR_URL}/v1/chat/completions",
                json={
                    "model": "auto",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 2000,
                },
                headers={"Authorization": f"Bearer {CONDUCTOR_KEY}"},
                timeout=120,
            )
            if response.status_code != 200:
                print(f"[PatternDiscovery] Conductor error: HTTP {response.status_code}")
                return None
            content = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            model_used = response.json().get("model", "unknown")
            print(f"[PatternDiscovery] Conductor response: {len(content)} chars via {model_used}")
            return content
        except Exception as e:
            print(f"[PatternDiscovery] Conductor error: {e}")
            return None

    def _call_ollama(self, prompt: str) -> str | None:
        """Call Ollama API."""
        if not HAS_REQUESTS:
            print("[PatternDiscovery] requests not installed")
            return None

        try:
            response = requests.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.3, "num_predict": 2000},
                },
                timeout=120,
            )

            if response.status_code != 200:
                print(f"[PatternDiscovery] Ollama error: HTTP {response.status_code}")
                return None

            result = response.json().get("response", "")
            print(f"[PatternDiscovery] Ollama response: {len(result)} chars")
            return result

        except Exception as e:
            print(f"[PatternDiscovery] Ollama error: {e}")
            return None

    def _call_claude_cli(self, prompt: str) -> str | None:
        """Call Claude via CLI."""
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
                f.write(prompt)
                prompt_file = f.name

            try:
                result = subprocess.run(
                    [
                        "claude",
                        "-p",
                        f"Read {prompt_file} and respond with JSON only.",
                        "--output-format",
                        "text",
                        "--model",
                        CLAUDE_MODEL,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=180,
                )

                if result.returncode != 0:
                    print(f"[PatternDiscovery] Claude error: {result.stderr}")
                    return None

                print(f"[PatternDiscovery] Claude response: {len(result.stdout)} chars")
                return result.stdout

            finally:
                Path(prompt_file).unlink(missing_ok=True)

        except FileNotFoundError:
            print("[PatternDiscovery] Claude CLI not found")
            return None
        except Exception as e:
            print(f"[PatternDiscovery] Claude error: {e}")
            return None

    def _parse_patterns(self, llm_response: str) -> list[dict]:
        """Parse patterns from LLM response."""
        patterns = []

        try:
            json_start = llm_response.find("{")
            json_end = llm_response.rfind("}") + 1

            if json_start >= 0 and json_end > json_start:
                json_str = llm_response[json_start:json_end]
                data = json.loads(json_str)

                if isinstance(data, dict) and "patterns" in data:
                    patterns = data["patterns"]
                elif isinstance(data, list):
                    patterns = data

        except json.JSONDecodeError as e:
            print(f"[PatternDiscovery] JSON parse error: {e}")

        # Validate
        valid = []
        for p in patterns:
            if self._validate_pattern(p):
                valid.append(p)

        return valid

    def _validate_pattern(self, pattern: dict) -> bool:
        """Validate a pattern has required fields."""
        if not isinstance(pattern, dict):
            return False
        if "name" not in pattern:
            return False
        if "entry_conditions" not in pattern or not pattern["entry_conditions"]:
            return False
        if "exit_conditions" not in pattern or not pattern["exit_conditions"]:
            return False
        return True

    async def _insert_patterns(
        self,
        session: AsyncSession,
        patterns: list[dict],
    ) -> int:
        """Insert discovered patterns to PostgreSQL."""
        if not patterns:
            return 0

        inserted = 0
        for p in patterns:
            try:
                pattern_id = f"auto_{uuid.uuid4().hex[:12]}"

                await session.execute(
                    text("""
                    INSERT INTO patterns (
                        pattern_id, name, origin, is_active,
                        entry_conditions, exit_conditions,
                        created_at
                    ) VALUES (
                        :pid, :name, :origin, TRUE,
                        :entry, :exit,
                        NOW()
                    )
                    ON CONFLICT (pattern_id) DO NOTHING
                """),
                    {
                        "pid": pattern_id,
                        "name": p.get("name", "Unnamed Pattern"),
                        "origin": "automated_discovery",
                        "entry": json.dumps(p.get("entry_conditions", [])),
                        "exit": json.dumps(p.get("exit_conditions", [])),
                    },
                )

                inserted += 1
                print(f"[PatternDiscovery] Inserted: {p.get('name')}")

            except Exception as e:
                print(f"[PatternDiscovery] Insert failed: {e}")

        await session.commit()
        return inserted
