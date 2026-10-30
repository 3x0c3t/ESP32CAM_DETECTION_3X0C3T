const categorySelect = document.getElementById("category");
const cameraStatus = document.getElementById("camera-status");
const captureStatus = document.getElementById("capture-status");
const cameraImage = document.getElementById("camera");
const cameraPlaceholder = document.getElementById("camera-placeholder");

let autoTimer = null;
let capturing = false;
let cameraActive = false;


async function api(url, options = {}) {

    const response = await fetch(url, {
        headers: {
            "Content-Type": "application/json"
        },
        ...options
    });

    const data = await response.json();

    if (!response.ok) {
        throw new Error(data.error || "Erreur serveur");
    }

    return data;
}


/* CAMERA */

function displayCamera(active) {

    cameraActive = active;

    if (active) {
        cameraImage.src = "/camera_feed?t=" + Date.now();
        cameraImage.style.display = "block";
        cameraPlaceholder.style.display = "none";
    } else {
        cameraImage.removeAttribute("src");
        cameraImage.style.display = "none";
        cameraPlaceholder.style.display = "flex";
    }

    document.getElementById("camera-on").disabled = active;
    document.getElementById("camera-off").disabled = !active;
}


async function cameraCommand(action) {

    captureStatus.textContent = "";

    try {
        await api("/api/camera/" + action, {
            method: "POST"
        });

        displayCamera(action === "on");
        await refreshStatus();

    } catch (error) {
        captureStatus.textContent = error.message;
    }
}


document.getElementById("camera-on").addEventListener(
    "click",
    () => cameraCommand("on")
);

document.getElementById("camera-off").addEventListener(
    "click",
    () => cameraCommand("off")
);


/* FLASH */

async function flashCommand(action) {

    try {
        await api("/api/flash/" + action, {
            method: "POST"
        });

        await refreshStatus();

    } catch (error) {
        document.getElementById("flash-status").textContent =
            "FLASH : " + error.message;
    }
}


document.getElementById("flash-on").addEventListener(
    "click",
    () => flashCommand("on")
);

document.getElementById("flash-off").addEventListener(
    "click",
    () => flashCommand("off")
);


/* DATASET */

function updateDataset(categories) {

    const current = categorySelect.value;

    categorySelect.innerHTML = "";

    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "Sélectionner une catégorie";
    categorySelect.appendChild(placeholder);

    for (const [name, count] of Object.entries(categories)) {

        const option = document.createElement("option");
        option.value = name;
        option.textContent = name;

        categorySelect.appendChild(option);
    }

    if (categories[current] !== undefined) {
        categorySelect.value = current;
    }

    const list = document.getElementById("dataset-list");
    list.innerHTML = "";

    let total = 0;

    for (const [name, count] of Object.entries(categories)) {

        total += count;

        const item = document.createElement("div");
        item.className = "dataset-item";

        const label = document.createElement("span");
        label.textContent = name;

        const value = document.createElement("strong");
        value.textContent = count + " images";

        item.append(label, value);
        list.appendChild(item);
    }

    if (total === 0) {
        list.innerHTML =
            '<div class="empty-state">Aucune image collectée.</div>';
    }

    document.getElementById("total").textContent =
        total + (total > 1 ? " IMAGES" : " IMAGE");
}


/* STATUS */

async function refreshStatus() {

    try {

        const data = await api("/api/status");

        const connected = data.camera_connected;

        cameraStatus.textContent = connected
            ? "CONNECTÉE"
            : "DÉCONNECTÉE";

        cameraStatus.className = connected
            ? "status online"
            : "status offline";

        document.getElementById("connection-info").textContent =
            connected ? "Flux caméra actif" : "Aucun flux disponible";

        if (data.camera_active !== undefined) {
            displayCamera(data.camera_active);
        }

        document.getElementById("flash-status").textContent =
            data.flash_available
                ? "FLASH : " + (data.flash_on ? "ALLUMÉ" : "ÉTEINT")
                : "FLASH : NON DISPONIBLE";

        document.getElementById("flash-on").disabled =
            !data.flash_available || data.flash_on;

        document.getElementById("flash-off").disabled =
            !data.flash_available || !data.flash_on;

        updateDataset(data.categories || {});

    } catch (error) {

        cameraStatus.textContent = "SERVEUR INJOIGNABLE";
        cameraStatus.className = "status offline";
    }
}


/* CAPTURE */

async function captureImage() {

    if (capturing) return;

    const category = categorySelect.value;

    if (!category) {
        captureStatus.textContent = "Sélectionne une catégorie.";
        return;
    }

    capturing = true;

    try {

        const data = await api("/api/capture", {
            method: "POST",
            body: JSON.stringify({ category })
        });

        captureStatus.textContent =
            "Image enregistrée : " + data.filename;

        await refreshStatus();

    } catch (error) {

        captureStatus.textContent = error.message;

    } finally {

        capturing = false;
    }
}


document.getElementById("capture").addEventListener(
    "click",
    captureImage
);


/* ADD CATEGORY */

document.getElementById("add-category").addEventListener(
    "click",
    async () => {

        const input = document.getElementById("new-category");
        const name = input.value.trim();

        if (!name) {
            captureStatus.textContent = "Saisis un nom de catégorie.";
            return;
        }

        try {

            await api("/api/categories", {
                method: "POST",
                body: JSON.stringify({ name })
            });

            input.value = "";
            captureStatus.textContent = "Catégorie ajoutée.";

            await refreshStatus();

        } catch (error) {

            captureStatus.textContent = error.message;
        }
    }
);


/* AUTOMATIC CAPTURE */

document.getElementById("start-auto").addEventListener(
    "click",
    () => {

        if (!categorySelect.value) {
            captureStatus.textContent = "Sélectionne une catégorie.";
            return;
        }

        const interval = Number(
            document.getElementById("interval").value
        );

        if (!Number.isFinite(interval) || interval < 1 || interval > 3600) {
            captureStatus.textContent = "Intervalle invalide.";
            return;
        }

        if (autoTimer !== null) return;

        autoTimer = setInterval(captureImage, interval * 1000);

        document.getElementById("start-auto").disabled = true;
        document.getElementById("stop-auto").disabled = false;

        document.getElementById("auto-status").textContent = "ACTIVE";
        document.getElementById("auto-status").className = "status online";

        captureStatus.textContent = "Capture automatique activée.";
    }
);


document.getElementById("stop-auto").addEventListener(
    "click",
    () => {

        clearInterval(autoTimer);
        autoTimer = null;

        document.getElementById("start-auto").disabled = false;
        document.getElementById("stop-auto").disabled = true;

        document.getElementById("auto-status").textContent = "ARRÊTÉE";
        document.getElementById("auto-status").className = "status offline";

        captureStatus.textContent = "Capture automatique arrêtée.";
    }
);


/* INITIALISATION */

displayCamera(false);
refreshStatus();

setInterval(refreshStatus, 2000);
