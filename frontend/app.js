// Sentiment Ledger dashboard.
// Scores and the trend chart are read DIRECTLY from the contract (no backend needed).
// The backend only adds the "why": headlines, AI reasons and transaction links.
"use strict";

const $ = (id) => document.getElementById(id);
const readProvider = new ethers.JsonRpcProvider(CONFIG.RPC_URL, CONFIG.CHAIN_ID, { staticNetwork: true });
const registry = new ethers.Contract(CONFIG.CONTRACT_ADDRESS, CONTRACT_ABI, readProvider);
const CHAIN_HEX = "0x" + CONFIG.CHAIN_ID.toString(16);

const state = {
  tokens: [],          // token symbols on-chain (minus hidden ones)
  history: {},         // token -> [{score, confidence, sourceCount, observedAt, recordedAt, analysisHash}]
  details: {},         // analysisHash -> backend row (headlines, tx_hash, method)
  selected: null,
  selectedIndex: null, // which history point is shown (null = latest)
  chart: null,
  backendUp: true,
};

// ------------------------------------------------------------------ helpers
function classify(score) {
  if (score >= CONFIG.THRESHOLD) return { text: "Bullish", cls: "bull" };
  if (score <= -CONFIG.THRESHOLD) return { text: "Bearish", cls: "bear" };
  return { text: "Neutral", cls: "neu" };
}
const signed = (n) => (n > 0 ? "+" : n < 0 ? "−" : "") + Math.abs(n);
const short = (h) => (h ? h.slice(0, 6) + "…" + h.slice(-4) : "");
const txLink = (hash) => `${CONFIG.EXPLORER}/tx/${hash}`;
function when(ts) {
  const d = new Date(ts * 1000);
  const ago = Math.round((Date.now() / 1000 - ts) / 60);
  const rel = ago < 1 ? "just now" : ago < 60 ? `${ago} min ago` : ago < 1440 ? `${Math.round(ago / 60)} h ago` : `${Math.round(ago / 1440)} d ago`;
  return `${d.toLocaleDateString([], { day: "numeric", month: "short" })} ${d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} (${rel})`;
}
function el(tag, props = {}, children = []) {          // builds DOM safely: headline text never becomes HTML
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") node.className = v; else if (k === "text") node.textContent = v; else node.setAttribute(k, v);
  }
  for (const c of [].concat(children)) node.append(c);
  return node;
}
function showNotice(msg) { $("notice").hidden = !msg; $("notice").textContent = msg || ""; }

async function api(path, opts = {}) {
  const res = await fetch(CONFIG.BACKEND_URL + path, opts);
  let body = {};
  try { body = await res.json(); } catch { /* non-JSON */ }
  if (!res.ok) throw new Error(body.error || `Backend answered ${res.status}`);
  return body;
}

// ------------------------------------------------------------------ data loading
async function loadChain() {
  const all = await registry.getTokens();
  state.tokens = all.filter((t) => !CONFIG.HIDDEN_TOKENS.includes(t));
  await Promise.all(state.tokens.map(async (t) => {
    const len = Number(await registry.historyLength(t));
    const start = Math.max(0, len - 200);
    const rows = await registry.getHistory(t, start, 200);
    state.history[t] = rows.map((r) => ({
      score: Number(r.score), confidence: Number(r.confidence), sourceCount: Number(r.sourceCount),
      observedAt: Number(r.observedAt), recordedAt: Number(r.recordedAt), analysisHash: r.analysisHash.toLowerCase(),
    }));
  }));
}

async function loadDetails(token) {
  try {
    const { signals } = await api(`/signals?token=${encodeURIComponent(token)}&limit=200`);
    for (const s of signals) state.details[s.analysis_hash.toLowerCase()] = s;
    if (!state.backendUp) showNotice("");
    state.backendUp = true;
  } catch {
    state.backendUp = false;
    showNotice("The backend is not reachable, so headlines and reasons are hidden. Scores and the chart still work because they come straight from the contract.");
  }
}

// ------------------------------------------------------------------ rendering
function renderTabs() {
  const nav = $("token-tabs");
  nav.replaceChildren();
  for (const t of state.tokens) {
    const h = state.history[t];
    const last = h[h.length - 1];
    const c = classify(last.score);
    const btn = el("button", { class: "tab", role: "tab", "aria-selected": String(t === state.selected) }, [
      el("strong", { text: t }),
      el("span", { class: `t-score label ${c.cls}`, text: `${signed(last.score)} ${c.text}` }),
    ]);
    btn.addEventListener("click", () => selectToken(t));
    nav.append(btn);
  }
}

