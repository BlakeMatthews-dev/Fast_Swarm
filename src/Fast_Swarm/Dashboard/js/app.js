/**
 * CoinSwarm Command Center - Main Application
 * Cyberpunk Dashboard for Fast_Swarm
 * Note: innerHTML usage is safe here as all data comes from our own FastAPI backend
 */

// Use same origin as the dashboard (works on any port)
const API_URL = window.location.origin;
const REFRESH_INTERVAL = 60000; // 60 seconds for full refresh (SSE handles real-time)
const CACHE_TTL = 30000; // 30 second cache TTL

// State
let currentPage = 'orchestrator';
let agentsData = [];
let patternsData = [];
let tradesData = [];
let currentSort = { agents: 'fitness_score', patterns: 'fitness_score' };
let killRateHistory = [];
let eventSource = null;

// ============================================
// CACHING LAYER
// ============================================

const cache = new Map();

async function fetchWithCache(url, maxAgeMs = CACHE_TTL) {
    const cacheKey = url;
    const cached = cache.get(cacheKey);

    if (cached && (Date.now() - cached.timestamp < maxAgeMs)) {
        return cached.data;
    }

    try {
        const response = await fetch(API_URL + url);
        if (!response.ok) throw new Error('HTTP ' + response.status);
        const data = await response.json();

        cache.set(cacheKey, { data, timestamp: Date.now() });
        return data;
    } catch (error) {
        // Return stale cache if available on error
        if (cached) {
            console.warn('Using stale cache for', url, ':', error.message);
            return cached.data;
        }
        throw error;
    }
}

function invalidateCache(urlPattern) {
    for (const key of cache.keys()) {
        if (key.includes(urlPattern)) {
            cache.delete(key);
        }
    }
}

// ============================================
// SERVER-SENT EVENTS (Real-time updates)
// ============================================

function initSSE() {
    if (eventSource) {
        eventSource.close();
    }

    eventSource = new EventSource(API_URL + '/system/events');

    eventSource.onmessage = function(event) {
        try {
            const message = JSON.parse(event.data);

            switch (message.type) {
                case 'orchestrator':
                    // Update orchestrator HUD in real-time
                    if (currentPage === 'orchestrator') {
                        updatePhaseHUD(message.data);
                        updateOrchestratorMetrics(message.data);
                    }
                    break;

                case 'streams':
                    // Update stream status indicator
                    updateStreamStatus(message.data);
                    break;

                case 'error':
                    console.warn('SSE error:', message.data);
                    break;
            }
        } catch (e) {
            console.error('SSE parse error:', e);
        }
    };

    eventSource.onerror = function(event) {
        console.warn('SSE connection error, will reconnect...');
        // EventSource automatically reconnects
    };

    addLogEntry('SYSTEM', 'Real-time updates connected');
}

function updateOrchestratorMetrics(data) {
    // Update progress bars and counts from SSE data
    if (data.patterns_total > 0) {
        var pct = Math.round((data.patterns_tested / data.patterns_total) * 100);
        updateBar('patterns-bar', pct);
    }
    if (data.agents_total > 0) {
        var pct = Math.round((data.agents_tested / data.agents_total) * 100);
        updateBar('agents-bar', pct);
    }
}

function updateStreamStatus(streams) {
    var statusIndicator = document.getElementById('system-status');
    if (!statusIndicator) return;

    var allConnected = Object.values(streams).every(function(s) {
        return s.state === 'connected';
    });

    statusIndicator.classList.toggle('offline', !allConnected);
    statusIndicator.querySelector('.status-text').textContent = allConnected ? 'ONLINE' : 'DEGRADED';
}

// ============================================
// INITIALIZATION
// ============================================

document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    initControls();
    initClock();
    initSSE();  // Start real-time updates
    startDataRefresh();
    addLogEntry('SYSTEM', 'Dashboard initialized');
});

// ============================================
// NAVIGATION
// ============================================

function initNavigation() {
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const page = btn.dataset.page;
            navigateTo(page);
        });
    });
}

function navigateTo(page) {
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.page === page);
    });

    document.querySelectorAll('.page').forEach(p => {
        p.classList.toggle('active', p.id === 'page-' + page);
    });

    currentPage = page;

    switch(page) {
        case 'orchestrator': fetchOrchestratorData(); break;
        case 'market': fetchMarketData(); break;
        case 'patterns': fetchPatternsData(); break;
        case 'agents': fetchAgentsData(); break;
        case 'trades': fetchTradesData(); break;
    }
}

// ============================================
// CONTROLS & BUTTONS
// ============================================

function initControls() {
    var btnEvolution = document.getElementById('btn-evolution');
    var btnSpawn = document.getElementById('btn-spawn');
    var btnBacktest = document.getElementById('btn-backtest');
    var btnCull = document.getElementById('btn-cull');
    var btnChaos = document.getElementById('btn-chaos');
    var btnTests = document.getElementById('btn-tests');

    if (btnEvolution) btnEvolution.addEventListener('click', function() { triggerAction('/evolution/start', 'POST', 'Evolution started'); });
    if (btnSpawn) btnSpawn.addEventListener('click', spawnAgentsWithPrompt);
    if (btnBacktest) btnBacktest.addEventListener('click', triggerBacktestWithProgress);
    if (btnCull) btnCull.addEventListener('click', cullWithPreview);
    if (btnChaos) btnChaos.addEventListener('click', function() { triggerAction('/system/robustness/trigger_chaos', 'POST', 'Chaos triggered'); });
    if (btnTests) btnTests.addEventListener('click', function() { triggerAction('/tests/run/all', 'POST', 'Tests started'); });

    var slider = document.getElementById('parallelism-slider');
    var sliderValue = document.getElementById('parallelism-value');
    if (slider && sliderValue) {
        slider.addEventListener('input', function() {
            sliderValue.textContent = slider.value;
        });
    }

    document.querySelectorAll('#page-patterns .sort-btn').forEach(function(btn) {
        btn.addEventListener('click', function() {
            document.querySelectorAll('#page-patterns .sort-btn').forEach(function(b) { b.classList.remove('active'); });
            btn.classList.add('active');
            currentSort.patterns = btn.dataset.sort;
            renderPatternsTable();
        });
    });

    document.querySelectorAll('#page-agents .sort-btn').forEach(function(btn) {
        btn.addEventListener('click', function() {
            document.querySelectorAll('#page-agents .sort-btn').forEach(function(b) { b.classList.remove('active'); });
            btn.classList.add('active');
            currentSort.agents = btn.dataset.sort;
            renderAgentsTable();
        });
    });
}

