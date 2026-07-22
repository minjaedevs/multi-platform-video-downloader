const form = document.querySelector("#downloadForm");
const jobsEl = document.querySelector("#jobs");
const jobCountEl = document.querySelector("#jobCount");
const downloadDirEl = document.querySelector("#downloadDir");
const urlInput = document.querySelector("#urlInput");
const qualitySelect = document.querySelector("#qualitySelect");
const outputDir = document.querySelector("#outputDir");
const useAppProfile = document.querySelector("#useAppProfile");
const authStatus = document.querySelector("#authStatus");
const urlStatus = document.querySelector("#urlStatus");
const serverInfo = document.querySelector("#serverInfo");
const setupSummary = document.querySelector("#setupSummary");
const setupItems = document.querySelector("#setupItems");
const platformChecks = document.querySelector("#platformChecks");

const params = new URLSearchParams(window.location.search);
const queryApiBase = params.get("api");
const queryApiToken = params.get("token");
if (queryApiBase) localStorage.setItem("VIDEOGET_API_BASE", queryApiBase);
if (queryApiToken) localStorage.setItem("VIDEOGET_API_TOKEN", queryApiToken);
const API_BASE = (queryApiBase || localStorage.getItem("VIDEOGET_API_BASE") || "").replace(/\/+$/, "");
const API_TOKEN = queryApiToken || localStorage.getItem("VIDEOGET_API_TOKEN") || "";

let activeSource = "youtube";
let urlCheckTimer = null;

function apiUrl(path) {
  return `${API_BASE}${path}`;
}

function apiFetch(path, options = {}) {
  const headers = { "ngrok-skip-browser-warning": "true", ...(options.headers || {}) };
  if (API_TOKEN) {
    headers["X-VideoGet-Token"] = API_TOKEN;
  }
  return fetch(apiUrl(path), { ...options, headers });
}

document.querySelectorAll(".source").forEach((button) => {
  button.addEventListener("click", () => {
    selectSource(button.dataset.source);
    analyzeUrl();
    authStatus.textContent = `Dùng Chrome profile riêng cho ${sourceLabel({ source: activeSource })}.`;
  });
});

urlInput.addEventListener("input", () => {
  clearTimeout(urlCheckTimer);
  urlCheckTimer = setTimeout(analyzeUrl, 450);
});

document.querySelector("#refreshBtn").addEventListener("click", async () => {
  await Promise.all([loadJobs(), loadSetupStatus()]);
});

document.querySelector("#checkSetupBtn").addEventListener("click", loadSetupStatus);

document.querySelector("#clearBtn").addEventListener("click", async () => {
  await apiFetch("/api/jobs/completed", { method: "DELETE" });
  await loadJobs();
});

document.querySelector("#openLoginBtn").addEventListener("click", async () => {
  const response = await apiFetch("/api/auth/open", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source: activeSource }),
  });
  const payload = await response.json().catch(() => ({}));
  authStatus.textContent = payload.message || payload.error || "Đã gửi lệnh mở Chrome.";
  setTimeout(loadSetupStatus, 1200);
});

document.querySelector("#checkLoginBtn").addEventListener("click", async () => {
  authStatus.textContent = "Đang kiểm tra link với Chrome profile...";
  const response = await apiFetch("/api/auth/check", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source: activeSource, url: urlInput.value.trim() || null }),
  });
  const payload = await response.json().catch(() => ({}));
  if (response.ok) {
    authStatus.textContent = `OK: ${payload.output.trim().split("\n").pop()}`;
  } else {
    authStatus.textContent = payload.output || payload.error || "Chưa kiểm tra được đăng nhập.";
  }
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const url = urlInput.value.trim();
  if (!url) return;

  const check = await analyzeUrl();
  if (check && !check.supported) {
    alert(check.message || "Nền tảng này chưa hỗ trợ.");
    return;
  }

  const response = await apiFetch("/api/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      url,
      source: activeSource,
      quality: qualitySelect.value,
      output_dir: outputDir.value.trim() || null,
      use_app_profile: useAppProfile.checked,
      cookies_file: null,
      use_browser_cookies: false,
    }),
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    alert(payload.error || "Không tạo được lượt tải.");
    return;
  }

  urlInput.value = "";
  await loadJobs();
});

