---
paths:
  - "**/pattern*.ts"
  - "**/evolution*.ts"
  - "**/fitness*.ts"
  - "**/backtest*.ts"
---

# Trading Pattern Rules

## Core Philosophy
Evolution discovers optimal boundaries - NOT humans.

## Raw Data Storage
```typescript
// ALWAYS store raw values
tradeData = {
  rsi: 28.3,           // NOT rsi_bucket_3 or rsi_oversold
  macd: -0.23,         // Raw float
  volumeRatio: 1.45,   // Raw ratio
  hour: 10,            // Raw integer
};
```

## Pattern Generation
```typescript
// Generate RANDOM ranges - evolution discovers optimal
pattern.conditions = [
  { indicator: 'rsi', min: Math.random() * 50, max: 50 + Math.random() * 50 },
  { indicator: 'volume', min: 0.5, max: 0.5 + Math.random() * 3 },
];
```

## Fitness Calculation
- Always bound values: no Infinity, NaN, or unbounded results
- Include multiple metrics: ROI, Sharpe, win rate, trade count
- Penalize overfitting (too few trades, extreme values)

## Backtesting
- Use REAL historical data only (ohlcv_1h, ohlcv_6h, ohlcv_1d)
- Minimum 100 trades for statistical significance
- Walk-forward validation: train on past, test on future
- Never peek at future data

## Selection Pressure
```typescript
// High fitness survives, low fitness dies
if (fitness > threshold) {
  surviveAndReproduce(pattern);
} else {
  markForDeletion(pattern);
}
```