async function triggerAction(endpoint, method, successMsg) {
    try {
        addLogEntry('ACTION', 'Triggering ' + endpoint + '...');
        var response = await fetch(API_URL + endpoint, { method: method });
        if (response.ok) {
            addLogEntry('SUCCESS', successMsg);
        } else {
            var error = await response.text();
            addLogEntry('ERROR', 'Failed: ' + error);
        }
    } catch (error) {
        addLogEntry('ERROR', 'Request failed: ' + error.message);
    }
}

// Spawn agents with count prompt
async function spawnAgentsWithPrompt() {
    var count = prompt('How many agents to spawn?', '10');
    if (!count) return;
    var countNum = parseInt(count, 10);
    if (isNaN(countNum) || countNum < 1) {
        addLogEntry('ERROR', 'Invalid count');
        return;
    }
    addLogEntry('ACTION', 'Spawning ' + countNum + ' agents...');
    try {
        var response = await fetch(API_URL + '/actions/spawn?count=' + countNum, { method: 'POST' });
        var data = await response.json();
        if (response.ok) {
            addLogEntry('SUCCESS', 'Spawned ' + (data.agents ? data.agents.length : countNum) + ' agents (AI: ' + (data.ai_selection ? 'Yes' : 'No') + ')');
            fetchOrchestratorData();
        } else {
            addLogEntry('ERROR', 'Spawn failed: ' + (data.detail || 'Unknown error'));
        }
    } catch (error) {
        addLogEntry('ERROR', 'Spawn request failed: ' + error.message);
    }
}

// Cull with dry_run preview first
async function cullWithPreview() {
    addLogEntry('ACTION', 'Analyzing agents for cull (dry run)...');
    try {
        var response = await fetch(API_URL + '/actions/cull?dry_run=true&survival_rate=0.6', { method: 'POST' });
        var data = await response.json();
        if (!response.ok) {
            addLogEntry('ERROR', 'Cull preview failed');
            return;
        }
        var msg = 'Would cull ' + data.would_cull + ' agents, keeping ' + data.would_survive;
        if (data.bottom_agents && data.bottom_agents.length > 0) {
            msg += '\nBottom agents: ' + data.bottom_agents.slice(0, 5).map(function(a) {
                return (a.name || 'Unknown') + ' (fitness: ' + (a.fitness || 0).toFixed(1) + ')';
            }).join(', ');
        }
        addLogEntry('INFO', msg);
        if (data.would_cull === 0) {
            addLogEntry('INFO', 'No agents to cull');
            return;
        }
        var confirmed = confirm('Cull ' + data.would_cull + ' weak agents?\n\n' + msg);
        if (!confirmed) {
            addLogEntry('INFO', 'Cull cancelled');
            return;
        }
        addLogEntry('ACTION', 'Executing cull...');
        var cullResponse = await fetch(API_URL + '/actions/cull?survival_rate=0.6', { method: 'POST' });
        var cullData = await cullResponse.json();
        if (cullResponse.ok) {
            addLogEntry('SUCCESS', 'Culled ' + (cullData.culled || data.would_cull) + ' agents');
            fetchOrchestratorData();
        } else {
            addLogEntry('ERROR', 'Cull failed: ' + (cullData.detail || 'Unknown error'));
        }
    } catch (error) {
        addLogEntry('ERROR', 'Cull request failed: ' + error.message);
    }
}

// Backtest with limit and progress polling
var backtestPollInterval = null;

async function triggerBacktestWithProgress() {
    var limitStr = prompt('Limit number of agents to backtest? (leave empty for all)', '');
    var limit = limitStr ? parseInt(limitStr, 10) : null;
    if (limitStr && (isNaN(limit) || limit < 1)) {
        addLogEntry('ERROR', 'Invalid limit');
        return;
    }
    var url = '/actions/backtest';
    if (limit) url += '?limit=' + limit;
    addLogEntry('ACTION', 'Starting backtest' + (limit ? ' (limit: ' + limit + ')' : '') + '...');
    try {
        var response = await fetch(API_URL + url, { method: 'POST' });
        var data = await response.json();
        if (response.ok) {
            addLogEntry('INFO', 'Backtest started in background');
            if (backtestPollInterval) clearInterval(backtestPollInterval);
            backtestPollInterval = setInterval(pollBacktestStatus, 2000);
        } else {
            addLogEntry('ERROR', 'Backtest failed: ' + (data.detail || 'Unknown error'));
        }
    } catch (error) {
        addLogEntry('ERROR', 'Backtest request failed: ' + error.message);
    }
}

