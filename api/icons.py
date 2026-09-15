"""Asset visual symbol & logo helper for TradeVerse.
Provides authentic, crisp vector SVGs and badge symbols for Indian stocks, Global stocks, and Crypto coins.
"""

from markupsafe import Markup

# Dictionary of authentic vector SVGs for all supported assets
ASSET_SVGS = {
    # --- Crypto Market (USDT) ---
    "BTC": """<svg viewBox="0 0 32 32" class="asset-svg crypto-btc" width="{size}" height="{size}">
        <circle cx="16" cy="16" r="16" fill="#F7931A"/>
        <path fill="#FFF" d="M23.189 14.02c.314-2.096-1.283-3.223-3.465-3.975l.708-2.84-1.728-.43-.69 2.765c-.454-.114-.92-.22-1.385-.326l.695-2.783L15.596 6l-.708 2.839c-.376-.086-.746-.17-1.104-.26l.002-.009-2.384-.595-.46 1.846s1.283.294 1.256.312c.7.175.826.638.805 1.006l-.806 3.235c.048.012.11.03.18.057l-.183-.045-1.13 4.532c-.086.212-.303.531-.793.41.018.025-1.256-.313-1.256-.313l-.858 1.978 2.25.561c.418.105.828.215 1.231.318l-.715 2.872 1.727.43.708-2.84c.472.127.93.245 1.378.357l-.706 2.828 1.728.43.715-2.866c2.948.558 5.164.333 6.097-2.333.752-2.146-.037-3.385-1.588-4.192 1.13-.26 1.98-1.003 2.207-2.538zm-3.95 5.538c-.535 2.146-4.148.986-5.32.695l.95-3.805c1.172.293 4.929.872 4.37 3.11zm.535-5.569c-.487 1.953-3.495.96-4.47.717l.86-3.45c.976.244 4.118.7 3.61 2.733z"/>
    </svg>""",

    "ETH": """<svg viewBox="0 0 32 32" class="asset-svg crypto-eth" width="{size}" height="{size}">
        <circle cx="16" cy="16" r="16" fill="#627EEA"/>
        <g fill="#FFF">
            <polygon fill-opacity=".6" points="16 4 16 16.34 22.99 13.21"/>
            <polygon points="16 4 9 13.21 16 16.34"/>
            <polygon fill-opacity=".6" points="16 21.97 16 28 23 18.25"/>
            <polygon points="16 21.97 9 18.25 16 28"/>
            <polygon fill-opacity=".2" points="16 16.34 22.99 13.21 16 10.15"/>
            <polygon fill-opacity=".4" points="9 13.21 16 16.34 16 10.15"/>
        </g>
    </svg>""",

    "SOL": """<svg viewBox="0 0 32 32" class="asset-svg crypto-sol" width="{size}" height="{size}">
        <circle cx="16" cy="16" r="16" fill="#13151D"/>
        <defs>
            <linearGradient id="solG_{uid}" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stop-color="#00FFA3"/>
                <stop offset="100%" stop-color="#DC1FFF"/>
            </linearGradient>
        </defs>
        <path fill="url(#solG_{uid})" d="M9.5 21.7c.1-.1.3-.2.5-.2h12.5c.3 0 .5.3.3.6l-2.3 2.3c-.1.1-.3.2-.5.2H7.5c-.3 0-.5-.3-.3-.6l2.3-2.3zm0-11.4c.1-.1.3-.2.5-.2h12.5c.3 0 .5.3.3.6l-2.3 2.3c-.1.1-.3.2-.5.2H7.5c-.3 0-.5-.3-.3-.6l2.3-2.3zm13 5.7c-.1-.1-.3-.2-.5-.2H9.5c-.3 0-.5.3-.3.6l2.3 2.3c.1.1.3.2.5.2h12.5c.3 0 .5-.3.3-.6l-2.3-2.3z"/>
    </svg>""",

    "BNB": """<svg viewBox="0 0 32 32" class="asset-svg crypto-bnb" width="{size}" height="{size}">
        <circle cx="16" cy="16" r="16" fill="#F3BA2F"/>
        <g fill="#FFF">
            <polygon points="16 7 19.2 10.2 16 13.4 12.8 10.2"/>
            <polygon points="22.2 13.4 25.4 16.6 22.2 19.8 19 16.6"/>
            <polygon points="9.8 13.4 13 16.6 9.8 19.8 6.6 16.6"/>
            <polygon points="16 19.8 19.2 23 16 26.2 12.8 23"/>
            <polygon points="16 14.8 17.8 16.6 16 18.4 14.2 16.6"/>
        </g>
    </svg>""",

    "XRP": """<svg viewBox="0 0 32 32" class="asset-svg crypto-xrp" width="{size}" height="{size}">
        <circle cx="16" cy="16" r="16" fill="#23292F"/>
        <path fill="#FFF" d="M23.8 8h2.3l-5.6 5.5-2.2-2.2 4.1-4c.4-.4.9-.7 1.4-.7v1.4zm-15.6 0h2.3l4.1 4-2.2 2.2L6.8 8.7c.4 0 .9.3 1.4.7zm0 16h2.3l9.8-9.6 2.2 2.2-7.8 7.4h-6.5zm15.6 0h-2.3l-4.1-4 2.2-2.2 4.2 4.1v2.1z"/>
    </svg>""",

    "DOGE": """<svg viewBox="0 0 32 32" class="asset-svg crypto-doge" width="{size}" height="{size}">
        <circle cx="16" cy="16" r="16" fill="#C2A633"/>
        <path fill="#FFF" d="M12 8.5h6c4.5 0 7.5 3 7.5 7.5s-3 7.5-7.5 7.5h-6V8.5zm3.5 12h2.2c2.5 0 4.2-1.7 4.2-4.5s-1.7-4.5-4.2-4.5h-2.2v9zm-6.5-5.2h8.5v2H9v-2z"/>
    </svg>""",

    "ADA": """<svg viewBox="0 0 32 32" class="asset-svg crypto-ada" width="{size}" height="{size}">
        <circle cx="16" cy="16" r="16" fill="#0033AD"/>
        <g fill="#FFF">
            <circle cx="16" cy="16" r="3.2"/>
            <circle cx="16" cy="8.5" r="1.3"/>
            <circle cx="16" cy="23.5" r="1.3"/>
            <circle cx="8.5" cy="16" r="1.3"/>
            <circle cx="23.5" cy="16" r="1.3"/>
            <circle cx="10.8" cy="10.8" r="1.3"/>
            <circle cx="21.2" cy="21.2" r="1.3"/>
            <circle cx="10.8" cy="21.2" r="1.3"/>
            <circle cx="21.2" cy="10.8" r="1.3"/>
        </g>
    </svg>""",

    "MATIC": """<svg viewBox="0 0 32 32" class="asset-svg crypto-matic" width="{size}" height="{size}">
        <circle cx="16" cy="16" r="16" fill="#8247E5"/>
        <path fill="#FFF" d="M21 13.5l-4.2-2.4c-.5-.3-1.1-.3-1.6 0L11 13.5c-.5.3-.8.8-.8 1.4v4.8c0 .6.3 1.1.8 1.4l4.2 2.4c.5.3 1.1.3 1.6 0l4.2-2.4c.5-.3.8-.8.8-1.4v-4.8c0-.6-.3-1.1-.8-1.4zm-5 7.2l-3.5-2v-4l3.5 2v4zm1.5-4.8l-3.5-2 3.5-2 3.5 2-3.5 2zm3.5 2.8l-3.5 2v-4l3.5-2v4z"/>
    </svg>""",

    # --- Global Equities (USDT) ---
    "AAPL": """<svg viewBox="0 0 32 32" class="asset-svg stock-aapl" width="{size}" height="{size}">
        <circle cx="16" cy="16" r="16" fill="#1C1C1E"/>
        <path fill="#FFF" d="M19.9 16.6c0-2.4 1.9-3.5 2-3.6-1.1-1.6-2.8-1.8-3.4-1.9-1.4-.1-2.8.8-3.5.8-.7 0-1.8-.8-3-.8-1.5 0-2.9.9-3.7 2.3-1.6 2.8-.4 6.9 1.1 9.2.8 1.1 1.6 2.3 2.8 2.2 1.1 0 1.6-.7 2.9-.7s1.7.7 2.9.7c1.2 0 2-.1 2.8-1.2.9-1.3 1.2-2.5 1.3-2.6-.1 0-2.3-.9-2.3-3.5zm-2.4-7.5c.6-.8 1.1-1.9.9-3.1-1 .1-2.1.7-2.7 1.4-.6.7-1.1 1.8-.9 2.9 1.1.1 2.1-.5 2.7-1.2z"/>
    </svg>""",

    "MSFT": """<svg viewBox="0 0 32 32" class="asset-svg stock-msft" width="{size}" height="{size}">
        <circle cx="16" cy="16" r="16" fill="#0F172A"/>
        <g transform="translate(8.5, 8.5)">
            <rect x="0" y="0" width="6.8" height="6.8" fill="#F25022"/>
            <rect x="8.2" y="0" width="6.8" height="6.8" fill="#7FBA00"/>
            <rect x="0" y="8.2" width="6.8" height="6.8" fill="#00A4EF"/>
            <rect x="8.2" y="8.2" width="6.8" height="6.8" fill="#FFB900"/>
        </g>
    </svg>""",

    "NVDA": """<svg viewBox="0 0 32 32" class="asset-svg stock-nvda" width="{size}" height="{size}">
        <circle cx="16" cy="16" r="16" fill="#1A1A1A"/>
        <circle cx="16" cy="16" r="14.5" fill="none" stroke="#76B900" stroke-width="1.2"/>
        <path fill="#76B900" d="M12 10.5c-.5.3-.9.7-1.2 1.2-2.2 2.9-1.5 7.3 1.6 9.3 2.7 1.8 6.4 1.3 8.6-.8l-1.6-1.3c-1.5 1.4-3.9 1.7-5.8.5-2-1.3-2.5-4.1-1.1-6.1.8-1 2-1.7 3.3-1.6l1.2-1.8c-1.7-.3-3.5.1-5 .6zm6 3c-1.1-.1-2.2.5-2.7 1.5-.7 1.3-.4 3 .8 3.8 1.1.8 2.5.6 3.4-.3l1.3 1.1c-1.5 1.6-3.9 1.8-5.7.5-1.9-1.3-2.5-4-1.1-6.1 1-1.6 2.9-2.5 4.8-2.1l-.8 1.6z"/>
    </svg>""",

    "TSLA": """<svg viewBox="0 0 32 32" class="asset-svg stock-tsla" width="{size}" height="{size}">
        <circle cx="16" cy="16" r="16" fill="#E82127"/>
        <path fill="#FFF" d="M16 10c2.2 0 4.4.4 6.2 1l.5-2.2C20.8 8 18.4 7.6 16 7.6s-4.8.4-6.7 1.2l.5 2.2c1.8-.6 4-1 6.2-1zm6.6 2.8l.6-2.4c-2.1-.5-4.7-.8-7.2-.8s-5.1.3-7.2.8l.6 2.4c1.9-.4 4.3-.7 6.6-.7s4.7.3 6.6.7zm-5.3 1.4h-2.6v9.8h2.6v-9.8z"/>
    </svg>""",

    "AMZN": """<svg viewBox="0 0 32 32" class="asset-svg stock-amzn" width="{size}" height="{size}">
        <circle cx="16" cy="16" r="16" fill="#232F3E"/>
        <path fill="#FF9900" d="M9 20.5c2.6 1.5 5.8 2 8.8 1.3 1.6-.4 3.2-1 4.4-2 .3-.2.1-.5-.2-.4-2.5.8-5.2.8-7.7.1-1.6-.5-3.3-1.4-4.8-2.5-.2-.2-.5.1-.5.3l0 .2zm13-1.2c-.3-.4-1.7-.2-2.4-.1-.2 0-.3.2-.1.3.7.5 1.9.5 2.2.5.3-.1.5-.4.3-.7z"/>
        <path fill="#FFF" d="M16 13c-2 0-3.2 1-3.4 2.5l1.6.3c.1-.8.7-1.3 1.7-1.3 1 0 1.6.5 1.6 1.4v.5c-.5-.1-1.3-.2-2.1-.2-1.9 0-3.3.9-3.3 2.4 0 1.4 1.1 2.2 2.6 2.2 1.2 0 2-.6 2.5-1.3h.1v1.1h1.6v-5c0-1.8-1.4-2.6-2.9-2.6zm.3 6.3c-.7 0-1.3-.5-1.3-1.2 0-.7.6-1.2 1.5-1.2.6 0 1 .1 1.3.2v.8c-.3.8-.8 1.4-1.5 1.4z"/>
    </svg>""",

    "GOOGL": """<svg viewBox="0 0 32 32" class="asset-svg stock-googl" width="{size}" height="{size}">
        <circle cx="16" cy="16" r="16" fill="#FFFFFF"/>
        <circle cx="16" cy="16" r="15" fill="none" stroke="#E2E8F0" stroke-width="1"/>
        <g transform="translate(8, 8)">
            <path fill="#4285F4" d="M15.7 8.2c0-.5 0-1.1-.2-1.6H8v3.1h4.3c-.2 1-.8 1.8-1.6 2.4v2h2.6c1.5-1.4 2.4-3.5 2.4-5.9z"/>
            <path fill="#34A853" d="M8 16c2.2 0 4-.7 5.3-2l-2.6-2c-.7.5-1.6.8-2.7.8-2.1 0-3.9-1.4-4.5-3.4H.8v2.1C2.1 14.1 4.9 16 8 16z"/>
            <path fill="#FBBC05" d="M3.5 9.4c-.2-.5-.3-1.1-.3-1.7s.1-1.2.3-1.7V3.9H.8C.3 5 0 6.3 0 7.7s.3 2.7.8 3.8l2.7-2.1z"/>
            <path fill="#EA4335" d="M8 3.1c1.2 0 2.2.4 3 1.2L13.4 2C12 1 10.1 0 8 0 4.9 0 2.1 1.9.8 4.6l2.7 2.1c.6-2 2.4-3.6 4.5-3.6z"/>
        </g>
    </svg>""",

    # --- Indian Stock Market (NSE / BSE in INR ₹) ---
    "RELIANCE.NS": """<svg viewBox="0 0 32 32" class="asset-svg stock-reliance" width="{size}" height="{size}">
        <circle cx="16" cy="16" r="16" fill="#0B2545"/>
        <circle cx="16" cy="16" r="14.5" fill="none" stroke="#D4AF37" stroke-width="1.2"/>
        <g fill="#FFF" font-family="'Manrope', Arial, sans-serif" font-weight="800" text-anchor="middle">
            <text x="16" y="16.5" font-size="8" fill="#FFF" letter-spacing="0.5">RIL</text>
            <text x="16" y="23" font-size="5" fill="#F3C64F">₹ &bull; NSE</text>
            <path d="M16 6.8c-.8 1.2-1.2 2-.4 2.8.8-.8 1.2-1.6.4-2.8z" fill="#E63946"/>
        </g>
    </svg>""",

    "TCS.NS": """<svg viewBox="0 0 32 32" class="asset-svg stock-tcs" width="{size}" height="{size}">
        <circle cx="16" cy="16" r="16" fill="#004F9E"/>
        <circle cx="16" cy="16" r="14.5" fill="none" stroke="#60A5FA" stroke-width="1"/>
        <g fill="#FFF" font-family="'Manrope', Arial, sans-serif" font-weight="800" text-anchor="middle">
            <text x="16" y="16" font-size="8.5" letter-spacing="0.8">TCS</text>
            <text x="16" y="23" font-size="5" fill="#BAE6FD">TATA &bull; ₹</text>
        </g>
    </svg>""",

    "INFY.NS": """<svg viewBox="0 0 32 32" class="asset-svg stock-infy" width="{size}" height="{size}">
        <circle cx="16" cy="16" r="16" fill="#007CC3"/>
        <g fill="#FFF" font-family="'Manrope', Arial, sans-serif" font-weight="800" text-anchor="middle">
            <text x="16" y="16.5" font-size="8" letter-spacing="0.4">INFY</text>
            <text x="16" y="23.5" font-size="5" fill="#E0F2FE">NSE &bull; ₹</text>
            <circle cx="16" cy="8" r="1.3" fill="#FFF"/>
        </g>
    </svg>""",

    "HDFCBANK.NS": """<svg viewBox="0 0 32 32" class="asset-svg stock-hdfc" width="{size}" height="{size}">
        <circle cx="16" cy="16" r="16" fill="#004C8F"/>
        <rect x="8.5" y="8.5" width="15" height="15" rx="2.5" fill="#ED232A"/>
        <rect x="10.5" y="14" width="11" height="4" fill="#004C8F"/>
        <rect x="14" y="10.5" width="4" height="11" fill="#004C8F"/>
        <g fill="#FFF" font-family="'Manrope', Arial, sans-serif" font-weight="800" text-anchor="middle">
            <text x="16" y="17.2" font-size="7">₹</text>
        </g>
    </svg>""",

    "ICICIBANK.NS": """<svg viewBox="0 0 32 32" class="asset-svg stock-icici" width="{size}" height="{size}">
        <circle cx="16" cy="16" r="16" fill="#9B2329"/>
        <circle cx="16" cy="16" r="14.5" fill="none" stroke="#F58220" stroke-width="1.2"/>
        <g font-family="'Manrope', Arial, sans-serif" font-weight="800" text-anchor="middle">
            <text x="16" y="17" font-size="7.5" fill="#F58220" letter-spacing="0.4">ICICI</text>
            <text x="16" y="23" font-size="4.8" fill="#FFF">BANK &bull; ₹</text>
            <circle cx="16" cy="9" r="1.2" fill="#F58220"/>
        </g>
    </svg>""",

    "TATAMOTORS.NS": """<svg viewBox="0 0 32 32" class="asset-svg stock-tatamotors" width="{size}" height="{size}">
        <circle cx="16" cy="16" r="16" fill="#1E3A8A"/>
        <circle cx="16" cy="16" r="14.5" fill="none" stroke="#93C5FD" stroke-width="1"/>
        <g fill="#FFF" font-family="'Manrope', Arial, sans-serif" font-weight="800" text-anchor="middle">
            <text x="16" y="15.5" font-size="6.5" letter-spacing="0.5">TATA</text>
            <text x="16" y="22" font-size="4.8" fill="#93C5FD">MOTORS &bull; ₹</text>
            <path d="M11 9c2.5-1 7.5-1 10 0" stroke="#FFF" stroke-width="1.2" fill="none"/>
        </g>
    </svg>""",

    "SBIN.NS": """<svg viewBox="0 0 32 32" class="asset-svg stock-sbin" width="{size}" height="{size}">
        <circle cx="16" cy="16" r="16" fill="#0284C7"/>
        <circle cx="16" cy="13.5" r="5" fill="#FFF"/>
        <rect x="14.8" y="13.5" width="2.4" height="8.5" fill="#0284C7"/>
        <circle cx="16" cy="13.5" r="2.5" fill="#0284C7"/>
        <text x="16" y="26.5" font-family="'Manrope', Arial, sans-serif" font-size="4.5" font-weight="800" fill="#FFF" text-anchor="middle">SBI &bull; ₹</text>
    </svg>""",
}

