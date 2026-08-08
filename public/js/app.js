/**
 * FINOPS INTELLIGENCE — FRONTEND APPLICATION
 * Institutional Financial Operations & Risk Analytics
 */

// Global State & Chart Handles
const state = {
    overview: null,
    risk: null,
    process: null,
    decisions: null,
    charts: {}
};

// Colors Palette for Charts
const CHART_COLORS = {
    dark: '#111111',
    bronze: '#8C6D46',
    bronzeLight: '#F5EFE6',
    blue: '#0072CE',
    blueLight: '#EBF4FC',
    gray: '#767676',
    border: '#E5E0D8',
    gridLines: '#F0ECE4'
};

document.addEventListener('DOMContentLoaded', async () => {
    setupTabNavigation();
    setupModalListeners();
    await loadAllData();
});

/* ==========================================================================
   NAVIGATION & TABS
   ========================================================================== */

function setupTabNavigation() {
    // Handle URL Hash if present
    const hash = window.location.hash.replace('#', '');
    if (hash && ['overview', 'risk', 'process', 'decisions'].includes(hash)) {
        switchTab(hash);
    }

    // Listen to window popstate
    window.addEventListener('popstate', () => {
        const h = window.location.hash.replace('#', '') || 'overview';
        switchTab(h, false);
    });
}

function switchTab(tabId, updateHash = true) {
    const navButtons = document.querySelectorAll('.nav-btn');
    const contentTabs = document.querySelectorAll('.content-tab');

    navButtons.forEach(btn => {
        if (btn.dataset.tab === tabId) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });

    contentTabs.forEach(tab => {
        if (tab.id === `tab-${tabId}`) {
            tab.classList.add('active');
        } else {
            tab.classList.remove('active');
        }
    });

    if (updateHash) {
        window.history.pushState(null, '', `#${tabId}`);
    }

    // Re-render or update charts on active tab
    window.dispatchEvent(new Event('resize'));
}

/* ==========================================================================
   DATA FETCHING & RENDERING
   ========================================================================== */

const fetchNoCache = (url) => fetch(`${url}?_t=${Date.now()}`, {
    cache: 'no-store',
    headers: {
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache'
    }
});

async function loadAllData() {
    // Clear stale state & charts before fetch
    state.overview = null;
    state.risk = null;
    state.process = null;
    state.decisions = null;

    try {
        const [overviewRes, riskRes, processRes, decisionsRes] = await Promise.all([
            fetchNoCache('/api/overview'),
            fetchNoCache('/api/risk'),
            fetchNoCache('/api/process'),
            fetchNoCache('/api/decisions')
        ]);

        if (!overviewRes.ok || !riskRes.ok || !processRes.ok || !decisionsRes.ok) {
            throw new Error('FinOps Intelligence API unavailable — dashboard data not loaded.');
        }

        state.overview = await overviewRes.json();
        state.risk = await riskRes.json();
        state.process = await processRes.json();
        state.decisions = await decisionsRes.json();

        setDataErrorState(false);
        // Render each section with loaded backend payloads
        renderOverview(state.overview);
        renderRisk(state.risk);
        renderProcess(state.process);
        renderDecisions(state.decisions);

    } catch (err) {
        console.error('FinOps Intelligence API unavailable — dashboard data not loaded.', err);
        setDataErrorState(true);
    }
}

function setDataErrorState(isVisible) {
    const errorState = document.getElementById('data-error-state');
    if (errorState) {
        errorState.style.display = isVisible ? 'flex' : 'none';
        errorState.hidden = !isVisible;
    }
    if (!isVisible) return;

    // Reset metric text elements
    document.querySelectorAll('.metric-value, .model-stat-val, .risk-band-count, .eff-stat-val, .score-val, .type-rate').forEach(el => {
        el.textContent = '—';
    });
    ['scenarios-container', 'decisions-table-body', 'feature-importance-container', 'fraud-type-container', 'high-risk-table-body', 'process-flow-container'].forEach(id => {
        const element = document.getElementById(id);
        if (element) element.replaceChildren();
    });
    ['rec-scenario-name', 'rec-scenario-reason', 'bottleneck-stage-name', 'bottleneck-desc-text', 'overview-fraud-count', 'model-architecture-name'].forEach(id => {
        const element = document.getElementById(id);
        if (element) element.textContent = '—';
    });

    // Destroy all charts
    Object.values(state.charts).forEach(chart => chart?.destroy());
    state.charts = {};
}