async function pollBacktestStatus() {
    try {
        var response = await fetch(API_URL + '/actions/backtest/status');
        var data = await response.json();
        var pct = data.total > 0 ? Math.round((data.progress / data.total) * 100) : 0;
        if (data.running) {
            addLogEntry('INFO', 'Backtest progress: ' + pct + '% (' + data.progress + '/' + data.total + ') - ' + (data.current_agent || '...'));
        } else {
            clearInterval(backtestPollInterval);
            backtestPollInterval = null;
            var completed = data.completed ? data.completed.length : 0;
            var errors = data.errors ? data.errors.length : 0;
            addLogEntry('SUCCESS', 'Backtest complete! ' + completed + ' agents tested' + (errors > 0 ? ', ' + errors + ' errors' : ''));
            fetchOrchestratorData();
        }
    } catch (error) {
        console.error('Backtest poll error:', error);
    }
}

// ============================================
// CLOCK
// ============================================

function initClock() {
    updateClock();
    setInterval(updateClock, 1000);
}

function updateClock() {
    var now = new Date();
    var timeStr = now.toLocaleTimeString('en-US', { hour12: false });
    document.getElementById('clock').textContent = timeStr;
}

// ============================================
// DATA REFRESH
// ============================================

function startDataRefresh() {
    fetchAllData();
    setInterval(fetchAllData, REFRESH_INTERVAL);
}

async function fetchAllData() {
    try {
        await fetchOrchestratorData();
        switch(currentPage) {
            case 'market': await fetchMarketData(); break;
            case 'patterns': await fetchPatternsData(); break;
            case 'agents': await fetchAgentsData(); break;
            case 'trades': await fetchTradesData(); break;
        }
        updateLastRefresh();
    } catch (error) {
        console.error('Data fetch error:', error);
        addLogEntry('ERROR', 'Data refresh failed: ' + error.message);
    }
}

function updateLastRefresh() {
    var now = new Date();
    document.getElementById('last-update').textContent = 'Last update: ' + now.toLocaleTimeString('en-US', { hour12: false });
}

// ============================================
// ORCHESTRATOR PAGE
// ============================================

async function fetchOrchestratorData() {
    try {
        var results = await Promise.allSettled([
            fetch(API_URL + '/agents/stats/average'),
            fetch(API_URL + '/patterns/stats/average'),
            fetch(API_URL + '/system/health'),
            fetch(API_URL + '/evolution/monitor/current')
        ]);

        if (results[0].status === 'fulfilled' && results[0].value.ok) {
            var stats = await results[0].value.json();
            // API returns: count, average_fitness, average_traits
            var agentCount = stats.count || 0;
            var avgFitness = stats.average_fitness || 0;
            updateMetric('metric-agents', agentCount || '--');
            updateMetric('metric-fitness', avgFitness ? avgFitness.toFixed(1) : '--');
            updateMetric('metric-elo', '--'); // Not in stats endpoint
            updateBar('agents-bar', Math.min(agentCount, 100));
            updateBar('fitness-bar', avgFitness);
            updateBar('elo-bar', 50); // Default until we add ELO to stats
        }

        if (results[1].status === 'fulfilled' && results[1].value.ok) {
            var pStats = await results[1].value.json();
            // API returns: count, averages, by_status, top_performers
            var patternCount = pStats.count || 0;
            updateMetric('metric-patterns', patternCount || '--');
            updateBar('patterns-bar', Math.min(patternCount, 100));
        }

        if (results[2].status === 'fulfilled' && results[2].value.ok) {
            var health = await results[2].value.json();
            var statusIndicator = document.getElementById('system-status');
            var isHealthy = health.streams && Object.values(health.streams).every(function(s) { return s.state === 'connected'; });
            if (statusIndicator) {
                statusIndicator.classList.toggle('offline', !isHealthy);
                statusIndicator.querySelector('.status-text').textContent = isHealthy ? 'ONLINE' : 'DEGRADED';
            }
        }

        if (results[3].status === 'fulfilled') {
            if (results[3].value.ok) {
                var cycle = await results[3].value.json();
                updatePhaseHUD(cycle);
            } else {
                // No active cycle - show all phases as idle
                updatePhaseHUD({ phase: null });
            }
        }

        updateKillRateChart();
    } catch (error) {
        console.error('Orchestrator data error:', error);
    }
}

function updateMetric(id, value) {
    var el = document.getElementById(id);
    if (el) el.textContent = value;
}

function updateBar(id, percent) {
    var el = document.getElementById(id);
    if (el) el.style.width = Math.min(100, Math.max(0, percent)) + '%';
}

function updatePhaseHUD(cycle) {
    var phases = ['chaos', 'discovery', 'backtest', 'select'];
    var currentPhase = cycle && cycle.phase ? cycle.phase.toLowerCase() : '';

    phases.forEach(function(phase, index) {
        var ring = document.getElementById('phase-' + phase + '-ring');
        var status = document.getElementById('phase-' + phase + '-status');
        var card = ring ? ring.closest('.phase-card') : null;

        if (ring && status && card) {
            var isActive = currentPhase === phase;
            var isComplete = phases.indexOf(currentPhase) > index;
            var progress = isComplete ? 0 : (isActive ? 141.5 : 283);
            ring.style.strokeDashoffset = progress;
            status.textContent = isComplete ? 'COMPLETE' : (isActive ? 'RUNNING' : 'IDLE');
            status.classList.toggle('running', isActive);
            card.classList.toggle('active', isActive);
        }
    });
}