# Aliases without extensions or lowercased
ALIAS_MAP = {
    "RELIANCE": "RELIANCE.NS",
    "TCS": "TCS.NS",
    "INFY": "INFY.NS",
    "HDFC": "HDFCBANK.NS",
    "HDFCBANK": "HDFCBANK.NS",
    "ICICI": "ICICIBANK.NS",
    "ICICIBANK": "ICICIBANK.NS",
    "TATAMOTORS": "TATAMOTORS.NS",
    "TATA": "TATAMOTORS.NS",
    "SBIN": "SBIN.NS",
    "SBI": "SBIN.NS",
    "POL": "MATIC",
}

_svg_counter = 0

def get_asset_svg(symbol: str, asset_type: str = "stock", size: int = 32) -> Markup:
    """Return crisp inline SVG markup for a given asset symbol."""
    global _svg_counter
    _svg_counter += 1
    sym_clean = (symbol or "").strip().upper()
    resolved = ALIAS_MAP.get(sym_clean, sym_clean)
    
    # Try direct match
    svg_template = ASSET_SVGS.get(resolved)
    if not svg_template:
        # Try stripping suffix (e.g. RELIANCE from RELIANCE.NS)
        base = sym_clean.split(".")[0]
        resolved = ALIAS_MAP.get(base, base)
        svg_template = ASSET_SVGS.get(resolved)

    if svg_template:
        svg_code = svg_template.replace("{size}", str(size)).replace("{uid}", str(_svg_counter))
        return Markup(svg_code)

    # Intelligent graceful fallback badge with currency glyph
    is_inr = sym_clean.endswith(".NS") or sym_clean.endswith(".BO") or asset_type == "inr"
    bg_color = "#007D70" if asset_type == "crypto" else ("#0B2545" if is_inr else "#1E293B")
    glyph = "₹" if is_inr else (sym_clean[:3] if len(sym_clean) <= 3 else sym_clean[0])
    sub = "INR" if is_inr else ("CRYPTO" if asset_type == "crypto" else "USDT")
    
    fallback_svg = f"""<svg viewBox="0 0 32 32" class="asset-svg fallback" width="{size}" height="{size}">
        <circle cx="16" cy="16" r="16" fill="{bg_color}"/>
        <g fill="#FFF" font-family="'Manrope', Arial, sans-serif" font-weight="800" text-anchor="middle">
            <text x="16" y="17" font-size="9">{glyph}</text>
            <text x="16" y="24" font-size="4.5" fill="#E2E8F0">{sub}</text>
        </g>
    </svg>"""
    return Markup(fallback_svg)


def get_market_pair(symbol: str, currency: str = "") -> str:
    """Return formatted trading pair string like 'BTC/USDT', 'RELIANCE/INR', 'AAPL/USDT'."""
    sym = (symbol or "").strip().upper()
    clean_sym = sym.split(".")[0]
    if not currency:
        currency = "INR" if (sym.endswith(".NS") or sym.endswith(".BO")) else "USDT"
    return f"{clean_sym}/{currency}"
