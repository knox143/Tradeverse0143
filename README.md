# 🚀 TradeVerse — Real-Time Paper Trading Platform

**TradeVerse** is a full-featured, multi-market paper trading and technical analysis platform built with **Python (Flask)**, **SQLite**, **vanilla JavaScript**, and **TradingView Lightweight Charts**.

It allows users to simulate real trading in **Indian Stocks (NSE in INR ₹)**, **US/Global Stocks (USDT)**, and **Cryptocurrencies (Binance Live in USDT)** with real-time candlestick charts, dedicated coin/stock studios, and complete trade close duration timeline tracking.

---

## ✨ Key Features

### 1. 💰 Dual-Currency Virtual Wallet System
- **Indian Stock Market**: Traded in **INR (₹)** with an initial virtual practice balance of **₹1,000,000.00 INR** (10 Lakhs).
- **Global Stocks & Crypto Markets**: Traded in **USDT** with an initial virtual practice balance of **10,000.00 USDT**.
- Balances are tracked and deducted independently without cross-currency contamination.

### 2. ⚡ Live Real-Time Market Data
- **Cryptocurrency (Binance Live Feed)**: Real-time tick-by-tick prices and 24h metrics directly from Binance Public API (`api.binance.com/api/v3/ticker/24hr`) with CoinGecko fallback.
- **Indian Equities (NSE)**: Real-time market prices streamed via Yahoo Finance (`.NS` tickers) with Twelve Data fallback.
- **Global Equities (US Stocks)**: Real-time quotes for Apple, Microsoft, NVIDIA, Tesla, Amazon, and Google.
- **Fast Performance**: Pooled HTTP sessions, in-memory caching, and concurrent multithreaded quote fetching.

### 3. 📊 Dedicated Candlestick Chart Studio
- **Coin Candlestick Studio (`/crypto`)**: Interactive candlestick chart for every major cryptocurrency (BTC, ETH, SOL, BNB, XRP, DOGE, ADA, MATIC).
- **Stock Candlestick Studio (`/stocks`)**: Daily OHLCV candlestick charts for Indian equities (Reliance, TCS, HDFC Bank, Infosys) and US stocks (Apple, Microsoft, Tesla, NVIDIA).
- **Multi-Asset Dashboard Switcher (`/dashboard`)**: Switch between the practice portfolio curve and live candlestick graphs with a single click.
- **Trade Modal Live Chart**: Clicking "Trade" on any asset loads its live candlestick chart right inside the order popup dialog.

### 4. ⏱️ Trade Close Lifecycle & Duration Timeline
- **Holding Time Tracking**: Measures the exact duration each trade was open (e.g. `⏱️ 45s`, `18m`, `2h 15m`, `3d 4h`).
- **Dedicated Timeline Page (`/timeline`)**:
  - Key stats: Total Closed Trades, Win Rate %, Average Hold Duration, Fastest & Longest Trades, and Net Realized P/L in INR & USDT.
  - Active Positions: Live tracking of how long currently open positions have been held.
  - Chronological Trade Cards: Visual breakdown showing `BUY entry` ➔ `Holding Duration` ➔ `SELL exit` ➔ `Realized Net P/L`.
- **Instant Order Feedback**: Confirmation toasts report holding duration and realized gain upon position close.

### 5. 🎨 Authentic Brand Vector Logos & Market Pairs
- Official vector SVG logos for all cryptocurrencies (Bitcoin ₿, Ethereum Ξ, Solana ◎, Binance BNB, Ripple ✕, Dogecoin Ð, Cardano ₳, Polygon ⬡).
- Official corporate brand badges with Indian Rupee symbol `₹` for Indian stocks (Reliance, TCS, Infosys, HDFC Bank, ICICI Bank, Tata Motors, SBI).
- Authentic brand vector logos for Global stocks (Apple , Microsoft, NVIDIA, Tesla, Amazon, Google).
- Standardized market pair tags (`BTC/USDT`, `RELIANCE/INR`, `AAPL/USDT`).

---

## 🛠️ Tech Stack

- **Backend**: Python 3.10+, Flask, Werkzeug, SQLite3
- **Frontend**: HTML5, CSS3 (Custom Responsive Design System), Vanilla JavaScript (No heavy frameworks)
- **Charting**: TradingView Lightweight Charts (v4.2.3)
- **Icons**: Lucide Icons & Custom SVG Vector Logos
- **Data Providers**: Binance API, Yahoo Finance API, CoinGecko, Finnhub

---

## 🚀 Quick Start (Run Locally)

### 1. Clone the repository
```bash
git clone https://github.com/YOUR_USERNAME/TradeVerse.git
cd TradeVerse
```

### 2. Create and activate a virtual environment
```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Setup environment variables (Optional)
```bash
# Copy the example environment file
cp .env.example .env
```

### 5. Start the application
```bash
python app.py
```

Open your browser and navigate to:
👉 **`http://127.0.0.1:5000`**

Register a new account or sign in with the default demo account to start paper trading!

---

## 📁 Project Structure

```text
TradeVerse/
├── api/
│   ├── crypto.py         # Binance & CoinGecko real-time crypto quote & candle fetcher
│   ├── stocks.py         # Yahoo Finance & Finnhub live stock quote & candle fetcher
│   ├── portfolio.py      # Dual-currency portfolio valuation & leaderboard logic
│   └── icons.py          # Vector SVG logos & badges for all coins & stocks
├── database/
│   └── tradeverse.db     # SQLite database (auto-created on first run)
├── static/
│   ├── css/
│   │   └── style.css     # Complete responsive design system
│   └── js/
│       └── main.js       # Dynamic charting, trade modal, and watchlist interactions
├── templates/
│   ├── base.html         # Main app layout, sidebar, and trade modal
│   ├── dashboard.html    # Summary cards, multi-asset chart switcher, market movers
│   ├── crypto.html       # Coin Chart Studio & crypto market table
│   ├── stocks.html       # Stock Chart Studio & equities directory (NSE & Global)
│   ├── portfolio.html    # Holdings with holding duration & closed trade ledger
│   ├── timeline.html     # Trade lifecycle, duration analytics, and closed trades
│   ├── watchlist.html    # Saved instruments shortlist
│   ├── leaderboard.html  # User ranking based on portfolio performance
│   └── login.html        # Authentication pages
├── app.py                # Flask routes, filters, and API endpoints
├── database.py           # SQLite database layer, migrations, and trade execution
├── requirements.txt      # Python dependencies
└── README.md             # Project documentation
```

---

## 🔒 Security & Privacy

- All trading is strictly **virtual paper trading** using simulated credits. No real financial transactions are executed.
- User passwords are encrypted using salted `werkzeug.security` hashes.
- Session cookies use `HttpOnly` and `SameSite=Lax` protection.

---

## 📄 License

This project is open-source and available under the [MIT License](LICENSE).