function updateKillRateChart() {
    var canvas = document.getElementById('kill-rate-chart');
    if (!canvas) return;

    var ctx = canvas.getContext('2d');
    var width = canvas.width;
    var height = canvas.height;

    killRateHistory.push(85 + Math.random() * 15);
    if (killRateHistory.length > 50) killRateHistory.shift();

    ctx.fillStyle = '#1a1a25';
    ctx.fillRect(0, 0, width, height);

    ctx.strokeStyle = '#2a2a3a';
    ctx.lineWidth = 1;
    for (var i = 0; i <= 4; i++) {
        var y = (height / 4) * i;
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(width, y);
        ctx.stroke();
    }

    if (killRateHistory.length > 1) {
        ctx.strokeStyle = '#00ffff';
        ctx.lineWidth = 2;
        ctx.shadowColor = '#00ffff';
        ctx.shadowBlur = 10;
        ctx.beginPath();

        killRateHistory.forEach(function(value, index) {
            var x = (width / (killRateHistory.length - 1)) * index;
            var chartY = height - (value / 100) * height;
            if (index === 0) {
                ctx.moveTo(x, chartY);
            } else {
                ctx.lineTo(x, chartY);
            }
        });

        ctx.stroke();
        ctx.shadowBlur = 0;
    }
}

// ============================================
// MARKET PAGE
// ============================================

async function fetchMarketData() {
    try {
        // Fetch latest candles for each asset to get current prices
        // DB stores symbols as BTC, ETH, SOL (no USDT suffix)
        var assets = ['BTC', 'ETH', 'SOL'];
        var results = await Promise.allSettled(
            assets.map(function(asset) {
                return fetch(API_URL + '/market_data/candles?symbol=' + encodeURIComponent(asset) + '&timeframe=1h&limit=2');
            })
        );

        var tickers = [];
        for (var i = 0; i < results.length; i++) {
            if (results[i].status === 'fulfilled' && results[i].value.ok) {
                var candles = await results[i].value.json();
                if (candles && candles.length >= 2) {
                    var current = candles[0];
                    var prev = candles[1];
                    var change = prev.close > 0 ? ((current.close - prev.close) / prev.close) * 100 : 0;
                    tickers.push({
                        symbol: assets[i].split('/')[0],
                        price: current.close,
                        change: change
                    });
                }
            }
        }

        if (tickers.length > 0) {
            updatePriceDisplays(tickers);
        }
    } catch (error) {
        console.error('Market data fetch error:', error);
    }

    // Fetch real sentiment data from API
    try {
        var sentimentRes = await fetch(API_URL + '/sentiment/summary');
        if (sentimentRes.ok) {
            var sentiment = await sentimentRes.json();
            if (sentiment.fear_greed) {
                updateFearGreed(sentiment.fear_greed.value);
            }
            if (sentiment.btc_dominance) {
                updateBtcDominance(sentiment.btc_dominance);
            }
        }
    } catch (error) {
        console.error('Sentiment fetch error:', error);
        updateFearGreed(50); // Neutral fallback
    }

    // Fetch funding rates
    fetchFundingRates();
}

function updatePriceDisplays(tickers) {
    var mapping = {
        'BTC': { price: 'btc-price', change: 'btc-change' },
        'BTCUSDT': { price: 'btc-price', change: 'btc-change' },
        'ETH': { price: 'eth-price', change: 'eth-change' },
        'ETHUSDT': { price: 'eth-price', change: 'eth-change' },
        'SOL': { price: 'sol-price', change: 'sol-change' },
        'SOLUSDT': { price: 'sol-price', change: 'sol-change' }
    };

    tickers.forEach(function(ticker) {
        var map = mapping[ticker.symbol];
        if (map) {
            var priceEl = document.getElementById(map.price);
            var changeEl = document.getElementById(map.change);

            if (priceEl && ticker.price) {
                priceEl.textContent = '$' + ticker.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
            }
            if (changeEl) {
                var change = ticker.change || 0;
                changeEl.textContent = (change >= 0 ? '+' : '') + change.toFixed(2) + '%';
                changeEl.className = 'price-change ' + (change >= 0 ? 'positive' : 'negative');
            }
        }
    });
}

function updateFearGreed(value) {
    var needle = document.getElementById('fear-greed-needle');
    var valueEl = document.getElementById('fear-greed-value');
    var labelEl = document.getElementById('fear-greed-label');

    if (needle) {
        var rotation = (value / 100) * 180 - 90;
        needle.style.transform = 'translateX(-50%) rotate(' + rotation + 'deg)';
    }
    if (valueEl) valueEl.textContent = value;
    if (labelEl) {
        if (value < 25) labelEl.textContent = 'EXTREME FEAR';
        else if (value < 45) labelEl.textContent = 'FEAR';
        else if (value < 55) labelEl.textContent = 'NEUTRAL';
        else if (value < 75) labelEl.textContent = 'GREED';
        else labelEl.textContent = 'EXTREME GREED';
    }
}

function updateBtcDominance(data) {
    var domEl = document.getElementById('btc-dominance-value');
    var capEl = document.getElementById('market-cap-value');

    if (domEl && data.dominance) {
        domEl.textContent = data.dominance.toFixed(1) + '%';
    }
    if (capEl && data.total_market_cap) {
        var cap = data.total_market_cap;
        if (cap >= 1e12) {
            capEl.textContent = '$' + (cap / 1e12).toFixed(2) + 'T';
        } else if (cap >= 1e9) {
            capEl.textContent = '$' + (cap / 1e9).toFixed(0) + 'B';
        } else {
            capEl.textContent = '$' + cap.toLocaleString();
        }
    }
}

async function fetchFundingRates() {
    try {
        var res = await fetch(API_URL + '/sentiment/funding-rates?limit=100');
        if (!res.ok) return;
        var rates = await res.json();

        // Get latest rate per symbol
        var latest = {};
        rates.forEach(function(r) {
            var sym = r.symbol.replace('-USD', '').replace('USDT', '');
            if (!latest[sym]) latest[sym] = r;
        });

        // Update display
        ['BTC', 'ETH', 'SOL'].forEach(function(sym) {
            var el = document.getElementById('funding-' + sym.toLowerCase());
            if (el && latest[sym]) {
                var rate = latest[sym].funding_rate * 100; // Convert to percentage
                var bps = (rate * 100).toFixed(2); // Basis points
                el.textContent = (rate >= 0 ? '+' : '') + bps + ' bps';
                el.className = 'funding-value ' + (rate >= 0 ? 'positive' : 'negative');
            }
        });
    } catch (e) {
        console.error('Funding rates error:', e);
    }
}