async function cancelJob(id) {
  await apiFetch(`/api/jobs/${id}`, { method: "DELETE" });
  await loadJobs();
}

async function loadSetupStatus() {
  setupSummary.textContent = "Đang kiểm tra setup...";
  try {
    const response = await apiFetch("/api/setup/status");
    const status = await response.json();
    renderSetupStatus(status);
  } catch {
    setupSummary.textContent = "Không gọi được API setup.";
    setupItems.innerHTML = "";
    platformChecks.innerHTML = "";
  }
}

function renderSetupStatus(status) {
  const coreItems = [
    ["Python", status.python?.ok, status.python?.version || status.python?.path],
    ["yt-dlp", status.yt_dlp?.ok, status.yt_dlp?.version || status.yt_dlp?.message],
    ["ffmpeg", status.ffmpeg?.ok, status.ffmpeg?.version || status.ffmpeg?.message],
    ["Chrome", status.chrome?.ok, status.chrome?.message],
    ["Profile", status.profile?.ok, status.profile?.message],
  ];
  const failed = coreItems.filter(([, ok]) => !ok).length;
  const warnings = Object.values(status.platforms || {}).filter((item) => !item.ok).length;
  setupSummary.textContent = failed
    ? `Thiếu ${failed} thành phần bắt buộc.`
    : warnings
      ? `Setup chạy được, nhưng ${warnings} nền tảng chưa thấy cookie đăng nhập.`
      : "Setup ổn, đã thấy cookies cho các nền tảng chính.";

  setupItems.innerHTML = coreItems
    .map(([name, ok, detail]) => `
      <div class="setup-chip ${ok ? "ok" : "bad"}" title="${escapeHtml(detail || "")}">
        <span>${ok ? "✓" : "!"}</span>
        <strong>${escapeHtml(name)}</strong>
      </div>
    `)
    .join("");

  const labels = {
    youtube: "YouTube",
    tiktok: "TikTok",
    facebook: "Facebook",
    google_drive: "Drive",
  };
  platformChecks.innerHTML = Object.entries(status.platforms || {})
    .map(([source, info]) => `
      <button class="platform-chip ${info.ok ? "ok" : "warn"}" type="button" data-login-source="${source}" title="${escapeHtml(info.message)}">
        <span>${info.ok ? "✓" : "!"}</span>
        ${labels[source] || source}
      </button>
    `)
    .join("");

  document.querySelectorAll("[data-login-source]").forEach((button) => {
    button.addEventListener("click", async () => {
      selectSource(button.dataset.loginSource);
      document.querySelector(".advanced").open = true;
      document.querySelector("#openLoginBtn").focus();
    });
  });
}

function sourceLabel(job) {
  const labels = {
    youtube: "YouTube",
    tiktok: "TikTok",
    facebook: "Facebook",
    google_drive: "Google Drive",
    direct: "Link file",
    other: "Nguồn khác",
    auto: "Tự động",
  };
  return labels[job.source] || "Tự động";
}

async function analyzeUrl() {
  const url = urlInput.value.trim();
  if (!url) {
    setUrlStatus("Dán link để kiểm tra hỗ trợ trước khi tải.", "neutral");
    return null;
  }

  try {
    const response = await apiFetch("/api/check-url", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, source: activeSource }),
    });
    const payload = await response.json().catch(() => ({}));
    setUrlStatus(payload.message || "Không kiểm tra được link.", response.ok ? "ok" : "bad");

    if (response.ok && payload.source && payload.source !== activeSource) {
      selectSource(payload.source);
    }
    if (response.ok && payload.normalized_url && payload.normalized_url !== urlInput.value.trim()) {
      urlInput.value = payload.normalized_url;
    }
    return payload;
  } catch {
    setUrlStatus("Không gọi được server kiểm tra link.", "bad");
    return { supported: false, message: "Không gọi được server kiểm tra link." };
  }
}

