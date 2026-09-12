const ACCENT = "#00FF66", MUTED = "#9a9c96", BORDER = "#2a2c28", TEXT = "#F4F5F2", RED = "#ff5c5c";
Chart.defaults.color = MUTED;
Chart.defaults.borderColor = BORDER;
Chart.defaults.font.family = "-apple-system, sans-serif";

const SRC_FILES = [
  "vanna/__init__.py",
  "vanna/pricing/__init__.py",
  "vanna/pricing/black_scholes.py",
  "vanna/pricing/binomial.py",
  "vanna/pricing/implied_vol.py",
  "vanna/backtest/__init__.py",
  "vanna/backtest/chain.py",
  "vanna/backtest/strategies.py",
  "vanna/backtest/attribution.py",
  "vanna/backtest/engine.py",
  "vanna/backtest/metrics.py",
  "web_glue.py",
];

// Mirrors the validation the Python engine itself enforces
// (vanna/backtest/engine.py's run_backtest) - checking here first means a
// bad value gets an immediate, specific, in-place message pointing at the
// actual field, instead of a round trip into Pyodide just to find out the
// same thing from a generic error string.
const FIELD_RULES = {
  spot: { label: "Spot", min: 0.01, max: 1_000_000, finite: true },
  iv: { label: "Entry IV", min: 0.001, max: 5, finite: true },
  rate: { label: "Risk-free rate", min: -1, max: 1, finite: true },
  drift: { label: "Underlying drift", min: -5, max: 5, finite: true },
  entryDte: { label: "Entry DTE", min: 1, max: 3650, integer: true },
  exitDte: { label: "Exit DTE", min: 0, max: 3649, integer: true },
  trades: { label: "Number of trades", min: 1, max: 5000, integer: true },
  seed: { label: "Random seed", min: 0, max: 2147483647, integer: true },
};

let pyodide;
let charts = {};
let booted = false;
let running = false;

function setStatus(msg, isError) {
  const el = document.getElementById("status");
  el.textContent = msg;
  el.className = isError ? "error" : "";
}

function clearFieldErrors() {
  Object.keys(FIELD_RULES).forEach((id) => document.getElementById(id).classList.remove("invalid"));
}

// Returns null if every field is valid, or the first problem's message
// (after marking every invalid field, not just the first, so a user
// fixing one mistake doesn't get surprised by the next one).
function validateFields() {
  let firstMessage = null;
  for (const [id, rule] of Object.entries(FIELD_RULES)) {
    const el = document.getElementById(id);
    const raw = el.value.trim();
    const value = rule.integer ? parseInt(raw, 10) : parseFloat(raw);
    let message = null;
    if (raw === "" || Number.isNaN(value)) {
      message = `${rule.label} must be a number.`;
    } else if (!Number.isFinite(value)) {
      message = `${rule.label} must be finite.`;
    } else if (value < rule.min || value > rule.max) {
      message = `${rule.label} must be between ${rule.min} and ${rule.max}.`;
    }
    el.classList.toggle("invalid", !!message);
    if (message && !firstMessage) firstMessage = message;
  }

  const entryDte = parseInt(document.getElementById("entryDte").value, 10);
  const exitDte = parseInt(document.getElementById("exitDte").value, 10);
  if (Number.isFinite(entryDte) && Number.isFinite(exitDte) && exitDte >= entryDte) {
    document.getElementById("exitDte").classList.add("invalid");
    document.getElementById("entryDte").classList.add("invalid");
    firstMessage = firstMessage || "Exit DTE must be less than Entry DTE.";
  }

  return firstMessage;
}

async function boot() {
  try {
    pyodide = await loadPyodide();
    await pyodide.loadPackage(["numpy"]);

    pyodide.FS.mkdirTree("/vanna_pkg/vanna/pricing");
    pyodide.FS.mkdirTree("/vanna_pkg/vanna/backtest");
    for (const f of SRC_FILES) {
      const resp = await fetch("vanna_src/" + f);
      if (!resp.ok) throw new Error("failed to fetch " + f + " (" + resp.status + ")");
      const text = await resp.text();
      pyodide.FS.writeFile("/vanna_pkg/" + f, text);
    }
    pyodide.runPython(`
import sys
sys.path.insert(0, "/vanna_pkg")
from web_glue import run_web_backtest
`);

    booted = true;
    document.getElementById("run").disabled = false;
    document.getElementById("run").textContent = "Run backtest";
    setStatus("Ready.");
    runBacktest();
  } catch (e) {
    setStatus("Failed to load: " + e, true);
  }
}