// ============================================
// PATTERNS PAGE
// ============================================

async function fetchPatternsData() {
    try {
        var results = await Promise.allSettled([
            fetch(API_URL + '/patterns?limit=100'),
            fetch(API_URL + '/patterns/stats/average')
        ]);

        // Handle patterns list
        if (results[0].status === 'fulfilled' && results[0].value.ok) {
            patternsData = await results[0].value.json();
            console.log('Patterns loaded:', patternsData.length, 'patterns');
            renderPatternsTable();
        } else {
            var reason = results[0].status === 'rejected' ? results[0].reason : 'HTTP ' + results[0].value.status;
            console.error('Patterns fetch failed:', reason);
            document.getElementById('patterns-table').textContent = 'Error loading patterns: ' + reason;
        }

        // Handle stats separately
        if (results[1].status === 'fulfilled' && results[1].value.ok) {
            var stats = await results[1].value.json();
            // API returns: count, averages {fitness_score, win_rate, total_trades, total_roi_pct}, by_status, top_performers
            var avgs = stats.averages || {};
            document.getElementById('stat-pattern-total').textContent = stats.count || patternsData.length;
            document.getElementById('stat-pattern-fitness').textContent = avgs.fitness_score ? avgs.fitness_score.toFixed(1) : '--';
            document.getElementById('stat-pattern-sharpe').textContent = avgs.sortino_ratio ? avgs.sortino_ratio.toFixed(2) : '--';
            document.getElementById('stat-pattern-roi').textContent = avgs.total_roi_pct ? avgs.total_roi_pct.toFixed(1) + '%' : '--';
        }
    } catch (error) {
        console.error('Patterns fetch error:', error);
        document.getElementById('patterns-table').textContent = 'Error loading patterns: ' + error.message;
    }
}

function renderPatternsTable() {
    var container = document.getElementById('patterns-table');
    if (!container) {
        console.error('patterns-table container not found');
        return;
    }

    console.log('renderPatternsTable called, patternsData.length:', patternsData.length);

    if (patternsData.length === 0) {
        container.textContent = 'No patterns found';
        return;
    }

    try {
        // Filter out patterns with zero/null fitness (untested chaos patterns)
        var testedPatterns = patternsData.filter(function(p) {
            return p.fitness_score && parseFloat(p.fitness_score) > 0;
        });

        console.log('Tested patterns (fitness > 0):', testedPatterns.length);

        if (testedPatterns.length === 0) {
            container.textContent = 'No backtested patterns yet (all ' + patternsData.length + ' patterns pending backtest)';
            return;
        }

        var sorted = testedPatterns.slice().sort(function(a, b) {
            return (parseFloat(b[currentSort.patterns]) || 0) - (parseFloat(a[currentSort.patterns]) || 0);
        });

        var table = document.createElement('table');
    var thead = document.createElement('thead');
    var headerRow = document.createElement('tr');
    ['RANK', 'PATTERN ID', 'FITNESS', 'ROI %', 'SORTINO', 'WIN RATE', 'MAX DD'].forEach(function(text) {
        var th = document.createElement('th');
        th.textContent = text;
        headerRow.appendChild(th);
    });
    thead.appendChild(headerRow);
    table.appendChild(thead);

    var tbody = document.createElement('tbody');
    sorted.forEach(function(pattern, index) {
        var rank = index + 1;
        var fitness = parseFloat(pattern.fitness_score) || 0;
        var roi = parseFloat(pattern.total_roi_pct) || 0; // Model uses total_roi_pct
        var sortino = parseFloat(pattern.sortino_ratio) || 0;
        var winRate = (parseFloat(pattern.win_rate) || 0) * 100;
        var maxDD = parseFloat(pattern.max_drawdown_pct) || 0;

        var tr = document.createElement('tr');
        tr.onclick = function() { toggleDetails('details-' + pattern.pattern_id); };

        var tdRank = document.createElement('td');
        tdRank.className = 'rank' + (rank <= 3 ? ' rank-' + rank : '');
        tdRank.textContent = rank;
        tr.appendChild(tdRank);

        var tdId = document.createElement('td');
        tdId.style.fontFamily = 'var(--font-mono)';
        tdId.style.fontSize = '0.8em';
        tdId.textContent = (pattern.pattern_id || 'N/A').slice(0, 16) + '...';
        tr.appendChild(tdId);

        var tdFitness = document.createElement('td');
        var fitnessSpan = document.createElement('span');
        fitnessSpan.className = 'metric positive';
        fitnessSpan.textContent = fitness.toFixed(1);
        tdFitness.appendChild(fitnessSpan);
        var fitnessBar = document.createElement('div');
        fitnessBar.className = 'fitness-bar';
        var fitnessFill = document.createElement('div');
        fitnessFill.className = 'fitness-fill';
        fitnessFill.style.width = Math.min(fitness, 100) + '%';
        fitnessBar.appendChild(fitnessFill);
        tdFitness.appendChild(fitnessBar);
        tr.appendChild(tdFitness);

        var tdRoi = document.createElement('td');
        tdRoi.className = 'metric ' + (roi >= 10 ? 'positive' : roi < 0 ? 'negative' : 'neutral');
        tdRoi.textContent = roi.toFixed(1) + '%';
        tr.appendChild(tdRoi);

        var tdSortino = document.createElement('td');
        tdSortino.className = 'metric ' + (sortino >= 1.5 ? 'positive' : sortino < 0.5 ? 'negative' : 'neutral');
        tdSortino.textContent = sortino.toFixed(2);
        tr.appendChild(tdSortino);

        var tdWr = document.createElement('td');
        tdWr.className = 'metric ' + (winRate >= 55 ? 'positive' : winRate < 45 ? 'negative' : 'neutral');
        tdWr.textContent = winRate.toFixed(1) + '%';
        tr.appendChild(tdWr);

        var tdDD = document.createElement('td');
        tdDD.className = 'metric ' + (maxDD < 15 ? 'positive' : 'negative');
        tdDD.textContent = maxDD.toFixed(1) + '%';
        tr.appendChild(tdDD);

        tbody.appendChild(tr);

        // Details row
        var detailsRow = document.createElement('tr');
        detailsRow.className = 'details-row';
        detailsRow.id = 'details-' + pattern.pattern_id;
        var detailsTd = document.createElement('td');
        detailsTd.colSpan = 7;
        var detailsGrid = document.createElement('div');
        detailsGrid.className = 'details-grid';

        var details = [
            ['Total Trades', pattern.total_trades || 0],
            ['Origin', pattern.origin || 'unknown'],
            ['Status', pattern.status || 'untested'],
            ['Profit Factor', (pattern.profit_factor || 0).toFixed(2)],
            ['Timeframe', pattern.timeframe || '--']
        ];

        details.forEach(function(d) {
            var item = document.createElement('div');
            item.className = 'detail-item';
            var label = document.createElement('div');
            label.className = 'detail-label';
            label.textContent = d[0];
            var value = document.createElement('div');
            value.className = 'detail-value';
            value.textContent = d[1];
            item.appendChild(label);
            item.appendChild(value);
            detailsGrid.appendChild(item);
        });

        detailsTd.appendChild(detailsGrid);
        detailsRow.appendChild(detailsTd);
        tbody.appendChild(detailsRow);
    });

        table.appendChild(tbody);
        container.textContent = '';
        container.appendChild(table);
        console.log('Patterns table rendered successfully');
    } catch (err) {
        console.error('Error rendering patterns table:', err);
        container.textContent = 'Error rendering patterns: ' + err.message;
    }
}