function renderReading() {
  const h = state.history[state.selected] || [];
  if (!h.length) return;
  const i = state.selectedIndex ?? h.length - 1;
  const r = h[i];
  const c = classify(r.score);
  const isLatest = i === h.length - 1;
  $("r-token").textContent = isLatest ? `${state.selected} now` : `${state.selected} on ${new Date(r.observedAt * 1000).toLocaleDateString([], { day: "numeric", month: "short" })}`;
  $("r-label").textContent = c.text;
  $("r-label").className = `label ${c.cls}`;
  $("r-score").textContent = signed(r.score);
  $("r-score").className = `score ${c.cls}`;
  $("r-needle").style.left = `${(r.score + 100) / 2}%`;
  $("r-conf").textContent = `${r.confidence}%`;
  $("r-conf-bar").style.width = `${r.confidence}%`;
  $("r-sources").textContent = `${r.sourceCount}`;
  $("r-observed").textContent = when(r.observedAt);
  $("r-recorded").textContent = when(r.recordedAt);

  const d = state.details[r.analysisHash];
  const tx = $("r-tx");
  tx.replaceChildren();
  if (d && d.tx_hash) {
    tx.append("Published in block ", String(d.block_number), ". ",
      el("a", { href: txLink(d.tx_hash), target: "_blank", rel: "noopener", text: `View transaction ${short(d.tx_hash)}` }));
  } else {
    tx.append(el("a", { href: `${CONFIG.EXPLORER}/address/${CONFIG.CONTRACT_ADDRESS}#events`, target: "_blank", rel: "noopener", text: "View this contract's records on Etherscan" }));
  }
  renderWhy(r, d);
  renderVerify(r, d);
}

function renderWhy(r, d) {
  const list = $("headlines");
  list.replaceChildren();
  if (!d) {
    $("why-method").textContent = "";
    list.append(el("li", { class: "empty", text: state.backendUp ? "No off-chain details stored for this record." : "Headlines need the backend, which is offline." }));
    return;
  }
  const method = d.method.startsWith("llm:") ? `AI model ${d.method.slice(4)}` : "keyword scorer (AI fallback)";
  $("why-method").textContent = `Scored by ${method}. These headlines moved the score the most.`;
  for (const hl of d.top_headlines) {
    const c = classify(hl.score);
    const title = hl.url ? el("a", { href: hl.url, target: "_blank", rel: "noopener noreferrer", text: hl.title }) : hl.title;
    list.append(el("li", {}, [
      el("span", { class: `h-score label ${c.cls}`, text: signed(hl.score) }),
      el("div", {}, [
        el("div", { class: "h-title" }, [title]),
        el("div", { class: "h-meta", text: `${hl.source}. ${String(hl.reason || "").replace(/[.\s]+$/, "")}. Confidence ${Math.round(hl.confidence * 100)}%.` }),
      ]),
    ]));
  }
}

async function renderVerify(r, d) {
  $("v-onchain").textContent = r.analysisHash;
  $("v-result").textContent = "";
  $("v-result").className = "v-result";
  const ta = $("v-json");
  ta.value = "";
  ta.dataset.original = "";
  const zero = /^0x0+$/.test(r.analysisHash);
  $("v-btn").disabled = $("v-reset").disabled = zero || !d;
  if (zero) { ta.placeholder = "This record was published without an analysis fingerprint."; return; }
  if (!d) { ta.placeholder = "The full analysis is stored by the backend, which is not reachable."; return; }
  try {
    const { analysis_json } = await api(`/analysis/${r.analysisHash}`);
    ta.value = analysis_json;
    ta.dataset.original = analysis_json;
  } catch (e) {
    ta.placeholder = `Could not load the analysis: ${e.message}`;
  }
}

function verifyNow() {
  const r = currentRecord();
  const local = ethers.keccak256(ethers.toUtf8Bytes($("v-json").value)).toLowerCase();
  const ok = local === r.analysisHash;
  const out = $("v-result");
  out.className = `v-result ${ok ? "ok" : "err"}`;
  out.textContent = ok ? "Matches the chain. This is exactly what the agent published."
                       : `Does not match. Your text hashes to ${short(local)}, the chain has ${short(r.analysisHash)}.`;
}

