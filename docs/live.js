// Live chain tab: real public Deribit option book, priced by the real vanna
// engine running in Pyodide. The only thing JS does is the network fetch
// (Pyodide has no sockets) and rendering; parsing, implied vol, model
// prices and Greeks all come from vanna.marketdata / vanna.pricing.
const DERIBIT_BOOK = "https://www.deribit.com/api/v2/public/get_book_summary_by_currency?currency=BTC&kind=option";
let livePayload = null, liveFetchedAt = null, liveBusy = false, liveReady = false;
let liveExpiries = [];

function liveSet(msg, isError) {
  const el = document.getElementById("liveStatus");
  el.textContent = msg;
  el.className = isError ? "error" : "";
}

const fmtUsd = (x, d = 2) => (x === null || x === undefined ? "–" : x.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }));
const fmtPct = (x) => (x === null || x === undefined ? "–" : (x * 100).toFixed(2) + "%");
const fmtG = (x, d = 4) => (x === null || x === undefined ? "–" : x.toFixed(d));

async function liveFetch() {
  if (liveBusy || !liveReady) return;
  liveBusy = true;
  const btn = document.getElementById("liveRefresh");
  btn.disabled = true;
  liveSet("Fetching the public Deribit option book…");
  try {
    const resp = await fetch(DERIBIT_BOOK, { cache: "no-store" });
    if (!resp.ok) throw new Error("Deribit answered HTTP " + resp.status);
    livePayload = await resp.text();
    liveFetchedAt = new Date();
    liveRender(true);
  } catch (e) {
    liveSet("Could not fetch live data (" + e.message + "). Nothing is simulated as a fallback; try again in a moment.", true);
  } finally {
    liveBusy = false;
    btn.disabled = false;
  }
}

function liveAnalyze(expiry) {
  const fn = pyodide.globals.get("analyze_live_chain");
  const out = JSON.parse(fn(livePayload, 0.0, expiry || ""));
  fn.destroy();
  return out;
}

