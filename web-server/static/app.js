// SDV Application Deployment Manager Frontend Logic

if (window.location.search) {
    window.history.replaceState({}, document.title, window.location.pathname + window.location.hash);
}

let selectedFile = null;
let activeLogAppId = null;
let activeView = "environment";

document.addEventListener("DOMContentLoaded", () => {
    const passwordInput = document.getElementById("loginPassword");
    document.getElementById("showPassword").addEventListener("change", (event) => {
        passwordInput.type = event.target.checked ? "text" : "password";
    });

    document.getElementById("loginForm").addEventListener("submit", async (event) => {
        event.preventDefault();
        const emailInput = document.getElementById("loginEmail");
        const passwordInput = document.getElementById("loginPassword");
        const error = document.getElementById("loginError");
        const button = document.getElementById("loginButton");
        error.hidden = true;
        button.disabled = true;

        try {
            const response = await fetch("/api/v1/login", {
                method: "POST",
                credentials: "same-origin",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ email: emailInput.value, password: passwordInput.value })
            });
            const result = await response.json();
            if (!response.ok || !result.success) {
                throw new Error(result.error || "Sign-in failed");
            }

            const sessionResponse = await fetch("/api/v1/session", { credentials: "same-origin" });
            const session = await sessionResponse.json();
            if (!sessionResponse.ok || !session.authenticated) {
                throw new Error("Sign-in succeeded but the browser session was not established. Try again.");
            }
            passwordInput.value = "";
            showDashboard(session.email || result.email);
        } catch (err) {
            error.textContent = err.message;
            error.hidden = false;
        } finally {
            button.disabled = false;
        }
    });

    document.getElementById("logoutBtn").addEventListener("click", async () => {
        await fetch("/api/v1/logout", { method: "POST", credentials: "same-origin" });
        showLogin();
    });

    document.querySelectorAll(".view-nav-item").forEach((button) => {
        button.addEventListener("click", () => showView(button.dataset.view));
    });

    document.getElementById("getEnvironmentBtn").addEventListener("click", fetchEnvironment);
    document.getElementById("refreshAppsBtn").addEventListener("click", fetchApplications);

    document.getElementById("refreshLogsBtn").addEventListener("click", () => {
        const appId = document.getElementById("logAppSelect").value;
        if (appId) fetchLogs(appId);
    });

    setupUploadEvents();
    checkSession();
});

async function checkSession() {
    try {
        const response = await fetch("/api/v1/session", { credentials: "same-origin" });
        const session = await response.json();
        if (session.authenticated) showDashboard(session.email);
        else showLogin();
    } catch (_) {
        showLogin();
    }
}

function showDashboard(email = "") {
    document.getElementById("loginScreen").hidden = true;
    document.getElementById("applicationShell").hidden = false;
    document.getElementById("sessionLabel").textContent = email ? `Signed in as ${email}` : "Signed in";
    window.scrollTo(0, 0);
    showView("environment");
}

function showView(viewName) {
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
        if (activeLogAppId && applications.some((app) => app.app_id === activeLogAppId)) {
            select.value = activeLogAppId;
            fetchLogs(activeLogAppId);
        } else {
            activeLogAppId = "";
            logContent.textContent = applications.length
                ? "Choose an application, then select View logs."
                : "No deployed applications are available yet.";
        }
    } catch (error) {
        logContent.textContent = error.message;
    }
}

function showLogin() {
    document.getElementById("applicationShell").hidden = true;
    document.getElementById("loginScreen").hidden = false;
    window.scrollTo(0, 0);
}

async function apiFetch(url, options = {}) {
    const response = await fetch(url, { ...options, credentials: "same-origin" });
    if (response.status === 401) showLogin();
    return response;
}

// ----------------- Environment Detection -----------------
async function fetchEnvironment() {
    const badge = document.getElementById("envTimestamp");
    const button = document.getElementById("getEnvironmentBtn");
    const errorMessage = document.getElementById("environmentError");
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

        document.getElementById("envArch").textContent = `${data.system.architecture} (${data.system.target_arch_configured})`;
        document.getElementById("envOs").textContent = data.system.os_release || data.system.os;
        document.getElementById("envKernel").textContent = data.system.kernel;
        document.getElementById("envGlibc").textContent = data.toolchain.glibc_version;
        document.getElementById("envPython").textContent = `Python ${data.toolchain.python_version}`;

        const kuksaEl = document.getElementById("envKuksa");
        if (data.middleware.kuksa_databroker.connected) {
            kuksaEl.textContent = "CONNECTED (55555)";
            kuksaEl.className = "badge badge-success";
        } else {
            kuksaEl.textContent = "DISCONNECTED";
            kuksaEl.className = "badge badge-warning";
        }

        const lolaEl = document.getElementById("envLola");
        const shmCount = data.middleware.score_mw_com_shm.active_lola_segments.length;
        if (shmCount > 0) {
            lolaEl.textContent = `READY (${shmCount} segments)`;
            lolaEl.className = "badge badge-success";
        } else {
            lolaEl.textContent = "/dev/shm IDLE";
            lolaEl.className = "badge badge-neutral";
        }

        const supEl = document.getElementById("envSupervisor");
        supEl.textContent = data.middleware.systemd_available.supervision_mode.toUpperCase();
        supEl.className = "badge badge-info";

        badge.textContent = `Updated ${new Date().toLocaleTimeString()}`;
        badge.className = "badge badge-success";
    } catch (err) {
        badge.textContent = "Unavailable";
        badge.className = "badge badge-error";
        errorMessage.textContent = "Could not read target environment. Check the Pi server connection and try again.";
        errorMessage.hidden = false;
    } finally {
        button.disabled = false;
        button.textContent = "Get info";
    }
}

