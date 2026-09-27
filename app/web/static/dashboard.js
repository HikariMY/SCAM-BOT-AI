const COLORS = {
  PHISHING: "#2f5bff",
  MONEY_TRANSFER: "#ff4d6d",
  IMPERSONATION: "#a45cff",
  INVESTMENT: "#ffb020",
  SAFE: "#22c58b",
};
const CATEGORY_LABELS = {
  PHISHING: "ลิงก์ปลอม",
  MONEY_TRANSFER: "หลอกโอนเงิน",
  IMPERSONATION: "แอบอ้างหน่วยงาน",
  INVESTMENT: "หลอกลงทุน",
  SAFE: "ปลอดภัย",
};
const WINDOW_LABELS = { day: "30 วันล่าสุด", week: "12 สัปดาห์ล่าสุด", month: "12 เดือนล่าสุด" };
const REFRESH_MS = 30000;

Chart.defaults.color = "#9a9ab5";
Chart.defaults.borderColor = "#2a2a40";
Chart.defaults.font.family = "Prompt, system-ui, sans-serif";

const charts = {};
let currentPeriod = "day";

const $ = (id) => document.getElementById(id);

function upsertChart(key, canvasId, config) {
  if (charts[key]) {
    charts[key].data = config.data;
    charts[key].update();
    return;
  }
  charts[key] = new Chart($(canvasId), config);
}

function renderKpis(totals) {
  $("k-total").textContent = totals.total.toLocaleString("th-TH");
  $("k-scams").textContent = totals.scams.toLocaleString("th-TH");
  $("k-high").textContent = totals.high_risk.toLocaleString("th-TH");
  $("k-rate").textContent = totals.total ? `${Math.round((totals.scams / totals.total) * 100)}%` : "-";
}

function renderCategory(rows) {
  upsertChart("category", "c-category", {
    type: "doughnut",
    data: {
      labels: rows.map((r) => CATEGORY_LABELS[r.category] || r.label),
      datasets: [{ data: rows.map((r) => r.count), backgroundColor: rows.map((r) => COLORS[r.category]), borderWidth: 0 }],
    },
    options: { maintainAspectRatio: false, plugins: { legend: { position: "right" } } },
  });
}

function renderOrgs(rows) {
  upsertChart("org", "c-org", {
    type: "bar",
    data: {
      labels: rows.map((r) => r.org),
      datasets: [{ label: "จำนวนครั้ง", data: rows.map((r) => r.count), backgroundColor: "#a45cff", borderRadius: 6 }],
    },
    options: { indexAxis: "y", maintainAspectRatio: false, plugins: { legend: { display: false } } },
  });
}

function renderTrend(rows) {
  upsertChart("trend", "c-trend", {
    type: "line",
    data: {
      labels: rows.map((r) => r.bucket),
      datasets: [
        { label: "พบกลโกง", data: rows.map((r) => r.scams), borderColor: "#ff4d6d", backgroundColor: "#ff4d6d33", fill: true, tension: 0.3 },
        { label: "ตรวจทั้งหมด", data: rows.map((r) => r.total), borderColor: "#2f5bff", tension: 0.3 },
      ],
    },
    options: { maintainAspectRatio: false, scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } },
  });
}

function renderEmerging(rows) {
  const list = $("emerging");
  list.replaceChildren();
  if (rows.length === 0) {
    const li = document.createElement("li");
    li.className = "muted";
    li.textContent = "ยังไม่พบลิงก์ที่ถูกรายงานซ้ำ";
    list.append(li);
    return;
  }
  for (const row of rows) {
    const li = document.createElement("li");
    li.textContent = `⚠ ${row.domain.replaceAll(".", "[.]")} — รายงาน ${row.count} ครั้ง`;
    list.append(li);
  }
}

function renderRecent(rows) {
  const body = $("recent");
  body.replaceChildren();
  for (const row of rows) {
    const tr = document.createElement("tr");
    const cells = [row.report_code, CATEGORY_LABELS[row.category] || row.category, `${row.risk}%`, row.impersonated_org || "-"];
    for (const value of cells) {
      const td = document.createElement("td");
      td.textContent = value;
      tr.append(td);
    }
    body.append(tr);
  }
}

async function load() {
  try {
    const body = await (await fetch(`/api/stats?period=${currentPeriod}`)).json();
    if (!body.success) throw new Error(body.error);
    const stats = body.data;
    $("window-label").textContent = `ข้อมูล ${WINDOW_LABELS[currentPeriod]} · อัปเดตอัตโนมัติทุก 30 วินาที`;
    renderKpis(stats.totals);
    renderCategory(stats.by_category);
    renderOrgs(stats.by_org);
    renderTrend(stats.trend);
    renderEmerging(stats.emerging_domains);
    renderRecent(stats.recent);
  } catch (err) {
    $("window-label").textContent = "โหลดข้อมูลไม่สำเร็จ";
  }
}

for (const button of document.querySelectorAll("#periods button")) {
  button.addEventListener("click", () => {
    currentPeriod = button.dataset.period;
    document.querySelectorAll("#periods button").forEach((b) => b.classList.toggle("selected", b === button));
    load();
  });
}

load();
setInterval(load, REFRESH_MS);
