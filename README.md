# QQQ Opening Range Breakout Strategy Backtester

## Overview

This project implements and backtests a simple Opening Range Breakout (ORB) strategy on QQQ using 5-minute intraday data. The strategy combines price action with relative volume analysis to identify potential trading opportunities at market open.

## Strategy Rules

### Entry Conditions

1. **Opening Range (OR)**

   - Uses the first 5-minute candle (9:30-9:35 ET)
   - Determines high and low of this range

2. **Volume Filter**

   - Calculates Relative Volume of the first 5-minute candle
   - Compares to 14-day average of first 5-minute volume
   - Only trades if Relative Volume ≥ 100%

3. **Direction Filter**

   - Long only on bullish OR candle (close > open)
   - Short only on bearish OR candle (close < open)
   - No trades on doji candles (close = open)

4. **Entry Execution**
   - Long: Stop order above OR high
   - Short: Stop order below OR low

### Risk Management

- Stop Loss: 10% of 14-day ATR from entry price
- Position Size: Risks 1% of account per trade
- Exit: Either stop loss hit or market close (16:00 ET)

## Implementation Details

### Key Components

- Daily ATR calculation
- Relative Volume computation
- Position sizing based on account risk
- IBKR commission simulation

### Data Requirements

- 5-minute OHLCV data for QQQ
- Minimum 14 days of historical data for indicators

## Results

The backtest results compare the strategy's performance against a buy & hold approach on QQQ, showing:

- Equity curve comparison
- Key performance metrics
- Risk-adjusted returns

Dependencies - pandas - numpy - matplotlib - seaborn
Future Improvements - Add multiple time frame analysis - Implement adaptive position sizing - Add more sophisticated exit strategies - Include market regime filters

Author
Francesco Bellingeri
