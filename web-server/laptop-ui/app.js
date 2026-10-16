// SDV Application Deployment Manager Frontend Logic

const API_BASE_URL = (window.DEPLOYER_CONFIG?.apiBaseUrl || "http://localhost:18443").replace(/\/+$/, "");

function apiUrl(path) {
    return `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

if (window.location.search) {
    window.history.replaceState({}, document.title, window.location.pathname + window.location.hash);
}

let selectedFiles = [];
let activeLogAppId = null;
let activeView = "environment";
let liveLogsTimer = null;
let logsRequestInFlight = false;
let logsFirstLoad = true;

document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".view-nav-item").forEach((button) => {
        button.addEventListener("click", () => showView(button.dataset.view));
    });

    document.getElementById("getEnvironmentBtn").addEventListener("click", fetchEnvironment);
    document.getElementById("refreshAppsBtn").addEventListener("click", () => fetchApplications());

    document.getElementById("logAppSelect").addEventListener("change", (event) => {
        stopLogPolling();
        activeLogAppId = event.target.value;
        if (activeLogAppId) {
            startLogPolling(activeLogAppId);
        } else {
            document.getElementById("logContent").textContent = "Select an application to load its logs.";
            document.getElementById("logsSyncState").textContent = "Choose an application to follow its live logs.";
        }
    });

    setupUploadEvents();
    showView("environment");
});

function showView(viewName) {
    if (activeView === "logs" && viewName !== "logs") stopLogPolling();
    activeView = viewName;
    document.querySelectorAll(".view-nav-item").forEach((button) => {
        if (button.dataset.view === viewName) {
            button.setAttribute("aria-current", "page");
        } else {
            button.removeAttribute("aria-current");
        }
    });
    document.querySelectorAll(".view-panel").forEach((panel) => {
        panel.hidden = panel.dataset.panel !== viewName;
    });
    window.scrollTo(0, 0);

    if (viewName === "applications") fetchApplications();
    if (viewName === "logs") populateLogApplications();
}

async function populateLogApplications() {
    const select = document.getElementById("logAppSelect");
    const logContent = document.getElementById("logContent");
    try {
        const response = await apiFetch("/api/v1/apps");
        if (!response.ok) throw new Error("Could not load deployed applications");
        const result = await response.json();
        const applications = result.data || [];
        select.replaceChildren(new Option("Choose an application", ""));
        applications.forEach((app) => {
            select.add(new Option(`${app.name || app.app_id} (v${app.active_version})`, app.app_id));
        });
        const selectedAppExists = applications.some((app) => app.app_id === activeLogAppId);
        if (activeLogAppId && selectedAppExists) {
            select.value = activeLogAppId;
            startLogPolling(activeLogAppId);
        } else {
            stopLogPolling();
            activeLogAppId = "";
            logContent.textContent = applications.length
                ? "Choose an application to load its logs."
                : "No deployed applications are available yet.";
            select.value = "";
            document.getElementById("logsSyncState").textContent = applications.length
                ? "Choose an application to follow its live logs."
                : "No application logs are available yet.";
        }
    } catch (error) {
        logContent.textContent = error.message;
    }
}

function apiFetch(url, options = {}) {
    return fetch(apiUrl(url), options);
}

// ----------------- Environment Detection -----------------
async function fetchEnvironment() {
    const badge = document.getElementById("envTimestamp");
    const button = document.getElementById("getEnvironmentBtn");
    const errorMessage = document.getElementById("environmentError");
    resetEnvironmentValues();
    button.disabled = true;
    button.textContent = "Checking…";
    badge.textContent = "Fetching from target";
    badge.className = "badge badge-info";
    errorMessage.hidden = true;
    try {
        const res = await apiFetch("/api/v1/environment");
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = await res.json();
        const data = json.data;

        document.getElementById("envArch").textContent = data.system.architecture || "Unknown";
        document.getElementById("envOs").textContent = data.system.os_release || data.system.os;
        document.getElementById("envKernel").textContent = data.system.kernel;
        document.getElementById("envGlibc").textContent = data.toolchain.glibc_version;
        document.getElementById("envGxx").textContent = data.toolchain.gxx_version;
        document.getElementById("envPython").textContent = `Python ${data.toolchain.python_version}`;

        const kuksaEl = document.getElementById("envKuksa");
        if (data.middleware.kuksa_databroker.running) {
            kuksaEl.textContent = "RUNNING";
            kuksaEl.className = "badge badge-success";
        } else {
            kuksaEl.textContent = "NOT RUNNING";
            kuksaEl.className = "badge badge-warning";
        }

        const lolaEl = document.getElementById("envLola");
        const lolaStatus = data.middleware.score_mw_com_shm;
        const shmCount = (lolaStatus.active_lola_segments || []).length;
        if (shmCount > 0) {
            lolaEl.textContent = `READY · ${shmCount} segments`;
            lolaEl.className = "badge badge-success";
        } else if (!lolaStatus.dev_shm_mounted) {
            lolaEl.textContent = "SHARED MEMORY UNAVAILABLE";
            lolaEl.className = "badge badge-warning";
        } else {
            lolaEl.textContent = "NO ACTIVE SEGMENTS";
            lolaEl.className = "badge badge-neutral";
        }

        const supEl = document.getElementById("envSupervisor");
        supEl.textContent = data.middleware.systemd_available.supervision_mode.toUpperCase();
        supEl.className = "badge badge-info";

        badge.textContent = `Updated ${new Date().toLocaleTimeString()}`;
        badge.className = "badge badge-success";
    } catch (err) {
        resetEnvironmentValues();
        badge.textContent = "Unavailable";
        badge.className = "badge badge-error";
        errorMessage.textContent = `Could not fetch target environment: ${err.message}. Check the Pi API connection and try again.`;
        errorMessage.hidden = false;
    } finally {
        button.disabled = false;
        button.textContent = "Get info";
    }
}

function resetEnvironmentValues() {
    ["envArch", "envOs", "envKernel", "envGlibc", "envGxx", "envPython"].forEach((id) => {
        document.getElementById(id).textContent = "--";
    });
    ["envKuksa", "envLola", "envSupervisor"].forEach((id) => {
        const badge = document.getElementById(id);
        badge.textContent = "--";
        badge.className = "badge badge-neutral";
    });
}

// ----------------- Upload & Benchmark Handling -----------------
function setupUploadEvents() {
    const dropZone = document.getElementById("dropZone");
    const fileInput = document.getElementById("fileInput");
    const browseBtn = document.getElementById("browseBtn");
    const uploadBtn = document.getElementById("uploadBtn");
    const fileInfo = document.getElementById("selectedFileInfo");
    const fileName = document.getElementById("selectedFileName");
    const fileList = document.getElementById("selectedFileList");
    const fileSize = document.getElementById("selectedFileSize");

    browseBtn.addEventListener("click", () => fileInput.click());
    dropZone.addEventListener("click", (e) => {
        if (!e.target.closest("button, input, .selected-file-info")) {
            fileInput.click();
        }
    });

    fileInput.addEventListener("change", (e) => {
        if (e.target.files.length > 0) {
            handleSelectedFiles(Array.from(e.target.files));
        }
    });

    dropZone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropZone.classList.add("dragover");
    });

    dropZone.addEventListener("dragleave", () => {
        dropZone.classList.remove("dragover");
    });

    dropZone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropZone.classList.remove("dragover");
        if (e.dataTransfer.files.length > 0) {
            handleSelectedFiles(Array.from(e.dataTransfer.files));
        }
    });

    function handleSelectedFiles(files) {
        if (uploadBtn.disabled) return;
        const validFiles = [];
        const rejectedFiles = [];
        files.forEach((file) => {
            if (!file.name.endsWith(".tar.gz") && !file.name.endsWith(".tgz")) {
                rejectedFiles.push(`${file.name}: unsupported format`);
            } else if (file.size === 0 || file.size > 100 * 1024 * 1024) {
                rejectedFiles.push(`${file.name}: empty or larger than 100 MB`);
            } else {
                validFiles.push(file);
            }
        });

        selectedFiles = validFiles;
        if (validFiles.length === 0) {
            fileInfo.style.display = "none";
            fileInput.value = "";
            setUploadFeedback(rejectedFiles.join(". ") || "Choose one or more .tar.gz or .tgz bundles.", "error");
            return;
        }

        fileName.textContent = `${validFiles.length} package${validFiles.length === 1 ? "" : "s"} selected`;
        fileList.replaceChildren(...validFiles.map((file) => {
            const item = document.createElement("li");
            item.textContent = `${file.name} (${(file.size / (1024 * 1024)).toFixed(2)} MB)`;
            return item;
        }));
        const totalSize = validFiles.reduce((total, file) => total + file.size, 0);
        fileSize.textContent = `${(totalSize / (1024 * 1024)).toFixed(2)} MB total`;
        fileInfo.style.display = "flex";
        uploadBtn.disabled = false;
        uploadBtn.textContent = `Validate & Deploy ${validFiles.length}`;
        const selectionMessage = `${validFiles.length} package${validFiles.length === 1 ? "" : "s"} ready. Each is validated and deployed separately.`;
        setUploadFeedback(rejectedFiles.length ? `${selectionMessage} Skipped: ${rejectedFiles.join("; ")}` : selectionMessage, rejectedFiles.length ? "error" : "info");
    }

    uploadBtn.addEventListener("click", async () => {
        if (selectedFiles.length === 0) return;
        await executeUploadAndValidation(selectedFiles);
    });
}

async function executeUploadAndValidation(files) {
    const benchmarkPanel = document.getElementById("benchmarkPanel");
    const errorEl = document.getElementById("benchmarkError");
    const successEl = document.getElementById("benchmarkSuccess");
    const uploadBtn = document.getElementById("uploadBtn");
    const browseBtn = document.getElementById("browseBtn");
    const fileInput = document.getElementById("fileInput");
    const fileInfo = document.getElementById("selectedFileInfo");
    const packageQueue = Array.isArray(files) ? files : [files];
    const deployed = [];
    const failed = [];

    benchmarkPanel.style.display = "block";
    errorEl.style.display = "none";
    successEl.style.display = "none";
    uploadBtn.disabled = true;
    uploadBtn.textContent = `Deploying 0/${packageQueue.length}…`;
    browseBtn.disabled = true;
    fileInput.disabled = true;
    setUploadFeedback(`Preparing ${packageQueue.length} application package${packageQueue.length === 1 ? "" : "s"}…`, "info");

    try {
        for (const [index, file] of packageQueue.entries()) {
            uploadBtn.textContent = `Deploying ${index + 1}/${packageQueue.length}…`;
            setUploadFeedback(`Validating ${index + 1} of ${packageQueue.length}: ${file.name}`, "info");
            errorEl.style.display = "none";
            successEl.style.display = "none";

            for (let stepIndex = 1; stepIndex <= 5; stepIndex++) {
                const step = document.getElementById(`step${stepIndex}`);
                step.className = "benchmark-step";
                step.querySelector(".step-status").textContent = "Running";
                const desc = step.querySelector(".step-desc");
                desc.dataset.default ??= desc.textContent;
                desc.textContent = desc.dataset.default;
            }

            const formData = new FormData();
            formData.append("package", file);

            try {
                const response = await apiFetch("/api/v1/apps/upload", { method: "POST", body: formData });
                const result = await response.json();
                const benchmarkResults = result.benchmark_results || result.benchmarks;
                if (benchmarkResults) updateBenchmarkUI(benchmarkResults);
                if (!response.ok || !result.success) {
                    const message = result.error || (benchmarkResults?.errors || []).join("; ") || "Validation failed";
                    failed.push(`${file.name}: ${message}`);
                } else {
                    deployed.push(`${result.app?.name || result.app?.app_id || file.name} v${result.app?.active_version || ""}`);
                }
            } catch (error) {
                failed.push(`${file.name}: ${error.message}`);
            }
        }

        if (deployed.length > 0) {
            successEl.textContent = `Deployed ${deployed.length} of ${packageQueue.length}: ${deployed.join(", ")}`;
            successEl.style.display = "block";
            fetchApplications();
        }
        if (failed.length > 0) {
            errorEl.textContent = `Failed ${failed.length} of ${packageQueue.length}: ${failed.join("; ")}`;
            errorEl.style.display = "block";
        }

        selectedFiles = failed.length ? packageQueue.filter((file) => failed.some((item) => item.startsWith(`${file.name}:`))) : [];
        if (selectedFiles.length === 0) {
            fileInput.value = "";
            fileInfo.style.display = "none";
            document.getElementById("selectedFileList").replaceChildren();
            setUploadFeedback(`Deployment finished: ${deployed.length} of ${packageQueue.length} succeeded.`, failed.length ? "error" : "success");
        } else {
            renderSelectedFiles(selectedFiles);
            setUploadFeedback(`${deployed.length} deployed; ${failed.length} failed. Failed packages remain selected for retry.`, "error");
        }
    } finally {
        uploadBtn.disabled = false;
        uploadBtn.textContent = `Validate & Deploy ${selectedFiles.length || packageQueue.length}`;
        browseBtn.disabled = false;
        fileInput.disabled = false;
    }
}

function renderSelectedFiles(files) {
    document.getElementById("selectedFileName").textContent = `${files.length} package${files.length === 1 ? "" : "s"} selected`;
    const list = document.getElementById("selectedFileList");
    list.replaceChildren(...files.map((file) => {
        const item = document.createElement("li");
        item.textContent = `${file.name} (${(file.size / (1024 * 1024)).toFixed(2)} MB)`;
        return item;
    }));
    const totalSize = files.reduce((total, file) => total + file.size, 0);
    document.getElementById("selectedFileSize").textContent = `${(totalSize / (1024 * 1024)).toFixed(2)} MB total`;
    document.getElementById("selectedFileInfo").style.display = "flex";
}

function setUploadFeedback(message, state) {
    const feedback = document.getElementById("uploadFeedback");
    feedback.textContent = message;
    feedback.className = `upload-feedback ${state}`;
    feedback.hidden = !message;
}

function updateBenchmarkUI(benchmarks) {
    const stages = benchmarks.stages;
    const stageMap = [
        { id: "step1", key: "stage1_archive_safety" },
        { id: "step2", key: "stage2_manifest_checksum" },
        { id: "step3", key: "stage3_compatibility" },
        { id: "step4", key: "stage4_security_permissions" },
        { id: "step5", key: "stage5_startup_smoke" }
    ];

    const fallbackError = (benchmarks.errors || []).join("; ") || "Validation failed";
    let blocker = null;

    stageMap.forEach((item, index) => {
        const el = document.getElementById(item.id);
        const stage = stages[item.key];
        if (!stage) return;

        let status = stage.status || (stage.passed ? "passed" : "failed");
        if (blocker && status !== "passed") status = "not_run";
        if (status === "failed" && !blocker) {
            blocker = { number: index + 1, name: stage.name || el.querySelector("strong").textContent, error: stage.error || fallbackError };
        }
        const labels = { passed: "Passed", failed: "Failed", not_run: "Not run", pending: "Running" };
        el.className = `benchmark-step ${status.replace("_", "-")}`;
        el.querySelector(".step-status").textContent = labels[status] || status;

        const desc = el.querySelector(".step-desc");
        desc.dataset.default ??= desc.textContent;
        if (status === "failed") {
            const reasons = [...(stage.details || []).filter((line) => line !== blocker.error), blocker.error];
            desc.textContent = reasons.join(" | ");
        } else if (status === "not_run") {
            desc.textContent = `Not run: stage ${blocker.number} failed (${blocker.error})`;
        } else if (stage.details && stage.details.length > 0) {
            desc.textContent = stage.details.join(" | ");
        }
    });
}

// ----------------- Applications Listing & Controls -----------------
async function fetchApplications(silent = false) {
    const container = document.getElementById("appsContainer");
    const countBadge = document.getElementById("appCountBadge");

    try {
        const res = await apiFetch("/api/v1/apps");
        if (!res.ok) return;
        const json = await res.json();
        const apps = json.data;

        countBadge.textContent = `${apps.length} Apps`;

        if (apps.length === 0) {
            container.innerHTML = `<div class="empty-state">No applications deployed yet. Upload a bundle above.</div>`;
            return;
        }

        container.innerHTML = apps.map(app => renderAppCard(app)).join("");
        attachAppActionListeners();
    } catch (err) {
        if (!silent) console.error("Error fetching apps:", err);
    }
}

function renderAppCard(app) {
    const status = app.status || {};
    const state = status.state || "unknown";
    let badgeClass = "badge-neutral";
    let stateLabel = "STOPPED";

    if (state === "running") {
        badgeClass = "badge-success";
        stateLabel = `RUNNING (PID ${status.pid || "--"})`;
    } else if (state === "failed") {
        badgeClass = "badge-error";
        stateLabel = "FAILED / CRASHED";
    }

    const hasRollback = !!app.previous_known_good_version;

    return `
        <div class="app-card" data-app-id="${app.app_id}">
            <div class="app-card-header">
                <span class="app-title">${app.name || app.app_id}</span>
                <span class="badge ${badgeClass}">${stateLabel}</span>
            </div>
            <div class="app-meta">
                <div><strong>ID:</strong> ${app.app_id}</div>
                <div><strong>Active Version:</strong> v${app.active_version}</div>
                <div><strong>Runtime:</strong> ${app.runtime} (${app.target_architecture})</div>
                <div><strong>Previous Good Version:</strong> ${app.previous_known_good_version ? `v${app.previous_known_good_version}` : "None"}</div>
            </div>
            <div class="app-actions">
                ${state === "running" 
                    ? `<button class="btn btn-secondary btn-sm action-btn" data-action="stop">Stop</button>`
                    : `<button class="btn btn-success btn-sm action-btn" data-action="start">Start</button>`
                }
                <button class="btn btn-secondary btn-sm action-btn" data-action="restart">Restart</button>
                ${hasRollback ? `<button class="btn btn-outline btn-sm action-btn" data-action="rollback" title="Rollback to v${app.previous_known_good_version}">Rollback</button>` : ""}
                <button class="btn btn-primary btn-sm action-btn" data-action="logs">Logs</button>
                <button class="btn btn-danger btn-sm action-btn" data-action="delete">Remove</button>
            </div>
        </div>
    `;
}

function attachAppActionListeners() {
    document.querySelectorAll(".action-btn").forEach(btn => {
        btn.addEventListener("click", async (e) => {
            const card = e.target.closest(".app-card");
            const appId = card.dataset.appId;
            const action = e.target.dataset.action;

            if (action === "logs") {
                activeLogAppId = appId;
                showView("logs");
                return;
            }

            if (action === "delete" && !confirm(`Are you sure you want to completely remove '${appId}'?`)) {
                return;
            }

            const method = action === "delete" ? "DELETE" : "POST";
            const url = action === "delete" ? `/api/v1/apps/${appId}` : `/api/v1/apps/${appId}/${action}`;
            btn.disabled = true;

            try {
                const res = await apiFetch(url, { method });
                const json = await res.json();
                if (res.ok) {
                    showToast(json.message || `Action ${action} successful`);
                    await fetchApplications();
                } else {
                    alert(`Error: ${json.error}`);
                }
            } catch (err) {
                alert(`Request failed: ${err.message}`);
            } finally {
                btn.disabled = false;
            }
        });
    });
}

// ----------------- Log Viewing -----------------
async function fetchLogs(appId) {
    const consoleEl = document.getElementById("logContent");
    if (!appId) {
        consoleEl.textContent = "Choose an application to view its logs.";
        return;
    }
    if (logsRequestInFlight) return;
    activeLogAppId = appId;
    logsRequestInFlight = true;
    try {
        const res = await apiFetch(`/api/v1/apps/${appId}/logs?lines=150`);
        if (!res.ok) throw new Error(`Could not load logs (HTTP ${res.status})`);
        const json = await res.json();
        if (activeView !== "logs" || activeLogAppId !== appId) return;
        const viewer = document.getElementById("logConsole");
        const followLatest = logsFirstLoad || viewer.scrollHeight - viewer.scrollTop - viewer.clientHeight < 40;
        logsFirstLoad = false;
        consoleEl.textContent = json.logs || "No logs found.";
        document.getElementById("logsSyncState").textContent = `Live · updated ${new Date().toLocaleTimeString()}`;
        if (followLatest) viewer.scrollTop = viewer.scrollHeight;
    } catch (err) {
        if (activeView === "logs" && activeLogAppId === appId) {
            consoleEl.textContent = `Error reading logs: ${err.message}`;
            document.getElementById("logsSyncState").textContent = "Log refresh failed; retrying.";
        }
    } finally {
        logsRequestInFlight = false;
    }
}

function startLogPolling(appId) {
    stopLogPolling();
    activeLogAppId = appId;
    logsFirstLoad = true;
    document.getElementById("logsSyncState").textContent = "Connecting to application log stream…";
    fetchLogs(appId);
    liveLogsTimer = setInterval(() => {
        if (activeView === "logs" && activeLogAppId === appId) fetchLogs(appId);
    }, 2000);
}

function stopLogPolling() {
    if (liveLogsTimer !== null) {
        clearInterval(liveLogsTimer);
        liveLogsTimer = null;
    }
}

function showToast(msg) {
    console.log("[SDV]", msg);
}