function finiteNumber(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
}

function formatWholeNumber(value) {
    const number = finiteNumber(value);
    return number === null ? '—' : number.toLocaleString();
}

function formatNumber(value, decimals = 2) {
    const number = finiteNumber(value);
    return number === null ? '—' : number.toFixed(decimals);
}

function formatPercent(value, decimals = 2) {
    const number = finiteNumber(value);
    return number === null ? '—' : (number * 100).toFixed(decimals) + '%';
}

function formatScore(value) {
    return formatNumber(value, 4);
}

function formatMinutes(value) {
    return formatNumber(value, 2);
}

/* ==========================================================================
   SECTION 1: OVERVIEW RENDERING
   ========================================================================== */

function renderOverview(data) {
    if (!data) return;

    // Format metrics
    const totalTxn = data.total_transactions;
    const fraudRate = formatPercent(data.fraud_rate, 4);
    const fraudCount = formatWholeNumber(data.fraud_count);
    const highRisk = formatWholeNumber(data.high_risk_count);
    const totalVal = formatCurrency(data.total_transaction_value);

    document.getElementById('overview-total-transactions').textContent = formatCompactNumber(totalTxn);
    document.getElementById('overview-fraud-rate').textContent = fraudRate;
    document.getElementById('overview-fraud-count').textContent = `${fraudCount} Fraud Instances`;
    document.getElementById('overview-high-risk').textContent = highRisk;
    document.getElementById('overview-total-value').textContent = totalVal;

    // Risk Bands Breakdown
    document.getElementById('overview-low-risk-count').textContent = formatWholeNumber(data.low_risk_count);
    document.getElementById('overview-medium-risk-count').textContent = formatWholeNumber(data.medium_risk_count);
    document.getElementById('overview-high-risk-count-band').textContent = formatWholeNumber(data.high_risk_count);

    // Chart 1: Transaction Volume by Type
    renderTypeDistributionChart(data.transaction_type_distribution);

    // Chart 2: Transaction Trend
    renderTransactionTrendChart(data.transaction_trend);
}

function renderTypeDistributionChart(dist) {
    const ctx = document.getElementById('chart-type-distribution')?.getContext('2d');
    if (!ctx || !dist) return;

    if (state.charts.typeDist) state.charts.typeDist.destroy();

    let labels = [];
    let values = [];

    if (Array.isArray(dist)) {
        labels = dist.map(item => item.type);
        values = dist.map(item => finiteNumber(item.transaction_count));
    } else if (typeof dist === 'object' && dist !== null) {
        labels = Object.keys(dist);
        values = Object.values(dist).map(val => typeof val === 'object' ? finiteNumber(val.transaction_count) : finiteNumber(val));
    }

    if (!labels.length || values.some(value => value === null)) return;

    state.charts.typeDist = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Transaction Count',
                data: values,
                backgroundColor: [
                    CHART_COLORS.dark,
                    CHART_COLORS.bronze,
                    CHART_COLORS.blue,
                    '#A89B8C',
                    '#D4C9B8'
                ],
                borderRadius: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: {
                duration: 1000,
                easing: 'easeOutQuart'
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: CHART_COLORS.dark,
                    titleFont: { family: 'Plus Jakarta Sans', size: 13 },
                    bodyFont: { family: 'Plus Jakarta Sans', size: 12 },
                    callbacks: {
                        label: (ctx) => ` Transactions: ${ctx.parsed.y.toLocaleString()}`
                    }
                }
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { font: { family: 'Plus Jakarta Sans', size: 11, weight: '600' }, color: CHART_COLORS.dark }
                },
                y: {
                    grid: { color: CHART_COLORS.gridLines },
                    ticks: {
                        font: { family: 'Plus Jakarta Sans', size: 11 },
                        color: CHART_COLORS.gray,
                        callback: (v) => formatCompactNumber(v)
                    }
                }
            }
        }
    });
}