function toggleDetails(id) {
    var row = document.getElementById(id);
    if (row) row.classList.toggle('show');
}

// ============================================
// AGENTS PAGE
// ============================================

async function fetchAgentsData() {
    try {
        var results = await Promise.all([
            fetch(API_URL + '/agents?limit=100'),
            fetch(API_URL + '/agents/stats/average')
        ]);

        if (results[0].ok) {
            agentsData = await results[0].json();
            renderAgentsTable();
            renderDistributions();
        }

        if (results[1].ok) {
            var stats = await results[1].json();
            // API returns: count, average_fitness, average_traits
            var activeCount = stats.count || agentsData.filter(function(a) { return a.is_active; }).length;
            document.getElementById('stat-agent-active').textContent = activeCount;
            document.getElementById('stat-agent-fitness').textContent = stats.average_fitness ? parseFloat(stats.average_fitness).toFixed(1) : '--';
            // Calculate avg ELO and sortino from agentsData since not in stats
            var totalElo = 0, totalSortino = 0, eloCount = 0, sortinoCount = 0;
            agentsData.forEach(function(a) {
                var elo = parseFloat(a.elo_rating);
                var sortino = parseFloat(a.sortino_ratio);
                if (elo) { totalElo += elo; eloCount++; }
                if (sortino) { totalSortino += sortino; sortinoCount++; }
            });
            document.getElementById('stat-agent-elo').textContent = eloCount > 0 ? (totalElo / eloCount).toFixed(0) : '--';
            document.getElementById('stat-agent-sortino').textContent = sortinoCount > 0 ? (totalSortino / sortinoCount).toFixed(2) : '--';
        }
    } catch (error) {
        console.error('Agents fetch error:', error);
        document.getElementById('agents-table').textContent = 'Error loading agents';
    }
}