// ----------------- Upload & Benchmark Handling -----------------
function setupUploadEvents() {
    const dropZone = document.getElementById("dropZone");
    const fileInput = document.getElementById("fileInput");
    const browseBtn = document.getElementById("browseBtn");
    const uploadBtn = document.getElementById("uploadBtn");
    const fileInfo = document.getElementById("selectedFileInfo");
    const fileName = document.getElementById("selectedFileName");
    const fileSize = document.getElementById("selectedFileSize");

    browseBtn.addEventListener("click", () => fileInput.click());
    dropZone.addEventListener("click", (e) => {
        if (!e.target.closest("button, input, .selected-file-info")) {
            fileInput.click();
        }
    });

    fileInput.addEventListener("change", (e) => {
        if (e.target.files.length > 0) {
            handleSelectedFile(e.target.files[0]);
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
            handleSelectedFile(e.dataTransfer.files[0]);
        }
    });

    function handleSelectedFile(file) {
        if (uploadBtn.disabled) return;
        if (!file.name.endsWith(".tar.gz") && !file.name.endsWith(".tgz")) {
            selectedFile = null;
            fileInfo.style.display = "none";
            fileInput.value = "";
            setUploadFeedback("Choose a .tar.gz or .tgz application bundle.", "error");
            return;
        }
        if (file.size > 100 * 1024 * 1024) {
            selectedFile = null;
            fileInfo.style.display = "none";
            fileInput.value = "";
            setUploadFeedback("This package exceeds the 100 MB upload limit.", "error");
            return;
        }
        selectedFile = file;
        fileName.textContent = file.name;
        fileSize.textContent = `(${(file.size / (1024 * 1024)).toFixed(2)} MB)`;
        fileInfo.style.display = "flex";
        uploadBtn.disabled = false;
        uploadBtn.textContent = "Validate & Deploy";
        setUploadFeedback("Package selected. It will be checked before activation.", "info");
    }

    uploadBtn.addEventListener("click", async () => {
        if (!selectedFile) return;
        await executeUploadAndValidation(selectedFile);
    });
}

async function executeUploadAndValidation(file) {
    const benchmarkPanel = document.getElementById("benchmarkPanel");
    const errorEl = document.getElementById("benchmarkError");
    const successEl = document.getElementById("benchmarkSuccess");
    const uploadBtn = document.getElementById("uploadBtn");
    const browseBtn = document.getElementById("browseBtn");
    const fileInput = document.getElementById("fileInput");

    benchmarkPanel.style.display = "block";
    errorEl.style.display = "none";
    successEl.style.display = "none";
    uploadBtn.disabled = true;
    uploadBtn.textContent = "Uploading & validating…";
    browseBtn.disabled = true;
    fileInput.disabled = true;
    setUploadFeedback("Uploading package and running validation checks…", "info");

    // Reset steps
    for (let i = 1; i <= 5; i++) {
        const step = document.getElementById(`step${i}`);
        step.className = "benchmark-step";
        step.querySelector(".step-icon").textContent = "⏳";
    }

    const formData = new FormData();
    formData.append("package", file);

    try {
        const res = await apiFetch("/api/v1/apps/upload", {
            method: "POST",
            body: formData
        });

        const json = await res.json();

        if (json.benchmark_results) {
            updateBenchmarkUI(json.benchmark_results);
        }

        if (!res.ok || !json.success) {
            const err = json.error || (json.benchmark_results?.errors || []).join("; ") || "Validation failed";
            errorEl.textContent = `❌ ${err}`;
            errorEl.style.display = "block";
            setUploadFeedback("Validation failed. Review the checks below, then try again.", "error");
        } else {
            successEl.textContent = `✅ ${json.message}`;
            successEl.style.display = "block";
            setUploadFeedback("Application deployed successfully.", "success");
            selectedFile = null;
            fileInput.value = "";
            document.getElementById("selectedFileInfo").style.display = "none";
            fetchApplications();
        }
    } catch (err) {
        errorEl.textContent = `❌ Upload failed: ${err.message}`;
        errorEl.style.display = "block";
        setUploadFeedback("Upload failed. The active application was not replaced.", "error");
    } finally {
        uploadBtn.disabled = false;
        uploadBtn.textContent = "Validate & Deploy";
        browseBtn.disabled = false;
        fileInput.disabled = false;
    }
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

    stageMap.forEach(item => {
        const el = document.getElementById(item.id);
        const stage = stages[item.key];
        if (!stage) return;

        if (stage.passed) {
            el.className = "benchmark-step passed";
            el.querySelector(".step-icon").textContent = "✅";
            if (stage.details.length > 0) {
                el.querySelector(".step-desc").textContent = stage.details.join(" | ");
            }
        } else {
            el.className = "benchmark-step failed";
            el.querySelector(".step-icon").textContent = "❌";
            if (stage.details.length > 0) {
                el.querySelector(".step-desc").textContent = stage.details.join(" | ");
            }
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

            try {
                const res = await apiFetch(url, { method });
                const json = await res.json();
                if (res.ok) {
                    showToast(json.message || `Action ${action} successful`);
                    fetchApplications();
                } else {
                    alert(`Error: ${json.error}`);
                }
            } catch (err) {
                alert(`Request failed: ${err.message}`);
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
    activeLogAppId = appId;
    consoleEl.textContent = "Loading logs…";
    try {
        const res = await apiFetch(`/api/v1/apps/${appId}/logs?lines=150`);
        if (!res.ok) throw new Error(`Could not load logs (HTTP ${res.status})`);
        const json = await res.json();
        consoleEl.textContent = json.logs || "No logs found.";
    } catch (err) {
        consoleEl.textContent = `Error reading logs: ${err.message}`;
    }
}

function showToast(msg) {
    console.log("[SDV]", msg);
}