function renderTransactionTrendChart(trendData) {
    if (!trendData || !Array.isArray(trendData)) return;

    const labels = trendData.map(d => `Step ${d.step}`);
    const volumes = trendData.map(d => finiteNumber(d.transaction_count));
    const frauds = trendData.map(d => finiteNumber(d.fraud_count));
    if (volumes.some(value => value === null) || frauds.some(value => value === null)) return;

    // 1. Transaction Activity Over Time (Volume)
    const ctxVol = document.getElementById('chart-transaction-volume')?.getContext('2d');
    if (ctxVol) {
        if (state.charts.txnVolume) state.charts.txnVolume.destroy();

        state.charts.txnVolume = new Chart(ctxVol, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Transaction Count',
                    data: volumes,
                    borderColor: CHART_COLORS.dark,
                    backgroundColor: 'rgba(17, 17, 17, 0.04)',
                    borderWidth: 1.5,
                    fill: true,
                    tension: 0.2,
                    pointRadius: 0
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: {
                    duration: 1200,
                    easing: 'easeOutQuart'
                },
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: CHART_COLORS.dark,
                        titleFont: { family: 'Plus Jakarta Sans', size: 12 },
                        callbacks: {
                            label: (ctx) => ` Volume: ${ctx.parsed.y.toLocaleString()} transactions`
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { font: { family: 'Plus Jakarta Sans', size: 10 }, color: CHART_COLORS.gray, maxTicksLimit: 12 },
                        title: { display: true, text: 'Hourly Step Index (PaySim)', font: { family: 'Plus Jakarta Sans', size: 11 } }
                    },
                    y: {
                        grid: { color: CHART_COLORS.gridLines },
                        ticks: {
                            font: { family: 'Plus Jakarta Sans', size: 10 },
                            color: CHART_COLORS.gray,
                            callback: (v) => formatCompactNumber(v)
                        },
                        title: { display: true, text: 'Transaction Volume', font: { family: 'Plus Jakarta Sans', size: 11 } }
                    }
                }
            }
        });
    }

    // 2. Fraud Activity Over Time (Incidents)
    const ctxFraud = document.getElementById('chart-fraud-trend')?.getContext('2d');
    if (ctxFraud) {
        if (state.charts.fraudTrend) state.charts.fraudTrend.destroy();

        state.charts.fraudTrend = new Chart(ctxFraud, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Fraud Cases',
                    data: frauds,
                    backgroundColor: '#B83232',
                    borderRadius: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: CHART_COLORS.dark,
                        titleFont: { family: 'Plus Jakarta Sans', size: 12 },
                        callbacks: {
                            label: (ctx) => ` Fraud Incidents: ${ctx.parsed.y.toLocaleString()}`
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: { font: { family: 'Plus Jakarta Sans', size: 10 }, color: CHART_COLORS.gray, maxTicksLimit: 12 },
                        title: { display: true, text: 'Hourly Step Index (PaySim)', font: { family: 'Plus Jakarta Sans', size: 11 } }
                    },
                    y: {
                        grid: { color: CHART_COLORS.gridLines },
                        ticks: { font: { family: 'Plus Jakarta Sans', size: 10 }, color: CHART_COLORS.gray },
                        title: { display: true, text: 'Fraud Count', font: { family: 'Plus Jakarta Sans', size: 11 } }
                    }
                }
            }
        });
    }
}

/* ==========================================================================
   SECTION 2: RISK ANALYTICS RENDERING
   ========================================================================== */