function runBacktest() {
  if (!booted || running) return;

  clearFieldErrors();
  const problem = validateFields();
  if (problem) {
    setStatus(problem, true);
    return;
  }

  const params = {
    strategy: document.getElementById("strategy").value,
    s0: parseFloat(document.getElementById("spot").value),
    iv0: parseFloat(document.getElementById("iv").value),
    r: parseFloat(document.getElementById("rate").value),
    mu: parseFloat(document.getElementById("drift").value),
    entry_dte: parseInt(document.getElementById("entryDte").value, 10),
    exit_dte: parseInt(document.getElementById("exitDte").value, 10),
    n_trades: parseInt(document.getElementById("trades").value, 10),
    seed: parseInt(document.getElementById("seed").value, 10),
  };

  running = true;
  const runBtn = document.getElementById("run");
  runBtn.disabled = true;
  runBtn.textContent = "Running…";
  setStatus("Running backtest…");

  // Yield one frame so the "Running…" state actually paints before the
  // (synchronous, potentially not-instant) Pyodide call blocks the thread.
  requestAnimationFrame(() => {
    try {
      const fn = pyodide.globals.get("run_web_backtest");
      const raw = fn(params.strategy, params.s0, params.iv0, params.r, params.mu,
                      params.entry_dte, params.exit_dte, params.n_trades, params.seed);
      const data = JSON.parse(raw);
      if (data.error) {
        setStatus(data.error, true);
      } else {
        setStatus("Ready.");
        renderEquity(data.equity_curve);
        renderPayoff(data.payoff_x, data.payoff_y, data.entry_spot);
        renderAttribution(data.attribution);
        renderSummary(data.summary);
      }
    } catch (e) {
      setStatus("Backtest error: " + e, true);
    } finally {
      running = false;
      runBtn.disabled = false;
      runBtn.textContent = "Run backtest";
    }
  });
}

function destroyIfExists(key) {
  if (charts[key]) { charts[key].destroy(); }
}

function renderEquity(curve) {
  destroyIfExists("equity");
  const ctx = document.getElementById("chartEquity");
  charts.equity = new Chart(ctx, {
    type: "line",
    data: {
      labels: curve.map((_, i) => i),
      datasets: [{
        data: curve, borderColor: ACCENT, backgroundColor: "rgba(0,255,102,0.12)",
        fill: true, tension: 0.15, pointRadius: 0, borderWidth: 2,
      }],
    },
    options: {
      plugins: { legend: { display: false }, title: { display: true, text: "Equity Curve", color: TEXT } },
      scales: {
        x: { title: { display: true, text: "Trade #" }, grid: { color: BORDER } },
        y: { title: { display: true, text: "Cumulative P&L ($/share)" }, grid: { color: BORDER } },
      },
    },
  });
}

function renderPayoff(xs, ys, entrySpot) {
  destroyIfExists("payoff");
  const ctx = document.getElementById("chartPayoff");
  charts.payoff = new Chart(ctx, {
    type: "line",
    data: {
      labels: xs.map((x) => x.toFixed(1)),
      datasets: [{
        data: ys, borderColor: ACCENT, backgroundColor: "rgba(0,255,102,0.12)",
        fill: true, tension: 0, pointRadius: 0, borderWidth: 2,
      }],
    },
    options: {
      plugins: {
        legend: { display: false },
        title: { display: true, text: "Payoff at Expiration (most recent trade)", color: TEXT },
      },
      scales: {
        x: { title: { display: true, text: "Underlying price at expiration" }, grid: { color: BORDER } },
        y: { title: { display: true, text: "P&L ($/share)" }, grid: { color: BORDER } },
      },
    },
  });
}

function renderAttribution(attribution) {
  destroyIfExists("attribution");
  const ctx = document.getElementById("chartAttribution");
  const labels = Object.keys(attribution);
  const values = Object.values(attribution);
  const colors = ["#00FF66", "#6fd94f", "#4fb8d9", "#d9b04f", "#c084fc", "#f472b6", "#5a5c58"];
  charts.attribution = new Chart(ctx, {
    type: "bar",
    data: { labels, datasets: [{ data: values, backgroundColor: colors }] },
    options: {
      plugins: {
        legend: { display: false },
        title: { display: true, text: "Greek P&L Attribution (most recent trade)", color: TEXT },
      },
      scales: {
        y: { title: { display: true, text: "P&L contribution ($/share)" }, grid: { color: BORDER } },
        x: { grid: { display: false } },
      },
    },
  });
}

function renderSummary(s) {
  const rows = [
    ["Trades", s.n_trades],
    ["Win rate", (s.win_rate * 100).toFixed(1) + "%"],
    ["Profit factor", s.profit_factor === null ? "∞" : s.profit_factor.toFixed(2)],
    ["Total P&L", "$" + s.total_pnl.toFixed(2)],
    ["Max drawdown", "$" + s.max_drawdown.toFixed(2)],
    ["Avg P&L / trade", "$" + s.avg_pnl.toFixed(2)],
  ];
  const tbody = document.querySelector("#summary tbody");
  tbody.textContent = "";
  for (const [k, v] of rows) {
    const tr = document.createElement("tr");
    const tdK = document.createElement("td");
    tdK.textContent = k;
    const tdV = document.createElement("td");
    tdV.textContent = v;
    tr.append(tdK, tdV);
    tbody.appendChild(tr);
  }
}

document.querySelectorAll(".tabs button").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tabs button").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tabpage").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById("tab-" + btn.dataset.tab).classList.add("active");
    // Chart.js sizes a canvas from its parent's layout box at creation
    // time; a canvas created while its .tabpage is display:none has no
    // box to measure, so it can end up 0-height. Resizing on reveal is
    // the standard fix - cheap, and correct regardless of which tab
    // happened to be active when the chart was first drawn.
    const chart = charts[btn.dataset.tab];
    if (chart) chart.resize();
  });
});

document.getElementById("run").addEventListener("click", runBacktest);
document.getElementById("controls").addEventListener("keydown", (e) => {
  if (e.key === "Enter") runBacktest();
});
boot();