function renderAgentsTable() {
    var container = document.getElementById('agents-table');
    if (!container || agentsData.length === 0) {
        if (container) container.textContent = 'No agents found';
        return;
    }

    var sorted = agentsData.slice().sort(function(a, b) {
        return (parseFloat(b[currentSort.agents]) || 0) - (parseFloat(a[currentSort.agents]) || 0);
    });

    var table = document.createElement('table');
    var thead = document.createElement('thead');
    var headerRow = document.createElement('tr');
    ['RANK', 'AGENT', 'STATUS', 'GEN', 'FITNESS', 'ELO', 'ROI %', 'SORTINO'].forEach(function(text) {
        var th = document.createElement('th');
        th.textContent = text;
        headerRow.appendChild(th);
    });
    thead.appendChild(headerRow);
    table.appendChild(thead);

    var tbody = document.createElement('tbody');
    sorted.forEach(function(agent, index) {
        var rank = index + 1;
        var fitness = parseFloat(agent.fitness_score) || 0;
        var elo = parseFloat(agent.elo_rating) || 1500;
        var roi = parseFloat(agent.annualized_roi_pct) || 0;
        var sortino = parseFloat(agent.sortino_ratio) || 0;
        var traits = agent.traits || {};

        var tr = document.createElement('tr');
        tr.onclick = function() { toggleDetails('agent-details-' + agent.agent_id); };

        var tdRank = document.createElement('td');
        tdRank.className = 'rank' + (rank <= 3 ? ' rank-' + rank : '');
        tdRank.textContent = rank;
        tr.appendChild(tdRank);

        var tdName = document.createElement('td');
        tdName.style.fontFamily = 'var(--font-mono)';
        tdName.textContent = 'Agent #' + (agent.agent_id || 'N/A').slice(-6);
        tr.appendChild(tdName);

        var tdStatus = document.createElement('td');
        var statusSpan = document.createElement('span');
        statusSpan.style.color = agent.is_active ? 'var(--neon-green)' : 'var(--text-dim)';
        statusSpan.textContent = agent.is_active ? 'ACTIVE' : 'INACTIVE';
        tdStatus.appendChild(statusSpan);
        tr.appendChild(tdStatus);

        var tdGen = document.createElement('td');
        tdGen.textContent = 'Gen ' + (agent.generation || 1);
        tr.appendChild(tdGen);

        var tdFitness = document.createElement('td');
        var fitnessSpan = document.createElement('span');
        fitnessSpan.className = 'metric positive';
        fitnessSpan.textContent = fitness.toFixed(1);
        tdFitness.appendChild(fitnessSpan);
        var fitnessBar = document.createElement('div');
        fitnessBar.className = 'fitness-bar';
        var fitnessFill = document.createElement('div');
        fitnessFill.className = 'fitness-fill';
        fitnessFill.style.width = Math.min(fitness, 100) + '%';
        fitnessBar.appendChild(fitnessFill);
        tdFitness.appendChild(fitnessBar);
        tr.appendChild(tdFitness);

        var tdElo = document.createElement('td');
        tdElo.className = 'metric';
        tdElo.style.color = 'var(--neon-magenta)';
        tdElo.textContent = elo.toFixed(0);
        tr.appendChild(tdElo);

        var tdRoi = document.createElement('td');
        tdRoi.className = 'metric ' + (roi >= 15 ? 'positive' : roi < 0 ? 'negative' : 'neutral');
        tdRoi.textContent = roi.toFixed(1) + '%';
        tr.appendChild(tdRoi);

        var tdSortino = document.createElement('td');
        tdSortino.className = 'metric ' + (sortino >= 1.5 ? 'positive' : sortino < 0.5 ? 'negative' : 'neutral');
        tdSortino.textContent = sortino.toFixed(2);
        tr.appendChild(tdSortino);

        tbody.appendChild(tr);

        // Details row
        var detailsRow = document.createElement('tr');
        detailsRow.className = 'details-row';
        detailsRow.id = 'agent-details-' + agent.agent_id;
        var detailsTd = document.createElement('td');
        detailsTd.colSpan = 8;
        var detailsGrid = document.createElement('div');
        detailsGrid.className = 'details-grid';

        var details = [
            ['Trades', agent.total_trades || 0],
            ['Win Rate', ((parseFloat(agent.win_rate) || 0) * 100).toFixed(1) + '%'],
            ['Sortino', (parseFloat(agent.sortino_ratio) || 0).toFixed(2)],
            ['Max DD', (parseFloat(agent.max_drawdown_pct) || 0).toFixed(1) + '%'],
            ['Risk Tolerance', ((parseFloat(traits.risk_tolerance) || 0) * 100).toFixed(0) + '%'],
            ['Entry Aggression', ((parseFloat(traits.entry_aggression) || 0) * 100).toFixed(0) + '%'],
            ['Exit Aggression', ((parseFloat(traits.exit_aggression) || 0) * 100).toFixed(0) + '%'],
            ['Sentiment Weight', ((parseFloat(traits.sentiment_weight) || 0) * 100).toFixed(0) + '%']
        ];

        details.forEach(function(d) {
            var item = document.createElement('div');
            item.className = 'detail-item';
            var label = document.createElement('div');
            label.className = 'detail-label';
            label.textContent = d[0];
            var value = document.createElement('div');
            value.className = 'detail-value';
            value.textContent = d[1];
            item.appendChild(label);
            item.appendChild(value);
            detailsGrid.appendChild(item);
        });

        detailsTd.appendChild(detailsGrid);
        detailsRow.appendChild(detailsTd);
        tbody.appendChild(detailsRow);
    });

    table.appendChild(tbody);
    container.textContent = '';
    container.appendChild(table);
}

function renderDistributions() {
    renderDistribution('elo-distribution', agentsData.map(function(a) { return parseFloat(a.elo_rating) || 1500; }), [1000, 1250, 1500, 1750, 2000], '#ff00ff');
    renderDistribution('fitness-distribution', agentsData.map(function(a) { return parseFloat(a.fitness_score) || 0; }), [0, 20, 40, 60, 80], '#00ff88');
}

function renderDistribution(canvasId, values, buckets, color) {
    var canvas = document.getElementById(canvasId);
    if (!canvas) return;

    var ctx = canvas.getContext('2d');
    var width = canvas.width;
    var height = canvas.height;

    var counts = new Array(buckets.length).fill(0);
    values.forEach(function(v) {
        for (var i = buckets.length - 1; i >= 0; i--) {
            if (v >= buckets[i]) {
                counts[i]++;
                break;
            }
        }
    });

    var maxCount = Math.max.apply(null, counts.concat([1]));
    var barWidth = width / buckets.length - 10;

    ctx.fillStyle = '#1a1a25';
    ctx.fillRect(0, 0, width, height);

    counts.forEach(function(count, index) {
        var barHeight = (count / maxCount) * (height - 20);
        var x = index * (barWidth + 10) + 5;
        var y = height - barHeight - 10;

        ctx.fillStyle = color;
        ctx.shadowColor = color;
        ctx.shadowBlur = 10;
        ctx.fillRect(x, y, barWidth, barHeight);
        ctx.shadowBlur = 0;
    });
}

// ============================================
// TRADES PAGE
// ============================================