function renderRisk(data) {
    if (!data) return;

    const metrics = data.model_metrics || {};
    const archNameEl = document.getElementById('model-architecture-name');
    if (archNameEl) archNameEl.textContent = metrics.model ? `${metrics.model} fraud-risk classifier` : '—';

    if (document.getElementById('model-roc-auc')) document.getElementById('model-roc-auc').textContent = formatScore(metrics.roc_auc);
    if (document.getElementById('model-precision')) document.getElementById('model-precision').textContent = formatPercent(metrics.precision);
    if (document.getElementById('model-recall')) document.getElementById('model-recall').textContent = formatPercent(metrics.recall);
    if (document.getElementById('model-f1')) document.getElementById('model-f1').textContent = formatPercent(metrics.f1);
    if (document.getElementById('model-pr-auc')) document.getElementById('model-pr-auc').textContent = formatScore(metrics.pr_auc);

    // Risk Distribution Section
    if (data.risk_distribution) {
        const lowEl = document.getElementById('risk-page-low-count');
        const medEl = document.getElementById('risk-page-medium-count');
        const highEl = document.getElementById('risk-page-high-count');
        if (lowEl) lowEl.textContent = formatWholeNumber(data.risk_distribution.LOW);
        if (medEl) medEl.textContent = formatWholeNumber(data.risk_distribution.MEDIUM);
        if (highEl) highEl.textContent = formatWholeNumber(data.risk_distribution.HIGH);
    }

    // Feature Importances
    const featureContainer = document.getElementById('feature-importance-container');
    if (featureContainer && data.top_feature_importances) {
        const topFeatures = data.top_feature_importances.slice(0, 6);
        const validFeatures = topFeatures.filter(f => finiteNumber(f.importance) !== null);
        if (!validFeatures.length) {
            featureContainer.textContent = 'Unable to load data';
            return;
        }
        const maxImportance = Math.max(...validFeatures.map(f => finiteNumber(f.importance)));

        featureContainer.innerHTML = validFeatures.map(f => {
            const importance = finiteNumber(f.importance);
            const pct = Math.round((importance / maxImportance) * 100);
            return `
                <div class="feature-row">
                    <div class="feature-info">
                        <span class="feature-name">${formatFeatureLabel(f.feature)}</span>
                        <span class="feature-score">${(importance * 100).toFixed(2)}%</span>
                    </div>
                    <div class="feature-bar-bg">
                        <div class="feature-bar-fill" style="width: ${pct}%;"></div>
                    </div>
                </div>
            `;
        }).join('');
    }

    // Fraud Vulnerability by Type
    const typeContainer = document.getElementById('fraud-type-container');
    if (typeContainer && (data.risk_by_transaction_type || data.fraud_rate_by_transaction_type)) {
        const list = data.risk_by_transaction_type || data.fraud_rate_by_transaction_type;
        typeContainer.innerHTML = list.map(item => `
            <div class="fraud-type-item">
                <div>
                    <div class="type-title">${item.type}</div>
                    <div class="type-count">${formatWholeNumber(item.transaction_count)} Transactions</div>
                </div>
                <div class="type-stats">
                    <div class="type-rate">${formatPercent(item.fraud_rate, 3)}</div>
                    <div class="type-count">${formatWholeNumber(item.fraud_count)} Fraud Cases</div>
                </div>
            </div>
        `).join('');
    }

    // High Risk Table
    const tableBody = document.getElementById('high-risk-table-body');
    if (tableBody && data.top_high_risk_transactions) {
        tableBody.innerHTML = data.top_high_risk_transactions.slice(0, 10).map(tx => `
            <tr>
                <td>Step ${tx.step || '—'}</td>
                <td><strong>${tx.type || '—'}</strong></td>
                <td>${formatCurrency(tx.amount)}</td>
                <td><code>${tx.nameOrig || '—'}</code></td>
                <td><code>${tx.nameDest || '—'}</code></td>
                <td><strong>${formatScore(tx.risk_score ?? tx.fraud_probability)}</strong></td>
                <td><span class="risk-badge high">HIGH RISK</span></td>
            </tr>
        `).join('');
    }
}

