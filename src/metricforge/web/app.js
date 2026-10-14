"use strict";

const $ = (id) => document.getElementById(id);
const metricNames = { revenue_yoy: "营业收入同比", net_margin: "销售净利率", cash_conversion: "现金转化率" };
const examples = {
  revenue_yoy: "新增营业收入同比指标，核对跨年口径、金额单位、缺失期和非正基期，验收后交付趋势图。",
  net_margin: "新增销售净利率指标，统一收入和净利润的金额单位，处理缺失字段与零分母，验收后交付图表。",
  cash_conversion: "新增经营现金流与净利润比率，核对合并口径、金额单位和零利润样本，保存反例及验收报告。"
};
const toolNames = { describe_contract: "读取指标契约", propose_metric: "编译候选表达式", validate_candidate: "执行参考验证", minimize_failure: "缩减失败反例", preview_chart: "预览指标图表", accept_candidate: "验收候选表达式" };
const stateNames = { queued: "等待执行", running: "执行中", completed: "已完成", failed: "执行失败", interrupted: "服务重启中断" };
const failureNames = { value_mismatch: "数值不一致", status_mismatch: "状态不一致", source_mismatch: "来源不一致" };
const terminal = new Set(["completed", "failed", "interrupted"]);
const historyKey = "metricforge.workbench.history.v1";
let contracts = [], currentJob = null, timer = null, watchVersion = 0, refreshing = false, history = readHistory();
let removedHistory = null, requirementDirty = false;
const initialParams = new URLSearchParams(window.location.search);
const numbers = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 0 });
const ratios = new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 4, maximumFractionDigits: 4 });
const durations = new Intl.NumberFormat("zh-CN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const dates = new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
const clock = new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });

function syncUrl() {
  const url = new URL(window.location.href);
  url.searchParams.set("metric", $("metric").value);
  if (currentJob?.id) url.searchParams.set("run", currentJob.id);
  else url.searchParams.delete("run");
  if ($("trace-disclosure").open) url.searchParams.set("trace", "open");
  else url.searchParams.delete("trace");
  window.history.replaceState(null, "", url);
}
function updateRequirementCount() { $("requirement-count").textContent = $("requirement").value.length + " / 800"; }
function announce(message) { $("action-status").textContent = message; }
function updateProviderNote() {
  $("mode-note").textContent = $("provider").value === "replay" ? "固定策略提出候选，真实执行验证工具。无需模型密钥。" : "由服务端模型提出候选并调用工具。需求会发送给模型提供方，可能产生费用。";
}