function currentRecord() {
  const h = state.history[state.selected];
  return h[state.selectedIndex ?? h.length - 1];
}

// The ±20 neutral band, drawn behind the line
const bandPlugin = {
  id: "neutralBand",
  beforeDatasetsDraw(chart) {
    const { ctx, chartArea: a, scales: { y } } = chart;
    ctx.save();
    ctx.fillStyle = "rgba(107,118,133,0.10)";
    const top = y.getPixelForValue(CONFIG.THRESHOLD), bottom = y.getPixelForValue(-CONFIG.THRESHOLD);
    ctx.fillRect(a.left, top, a.right - a.left, bottom - top);
    ctx.restore();
  },
};

function renderChart() {
  const h = state.history[state.selected] || [];
  const colors = { bull: "#0F7B5F", bear: "#B4372A", neu: "#6B7685" };
  const points = h.map((r) => ({ x: r.observedAt * 1000, y: r.score }));
  const pointColors = h.map((r) => colors[classify(r.score).cls]);
  const sel = state.selectedIndex ?? h.length - 1;
  const radius = h.map((_, i) => (i === sel ? 8 : 5));
  if (state.chart) {
    const ds = state.chart.data.datasets[0];
    ds.data = points; ds.pointBackgroundColor = pointColors; ds.pointRadius = radius;
    state.chart.update();
    return;
  }
  state.chart = new Chart($("chart"), {
    type: "line",
    data: { datasets: [{ data: points, borderColor: "#17202E", borderWidth: 2, cubicInterpolationMode: "monotone",
      pointBackgroundColor: pointColors, pointBorderColor: "#fff", pointBorderWidth: 2, pointRadius: radius, pointHoverRadius: 9 }] },
    options: {
      maintainAspectRatio: false, parsing: false,
      animation: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? false : { duration: 500 },
      scales: {
        y: { min: -100, max: 100, ticks: { stepSize: 50, callback: (v) => signed(v) }, grid: { color: "#E3E8EE" } },
        x: { type: "linear", grid: { display: false },
             ticks: { maxTicksLimit: 7, callback: (v) => new Date(v).toLocaleDateString([], { day: "numeric", month: "short" }) } },
      },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: {
          title: (items) => when(items[0].raw.x / 1000),
          label: (item) => {
            const r = state.history[state.selected][item.dataIndex];
            return `${signed(r.score)} ${classify(r.score).text}, confidence ${r.confidence}%, ${r.sourceCount} headlines`;
          },
        } },
      },
      onClick: (_, els) => { if (els.length) { state.selectedIndex = els[0].index; renderChart(); renderReading(); } },
    },
    plugins: [bandPlugin],
  });
}

async function selectToken(t) {
  state.selected = t;
  state.selectedIndex = null;
  renderTabs();
  renderChart();
  renderReading();               // instant: on-chain data
  await loadDetails(t);          // then add the off-chain "why"
  renderReading();
}

async function refreshAll(keepToken = true) {
  await loadChain();
  if (!state.tokens.length) {
    $("r-token").textContent = "No signals on-chain yet";
    $("r-score").textContent = "—";
    return;
  }
  const t = keepToken && state.tokens.includes(state.selected) ? state.selected : state.tokens[0];
  await selectToken(t);
}

// ------------------------------------------------------------------ run the agent
function setStep(name, status) {
  for (const li of $("run-steps").children) {
    if (li.dataset.step === name) li.className = status;
  }
}

