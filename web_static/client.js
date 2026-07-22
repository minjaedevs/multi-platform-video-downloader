const form = document.querySelector("#downloadForm");
const jobsEl = document.querySelector("#jobs");
const jobCountEl = document.querySelector("#jobCount");
const urlInput = document.querySelector("#urlInput");
const qualitySelect = document.querySelector("#qualitySelect");
const outputDirInput = document.querySelector("#outputDirInput");
const urlStatus = document.querySelector("#urlStatus");
const serverInfo = document.querySelector("#serverInfo");
const downloadPath = document.querySelector("#downloadPath");
const copyPathBtn = document.querySelector("#copyPathBtn");

const params = new URLSearchParams(window.location.search);
const queryApiBase = params.get("api");
const queryApiToken = params.get("token");
if (queryApiBase) localStorage.setItem("VIDEOGET_API_BASE", queryApiBase);
if (queryApiToken) localStorage.setItem("VIDEOGET_API_TOKEN", queryApiToken);
const API_BASE = (queryApiBase || localStorage.getItem("VIDEOGET_API_BASE") || "").replace(/\/+$/, "");
const API_TOKEN = queryApiToken || localStorage.getItem("VIDEOGET_API_TOKEN") || "";
const CLIENT_ID_KEY = "VIDEOGET_CLIENT_ID";
const CLIENT_ID = localStorage.getItem(CLIENT_ID_KEY) || (
  crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`
);
localStorage.setItem(CLIENT_ID_KEY, CLIENT_ID);

let activeSource = "youtube";
let urlCheckTimer = null;
let downloadDirValue = "";

function apiUrl(path) {
  return `${API_BASE}${path}`;
}

function apiFetch(path, options = {}) {
  const headers = {
    "ngrok-skip-browser-warning": "true",
    "X-VideoGet-Client": CLIENT_ID,
    ...(options.headers || {}),
  };
  if (API_TOKEN) {
    headers["X-VideoGet-Token"] = API_TOKEN;
  }
  return fetch(apiUrl(path), { ...options, headers });
}

document.querySelectorAll(".source").forEach((button) => {
  button.addEventListener("click", () => {
    selectSource(button.dataset.source);
    analyzeUrl();
  });
});

urlInput.addEventListener("input", () => {
  clearTimeout(urlCheckTimer);
  urlCheckTimer = setTimeout(analyzeUrl, 450);
});

document.querySelector("#refreshBtn").addEventListener("click", loadJobs);
copyPathBtn?.addEventListener("click", copyDownloadPath);
outputDirInput?.addEventListener("input", () => {
  if (!outputDirInput.value.trim()) return;
  setDownloadPath(outputDirInput.value.trim());
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
      output_dir: outputDirInput.value.trim() || null,
      use_app_profile: true,
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
  setUrlStatus("Đã gửi lượt tải. Theo dõi trạng thái ở danh sách bên cạnh.", "ok");
  await loadJobs();
});

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
    setUrlStatus("Không gọi được API xử lý. Hãy kiểm tra link API hoặc token.", "bad");
    return { supported: false, message: "Không gọi được API xử lý." };
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
    return new URL(job.original_url || job.url).hostname;
  } catch {
    return job.original_url || job.url;
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
      const isNext = job.id === nextQueuedId;
      const meta = statusMeta(job.status, isNext);
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
          </div>
          <div class="job-status">
            <strong>${statusLabel(job.status)}</strong>
            <span>${Math.round(progress)}% ${job.speed ? "· " + escapeHtml(job.speed) : ""}</span>
          </div>
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
  try {
    const response = await apiFetch("/api/config");
    const config = await response.json();
    serverInfo.textContent = API_BASE || config.public_url;
    serverInfo.title = API_BASE || config.public_url;
    const configuredDir = outputDirInput.value.trim() || config.download_dir || "";
    if (outputDirInput && !outputDirInput.placeholder.includes(config.download_dir || "")) {
      outputDirInput.placeholder = `Mặc định: ${config.download_dir || ""}`;
    }
    setDownloadPath(configuredDir);
  } catch {
    serverInfo.textContent = "API chưa kết nối";
    downloadDirValue = "";
    if (downloadPath) {
      downloadPath.textContent = "Video lưu tại: chưa kết nối API";
      downloadPath.title = "Kiểm tra kết nối API";
    }
    if (copyPathBtn) {
      copyPathBtn.disabled = true;
      copyPathBtn.textContent = "Copy";
    }
  }
}

function setDownloadPath(path) {
  downloadDirValue = path || "";
  if (downloadPath) {
    downloadPath.textContent = `Video lưu tại: ${downloadDirValue || "chưa xác định"}`;
    downloadPath.title = downloadDirValue || "Đường dẫn thư mục chứa video tải về";
  }
  if (copyPathBtn) {
    copyPathBtn.disabled = !downloadDirValue;
    copyPathBtn.textContent = "Copy";
  }
}

async function copyDownloadPath() {
  if (!downloadDirValue) return;
  try {
    await navigator.clipboard.writeText(downloadDirValue);
    copyPathBtn.textContent = "Đã copy";
    setTimeout(() => {
      copyPathBtn.textContent = "Copy";
    }, 1400);
  } catch {
    window.prompt("Copy đường dẫn thư mục video:", downloadDirValue);
  }
}

async function loadJobs() {
  try {
    const response = await apiFetch("/api/jobs");
    const payload = await response.json();
    renderJobs(payload.jobs || []);
  } catch {
    jobsEl.innerHTML = `<div class="empty">Không gọi được API. Kiểm tra URL API hoặc token.</div>`;
  }
}

loadConfig();
loadJobs();
setInterval(loadJobs, 1500);