function formatFeatureLabel(name) {
    let clean = name.replace('numeric__', '').replace('categorical__', '');
    const map = {
        'amount': 'amount (Transaction Amount)',
        'transaction_amount_log': 'transaction_amount_log',
        'transaction_hour': 'transaction_hour',
        'transaction_category_funds_movement': 'transaction_category_funds_movement',
        'type_TRANSFER': 'type_TRANSFER',
        'type_CASH_OUT': 'type_CASH_OUT',
        'type_PAYMENT': 'type_PAYMENT',
        'amount_bucket': 'amount_bucket'
    };
    return map[clean] || clean;
}

/* ==========================================================================
   SECTION 3: PROCESS INTELLIGENCE RENDERING
   ========================================================================== */

function renderProcess(data) {
    if (!data) return;

    // Bottleneck Banner
    const bottleneck = data.bottleneck_stage || '—';
    if (document.getElementById('bottleneck-stage-name')) {
        document.getElementById('bottleneck-stage-name').textContent = bottleneck;
    }

    const bottleneckStage = data.process_stages?.find(s => s.stage === bottleneck);
    const avgLat = bottleneckStage ? formatMinutes(bottleneckStage.average_processing_time_minutes) : '—';
    const breachRate = bottleneckStage ? formatPercent(bottleneckStage.sla_breach_rate) : '—';
    const descEl = document.getElementById('bottleneck-desc-text');
    if (descEl) {
        descEl.textContent = `${bottleneck} has the highest average processing latency (${avgLat} min) and SLA breach rate (${breachRate}) across the simulated transaction pipeline.`;
    }

    // Process Flow Container
    const flowContainer = document.getElementById('process-flow-container');
    if (flowContainer && data.process_stages) {
        flowContainer.innerHTML = data.process_stages.map((st, idx) => {
            const isBottleneck = st.stage === bottleneck;
            return `
                <div class="process-stage-card ${isBottleneck ? 'bottleneck-highlight' : ''}">
                    ${isBottleneck ? '<div class="bottleneck-tag">BOTTLENECK</div>' : ''}
                    <div class="stage-num">0${idx + 1} / STAGE</div>
                    <div class="stage-name">${st.stage}</div>
                    <div class="stage-dept">${st.department}</div>
                    
                    <div class="stage-metric-row">
                        <span class="stage-metric-lbl">Avg Latency:</span>
                        <span class="stage-metric-val">${formatMinutes(st.average_processing_time_minutes)}m</span>
                    </div>
                    <div class="stage-metric-row">
                        <span class="stage-metric-lbl">P95 Latency:</span>
                        <span class="stage-metric-val">${formatMinutes(st.p95_processing_time_minutes)}m</span>
                    </div>
                    <div class="stage-metric-row">
                        <span class="stage-metric-lbl">SLA Breach:</span>
                        <span class="stage-metric-val">${formatPercent(st.sla_breach_rate)}</span>
                    </div>
                    <div class="stage-metric-row">
                        <span class="stage-metric-lbl">Total Cost:</span>
                        <span class="stage-metric-val">${formatCompactCurrency(st.simulated_total_operational_cost)}</span>
                    </div>
                </div>
            `;
        }).join('');
    }

    // Processing Latency Chart
    renderProcessingLatencyChart(data.processing_time_by_stage);

    // Efficiency Metrics
    const eff = data.process_efficiency_metrics || {};
    if (document.getElementById('process-end-to-end-time')) {
        document.getElementById('process-end-to-end-time').textContent = `${formatMinutes(eff.average_end_to_end_processing_time_minutes)} mins`;
    }
    if (document.getElementById('process-sla-breach-rate')) {
        document.getElementById('process-sla-breach-rate').textContent = formatPercent(eff.weighted_sla_breach_rate);
    }
    if (document.getElementById('process-operational-cost')) {
        document.getElementById('process-operational-cost').textContent = formatCompactCurrency(eff.total_simulated_operational_cost);
    }
    const noticeEl = document.getElementById('process-notice-text');
    if (noticeEl && !noticeEl.textContent.includes('PaySim provides')) {
        noticeEl.textContent = "PaySim provides transaction-level data; workflow timings, costs and SLA measures are simulated analytical assumptions for process analysis.";
    }
}