function liveRender(refreshExpiries) {
  if (!livePayload) return;
  const sel = document.getElementById("liveExpiry");
  let data;
  if (refreshExpiries) {
    const first = liveAnalyze("");
    if (first.error) { liveSet("Could not read the chain: " + first.error, true); return; }
    const keep = sel.value;
    sel.textContent = "";
    for (const e of first.expiries) { const o = document.createElement("option"); o.value = o.textContent = e; sel.appendChild(o); }
    sel.value = first.expiries.includes(keep) ? keep : first.expiries[Math.min(4, first.expiries.length - 1)];
    sel.disabled = false;
  }
  data = liveAnalyze(sel.value);
  if (data.error) { liveSet("Could not read the chain: " + data.error, true); return; }

  const side = document.getElementById("liveSide").value;
  const width = parseFloat(document.getElementById("liveWidth").value);
  const twoOnly = document.getElementById("liveTwo").checked;
  const c = data.counts;
  const fwd = data.rows.length ? data.rows[0].forward : null;
  let rows = data.rows.filter((r) =>
    (side === "all" || (side === "C") === r.is_call) &&
    (!twoOnly || r.two_sided) &&
    (fwd === null || Math.abs(r.strike / fwd - 1) <= width));

  const meta = document.getElementById("liveMeta");
  meta.textContent = "";
  const items = [
    ["Source", "Deribit public API (BTC options), unauthenticated"],
    ["Data timestamp", data.as_of.replace("T", " ").replace(/\.\d+/, "").replace("+00:00", "") + " UTC"],
    ["Fetched in your browser", liveFetchedAt.toISOString().replace("T", " ").replace(/\.\d+Z/, "") + " UTC"],
    ["BTC index", data.index_price ? "$" + fmtUsd(data.index_price, 0) : "–"],
    ["Forward (" + sel.value + ")", fwd ? "$" + fmtUsd(fwd, 0) : "–"],
    ["Quotes in expiry", String(c.total)],
    ["two-sided", String(c.two_sided)], ["one-sided", String(c.one_sided)], ["no quote", String(c.no_quote)],
    ["IV solved", c.iv_solved + " (failed " + c.iv_failed + ")"],
    ["Rows shown", String(rows.length)],
  ];
  for (const [k, v] of items) {
    const span = document.createElement("span");
    const b = document.createElement("b"); b.textContent = k + ": ";
    span.append(b, document.createTextNode(v));
    meta.appendChild(span);
  }

  const head = ["Strike", "C/P", "Bid", "Ask", "Mid", "Model@mark", "Δ vs mid", "IV(mid)", "Deribit IV", "Delta", "Gamma", "Vega/pt", "Theta/day", "Vanna", "Volga"];
  const thead = document.querySelector("#liveTable thead"); thead.textContent = "";
  const hr = document.createElement("tr");
  for (const h of head) { const th = document.createElement("th"); th.textContent = h; hr.appendChild(th); }
  thead.appendChild(hr);
  const tbody = document.querySelector("#liveTable tbody"); tbody.textContent = "";
  for (const r of rows) {
    const g = r.greeks;
    const diff = r.mid !== null && r.model_at_mark_iv !== null ? r.model_at_mark_iv - r.mid : null;
    const cells = [fmtUsd(r.strike, 0), r.is_call ? "C" : "P", fmtUsd(r.bid), fmtUsd(r.ask), fmtUsd(r.mid), fmtUsd(r.model_at_mark_iv),
      diff === null ? "–" : (diff >= 0 ? "+" : "") + fmtUsd(diff), fmtPct(r.iv_mid), fmtPct(r.mark_iv),
      g ? fmtG(g.delta) : "–", g ? fmtG(g.gamma, 6) : "–", g ? fmtG(g.vega, 2) : "–", g ? fmtG(g.theta_day, 2) : "–",
      g ? fmtG(g.vanna, 4) : "–", g ? fmtG(g.volga, 4) : "–"];
    const tr = document.createElement("tr");
    for (const v of cells) { const td = document.createElement("td"); td.textContent = v; tr.appendChild(td); }
    tbody.appendChild(tr);
  }
  liveSet(rows.length ? "Priced " + c.iv_solved + " options with vanna's engine from live Deribit quotes." : "No rows match these filters.");
  liveSmile(rows.filter((r) => r.iv_mid !== null));
}

function liveSmile(rows) {
  if (charts.smile) charts.smile.destroy();
  const calls = rows.filter((r) => r.is_call), puts = rows.filter((r) => !r.is_call);
  const pts = (rs, key) => rs.map((r) => ({ x: r.strike, y: r[key] * 100 }));
  charts.smile = new Chart(document.getElementById("chartSmile"), {
    type: "scatter",
    data: { datasets: [
      { label: "Calls IV(mid), vanna solver", data: pts(calls, "iv_mid"), borderColor: ACCENT, backgroundColor: ACCENT, pointRadius: 3 },
      { label: "Puts IV(mid), vanna solver", data: pts(puts, "iv_mid"), borderColor: "#4fb8d9", backgroundColor: "#4fb8d9", pointRadius: 3 },
      { label: "Deribit mark IV", data: pts(rows, "mark_iv"), borderColor: RED, backgroundColor: "transparent", pointStyle: "crossRot", pointRadius: 4, showLine: false },
    ] },
    options: {
      maintainAspectRatio: false,
      plugins: { title: { display: true, text: "Implied vol by strike (real quotes)", color: TEXT }, legend: { labels: { color: MUTED } } },
      scales: { x: { title: { display: true, text: "Strike (USD)" }, grid: { color: BORDER } },
                y: { title: { display: true, text: "Implied vol (%)" }, grid: { color: BORDER } } },
    },
  });
}

window.addEventListener("vanna-ready", () => {
  liveReady = true;
  document.getElementById("liveRefresh").disabled = false;
  liveSet("Ready. Fetching the live chain…");
  liveFetch();
});
document.getElementById("liveRefresh").addEventListener("click", liveFetch);
for (const id of ["liveExpiry", "liveSide", "liveWidth", "liveTwo"]) {
  document.getElementById(id).addEventListener("change", () => liveRender(false));
}