function element(tag, className, content) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content !== undefined) node.textContent = String(content);
  return node;
}
function readHistory() {
  try {
    const saved = JSON.parse(localStorage.getItem(historyKey) || "[]");
    return Array.isArray(saved) ? saved.filter((item) => item && /^[a-f0-9]{32}$/.test(item.id) && item.request && metricNames[item.request.metric_id]).slice(0, 10) : [];
  } catch { return []; }
}
function saveHistory(job) {
  const record = { id: job.id, request: job.request, created_at: job.created_at, status: job.status, decision: terminal.has(job.status) ? job.result?.decision : undefined };
  history = [record, ...history.filter((item) => item.id !== job.id)].slice(0, 10);
  try { localStorage.setItem(historyKey, JSON.stringify(history)); }
  catch { $("history-title").textContent = "最近任务 · 当前会话"; }
  renderHistory();
}
function renderHistory() {
  const list = $("history-list"); list.replaceChildren();
  $("clear-history").disabled = history.length === 0;
  if (!history.length) { list.append(element("p", "muted", "提交第一个任务，之后可从这里恢复结果。")); return; }
  history.forEach((item) => {
    const button = element("button", "history-item" + (currentJob?.id === item.id ? " active" : ""));
    button.type = "button";
    const body = element("span"); body.append(element("strong", "", metricNames[item.request.metric_id]), element("small", "", formatTime(item.created_at) + " · " + item.id.slice(0, 8)));
    button.append(body, element("span", "history-status", terminal.has(item.status) && item.decision === "accepted" ? "已验收 ✓" : stateNames[item.status] || "已保存"));
    button.addEventListener("click", () => restoreJob(item)); list.append(button);
  });
}
function formatTime(value) {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "—" : dates.format(date);
}
async function request(path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15000);
  try {
    const response = await fetch(path, { ...options, signal: controller.signal });
    let body;
    try { body = await response.json(); } catch { throw new Error("服务返回了无法解析的内容，请检查服务是否正常运行。"); }
    if (!response.ok) {
      const messages = { 404: "未找到这项任务。历史记录保存在浏览器，后台状态目录可能已更换。", 429: "当前运行队列已满，请稍后重试。", 409: "提交标识发生冲突，请重新提交。" };
      const detail = Array.isArray(body.detail) ? body.detail.map((item) => item.msg).join("；") : body.detail;
      throw new Error(messages[response.status] || detail || "请求失败（" + response.status + "）");
    }
    return body;
  } catch (error) {
    if (error.name === "AbortError") throw new Error("请求超时，请确认服务连接后重试。");
    if (error instanceof TypeError) throw new Error("无法连接服务，请检查本地服务是否仍在运行。");
    throw error;
  } finally { clearTimeout(timeout); }
}
function showError(id, message) { $(id).textContent = message || ""; $(id).hidden = !message; }
function selectMetric(value, updateRequirement = true) {
  $("metric").value = value;
  document.querySelectorAll(".metric-option").forEach((button) => { const selected = button.dataset.metric === value; button.classList.toggle("selected", selected); button.setAttribute("aria-pressed", String(selected)); });
  const contract = contracts.find((item) => item.metric_id === value);
  $("contract-definition").textContent = contract?.definition || "正在加载指标口径…";
  $("contract-unit").textContent = contract ? "输出单位 " + contract.output_unit + " · 回看 " + contract.lookback + " 期 · " + contract.domain : "";
  if (updateRequirement && !requirementDirty) $("requirement").value = examples[value];
  updateRequirementCount(); syncUrl();
}
function setBusy(busy) {
  $("submit").disabled = busy;
  $("submit").setAttribute("aria-busy", String(busy));
  $("delivery-panel").setAttribute("aria-busy", String(busy));
  document.querySelector(".button-icon").classList.toggle("is-loading", busy);
  $("submit-label").textContent = busy ? "正在验证与交付…" : "开始验证与交付";
}
function setProgress(stage, finished = false) {
  document.querySelectorAll("[data-stage]").forEach((item) => {
    const index = Number(item.dataset.stage);
    item.classList.toggle("done", index < stage || finished);
    item.classList.toggle("current", index === stage && !finished);
    if (index === stage && !finished) item.setAttribute("aria-current", "step");
    else item.removeAttribute("aria-current");
  });
}
function resetResult() {
  $("result").hidden = true; $("empty-state").hidden = true; $("running-state").hidden = false;
  $("candidates").replaceChildren(); $("events").replaceChildren(); $("event-count").textContent = "0 条事件";
  $("chart").removeAttribute("src"); showError("run-error", "");
  announce("");
  if (currentJob?.id) {
    $("run-meta").hidden = false; $("run-id").textContent = "任务 " + currentJob.id.slice(0, 12);
    $("run-provider").textContent = currentJob.request?.provider === "llm" ? "LLM · 工具调用" : currentJob.request ? "Replay · 固定策略" : "恢复任务";
  }
  setProgress(0); $("status-badge").className = "status-badge running"; $("status-badge").textContent = "等待执行";
  $("running-title").textContent = "任务已提交"; $("running-description").textContent = "正在获取后台执行结果…";
}
function stopPolling() {
  clearTimeout(timer); timer = null; watchVersion += 1; refreshing = false;
  $("poll-toggle").textContent = "继续刷新";
}
function startPolling(id) {
  stopPolling(); refreshing = true; const version = watchVersion;
  $("poll-toggle").hidden = false; $("poll-toggle").textContent = "暂停刷新";
  const tick = async (failures = 0) => {
    try {
      const [job, events] = await Promise.all([request("/v1/jobs/" + id), request("/v1/jobs/" + id + "/events")]);
      if (version !== watchVersion) return;
      showError("run-error", "");
      if (!currentJob?.request && !requirementDirty) fillRequestControls(job.request);
      currentJob = job; renderJob(job); renderEvents(events); saveHistory(job);
      if (terminal.has(job.status)) { stopPolling(); $("poll-toggle").hidden = true; return; }
      timer = setTimeout(() => tick(), 650);
    } catch (error) {
      if (version !== watchVersion) return;
      showError("run-error", error.message + (failures < 2 ? " 正在重试…" : " 点击继续刷新可重新连接。"));
      if (failures < 2) timer = setTimeout(() => tick(failures + 1), 1500);
      else { stopPolling(); setBusy(false); }
    }
  };
  tick();
}
function renderJob(job) {
  syncUrl();
  $("run-meta").hidden = false; $("run-id").textContent = "任务 " + job.id.slice(0, 12);
  $("run-provider").textContent = job.request.provider === "replay" ? "Replay · 固定策略" : "LLM · 工具调用";
  const badge = $("status-badge");
  const hasFinalResult = terminal.has(job.status) && Boolean(job.result);
  const status = hasFinalResult ? job.result.decision === "accepted" ? "验收通过 ✓" : "未通过验收" : stateNames[job.status] || job.status;
  if (badge.textContent !== status) badge.textContent = status;
  badge.className = "status-badge " + (job.status === "completed" && job.result?.decision === "accepted" ? "accepted" : terminal.has(job.status) ? "rejected" : "running");
  setBusy(!terminal.has(job.status));
  if (hasFinalResult) {
    $("running-state").hidden = true; $("result").hidden = false;
    renderDelivery(job.result, job.id); setProgress(3, job.result.decision === "accepted");
    showError("run-error", job.result.error || "");
  } else if (terminal.has(job.status)) {
    $("running-state").hidden = true; showError("run-error", job.error || "服务重启打断了任务，请从左侧重新提交。");
  } else {
    $("running-state").hidden = false; $("result").hidden = true;
    $("running-title").textContent = job.status === "queued" ? "等待后台执行" : "正在验证指标表达式";
    $("running-description").textContent = "验证结果会自动更新。暂停刷新只停止页面轮询，后台任务继续执行。";
  }
}
function renderDelivery(delivery, id) {
  $("case-count").textContent = numbers.format(delivery.case_count);
  $("tool-count").textContent = numbers.format(delivery.tool_calls);
  $("candidate-count").textContent = numbers.format(delivery.candidates.length);
  $("elapsed").textContent = delivery.elapsed_ms < 1000 ? numbers.format(delivery.elapsed_ms) + " ms" : durations.format(delivery.elapsed_ms / 1000) + " s";
  const list = $("candidates"); list.replaceChildren();
  delivery.candidates.forEach((candidate, index) => {
    const accepted = candidate.id === delivery.accepted_candidate;
    const card = element("article", "candidate" + (accepted ? " accepted" : ""));
    const top = element("div", "candidate-top");
    const validation = candidate.validation;
    const total = validation?.total || 0, passed = validation?.passed || 0;
    const status = accepted ? "验收版本 ✓" : !candidate.compiled ? "编译未通过" : validation ? passed === total ? "参考比对通过" : "发现反例" : "未验证";
    const title = element("strong", "", "候选 " + (index + 1) + " · " + candidate.id);
    title.setAttribute("translate", "no");
    top.append(title, element("span", "candidate-badge", status));
    const stats = element("div", "candidate-stats");
    stats.append(element("span", "", candidate.compiled ? "AST 编译通过" : "AST 编译失败"), element("span", "", "验证 " + passed + " / " + total), element("span", total > passed ? "candidate-stat-fail" : "", "失败 " + (total - passed)), element("span", "", "节点 " + candidate.node_count));
    const expression = element("pre", "", candidate.expression); expression.setAttribute("translate", "no");
    const actions = element("div", "candidate-actions");
    const copy = element("button", "candidate-copy", "复制公式"); copy.type = "button";
    copy.setAttribute("aria-label", "复制候选 " + (index + 1) + " 的公式");
    copy.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(candidate.expression); announce("已复制候选 " + (index + 1) + " 的公式。"); }
      catch { announce("浏览器不允许复制，请选中上方公式后复制。"); }
    });
    actions.append(element("span", "preview-label", accepted ? "已冻结验收版本" : "保留失败证据"), copy);
    const details = element("details", "candidate-details");
    details.append(element("summary", "", "展开修订理由与诊断"), element("p", "", candidate.reason || "本候选未附修订理由。"));
    if (candidate.diagnostics?.length || validation?.diagnostics?.length) details.append(element("p", "candidate-stat-fail", [...(candidate.diagnostics || []), ...(validation?.diagnostics || [])].join("；")));
    card.append(top, expression, stats, actions, details);
    list.append(card);
  });
  if (!delivery.candidates.length) list.append(element("p", "muted", "本次运行没有生成候选，请查看执行轨迹和配置。"));
  $("counterexample").hidden = !delivery.shrink;
  if (delivery.shrink) {
    const shrink = delivery.shrink, reduced = shrink.reduced;
    $("shrink-budget").textContent = "尝试 " + shrink.attempts + " / " + shrink.budget;
    $("shrink-caption").textContent = (failureNames[reduced.category] || reduced.category) + " · " + (shrink.changed ? "已缩减输入，并保留原失败类别与状态。" : "未进一步缩减，保留原始失败输入。") ;
    $("expected-value").textContent = formatEval(reduced.expected, delivery.contract.output_unit);
    $("actual-value").textContent = formatEval(reduced.actual, delivery.contract.output_unit);
    $("shrink-json").textContent = JSON.stringify({ input: reduced.case, expected: reduced.expected, actual: reduced.actual }, null, 2);
  }
  const base = "/v1/jobs/" + id + "/artifacts/";
  $("report-link").href = base + "report.html"; $("json-link").href = base + "delivery.json";
  $("chart-section").hidden = !delivery.chart; $("svg-link").hidden = !delivery.chart;
  if (delivery.chart) {
    $("chart-title").textContent = delivery.chart.title; $("chart-unit").textContent = "单位：" + delivery.chart.unit;
    $("chart").width = 840; $("chart").height = 138 + 48 * delivery.chart.points.length;
    $("chart").src = base + "chart.svg"; $("svg-link").href = base + "chart.svg";
  }
}
function formatEval(value, unit) {
  if (value.status !== "ok" || value.value === null) return value.status + " · 无数值";
  const number = Number(value.value);
  return Number.isFinite(number) ? (unit === "%" ? ratios.format(number * 100) + "%" : ratios.format(number) + " 倍") : String(value.value);
}
function renderEvents(events) {
  const list = $("events"); list.replaceChildren(); $("event-count").textContent = events.length + " 条事件";
  let stage = 0;
  events.forEach((event) => {
    const payload = event.payload || {};
    const names = { "job.queued": "任务进入队列", "job.running": "后台开始执行", "job.completed": "任务完成", "job.failed": "任务执行失败", "agent.failed": "Agent 未完成验收", "delivery.accepted": "验收通过，冻结交付" };
    let title = names[event.event] || event.event;
    if (event.event.startsWith("tool.")) {
      const action = event.event === "tool.started" ? "调用" : event.event === "tool.failed" ? "失败" : "完成";
      title = (toolNames[payload.name] || payload.name || "工具") + " · " + action;
      if (["propose_metric", "validate_candidate"].includes(payload.name)) stage = Math.max(stage, 1);
      if (payload.name === "minimize_failure") stage = Math.max(stage, 2);
      if (payload.name === "accept_candidate") stage = Math.max(stage, 3);
    }
    if (event.event === "delivery.accepted") stage = 3;
    const item = element("li", "event" + (event.event.includes("failed") ? " failed" : ""));
    const timestamp = new Date(event.time);
    const row = element("div", "event-top"), time = element("time", "", Number.isNaN(timestamp.valueOf()) ? "—" : clock.format(timestamp));
    time.dateTime = event.time; row.append(element("strong", "", title), time);
    item.append(row, element("small", "", "#" + event.sequence + " · " + event.event));
    if (Object.keys(payload).length) {
      const details = element("details"), summary = element("summary", "", "工具输入 / 返回摘要");
      const detail = { ...payload };
      if (detail.result?.failures?.length > 2) detail.result = { ...detail.result, failures: detail.result.failures.slice(0, 2), shown_failures: "页面最多展示 2 个；完整结果请查看交付 JSON。" };
      details.append(summary, element("pre", "", JSON.stringify(detail, null, 2))); item.append(details);
    }
    list.append(item);
  });
  if (!events.length) list.append(element("li", "muted trace-empty", "后台尚未返回事件，继续刷新后会显示执行记录。"));
  if (currentJob?.status !== "completed") setProgress(stage);
}
async function restoreJob(item) {
  stopPolling(); currentJob = item; resetResult(); renderHistory(); showError("form-error", "");
  fillRequestControls(item.request);
  startPolling(item.id);
}
function fillRequestControls(savedRequest) {
  selectMetric(savedRequest.metric_id, false); $("requirement").value = savedRequest.requirement; requirementDirty = false; updateRequirementCount();
  $("seed").value = savedRequest.seed ?? 20261012; $("generated-cases").value = savedRequest.generated_cases ?? 32;
  if (savedRequest.provider === "replay" || !$("provider").options[1].disabled) $("provider").value = savedRequest.provider;
  updateProviderNote(); syncUrl();
}
document.querySelectorAll(".metric-option").forEach((button) => button.addEventListener("click", () => selectMetric(button.dataset.metric)));
$("metric").addEventListener("change", () => selectMetric($("metric").value));
$("provider").addEventListener("change", updateProviderNote);
$("requirement").addEventListener("input", () => { requirementDirty = true; updateRequirementCount(); });
window.addEventListener("beforeunload", (event) => { if (requirementDirty) { event.preventDefault(); event.returnValue = ""; } });
$("job-form").addEventListener("invalid", (event) => { const details = event.target.closest("details"); if (details) details.open = true; }, true);
$("trace-disclosure").open = initialParams.get("trace") === "open" || window.location.hash === "#trace";
$("trace-disclosure").addEventListener("toggle", syncUrl);
$("trace-nav").addEventListener("click", () => { $("trace-disclosure").open = true; syncUrl(); });
$("poll-toggle").addEventListener("click", () => {
  if (refreshing) { stopPolling(); $("running-description").textContent = "已暂停页面刷新。后台任务继续执行，点击继续刷新查看最新状态。"; }
  else if (currentJob) startPolling(currentJob.id);
});
$("clear-history").addEventListener("click", () => {
  removedHistory = history.slice(); history = [];
  try { localStorage.removeItem(historyKey); } catch { /* In-memory history remains usable. */ }
  $("history-feedback").hidden = false; renderHistory(); $("undo-history").focus();
});
$("undo-history").addEventListener("click", () => {
  if (removedHistory) {
    history = [...history, ...removedHistory.filter((item) => !history.some((existing) => existing.id === item.id))].slice(0, 10);
    try { localStorage.setItem(historyKey, JSON.stringify(history)); } catch { /* In-memory history remains usable. */ }
  }
  removedHistory = null; $("history-feedback").hidden = true; renderHistory(); $("clear-history").focus();
});
$("job-form").addEventListener("submit", async (event) => {
  event.preventDefault(); if (!event.currentTarget.reportValidity()) return;
  const payload = { requirement: $("requirement").value.trim(), metric_id: $("metric").value, provider: $("provider").value, seed: Number($("seed").value), generated_cases: Number($("generated-cases").value) };
  if (payload.requirement.length < 4) { showError("form-error", "请至少填写 4 个字符的需求。" ); $("requirement").focus(); return; }
  stopPolling(); setBusy(true); showError("form-error", "");
  try {
    const key = window.crypto?.randomUUID?.() || "web-" + Date.now() + "-" + Math.random().toString(16).slice(2);
    const job = await request("/v1/jobs", { method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": key }, body: JSON.stringify(payload) });
    currentJob = job; requirementDirty = false; resetResult(); renderJob(job); saveHistory(job); syncUrl(); startPolling(job.id);
  } catch (error) { setBusy(false); showError("form-error", error.message); }
});
renderHistory();
$("submit").disabled = true;
request("/v1/capabilities").then((capabilities) => {
  contracts = capabilities.metrics;
  const initialMetric = metricNames[initialParams.get("metric")] ? initialParams.get("metric") : "revenue_yoy";
  selectMetric(initialMetric);
  if (capabilities.llm_configured) { $("provider").options[1].disabled = false; $("provider").options[1].textContent = "LLM · 服务端已配置"; }
  $("connection").className = "connection ok"; const dot = element("i"); dot.setAttribute("aria-hidden", "true"); $("connection").replaceChildren(dot, document.createTextNode("本地服务已连接"));
  $("submit").disabled = false;
  const initialRun = initialParams.get("run");
  if (initialRun && /^[a-f0-9]{32}$/.test(initialRun)) {
    const item = history.find((record) => record.id === initialRun);
    if (item) restoreJob(item);
    else { currentJob = { id: initialRun }; resetResult(); syncUrl(); startPolling(initialRun); }
  }
}).catch((error) => { $("connection").className = "connection offline"; $("connection").replaceChildren(element("i"), document.createTextNode("服务未连接")); showError("form-error", error.message + " 刷新页面后重试。"); });
