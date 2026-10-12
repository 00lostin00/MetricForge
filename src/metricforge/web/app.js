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
  const record = { id: job.id, request: job.request, created_at: job.created_at, status: job.status, decision: job.result?.decision };
  history = [record, ...history.filter((item) => item.id !== job.id)].slice(0, 10);
  try { localStorage.setItem(historyKey, JSON.stringify(history)); }
  catch { $("history-title").textContent = "最近任务 · 当前会话"; }
  renderHistory();
}
function renderHistory() {
  const list = $("history-list"); list.replaceChildren();
  $("clear-history").disabled = history.length === 0;
  if (!history.length) { list.append(element("p", "muted", "暂无记录，提交第一个任务后会出现在这里。")); return; }
  history.forEach((item) => {
    const button = element("button", "history-item" + (currentJob?.id === item.id ? " active" : ""));
    button.type = "button";
    const body = element("span"); body.append(element("strong", "", metricNames[item.request.metric_id]), element("small", "", formatTime(item.created_at) + " · " + item.id.slice(0, 8)));
    button.append(body, element("span", "history-status", item.decision === "accepted" ? "已验收 ✓" : stateNames[item.status] || "已保存"));
    button.addEventListener("click", () => restoreJob(item)); list.append(button);
  });
}
function formatTime(value) {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "—" : date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
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
  if (updateRequirement) $("requirement").value = examples[value];
}
function setBusy(busy) {
  $("submit").disabled = busy;
  $("submit-label").textContent = busy ? "正在验证与交付…" : "开始验证与交付";
}
function setProgress(stage, finished = false) {
  document.querySelectorAll("[data-stage]").forEach((item) => {
    const index = Number(item.dataset.stage);
    item.classList.toggle("done", index < stage || finished);
    item.classList.toggle("current", index === stage && !finished);
  });
}
function resetResult() {
  $("result").hidden = true; $("empty-state").hidden = true; $("running-state").hidden = false;
  $("candidates").replaceChildren(); $("events").replaceChildren(); $("event-count").textContent = "0 条事件";
  $("chart").removeAttribute("src"); showError("run-error", "");
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
      showError("run-error", ""); currentJob = job; renderJob(job); renderEvents(events); saveHistory(job);
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
  $("run-meta").hidden = false; $("run-id").textContent = "RUN " + job.id.slice(0, 12);
  $("run-provider").textContent = job.request.provider === "replay" ? "Replay · 固定策略" : "LLM · 工具调用";
  const badge = $("status-badge"); badge.textContent = stateNames[job.status] || job.status;
  badge.className = "status-badge " + (job.status === "completed" && job.result?.decision === "accepted" ? "accepted" : terminal.has(job.status) ? "rejected" : "running");
  setBusy(!terminal.has(job.status));
  if (job.result) {
    badge.textContent = job.result.decision === "accepted" ? "验收通过 ✓" : "未通过验收";
    $("running-state").hidden = true; $("result").hidden = false;
    renderDelivery(job.result, job.id); setProgress(3, job.result.decision === "accepted");
    showError("run-error", job.result.error || "");
  } else if (terminal.has(job.status)) {
    $("running-state").hidden = true; showError("run-error", job.error || "服务重启打断了任务，请从左侧重新提交。");
  } else {
    $("running-title").textContent = job.status === "queued" ? "等待后台执行" : "正在验证指标表达式";
    $("running-description").textContent = "验证结果会自动更新。暂停刷新只停止页面轮询，后台任务继续执行。";
  }
}
function renderDelivery(delivery, id) {
  $("case-count").textContent = delivery.case_count;
  $("tool-count").textContent = delivery.tool_calls;
  $("candidate-count").textContent = delivery.candidates.length;
  $("elapsed").textContent = delivery.elapsed_ms < 1000 ? Math.round(delivery.elapsed_ms) + "ms" : (delivery.elapsed_ms / 1000).toFixed(2) + "s";
  const list = $("candidates"); list.replaceChildren();
  delivery.candidates.forEach((candidate, index) => {
    const accepted = candidate.id === delivery.accepted_candidate;
    const card = element("article", "candidate" + (accepted ? " accepted" : ""));
    const top = element("div", "candidate-top");
    const validation = candidate.validation;
    const total = validation?.total || 0, passed = validation?.passed || 0;
    const status = accepted ? "验收版本 ✓" : !candidate.compiled ? "编译未通过" : validation ? passed === total ? "参考比对通过" : "发现反例" : "未验证";
    top.append(element("strong", "", "VERSION " + String(index + 1).padStart(2, "0") + " / " + candidate.id), element("span", "candidate-badge", status));
    const stats = element("div", "candidate-stats");
    stats.append(element("span", "", candidate.compiled ? "AST 编译通过" : "AST 编译失败"), element("span", "", "验证 " + passed + " / " + total), element("span", total > passed ? "candidate-stat-fail" : "", "失败 " + (total - passed)), element("span", "", "节点 " + candidate.node_count));
    card.append(top, element("pre", "", candidate.expression), stats, element("p", "", candidate.reason));
    if (candidate.diagnostics?.length || validation?.diagnostics?.length) card.append(element("p", "candidate-stat-fail", [...(candidate.diagnostics || []), ...(validation?.diagnostics || [])].join("；")));
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
  if (delivery.chart) { $("chart-title").textContent = delivery.chart.title; $("chart-unit").textContent = "单位：" + delivery.chart.unit; $("chart").src = base + "chart.svg"; $("svg-link").href = base + "chart.svg"; }
}
function formatEval(value, unit) {
  if (value.status !== "ok" || value.value === null) return value.status + " · 无数值";
  const number = Number(value.value);
  return Number.isFinite(number) ? (unit === "%" ? (number * 100).toFixed(4) + "%" : number.toFixed(4) + " 倍") : String(value.value);
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
    const row = element("div", "event-top"), time = element("time", "", new Date(event.time).toLocaleTimeString("zh-CN", { hour12: false }));
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
  if (currentJob?.status !== "completed") setProgress(stage);
}
async function restoreJob(item) {
  stopPolling(); currentJob = item; resetResult(); renderHistory(); showError("form-error", "");
  selectMetric(item.request.metric_id, false); $("requirement").value = item.request.requirement;
  $("seed").value = item.request.seed ?? 20261012; $("generated-cases").value = item.request.generated_cases ?? 32;
  if (item.request.provider === "replay" || !$("provider").options[1].disabled) $("provider").value = item.request.provider;
  startPolling(item.id);
}
document.querySelectorAll(".metric-option").forEach((button) => button.addEventListener("click", () => selectMetric(button.dataset.metric)));
$("metric").addEventListener("change", () => selectMetric($("metric").value));
$("provider").addEventListener("change", () => { $("mode-note").textContent = $("provider").value === "replay" ? "固定策略提出候选，调用真实编译、验证与反例工具。无需 API Key。" : "使用服务端配置的模型调用工具。需求会发送给模型提供方；可能产生费用，效果以本次验证为准。"; });
$("poll-toggle").addEventListener("click", () => {
  if (refreshing) { stopPolling(); $("running-description").textContent = "已暂停页面刷新。后台任务继续执行，点击继续刷新查看最新状态。"; }
  else if (currentJob) startPolling(currentJob.id);
});
$("clear-history").addEventListener("click", () => { history = []; try { localStorage.removeItem(historyKey); } catch { /* In-memory history remains usable. */ } renderHistory(); });
$("job-form").addEventListener("submit", async (event) => {
  event.preventDefault(); if (!event.currentTarget.reportValidity()) return;
  const payload = { requirement: $("requirement").value.trim(), metric_id: $("metric").value, provider: $("provider").value, seed: Number($("seed").value), generated_cases: Number($("generated-cases").value) };
  if (payload.requirement.length < 4) { showError("form-error", "请至少填写 4 个字符的需求。" ); return; }
  stopPolling(); setBusy(true); showError("form-error", "");
  try {
    const key = window.crypto?.randomUUID?.() || "web-" + Date.now() + "-" + Math.random().toString(16).slice(2);
    const job = await request("/v1/jobs", { method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": key }, body: JSON.stringify(payload) });
    currentJob = job; resetResult(); renderJob(job); saveHistory(job); startPolling(job.id);
  } catch (error) { setBusy(false); showError("form-error", error.message); }
});
renderHistory();
$("submit").disabled = true;
request("/v1/capabilities").then((capabilities) => {
  contracts = capabilities.metrics; selectMetric("revenue_yoy", false);
  if (capabilities.llm_configured) { $("provider").options[1].disabled = false; $("provider").options[1].textContent = "LLM · 服务端已配置"; }
  $("connection").className = "connection ok"; $("connection").replaceChildren(element("i"), document.createTextNode("本地服务已连接"));
  $("submit").disabled = false;
}).catch((error) => { $("connection").className = "connection offline"; $("connection").replaceChildren(element("i"), document.createTextNode("服务未连接")); showError("form-error", error.message + " 刷新页面后重试。"); });