function renderProcessingLatencyChart(latencyData) {
    const ctx = document.getElementById('chart-processing-latency')?.getContext('2d');
    if (!ctx || !latencyData) return;

    if (state.charts.latency) state.charts.latency.destroy();

   const labels = latencyData.map(d => d.stage);
    const avgTimes = latencyData.map(d => finiteNumber(d.average_processing_time_minutes));
    const p95Times = latencyData.map(d => finiteNumber(d.p95_processing_time_minutes));
    if (avgTimes.some(value => value === null) || p95Times.some(value => value === null)) return;

    state.charts.latency = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Avg Minutes',
                    data: avgTimes,
                    backgroundColor: CHART_COLORS.dark,
                    borderRadius: 2
                },
                {
                    label: 'P95 Minutes',
                    data: p95Times,
                    backgroundColor: CHART_COLORS.bronze,
                    borderRadius: 2
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: { font: { family: 'Plus Jakarta Sans', size: 11 } }
                },
                tooltip: {
                    backgroundColor: CHART_COLORS.dark,
                    titleFont: { family: 'Plus Jakarta Sans', size: 12 }
                }
            },
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { font: { family: 'Plus Jakarta Sans', size: 10 }, color: CHART_COLORS.gray }
                },
                y: {
                    grid: { color: CHART_COLORS.gridLines },
                    ticks: { font: { family: 'Plus Jakarta Sans', size: 10 }, color: CHART_COLORS.gray }
                }
            }
        }
    });
}

/* ==========================================================================
   SECTION 4: DECISION SIMULATOR RENDERING
   ========================================================================== */

function renderDecisions(data) {
    if (!data) return;

    const rec = data.recommended_scenario;
    document.getElementById('rec-scenario-name').textContent = rec || '—';
    if (document.getElementById('rec-scenario-reason')) {
        document.getElementById('rec-scenario-reason').textContent = data.recommendation_reason || '—';
    }

    const scenarios = data.scenarios || [];

    // Scenarios Grid
    const scenariosContainer = document.getElementById('scenarios-container');
    if (scenariosContainer) {
        scenariosContainer.innerHTML = scenarios.map(sc => {
            const isRec = sc.scenario === rec;
            const savings = sc.projected_annual_savings;
            const speedup = sc.projected_processing_time_improvement_percent;
            const riskDelta = finiteNumber(sc.risk_impact?.fraud_rate_delta);

            return `
                <div class="scenario-card ${isRec ? 'recommended-card' : ''}">
                    ${isRec ? '<div class="scenario-rec-pill">RECOMMENDED</div>' : ''}
                    <div>
                        <div class="scenario-name">${sc.scenario}</div>
                        <div class="scenario-score-block">
                            <span class="score-lbl">DECISION SCORE</span>
                            <span class="score-val">${formatNumber(sc.decision_score, 2)}</span>
                        </div>

                        <div class="scenario-metrics-list">
                            <div class="scenario-metric-item">
                                <span class="scen-lbl">Annual Net Savings:</span>
                                <span class="scen-val ${savings >= 0 ? 'positive' : 'negative'}">
                                    ${finiteNumber(savings) !== null && savings >= 0 ? '+' : ''}${formatCompactCurrency(savings)}
                                </span>
                            </div>
                            <div class="scenario-metric-item">
                                <span class="scen-lbl">Processing Speedup:</span>
                                <span class="scen-val positive">+${formatNumber(speedup, 2)}%</span>
                            </div>
                            <div class="scenario-metric-item">
                                <span class="scen-lbl">Implementation Cost:</span>
                                <span class="scen-val">${formatCompactCurrency(sc.estimated_implementation_cost)}</span>
                            </div>
                            <div class="scenario-metric-item">
                                <span class="scen-lbl">Risk Delta:</span>
                                <span class="scen-val">${formatPercent(riskDelta, 3)}</span>
                            </div>
                        </div>
                    </div>

                    <button class="cta-button ${isRec ? '' : 'secondary'}" onclick="selectScenario('${sc.scenario}')">
                        ${isRec ? 'Review Recommendation' : 'View Scenario'}
                    </button>
                </div>
            `;
        }).join('');
    }

    // Decisions Table
    const tableBody = document.getElementById('decisions-table-body');
    if (tableBody) {
        tableBody.innerHTML = scenarios.map(sc => {
            const isRec = sc.scenario === rec;
            return `
                <tr style="${isRec ? 'background-color: var(--accent-blue-light); font-weight: 500;' : ''}">
                    <td><strong>${sc.scenario}</strong> ${isRec ? ' <span style="color:var(--accent-blue); font-size:10px; font-weight:700;">(REC)</span>' : ''}</td>
                            <td><strong>${formatNumber(sc.decision_score, 4)}</strong></td>
                    <td class="${sc.projected_annual_savings >= 0 ? 'positive' : 'negative'}">
                        ${finiteNumber(sc.projected_annual_savings) !== null && sc.projected_annual_savings >= 0 ? '+' : ''}${formatCompactCurrency(sc.projected_annual_savings)}
                    </td>
                    <td>+${formatNumber(sc.projected_processing_time_improvement_percent, 2)}%</td>
                    <td>${formatCompactCurrency(sc.estimated_implementation_cost)}</td>
                    <td>${sc.risk_impact?.interpretation || '—'}</td>
                    <td><span class="risk-badge ${isRec ? 'high' : 'low'}" style="${isRec ? 'background:#0072CE; color:#FFF; border:none;' : ''}">${isRec ? 'RECOMMENDED' : 'SIMULATED'}</span></td>
                </tr>
            `;
        }).join('');
    }
}

