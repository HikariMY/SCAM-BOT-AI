const MAX_IMAGE_SIDE = 2048;
const JPEG_QUALITY = 0.85;
const FONT_KEY = "scam-alert-large-font";

const $ = (id) => document.getElementById(id);

// ---------- storage helpers (may be unavailable in private mode) ----------
function readSetting(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}
function writeSetting(key, value) {
  try { localStorage.setItem(key, value); } catch { /* ignore */ }
}

// ---------- font size ----------
function applyFontSize(large) {
  document.documentElement.classList.toggle("large", large);
  $("font-toggle").setAttribute("aria-pressed", String(large));
  $("font-toggle").textContent = large ? "ก-" : "ก+";
}
$("font-toggle").addEventListener("click", () => {
  const large = !document.documentElement.classList.contains("large");
  applyFontSize(large);
  writeSetting(FONT_KEY, large ? "1" : "0");
});
applyFontSize(readSetting(FONT_KEY) === "1");

// ---------- view states ----------
function show(state, message) {
  $("loading").hidden = state !== "loading";
  $("error").hidden = state !== "error";
  $("result").hidden = state !== "result";
  $("input-card").hidden = state === "result";
  if (state === "loading") $("loading-text").textContent = message;
  if (state === "error") $("error").textContent = message;
  if (state !== "loading") window.scrollTo({ top: 0, behavior: "smooth" });
}

function addDetail(list, label, values) {
  const items = Array.isArray(values) ? values : [values];
  if (!items.length || !items[0]) return;
  const dt = document.createElement("dt");
  dt.textContent = label;
  const dd = document.createElement("dd");
  dd.textContent = items.join(", ");
  list.append(dt, dd);
}

function renderResult(data) {
  const v = data.verdict;
  $("result-head").className = `result-head ${v.tier}`;
  $("headline").textContent = v.headline;
  $("risk").textContent = `ความเสี่ยง ${data.risk}%`;
  $("explanation").textContent = v.explanation;

  const donts = $("donts");
  donts.replaceChildren();
  donts.classList.toggle("scam", v.tier !== "safe");
  for (const item of v.donts) {
    const li = document.createElement("li");
    li.textContent = `❌ ${item}`;
    donts.append(li);
  }
  $("tip").textContent = v.tip;

  $("read-text-block").hidden = !data.extracted_text;
  $("read-text").textContent = data.extracted_text || "";

  const details = $("details");
  details.replaceChildren();
  const e = data.entities;
  addDetail(details, "ประเภท", `${data.category_label} (${data.category})`);
  addDetail(details, "ลิงก์ที่พบ", data.domains.map((d) => d.host.replaceAll(".", "[.]")));
  addDetail(details, "เบอร์โทร", e.phones);
  addDetail(details, "เลขบัญชี", e.accounts);
  addDetail(details, "จำนวนเงิน", e.amounts);
  addDetail(details, "จุดน่าสงสัย", data.red_flags);
  addDetail(details, "สรุป", data.summary);
  addDetail(details, "คำแนะนำ", data.advice);
  addDetail(details, "Report ID", data.report_code);
  show("result");
}

async function post(url, payload, loadingMessage) {
  show("loading", loadingMessage);
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await response.json();
    if (!body.success) throw new Error(body.error || "ตรวจไม่สำเร็จ ลองใหม่อีกครั้ง");
    renderResult(body.data);
  } catch (err) {
    const offline = err instanceof TypeError;
    show("error", offline ? "เชื่อมต่ออินเทอร์เน็ตไม่ได้ ลองใหม่อีกครั้ง" : err.message);
    $("input-card").hidden = false;
  }
}

// ---------- text ----------
function checkText() {
  const text = $("message").value.trim();
  if (!text) {
    show("error", "ยังไม่มีข้อความ กรุณาวางหรือพิมพ์ข้อความก่อน");
    $("input-card").hidden = false;
    $("message").focus();
    return;
  }
  post("/api/analyze", { text }, "กำลังตรวจ รอสักครู่...");
}
$("check-button").addEventListener("click", checkText);

$("paste-button").addEventListener("click", async () => {
  try {
    const text = (await navigator.clipboard.readText()).trim();
    if (!text) throw new Error("empty");
    $("message").value = text;
    checkText();
  } catch {
    // Clipboard access denied or empty: guide the user to paste manually.
    $("message").focus();
    show("error", "กดค้างที่ช่องด้านล่าง แล้วเลือก \"วาง\" จากนั้นกด ตรวจเลย");
    $("input-card").hidden = false;
  }
});

// ---------- image ----------
function loadImage(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => { URL.revokeObjectURL(url); resolve(img); };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("อ่านรูปไม่ได้ กรุณาเลือกรูปใหม่")); };
    img.src = url;
  });
}

async function shrinkImage(file) {
  // Phone photos are large; shrink before upload to save data and time.
  const img = await loadImage(file);
  const scale = Math.min(1, MAX_IMAGE_SIDE / Math.max(img.width, img.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(img.width * scale);
  canvas.height = Math.round(img.height * scale);
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL("image/jpeg", JPEG_QUALITY);
}

$("image-input").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  event.target.value = "";
  if (!file) return;
  try {
    show("loading", "กำลังอ่านรูป...");
    const image = await shrinkImage(file);
    await post("/api/analyze-image", { image }, "กำลังอ่านข้อความในรูปและตรวจสอบ...");
  } catch (err) {
    show("error", err.message);
    $("input-card").hidden = false;
  }
});

// ---------- again ----------
$("again-button").addEventListener("click", () => {
  $("message").value = "";
  show("idle");
  $("input-card").hidden = false;
});

// ---------- install as app ----------
const isStandalone = window.matchMedia("(display-mode: standalone)").matches || navigator.standalone;
const isIos = /iphone|ipad|ipod/i.test(navigator.userAgent);
let installPrompt = null;

window.addEventListener("beforeinstallprompt", (event) => {
  event.preventDefault();
  installPrompt = event;
  $("install-card").hidden = false;
  $("install-button").hidden = false;
});
$("install-button").addEventListener("click", async () => {
  if (!installPrompt) return;
  installPrompt.prompt();
  await installPrompt.userChoice;
  installPrompt = null;
  $("install-card").hidden = true;
});
if (isIos && !isStandalone) {
  $("install-card").hidden = false;
  $("ios-hint").hidden = false;
}

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => { /* offline support is optional */ });
}
