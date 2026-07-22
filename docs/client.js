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
const chooseFolderBtn = document.querySelector("#chooseFolderBtn");

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
let downloadDirHandle = null;
const savingJobs = new Set();
const savedJobs = new Set();

function apiUrl(path) {
  return `${API_BASE}${path}`;
}

function contentDispositionFileName(headerValue) {
  const value = String(headerValue || "");
  const utf8Match = value.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match) {
    try {
      return decodeURIComponent(utf8Match[1]);
    } catch {
      return utf8Match[1];
    }
  }
  const plainMatch = value.match(/filename="?([^";]+)"?/i);
  return plainMatch ? plainMatch[1] : "";
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

async function chooseDownloadFolder() {
  if (!window.showDirectoryPicker) {
    alert("Trình duyệt chưa hỗ trợ chọn folder trực tiếp. Hãy dùng Chrome/Edge bản mới, hoặc bấm 'Tai file' khi job hoàn tất.");
    return;
  }
  downloadDirHandle = await window.showDirectoryPicker({ mode: "readwrite" });
  localStorage.setItem("VIDEOGET_CLIENT_DOWNLOAD_DIR_NAME", downloadDirHandle.name);
  setDownloadPath(downloadDirHandle.name);
  await loadJobs();
}

async function saveCompletedJobToUserFolder(job) {
  if (!downloadDirHandle || savingJobs.has(job.id) || savedJobs.has(job.id)) return;
  savingJobs.add(job.id);
  setUrlStatus(`Đang lưu file về folder ${downloadDirHandle.name}...`, "ok");
  try {
    const response = await apiFetch(`/api/jobs/${encodeURIComponent(job.id)}/file`);
    if (!response.ok) throw new Error(`Download failed: ${response.status}`);

    const serverName = contentDispositionFileName(response.headers.get("Content-Disposition")) || fileName(job) || `${job.id}.mp4`;
    const safeName = serverName.replace(/[<>:"/\\|?*\u0000-\u001f]/g, "_");
    await writeResponseToFolder(response, safeName);

    savedJobs.add(job.id);
    setUrlStatus(`Đã lưu file vào folder ${downloadDirHandle.name}.`, "ok");
    await apiFetch(`/api/jobs/${encodeURIComponent(job.id)}?remove=1`, { method: "DELETE" });
    await loadJobs();
  } catch (error) {
    console.error(error);
    setUrlStatus("Không tự lưu được file. Job vẫn giữ lại, bấm 'Tai file' để thử lại.", "bad");
    alert("Không tự lưu được file vào folder đã chọn. Hãy bấm 'Tai file' để tải thủ công.");
  } finally {
    savingJobs.delete(job.id);
  }
}

async function downloadJobManually(jobId, fallbackName = "") {
  const response = await apiFetch(`/api/jobs/${encodeURIComponent(jobId)}/file`);
  if (!response.ok) {
    alert("Không tải được file. Hãy làm mới trạng thái hoặc kiểm tra BE/ngrok.");
    return;
  }

  const serverName = contentDispositionFileName(response.headers.get("Content-Disposition")) || fallbackName || `${jobId}.mp4`;
  const safeName = serverName.replace(/[<>:"/\\|?*\u0000-\u001f]/g, "_");

  if (downloadDirHandle) {
    setUrlStatus(`Đang lưu file về folder ${downloadDirHandle.name}...`, "ok");
    await writeResponseToFolder(response, safeName);
    setUrlStatus(`Đã lưu file vào folder ${downloadDirHandle.name}.`, "ok");
  } else {
    const blob = await response.blob();
    const blobUrl = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = blobUrl;
    anchor.download = safeName;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(blobUrl), 60_000);
  }

  savedJobs.add(jobId);
  await apiFetch(`/api/jobs/${encodeURIComponent(jobId)}?remove=1`, { method: "DELETE" }).catch(() => {});
  await loadJobs();
}

async function writeResponseToFolder(response, safeName) {
  const expectedBytes = Number(response.headers.get("Content-Length") || 0);
  const fileHandle = await downloadDirHandle.getFileHandle(safeName, { create: true });
  const writable = await fileHandle.createWritable();
  let writtenBytes = 0;

  try {
    if (response.body?.getReader) {
      const reader = response.body.getReader();
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        writtenBytes += value.byteLength;
        await writable.write(value);
      }
    } else {
      const blob = await response.blob();
      writtenBytes = blob.size;
      await writable.write(blob);
    }
    await writable.close();
  } catch (error) {
    await writable.abort().catch(() => {});
    throw error;
  }

  if (expectedBytes && writtenBytes !== expectedBytes) {
    throw new Error(`Incomplete file: wrote ${writtenBytes}/${expectedBytes} bytes`);
  }
  return writtenBytes;
}

function pullCompletedJobs(jobs) {
  if (!downloadDirHandle) return;
  jobs
    .filter((job) => effectiveStatus(job) === "completed")
    .forEach((job) => {
      saveCompletedJobToUserFolder(job);
    });
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
chooseFolderBtn?.addEventListener("click", chooseDownloadFolder);
jobsEl?.addEventListener("click", (event) => {
  const link = event.target.closest("[data-download-job]");
  if (!link) return;
  event.preventDefault();
  const jobId = link.dataset.downloadJob;
  downloadJobManually(jobId, link.dataset.fileName || "").catch((error) => {
    console.error(error);
    alert("Không tải được file qua ngrok. Hãy kiểm tra API token hoặc thử lại.");
  });
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
      output_dir: null,
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
    converting: "Đang convert",
    optimizing: "Đang tối ưu",
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
    converting: { label: "Đang convert", tone: "converting" },
    optimizing: { label: "Đang tối ưu", tone: "optimizing" },
    completed: { label: "Hoàn tất", tone: "completed" },
    failed: { label: "Lỗi", tone: "failed" },
    cancelled: { label: "Đã hủy", tone: "cancelled" },
  }[status] || { label: status, tone: "neutral" };
}

function effectiveStatus(job) {
  const message = String(job.message || "").toLowerCase();
  if (job.status === "downloading" && (message.includes("converting") || message.includes("convert"))) {
    return "converting";
  }
  if (job.status === "downloading" && (message.includes("optimizing") || message.includes("bento4") || message.includes("tối ưu"))) {
    return "optimizing";
  }
  return job.status;
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
      const displayStatus = effectiveStatus(job);
      const meta = statusMeta(displayStatus, isNext);
      const currentFileName = fileName(job);
      const fileAction = displayStatus === "completed"
        ? `<button class="job-download" type="button" data-download-job="${escapeHtml(job.id)}" data-file-name="${escapeHtml(currentFileName)}">Tai file</button>`
        : "";
      return `
        <article class="job ${displayStatus} ${isNext ? "next" : ""}">
          <div class="thumb">
            <span>${sourceLabel(job)}</span>
            <small>#${jobs.length - index}</small>
          </div>
          <div class="job-main">
            <div class="job-title-row">
              <div class="job-title">${escapeHtml(currentFileName)}</div>
              <span class="status-badge ${meta.tone}">${escapeHtml(meta.label)}</span>
            </div>
            <div class="meta">Video ${escapeHtml(job.quality)} · ${escapeHtml(job.size || job.message || "Đang xác định dung lượng")}</div>
            <div class="bar"><div class="fill" style="width:${progress}%"></div></div>
          </div>
          <div class="job-status">
            <strong>${statusLabel(displayStatus)}</strong>
            <span>${Math.round(progress)}% ${job.speed ? "· " + escapeHtml(job.speed) : ""}</span>
            ${fileAction}
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
    const savedDirName = localStorage.getItem("VIDEOGET_CLIENT_DOWNLOAD_DIR_NAME") || "";
    const configuredDir = downloadDirHandle?.name || (savedDirName ? `${savedDirName} (cần chọn lại)` : "");
    if (outputDirInput) {
      outputDirInput.placeholder = window.showDirectoryPicker ? "Chọn folder trên máy bạn" : "Trình duyệt không hỗ trợ chọn folder";
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
  if (outputDirInput) {
    outputDirInput.value = downloadDirValue;
  }
  if (downloadPath) {
    downloadPath.textContent = `Video lưu tại: ${downloadDirValue || "chưa chọn folder"}`;
    downloadPath.title = downloadDirValue || "Folder trên máy user để nhận video";
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
    const jobs = payload.jobs || [];
    renderJobs(jobs);
    pullCompletedJobs(jobs);
  } catch {
    jobsEl.innerHTML = `<div class="empty">Không gọi được API. Kiểm tra URL API hoặc token.</div>`;
  }
}

loadConfig();
loadJobs();
setInterval(loadJobs, 1500);
