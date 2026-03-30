# 🤖 KITE AutoTrade — Professional Algorithmic Trading Bot

A sophisticated, production-ready automated trading bot for the Indian stock market (NSE) using Zerodha's Kite API. This system combines multi-strategy technical analysis, real-time risk management, and an interactive web dashboard to execute algorithmic trades with full automation.

**Version:** 7.0 | **Status:** Active Development | **License:** Personal Use

---

## 📋 Table of Contents

1. [Overview & Features](#overview--features)
2. [System Architecture](#system-architecture)
3. [Prerequisites & Requirements](#prerequisites--requirements)
4. [Installation & Setup](#installation--setup)
5. [Configuration Guide](#configuration-guide)
6. [Daily Trading Workflow](#daily-trading-workflow)
7. [Bot Features & Capabilities](#bot-features--capabilities)
8. [Dashboard Guide](#dashboard-guide)
9. [Trading Strategies](#trading-strategies)
10. [Risk Management](#risk-management)
11. [API Integration Details](#api-integration-details)
12. [Troubleshooting & FAQ](#troubleshooting--faq)
13. [Project Structure](#project-structure)
14. [Performance Monitoring](#performance-monitoring)
15. [Security Best Practices](#security-best-practices)

---

## Overview & Features

### 🎯 Core Capabilities

KITE AutoTrade is designed for active traders who want to automate their trading strategies while maintaining full control and visibility. The system combines:

- **Multi-Strategy Analysis**: Concurrent evaluation of multiple technical indicators and strategies
- **Automated Order Execution**: Market orders with GTT (Good-Till-Triggered) contingent orders
- **Real-Time Risk Management**: Position sizing, stop-loss adjustment, trailing stops, and daily loss limits
- **Interactive Dashboard**: Live P&L tracking, trade monitoring, parameter adjustment, and strategy statistics
- **Paper Trading Mode**: Risk-free testing environment with virtual capital
- **Live Trading Support**: Full live trading with real capital (after thorough testing)
- **Market Intelligence**: Index tracking, volatility monitoring (VIX), sector rotation, IPO analysis
- **Sentiment Integration**: Optional news sentiment analysis for trade filtering
- **Professional Logging**: Comprehensive trade logs, reports, and analytics

### ✨ Key Features

#### 1. **Intelligent Order Management**
   - Market orders for entry execution
   - GTT OCO (One-Cancels-Other) orders for exit automation
   - Limit orders for target achievement
   - Automatic order modification for trailing stops
   - Order tagging for strategy identification

#### 2. **Advanced Risk Management**
   - Position-wise stop-loss enforcement
   - Automatic trailing stop-loss updates based on market movement
   - Daily profit target achievement shutdown
   - Daily loss limit enforcement (auto square-off)
   - Maximum position limits (default: 5 concurrent trades)
   - Per-trade capital allocation based on confidence
   - Equity protection mechanisms

#### 3. **Market Awareness**
   - VIX (volatility index) monitoring with automatic entry suppression when VIX > 25
   - Nifty index tracking for market regime detection
   - Sector-wise hot sector identification for prioritization
   - Economic calendar integration (optional)
   - News sentiment scoring for trade validation

#### 4. **Trading Schedule Control**
   - Automatic market open/close detection
   - Entry window configuration (default: 9:15 AM - 3:20 PM IST)
   - Lunch break avoidance support
   - End-of-day square-off automation
   - Holiday market closure handling

#### 5. **Dashboard & Monitoring**
   - Real-time P&L tracking
   - Live position monitoring with current price
   - Order log with timestamps and trade details
   - Strategy performance statistics
   - Parameter adjustment without restarting bot
   - Start/Stop controls from dashboard

#### 6. **Data & Reporting**
   - Daily trading reports in JSON format
   - Win rate calculations
   - Strategy-wise performance breakdown
   - Closed trade history
   - Session parameters snapshot

---
Run it now

cd trading_bot_v7
python setup.py          # install packages once
python login.py          # every morning

python paper_trading.py  # safe mode — asks for your parameters
# Enter: capital, daily target, max loss, stop loss %, positions
# Open http://localhost:8050

python live_trading.py   # real money — same parameter setup
## System Architecture

### High-Level Architecture