async function runAgent() {
  const btn = $("run-btn");
  const out = $("run-result");
  btn.disabled = true;
  $("run-steps").hidden = false;
  for (const li of $("run-steps").children) li.className = "";
  out.className = "run-result";
  out.textContent = "Pending: the agent is working. This takes 20 to 60 seconds.";
  setStep("analyse", "active");
  const chainTimer = setTimeout(() => { setStep("analyse", "done"); setStep("chain", "active"); }, 6000);
  try {
    const res = await api("/run-batch", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source: $("run-source").value }),
    });
    clearTimeout(chainTimer);
    setStep("analyse", "done"); setStep("chain", "done");
    if (!res.tx_hash) {
      out.textContent = "Nothing new to publish: the latest records are already on-chain.";
      setStep("confirm", "done");
      return;
    }
    // Do not just trust the backend: ask the chain for the receipt ourselves.
    setStep("confirm", "active");
    const receipt = await readProvider.waitForTransaction(res.tx_hash, 1, 120000);
    if (!receipt || receipt.status !== 1) throw new Error(`Transaction failed on-chain (${short(res.tx_hash)})`);
    setStep("confirm", "done");
    out.className = "run-result ok";
    out.replaceChildren(
      `Confirmed in block ${receipt.blockNumber}: ${res.signals.length} token signals from ${res.headlines} headlines (${res.source === "rss" ? "live news" : "sample dataset"}). `,
      el("a", { href: txLink(res.tx_hash), target: "_blank", rel: "noopener", text: "View transaction" }),
    );
    if (res.notes && res.notes.length) out.append(el("div", { class: "h-meta", text: res.notes.join(" ") }));
    await refreshAll(true);
  } catch (e) {
    clearTimeout(chainTimer);
    for (const li of $("run-steps").children) if (li.className === "active") li.className = "fail";
    out.className = "run-result err";
    out.textContent = `Failed: ${e.message === "Failed to fetch" ? "the backend is not reachable. Start it, or check BACKEND_URL in config.js." : e.message}`;
  } finally {
    btn.disabled = false;
  }
}

// ------------------------------------------------------------------ wallet
async function connectWallet() {
  if (!window.ethereum) {
    showNotice("No wallet found. Install MetaMask, and open this page from http://localhost:8000 rather than as a file.");
    return;
  }
  try {
    await window.ethereum.request({ method: "eth_requestAccounts" });
    await ensureNetwork();
    await showWallet();
  } catch (e) {
    showNotice(`Wallet: ${e.shortMessage || e.message}`);
  }
}

async function ensureNetwork() {
  const chainId = await window.ethereum.request({ method: "eth_chainId" });
  if (chainId === CHAIN_HEX) return;
  await window.ethereum.request({ method: "wallet_switchEthereumChain", params: [{ chainId: CHAIN_HEX }] });
}

async function showWallet() {
  const provider = new ethers.BrowserProvider(window.ethereum);
  const [account] = await provider.send("eth_accounts", []);
  const net = await provider.getNetwork();
  const badge = $("net-badge");
  if (!account) { $("wallet-info").hidden = true; $("connect-btn").hidden = false; return; }
  const onRightChain = Number(net.chainId) === CONFIG.CHAIN_ID;
  badge.textContent = onRightChain ? CONFIG.CHAIN_NAME : "Wrong network: switch to Sepolia";
  badge.className = `net ${onRightChain ? "ok" : "bad"}`;
  const bal = onRightChain ? Number(ethers.formatEther(await provider.getBalance(account))).toFixed(4) : "?";
  let role = "";
  try { role = (await registry.isPublisher(account)) ? ", authorized publisher" : ""; } catch { /* ignore */ }
  $("wallet-info").textContent = `${short(account)} (${bal} ${CONFIG.CURRENCY}${role})`;
  $("wallet-info").hidden = false;
  $("connect-btn").hidden = true;
}

// ------------------------------------------------------------------ start
function init() {
  const addrUrl = `${CONFIG.EXPLORER}/address/${CONFIG.CONTRACT_ADDRESS}`;
  $("contract-link").href = addrUrl;
  $("foot-contract").href = addrUrl;
  $("foot-contract").textContent = CONFIG.CONTRACT_ADDRESS;
  $("connect-btn").addEventListener("click", connectWallet);
  $("run-btn").addEventListener("click", runAgent);
  $("v-btn").addEventListener("click", verifyNow);
  $("v-reset").addEventListener("click", () => { $("v-json").value = $("v-json").dataset.original || ""; $("v-result").textContent = ""; });
  if (window.ethereum) {
    window.ethereum.on?.("accountsChanged", showWallet);
    window.ethereum.on?.("chainChanged", showWallet);
    showWallet().catch(() => {});
  }
  refreshAll(false).catch((e) => {
    $("r-token").textContent = "Could not read the contract";
    showNotice(`Could not read the contract: ${e.shortMessage || e.message}. Check CONTRACT_ADDRESS and RPC_URL in config.js.`);
  });
}

init();