function selectSource(source) {
  const button = document.querySelector(`.source[data-source="${source}"]`);
  if (!button) return;
  document.querySelectorAll(".source").forEach((item) => item.classList.remove("active"));
  button.classList.add("active");
  activeSource = source;
}

function setUrlStatus(message, tone) {
  urlStatus.textContent = message;
  urlStatus.classList.remove("ok", "bad");
  if (tone === "ok" || tone === "bad") {
    urlStatus.classList.add(tone);
  }
}

function statusLabel(status) {
  return {
    queued: "Đang chờ",
    downloading: "Đang tải",
    completed: "Hoàn tất",
    failed: "Lỗi",
    cancelled: "Đã hủy",
  }[status] || status;
}

function statusMeta(status, isNext) {
  if (status === "queued" && isNext) {
    return { label: "Sắp chạy", tone: "next" };
  }
  return {
    queued: { label: "Đang chờ", tone: "queued" },
    downloading: { label: "Đang chạy", tone: "running" },
    completed: { label: "Hoàn tất", tone: "completed" },
    failed: { label: "Lỗi", tone: "failed" },
    cancelled: { label: "Đã hủy", tone: "cancelled" },
  }[status] || { label: status, tone: "neutral" };
}

function fileName(job) {
  if (job.file_path) {
    return job.file_path.split(/[\\/]/).pop();
  }
  try {
    return new URL(job.url).hostname;
  } catch {
    return job.url;
  }
}

function renderJobs(jobs) {
  jobCountEl.textContent = jobs.length;

  if (!jobs.length) {
    jobsEl.innerHTML = `<div class="empty">Chưa có lượt tải nào.</div>`;
    return;
  }

  const nextQueuedId = jobs
    .slice()
    .reverse()
    .find((job) => job.status === "queued")?.id;

  jobsEl.innerHTML = jobs
    .map((job, index) => {
      const progress = Math.max(0, Math.min(100, Number(job.progress || 0)));
      const canCancel = ["queued", "downloading"].includes(job.status);
      const isNext = job.id === nextQueuedId;
      const meta = statusMeta(job.status, isNext);
      const action = canCancel
        ? `<button class="icon-btn cancel" title="Hủy tải" onclick="cancelJob('${job.id}')">×</button>`
        : `<button class="icon-btn done" title="${escapeHtml(meta.label)}">✓</button>`;
      const logDetails = job.status === "failed" && job.log_tail?.length
        ? `<details class="job-log"><summary>Chi tiết lỗi</summary><pre>${escapeHtml(job.log_tail.join("\n"))}</pre></details>`
        : "";

      return `
        <article class="job ${job.status} ${isNext ? "next" : ""}">
          <div class="thumb">
            <span>${sourceLabel(job)}</span>
            <small>#${jobs.length - index}</small>
          </div>
          <div class="job-main">
            <div class="job-title-row">
              <div class="job-title">${escapeHtml(fileName(job))}</div>
              <span class="status-badge ${meta.tone}">${escapeHtml(meta.label)}</span>
            </div>
            <div class="meta">Video ${escapeHtml(job.quality)} · ${escapeHtml(job.size || job.message || "Đang xác định dung lượng")}</div>
            <div class="bar"><div class="fill" style="width:${progress}%"></div></div>
            ${logDetails}
          </div>
          <div class="job-status">
            <strong>${statusLabel(job.status)}</strong>
            <span>${Math.round(progress)}% ${job.speed ? "· " + escapeHtml(job.speed) : ""}</span>
          </div>
          ${action}
        </article>
      `;
    })
    .join("");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function loadConfig() {
  const response = await apiFetch("/api/config");
  const config = await response.json();
  downloadDirEl.textContent = config.download_dir;
  if (config.public_url) {
    serverInfo.textContent = API_BASE || config.public_url;
    serverInfo.title = API_BASE || config.public_url;
  }
}

async function loadJobs() {
  const response = await apiFetch("/api/jobs");
  const payload = await response.json();
  renderJobs(payload.jobs || []);
}

loadConfig();
loadJobs();
loadSetupStatus();
setInterval(loadJobs, 1500);
