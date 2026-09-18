/* TradeVerse browser behavior: navigation, dynamic candlestick charts, studios, timeline, watchlists, and paper orders. */
(function () {
    "use strict";

    const tradeDialog = document.getElementById("trade-dialog");
    const tradeForm = document.getElementById("trade-form");
    const tradeSymbol = document.getElementById("trade-symbol");
    const tradeAssetType = document.getElementById("trade-asset-type");
    const tradeSide = document.getElementById("trade-side");
    const tradeQuantity = document.getElementById("trade-quantity");
    const tradePrice = document.getElementById("trade-price");
    const tradeTotal = document.getElementById("trade-total");
    const tradeInstrument = document.getElementById("trade-instrument");
    const tradeCurrencyTag = document.getElementById("trade-currency-tag");
    const tradeWalletAvailable = document.getElementById("trade-wallet-available");
    const modalChartCanvas = document.getElementById("trade-modal-chart");
    const toastRegion = document.getElementById("toast-region");
    let activeTradePrice = 0;
    let activeTradeCurrency = "INR";
    const activeChartsMap = new WeakMap();

    /** Initialize the icon placeholders after first render and dynamic additions. */
    function refreshIcons() {
        if (window.lucide) {
            window.lucide.createIcons({ attrs: { "stroke-width": 1.8 } });
        }
    }

    /** Format a numeric value as INR or USDT depending on the currency. */
    function formatCurrency(value, currency = activeTradeCurrency) {
        const val = Number(value || 0);
        const formatted = val.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        if (currency === "INR") {
            return `₹${formatted}`;
        }
        return `${formatted} USDT`;
    }

    /** Show a short, accessible status notice without disrupting the page layout. */
    function showToast(message, isError) {
        if (!toastRegion) return;
        const toast = document.createElement("div");
        toast.className = `toast${isError ? " error" : ""}`;
        toast.innerHTML = `<i data-lucide="${isError ? "circle-alert" : "check-circle-2"}"></i><span></span>`;
        toast.querySelector("span").textContent = message;
        toastRegion.appendChild(toast);
        refreshIcons();
        window.setTimeout(() => toast.remove(), 4200);
    }

    /** Update available balance displayed in the trade modal. */
    function updateDialogWalletBalance() {
        if (!tradeWalletAvailable) return;
        const inrElem = document.querySelector("[data-wallet-inr]");
        const usdtElem = document.querySelector("[data-wallet-usdt]");
        if (activeTradeCurrency === "INR") {
            tradeWalletAvailable.textContent = inrElem ? inrElem.textContent.trim() : "₹1,000,000.00";
        } else {
            tradeWalletAvailable.textContent = usdtElem ? usdtElem.textContent.trim() : "10,000.00 USDT";
        }
    }

    /** Open the reusable modal with market information supplied by a clicked row or button. */
    
    /** Dynamically fetch and display an authentic SVG asset logo. */
    async function updateAssetIcon(element, symbol, assetType, size = 36) {
        if (!element || !symbol) return;
        try {
            const resp = await fetch(`/api/icon/${encodeURIComponent(assetType)}/${encodeURIComponent(symbol)}?size=${size}`);
            if (resp.ok) {
                const ct = resp.headers.get("content-type") || "";
                if (ct.includes("application/json")) {
                    const data = await resp.json();
                    if (data.ok && data.svg) {
                        element.innerHTML = data.svg;
                    }
                }
            }
        } catch (e) {}
    }

    function openTradeDialog(trigger) {
        if (!tradeDialog || !tradeForm) return;
        activeTradePrice = Number(trigger.dataset.price || 0);
        const symbol = trigger.dataset.symbol || "";
        const assetType = trigger.dataset.assetType || "stock";
        let currency = trigger.dataset.currency;
        if (!currency) {
            if (assetType === "crypto") {
                currency = "USDT";
            } else if (symbol.endsWith(".NS") || symbol.endsWith(".BO") || trigger.closest("tr")?.querySelector(".market-pill")?.textContent.includes("India")) {
                currency = "INR";
            } else {
                currency = "USDT";
            }
        }
        activeTradeCurrency = currency;
        tradeSymbol.value = symbol;
        tradeAssetType.value = assetType;
        tradeInstrument.textContent = `${trigger.dataset.name || symbol} (${symbol})`;
        if (tradeCurrencyTag) {
            tradeCurrencyTag.textContent = currency;
            tradeCurrencyTag.className = `currency-pill ${currency.toLowerCase()}`;
        }
        tradeQuantity.value = "1";
        setTradeSide(trigger.dataset.orderSide || "BUY");
        updateTradeEstimate();
        updateDialogWalletBalance();

        tradeDialog.showModal();

        // Dynamically update asset icon in modal
        const modalIcon = document.getElementById("trade-modal-icon");
        if (modalIcon) {
            updateAssetIcon(modalIcon, symbol, assetType, 38);
        }

        // Render live candlestick chart inside modal
        if (modalChartCanvas && symbol) {
            renderCandlestickChart(modalChartCanvas, assetType, symbol);
        }

        window.setTimeout(() => tradeQuantity.focus(), 60);
    }

    /** Set the selected buy or sell state and keep the hidden input synchronized. */
    function setTradeSide(side) {
        if (!tradeSide) return;
        tradeSide.value = side;
        document.querySelectorAll("[data-trade-side]").forEach((button) => {
            const selected = button.dataset.tradeSide === side;
            button.classList.toggle("is-selected", selected);
            button.setAttribute("aria-pressed", String(selected));
        });
    }

    /** Recalculate the virtual order estimate whenever the quantity changes. */
    function updateTradeEstimate() {
        if (!tradePrice || !tradeTotal || !tradeQuantity) return;
        const quantity = Number(tradeQuantity.value || 0);
        tradePrice.textContent = formatCurrency(activeTradePrice, activeTradeCurrency);
        tradeTotal.textContent = formatCurrency(quantity * activeTradePrice, activeTradeCurrency);
    }

    /** Submit a virtual market order and refresh the wallet amount in the dashboard. */
    async function submitTrade(event) {
        event.preventDefault();
        const submitButton = tradeForm.querySelector("button[type=submit]");
        submitButton.disabled = true;
        submitButton.textContent = "Placing order...";
        try {
            const response = await fetch("/trade", {
                method: "POST",
                headers: { "Content-Type": "application/json", "Accept": "application/json" },
                body: JSON.stringify({
                    symbol: tradeSymbol.value,
                    asset_type: tradeAssetType.value,
                    side: tradeSide.value,
                    quantity: tradeQuantity.value,
                }),
            });
            if (response.status === 401) {
                showToast("Please sign in to place orders.", true);
                window.setTimeout(() => { window.location.href = "/login"; }, 1200);
                return;
            }
            const ct = response.headers.get("content-type") || "";
            if (!ct.includes("application/json")) {
                throw new Error("Server returned an unexpected response. Please refresh.");
            }
            const result = await response.json();
            if (!response.ok || !result.ok) {
                throw new Error(result.message || "The virtual order could not be completed.");
            }
            if (result.inr_balance !== undefined) {
                document.querySelectorAll("[data-wallet-inr]").forEach((element) => {
                    element.textContent = formatCurrency(result.inr_balance, "INR");
                });
            }
            if (result.usdt_balance !== undefined) {
                document.querySelectorAll("[data-wallet-usdt]").forEach((element) => {
                    element.textContent = formatCurrency(result.usdt_balance, "USDT");
                });
            }
            tradeDialog.close();
            showToast(result.message, false);
            window.setTimeout(() => window.location.reload(), 800);
        } catch (error) {
            showToast(error.message, true);
        } finally {
            submitButton.innerHTML = '<i data-lucide="arrow-left-right"></i>Place virtual order';
            submitButton.disabled = false;
            refreshIcons();
        }
    }

    /** Add or remove a market symbol from the authenticated user's watchlist. */
    async function toggleWatchlist(button) {
        button.disabled = true;
        try {
            const response = await fetch("/watchlist/toggle", {
                method: "POST",
                headers: { "Content-Type": "application/json", "Accept": "application/json" },
                body: JSON.stringify({ symbol: button.dataset.symbol, asset_type: button.dataset.assetType }),
            });
            if (response.status === 401) {
                showToast("Please sign in to update your watchlist.", true);
                window.setTimeout(() => { window.location.href = "/login"; }, 1200);
                return;
            }
            const ct = response.headers.get("content-type") || "";
            if (!ct.includes("application/json")) {
                throw new Error("Watchlist service temporarily unavailable.");
            }
            const result = await response.json();
            if (!response.ok || !result.ok) {
                throw new Error(result.message || "Watchlist update failed.");
            }
            button.classList.toggle("is-saved", result.saved);
            showToast(result.message, false);
        } catch (error) {
            showToast(error.message, true);
        } finally {
            button.disabled = false;
        }
    }

    /** Remove an item directly from the full watchlist page using its dedicated API. */
    async function removeWatchlistItem(button) {
        button.disabled = true;
        try {
            const assetType = encodeURIComponent(button.dataset.assetType);
            const symbol = encodeURIComponent(button.dataset.symbol);
            const response = await fetch(`/api/watchlist/${assetType}/${symbol}`, {
                method: "DELETE",
                headers: { "Accept": "application/json" },
            });
            if (response.status === 401) {
                showToast("Please sign in to update your watchlist.", true);
                window.setTimeout(() => { window.location.href = "/login"; }, 1200);
                return;
            }
            const ct = response.headers.get("content-type") || "";
            if (!ct.includes("application/json")) {
                throw new Error("Watchlist service temporarily unavailable.");
            }
            const result = await response.json();
            if (!response.ok || !result.ok) {
                throw new Error(result.message || "Watchlist update failed.");
            }
            button.closest("tr").remove();
            showToast(result.message, false);
            window.setTimeout(() => window.location.reload(), 550);
        } catch (error) {
            showToast(error.message, true);
            button.disabled = false;
        }
    }

    /** Render a real-time candlestick chart in any container for any symbol. */
    async function renderCandlestickChart(container, assetType, symbol, timeframe) {
        if (!window.LightweightCharts || !container || !assetType || !symbol) return;
        const tf = timeframe || container.dataset.timeframe || (assetType === "crypto" ? "5y" : "1y");
        container.dataset.timeframe = tf;

        // Clean up any existing chart in container
        if (activeChartsMap.has(container)) {
            try {
                const oldChart = activeChartsMap.get(container);
                oldChart.remove();
            } catch (e) {}
            activeChartsMap.delete(container);
        }
        const tfLabel = tf.toUpperCase();
        container.innerHTML = `<div class="chart-loading"><i data-lucide="loader-2"></i><span>Loading ${symbol} (${tfLabel}) candlesticks...</span></div>`;
        refreshIcons();

        try {
            const response = await fetch(`/api/chart/${encodeURIComponent(assetType)}/${encodeURIComponent(symbol)}?timeframe=${encodeURIComponent(tf)}`, {
                headers: { "Accept": "application/json" },
            });
            if (response.status === 401) {
                container.innerHTML = `<div class="chart-error"><i data-lucide="log-in"></i><span>Please <a href="/login">sign in</a> to view live chart data.</span></div>`;
                refreshIcons();
                return;
            }
            const ct = response.headers.get("content-type") || "";
            if (!ct.includes("application/json")) {
                throw new Error("Invalid response format received from server.");
            }
            const result = await response.json();
            if (!result.ok || !result.candles || result.candles.length === 0) {
                throw new Error(result.message || "No candle data available");
            }
            container.innerHTML = "";

            const chart = window.LightweightCharts.createChart(container, {
                width: container.clientWidth || 300,
                height: container.clientHeight || 260,
                layout: {
                    background: { color: "#ffffff" },
                    textColor: "#64736f",
                    fontFamily: "Manrope, Arial, sans-serif",
                },
                grid: {
                    vertLines: { color: "#edf1ef" },
                    horzLines: { color: "#edf1ef" },
                },
                rightPriceScale: { borderColor: "#d9e2dd" },
                timeScale: { borderColor: "#d9e2dd", timeVisible: true },
                crosshair: {
                    vertLine: { color: "#007d70", style: 2 },
                    horzLine: { color: "#007d70", style: 2 },
                },
            });

            const series = chart.addCandlestickSeries({
                upColor: "#078263",
                downColor: "#c94d3d",
                borderVisible: false,
                wickUpColor: "#078263",
                wickDownColor: "#c94d3d",
            });

            series.setData(result.candles);
            chart.timeScale().fitContent();

            activeChartsMap.set(container, chart);

            if (!container._resizeObserverAttached) {
                const ro = new ResizeObserver(() => {
                    const activeChart = activeChartsMap.get(container);
                    if (activeChart && container.clientWidth > 0) {
                        activeChart.applyOptions({ width: container.clientWidth });
                    }
                });
                ro.observe(container);
                container._resizeObserverAttached = true;
            }
        } catch (error) {
            container.innerHTML = `<div class="chart-error"><i data-lucide="alert-circle"></i><span>Chart unavailable for ${symbol}. Please try again later.</span></div>`;
            refreshIcons();
        }
    }

    /** Draw a small portfolio reference trend for first-time and active accounts. */
    function initializePortfolioChart(container) {
        if (!window.LightweightCharts || !container) return;

        if (activeChartsMap.has(container)) {
            try {
                const oldChart = activeChartsMap.get(container);
                oldChart.remove();
            } catch (e) {}
            activeChartsMap.delete(container);
        }
        container.innerHTML = "";

        const currentValue = Number(container.dataset.value || 0);
        const base = currentValue > 0 ? currentValue : 10000;
        const today = new Date();
        const points = [];
        for (let index = 13; index >= 0; index -= 1) {
            const day = new Date(today);
            day.setDate(today.getDate() - index);
            const movement = ((13 - index) * 0.004) + Math.sin(index * 1.4) * 0.014;
            points.push({ time: day.toISOString().slice(0, 10), value: Number((base * (0.95 + movement)).toFixed(2)) });
        }
        points[points.length - 1].value = base;

        const chart = window.LightweightCharts.createChart(container, {
            width: container.clientWidth || 300,
            height: container.clientHeight || 260,
            layout: { background: { color: "#ffffff" }, textColor: "#64736f", fontFamily: "Manrope, Arial, sans-serif" },
            grid: { vertLines: { visible: false }, horzLines: { color: "#edf1ef" } },
            rightPriceScale: { borderColor: "#d9e2dd" },
            timeScale: { borderColor: "#d9e2dd", timeVisible: false },
        });
        const series = chart.addAreaSeries({ lineColor: "#007d70", topColor: "rgba(0, 125, 112, 0.24)", bottomColor: "rgba(0, 125, 112, 0.02)", lineWidth: 2 });
        series.setData(points);
        chart.timeScale().fitContent();

        activeChartsMap.set(container, chart);

        if (!container._resizeObserverAttached) {
            const ro = new ResizeObserver(() => {
                const activeChart = activeChartsMap.get(container);
                if (activeChart && container.clientWidth > 0) {
                    activeChart.applyOptions({ width: container.clientWidth });
                }
            });
            ro.observe(container);
            container._resizeObserverAttached = true;
        }
    }

    /** Setup the Coin Chart Studio on the crypto page. */
    function setupCryptoStudio() {
        const studio = document.getElementById("crypto-chart-studio");
        if (!studio) return;
        const canvas = document.getElementById("crypto-studio-canvas");
        const titleElem = document.getElementById("crypto-studio-title");
        const priceElem = document.getElementById("crypto-studio-price");
        const iconElem = document.getElementById("crypto-studio-icon");
        const tradeBtn = document.getElementById("crypto-studio-trade-btn");
        let currentSymbol = "BTC";
        let currentTimeframe = "5y";

        // Setup timeframe selector buttons
        const tfSelector = document.getElementById("crypto-timeframe-selector");
        if (tfSelector) {
            tfSelector.querySelectorAll(".tf-pill").forEach((btn) => {
                btn.addEventListener("click", () => {
                    tfSelector.querySelectorAll(".tf-pill").forEach((b) => b.classList.remove("is-active"));
                    btn.classList.add("is-active");
                    currentTimeframe = btn.dataset.timeframe || "5y";
                    canvas.dataset.timeframe = currentTimeframe;
                    renderCandlestickChart(canvas, "crypto", currentSymbol, currentTimeframe);
                });
            });
        }

        function activateCoin(symbol, name, price) {
            currentSymbol = symbol;
            studio.querySelectorAll(".asset-pill").forEach((pill) => {
                pill.classList.toggle("is-active", pill.dataset.symbol === symbol);
            });
            if (titleElem) titleElem.textContent = `${name} (${symbol})`;
            if (priceElem) priceElem.textContent = `${Number(price || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USDT`;
            if (iconElem) {
                updateAssetIcon(iconElem, symbol, "crypto", 36);
            }
            const pairElem = document.getElementById("crypto-studio-pair");
            if (pairElem) pairElem.textContent = `${symbol}/USDT`;
            if (tradeBtn) {
                tradeBtn.dataset.symbol = symbol;
                tradeBtn.dataset.name = name;
                tradeBtn.dataset.price = price || 0;
                tradeBtn.dataset.currency = "USDT";
                tradeBtn.dataset.assetType = "crypto";
                tradeBtn.innerHTML = `<i data-lucide="arrow-up-right"></i>Trade ${symbol}`;
            }
            refreshIcons();
            renderCandlestickChart(canvas, "crypto", symbol, currentTimeframe);
        }

        // Handle pill clicks
        studio.querySelectorAll(".asset-pill").forEach((pill) => {
            pill.addEventListener("click", () => {
                activateCoin(pill.dataset.symbol, pill.dataset.name, pill.dataset.price);
            });
        });

        // Initialize default BTC
        const activePill = studio.querySelector(".asset-pill.is-active") || studio.querySelector(".asset-pill");
        if (activePill) {
            activateCoin(activePill.dataset.symbol, activePill.dataset.name, activePill.dataset.price);
        }
    }

    /** Setup the Stock Chart Studio on the stocks page. */
    function setupStockStudio() {
        const studio = document.getElementById("stock-chart-studio");
        if (!studio) return;
        const canvas = document.getElementById("stock-studio-canvas");
        const titleElem = document.getElementById("stock-studio-title");
        const subtitleElem = document.getElementById("stock-studio-subtitle");
        const currencyElem = document.getElementById("stock-studio-currency");
        const priceElem = document.getElementById("stock-studio-price");
        const iconElem = document.getElementById("stock-studio-icon");
        const tradeBtn = document.getElementById("stock-studio-trade-btn");

        function activateStock(symbol, name, currency, price) {
            studio.querySelectorAll(".asset-pill").forEach((pill) => {
                pill.classList.toggle("is-active", pill.dataset.symbol === symbol);
            });
            if (titleElem) titleElem.textContent = `${name} (${symbol})`;
            if (subtitleElem) {
                subtitleElem.textContent = currency === "INR" ? "Indian NSE &bull; Live Daily Candlesticks" : "Global Equities &bull; Live Daily Candlesticks";
            }
            if (currencyElem) {
                currencyElem.textContent = currency;
                currencyElem.className = `currency-pill ${currency.toLowerCase()}`;
            }
            if (priceElem) {
                priceElem.textContent = formatCurrency(price, currency);
            }
            if (iconElem) {
                updateAssetIcon(iconElem, symbol, "stock", 36);
            }
            const pairElem = document.getElementById("stock-studio-pair");
            if (pairElem) pairElem.textContent = `${symbol.split(".")[0]}/${currency}`;
            if (tradeBtn) {
                tradeBtn.dataset.symbol = symbol;
                tradeBtn.dataset.name = name;
                tradeBtn.dataset.price = price || 0;
                tradeBtn.dataset.currency = currency;
                tradeBtn.dataset.assetType = "stock";
                tradeBtn.innerHTML = `<i data-lucide="arrow-up-right"></i>Trade ${symbol.split(".")[0]}`;
            }
            refreshIcons();
            renderCandlestickChart(canvas, "stock", symbol);
        }

        // Handle pill clicks
        studio.querySelectorAll(".asset-pill").forEach((pill) => {
            pill.addEventListener("click", () => {
                activateStock(pill.dataset.symbol, pill.dataset.name, pill.dataset.currency, pill.dataset.price);
            });
        });

        // Initialize default RELIANCE
        const activePill = studio.querySelector(".asset-pill.is-active") || studio.querySelector(".asset-pill");
        if (activePill) {
            activateStock(activePill.dataset.symbol, activePill.dataset.name, activePill.dataset.currency, activePill.dataset.price);
        }
    }

    /** Setup multi-asset tabbed chart switcher on the main dashboard. */
    function setupDashboardChartTabs() {
        const tabContainer = document.getElementById("dash-chart-tabs");
        const canvas = document.getElementById("dash-chart-canvas");
        const titleElem = document.getElementById("dash-chart-title");
        const legendElem = document.getElementById("dash-chart-legend");
        const footLeftElem = document.getElementById("dash-chart-foot-left");
        if (!tabContainer || !canvas) return;

        tabContainer.querySelectorAll(".dash-chart-tab").forEach((tab) => {
            tab.addEventListener("click", () => {
                tabContainer.querySelectorAll(".dash-chart-tab").forEach((t) => t.classList.remove("is-active"));
                tab.classList.add("is-active");

                const mode = tab.dataset.chartMode;
                if (mode === "portfolio") {
                    if (titleElem) titleElem.textContent = "Practice Account Value";
                    if (legendElem) legendElem.innerHTML = `<span><i></i>Reference trend</span>`;
                    if (footLeftElem) footLeftElem.textContent = "Virtual portfolio value &bull; Switch tabs to view individual coin/stock candles";
                    initializePortfolioChart(canvas);
                } else {
                    const symbol = tab.dataset.symbol;
                    const assetType = tab.dataset.assetType;
                    const label = tab.dataset.label || `${symbol} Candlesticks`;
                    if (titleElem) titleElem.textContent = label;
                    if (legendElem) {
                        legendElem.innerHTML = `<span><i class="legend-win"></i>Bullish</span> <span style="margin-left:8px;"><i class="legend-loss"></i>Bearish</span>`;
                    }
                    if (footLeftElem) footLeftElem.textContent = `Daily Candlestick OHLCV Chart for ${symbol}`;
                    renderCandlestickChart(canvas, assetType, symbol);
                }
            });
        });
    }

    /** Handle "Chart" buttons in the market tables to smoothly scroll and activate that asset in Studio. */
    function setupTableChartButtons() {
        document.querySelectorAll(".js-view-chart").forEach((button) => {
            button.addEventListener("click", () => {
                const symbol = button.dataset.symbol;
                const name = button.dataset.name;
                const assetType = button.dataset.assetType;
                const currency = button.dataset.currency;
                const price = button.dataset.price;

                if (assetType === "crypto") {
                    const studio = document.getElementById("crypto-chart-studio");
                    if (studio) {
                        studio.scrollIntoView({ behavior: "smooth", block: "start" });
                        const pill = studio.querySelector(`[data-symbol="${symbol}"]`);
                        if (pill) {
                            pill.click();
                        } else {
                            // Direct activation
                            const canvas = document.getElementById("crypto-studio-canvas");
                            const titleElem = document.getElementById("crypto-studio-title");
                            const priceElem = document.getElementById("crypto-studio-price");
                            const tradeBtn = document.getElementById("crypto-studio-trade-btn");
                            if (titleElem) titleElem.textContent = `${name} (${symbol})`;
                            if (priceElem) priceElem.textContent = `${formatCurrency(price, "USDT")}`;
                            if (tradeBtn) {
                                tradeBtn.dataset.symbol = symbol;
                                tradeBtn.dataset.name = name;
                                tradeBtn.dataset.price = price;
                                tradeBtn.dataset.currency = "USDT";
                                tradeBtn.dataset.assetType = "crypto";
                                tradeBtn.innerHTML = `<i data-lucide="arrow-up-right"></i>Trade ${symbol}`;
                            }
                            renderCandlestickChart(canvas, "crypto", symbol);
                            refreshIcons();
                        }
                    }
                } else {
                    const studio = document.getElementById("stock-chart-studio");
                    if (studio) {
                        studio.scrollIntoView({ behavior: "smooth", block: "start" });
                        const pill = studio.querySelector(`[data-symbol="${symbol}"]`);
                        if (pill) {
                            pill.click();
                        } else {
                            const canvas = document.getElementById("stock-studio-canvas");
                            const titleElem = document.getElementById("stock-studio-title");
                            const currencyElem = document.getElementById("stock-studio-currency");
                            const priceElem = document.getElementById("stock-studio-price");
                            const tradeBtn = document.getElementById("stock-studio-trade-btn");
                            if (titleElem) titleElem.textContent = `${name} (${symbol})`;
                            if (currencyElem) {
                                currencyElem.textContent = currency;
                                currencyElem.className = `currency-pill ${currency.toLowerCase()}`;
                            }
                            if (priceElem) priceElem.textContent = formatCurrency(price, currency);
                            if (tradeBtn) {
                                tradeBtn.dataset.symbol = symbol;
                                tradeBtn.dataset.name = name;
                                tradeBtn.dataset.price = price;
                                tradeBtn.dataset.currency = currency;
                                tradeBtn.dataset.assetType = "stock";
                                tradeBtn.innerHTML = `<i data-lucide="arrow-up-right"></i>Trade ${symbol.split(".")[0]}`;
                            }
                            renderCandlestickChart(canvas, "stock", symbol);
                            refreshIcons();
                        }
                    }
                }
            });
        });
    }

    /** Connect every page-local interaction once the DOM is ready. */
    function initializePage() {
        refreshIcons();
        document.querySelectorAll(".js-trade").forEach((trigger) => trigger.addEventListener("click", () => openTradeDialog(trigger)));
        document.querySelectorAll(".js-watchlist").forEach((button) => button.addEventListener("click", () => toggleWatchlist(button)));
        document.querySelectorAll(".js-watchlist-remove").forEach((button) => button.addEventListener("click", () => removeWatchlistItem(button)));
        document.querySelectorAll("[data-trade-side]").forEach((button) => button.addEventListener("click", () => setTradeSide(button.dataset.tradeSide)));
        if (tradeQuantity) tradeQuantity.addEventListener("input", updateTradeEstimate);
        if (tradeForm) tradeForm.addEventListener("submit", submitTrade);

        // Setup Studios & Chart switchers
        setupCryptoStudio();
        setupStockStudio();
        setupDashboardChartTabs();
        setupTableChartButtons();

        // Standalone charts if any
        document.querySelectorAll("[data-portfolio-chart]").forEach((canvas) => {
            if (!canvas.closest("#dashboard-chart-section")) {
                initializePortfolioChart(canvas);
            }
        });

        const menuButton = document.querySelector("[data-menu-toggle]");
        const sidebar = document.querySelector(".sidebar");
        if (menuButton && sidebar) {
            menuButton.addEventListener("click", () => sidebar.classList.toggle("is-open"));
            document.querySelectorAll(".sidebar a").forEach((link) => link.addEventListener("click", () => sidebar.classList.remove("is-open")));
        }
    }

    document.addEventListener("DOMContentLoaded", initializePage);
}());