function selectScenario(name) {
    openScenarioModal(name);
}

/* ==========================================================================
   SCENARIO MODAL INTERACTION
   ========================================================================== */

function openScenarioModal(name) {
    const overlay = document.getElementById('scenario-modal-overlay');
    const container = document.getElementById('modal-content-body');
    if (!overlay || !container) return;

    if (!state.decisions || !state.decisions.scenarios) {
        container.innerHTML = `
            <div class="modal-framework-box" style="background-color: #FDF2F2; border-color: #F8B4B4;">
                <div class="modal-framework-title" style="color: #B83232;">UNABLE TO LOAD SCENARIO DETAILS</div>
                <div class="modal-framework-desc">The decision scenario payload could not be loaded from the backend API.</div>
            </div>
        `;
        overlay.classList.add('active');
        overlay.setAttribute('aria-hidden', 'false');
        return;
    }

    const scenarios = state.decisions.scenarios || [];
    const recName = state.decisions.recommended_scenario;
    const targetName = name || recName;
    const sc = scenarios.find(s => s.scenario === targetName) || scenarios[0];
    if (!sc) return;

    const isRec = sc.scenario === recName;
    const score = formatNumber(sc.decision_score, 2);
    const fullScore = formatNumber(sc.decision_score, 4);
    const annualSavings = sc.projected_annual_savings;
    const speedup = sc.projected_processing_time_improvement_percent;
    const implCost = sc.estimated_implementation_cost;
    const riskDelta = finiteNumber(sc.risk_impact?.fraud_rate_delta);
    const weights = sc.score_components?.weights || { efficiency: 0.40, cost: 0.35, risk: 0.25 };
    const comp = sc.score_components || {};

    container.innerHTML = `
        <div class="modal-header-row">
            <div>
                <span class="modal-badge ${isRec ? 'recommended' : 'simulated'}">
                    ${isRec ? 'RECOMMENDED DECISION' : 'SIMULATED SCENARIO'}
                </span>
                <h2 class="modal-title" id="modal-scenario-title">${sc.scenario}</h2>
            </div>
            <div class="modal-score-badge">
                <div class="modal-score-val">${score}</div>
                <div class="modal-score-lbl">SCORE (${fullScore})</div>
            </div>
        </div>

        <div class="modal-metrics-grid">
            <div class="modal-metric-card">
                <div class="modal-metric-val ${annualSavings >= 0 ? 'positive' : 'negative'}">
                    ${finiteNumber(annualSavings) !== null && annualSavings >= 0 ? '+' : ''}${formatCompactCurrency(annualSavings)}
                </div>
                <div class="modal-metric-lbl">Projected Annual Savings (Simulated)</div>
            </div>
            <div class="modal-metric-card">
                <div class="modal-metric-val positive">+${formatNumber(speedup, 2)}%</div>
                <div class="modal-metric-lbl">Processing Speedup (Simulated)</div>
            </div>
            <div class="modal-metric-card">
                <div class="modal-metric-val">${formatCompactCurrency(implCost)}</div>
                <div class="modal-metric-lbl">Implementation Cost (Estimated)</div>
            </div>
            <div class="modal-metric-card">
                <div class="modal-metric-val">${formatPercent(riskDelta, 3)}</div>
                <div class="modal-metric-lbl">Fraud Control Risk Impact</div>
            </div>
        </div>

        <div class="modal-framework-box">
            <div class="modal-framework-title">${isRec ? 'Why This Scenario Was Recommended' : 'Scoring Framework Rationale'}</div>
            <div class="modal-framework-desc">
                ${isRec ? 'Selected using a weighted decision score based on efficiency (40%), cost savings (35%), and risk impact (25%).' : (sc.risk_impact?.interpretation || 'Evaluated against portfolio efficiency, operational cost, and fraud control trade-offs.')}
            </div>
            <div class="modal-weights-list">
                <div class="modal-weights-item">Efficiency Weight: <strong>${(weights.efficiency * 100).toFixed(0)}%</strong> (Score: ${formatNumber(comp.efficiency_score, 2)})</div>
                <div class="modal-weights-item">Cost Savings Weight: <strong>${(weights.cost * 100).toFixed(0)}%</strong> (Score: ${formatNumber(comp.cost_score, 2)})</div>
                <div class="modal-weights-item">Risk Impact Weight: <strong>${(weights.risk * 100).toFixed(0)}%</strong> (Score: ${formatNumber(comp.risk_score, 2)})</div>
            </div>
        </div>

        <div class="simulation-notice">
            <strong class="notice-tag">PROJECTION DISCLOSURE:</strong>
            <span>All scenario metrics, financial run rates, and decision scores are model simulations based on PaySim synthetic dataset assumptions.</span>
        </div>
    `;

    overlay.classList.add('active');
    overlay.setAttribute('aria-hidden', 'false');
}