async function fetchTradesData() {
    try {
        var limitEl = document.getElementById('filter-limit');
        var agentEl = document.getElementById('filter-agent');
        var assetEl = document.getElementById('filter-asset');

        var limit = limitEl ? limitEl.value : 100;
        var agentId = agentEl ? agentEl.value : '';
        var asset = assetEl ? assetEl.value : '';

        var url = API_URL + '/trades?limit=' + limit;
        if (agentId) url += '&agent_id=' + agentId;
        if (asset) url += '&symbol=' + asset;

        var response = await fetch(url);
        if (response.ok) {
            tradesData = await response.json();
            renderTradesTable();
            updateTradeStats();
        }
    } catch (error) {
        console.error('Trades fetch error:', error);
        document.getElementById('trades-table').textContent = 'Error loading trades';
    }
}

function renderTradesTable() {
    var container = document.getElementById('trades-table');
    if (!container || tradesData.length === 0) {
        if (container) container.textContent = 'No trades found';
        return;
    }

    var table = document.createElement('table');
    var thead = document.createElement('thead');
    var headerRow = document.createElement('tr');
    ['TIME', 'AGENT', 'ASSET', 'SIDE', 'ENTRY', 'EXIT', 'P&L', 'ROI %'].forEach(function(text) {
        var th = document.createElement('th');
        th.textContent = text;
        headerRow.appendChild(th);
    });
    thead.appendChild(headerRow);
    table.appendChild(thead);

    var tbody = document.createElement('tbody');
    tradesData.forEach(function(trade) {
        var pnl = trade.pnl_usd || 0;
        var roi = trade.net_pnl_pct || trade.gross_pnl_pct || 0;
        var time = trade.exit_timestamp ? new Date(trade.exit_timestamp).toLocaleString() : '--';

        var tr = document.createElement('tr');

        var tdTime = document.createElement('td');
        tdTime.style.fontSize = '0.8em';
        tdTime.style.color = 'var(--text-secondary)';
        tdTime.textContent = time;
        tr.appendChild(tdTime);

        var tdAgent = document.createElement('td');
        tdAgent.style.fontFamily = 'var(--font-mono)';
        tdAgent.style.fontSize = '0.8em';
        tdAgent.textContent = (trade.agent_id || 'N/A').slice(-6);
        tr.appendChild(tdAgent);

        var tdAsset = document.createElement('td');
        tdAsset.textContent = trade.symbol || 'N/A';
        tr.appendChild(tdAsset);

        var tdSide = document.createElement('td');
        var sideUpper = (trade.side || '').toUpperCase();
        tdSide.style.color = sideUpper === 'LONG' ? 'var(--neon-green)' : 'var(--neon-red)';
        tdSide.textContent = sideUpper || 'N/A';
        tr.appendChild(tdSide);

        var tdEntry = document.createElement('td');
        tdEntry.className = 'metric';
        tdEntry.textContent = trade.entry_price ? trade.entry_price.toFixed(2) : '--';
        tr.appendChild(tdEntry);

        var tdExit = document.createElement('td');
        tdExit.className = 'metric';
        tdExit.textContent = trade.exit_price ? trade.exit_price.toFixed(2) : '--';
        tr.appendChild(tdExit);

        var tdPnl = document.createElement('td');
        tdPnl.className = 'metric ' + (pnl >= 0 ? 'positive' : 'negative');
        tdPnl.textContent = (pnl >= 0 ? '+' : '') + pnl.toFixed(2);
        tr.appendChild(tdPnl);

        var tdRoi = document.createElement('td');
        tdRoi.className = 'metric ' + (roi >= 0 ? 'positive' : 'negative');
        tdRoi.textContent = (roi >= 0 ? '+' : '') + roi.toFixed(2) + '%';
        tr.appendChild(tdRoi);

        tbody.appendChild(tr);
    });

    table.appendChild(tbody);
    container.textContent = '';
    container.appendChild(table);
}

function updateTradeStats() {
    var totalPnl = tradesData.reduce(function(sum, t) { return sum + (t.pnl_usd || 0); }, 0);
    var wins = tradesData.filter(function(t) { return t.is_winner === true || (t.pnl_usd || 0) > 0; }).length;
    var winRate = tradesData.length > 0 ? (wins / tradesData.length) * 100 : 0;
    var avgTrade = tradesData.length > 0 ? totalPnl / tradesData.length : 0;

    document.getElementById('stat-trade-total').textContent = tradesData.length;
    document.getElementById('stat-trade-pnl').textContent = (totalPnl >= 0 ? '+' : '') + totalPnl.toFixed(2);
    document.getElementById('stat-trade-winrate').textContent = winRate.toFixed(1) + '%';
    document.getElementById('stat-trade-avg').textContent = (avgTrade >= 0 ? '+' : '') + avgTrade.toFixed(2);
}

// ============================================
// ACTIVITY LOG
// ============================================

function addLogEntry(component, message) {
    var log = document.getElementById('activity-log');
    if (!log) return;

    var entry = document.createElement('div');
    entry.className = 'log-entry';

    var now = new Date();
    var time = now.toLocaleTimeString('en-US', { hour12: false });

    var timeSpan = document.createElement('span');
    timeSpan.className = 'log-time';
    timeSpan.textContent = time;
    entry.appendChild(timeSpan);

    var compSpan = document.createElement('span');
    compSpan.className = 'log-component';
    compSpan.textContent = '[' + component + ']';
    entry.appendChild(compSpan);

    var msgSpan = document.createElement('span');
    msgSpan.className = 'log-message';
    msgSpan.textContent = message;
    entry.appendChild(msgSpan);

    log.insertBefore(entry, log.firstChild);

    while (log.children.length > 50) {
        log.removeChild(log.lastChild);
    }
}