function closeScenarioModal() {
    const overlay = document.getElementById('scenario-modal-overlay');
    if (overlay) {
        overlay.classList.remove('active');
        overlay.setAttribute('aria-hidden', 'true');
    }
}

function setupModalListeners() {
    const overlay = document.getElementById('scenario-modal-overlay');
    if (overlay) {
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) closeScenarioModal();
        });
    }

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeScenarioModal();
    });
}

/* ==========================================================================
   FORMATTING UTILITIES
   ========================================================================== */

function formatCompactNumber(num) {
    const value = finiteNumber(num);
    if (value === null) return '—';
    if (value >= 1e6) return (value / 1e6).toFixed(2) + 'M';
    if (value >= 1e3) return (value / 1e3).toFixed(1) + 'K';
    return value.toLocaleString();
}

function formatCurrency(amount) {
    const value = finiteNumber(amount);
    if (value === null) return '—';
    if (value >= 1e12) return '$' + (value / 1e12).toFixed(2) + 'T';
    if (value >= 1e9) return '$' + (value / 1e9).toFixed(2) + 'B';
    if (value >= 1e6) return '$' + (value / 1e6).toFixed(2) + 'M';
    return '$' + value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatCompactCurrency(amount) {
    const value = finiteNumber(amount);
    if (value === null) return '—';
    if (Math.abs(value) >= 1e6) return '$' + (value / 1e6).toFixed(2) + 'M';
    if (Math.abs(value) >= 1e3) return '$' + (value / 1e3).toFixed(1) + 'K';
    return '$' + value.toFixed(0);
}
