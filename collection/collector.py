import json
import urllib.request
from urllib.parse import urlsplit
from pathlib import Path

from flask import (
    Flask,
    Response,
    jsonify,
    request,
    send_from_directory
)

from .camera import CameraStream
from .detector import ObjectDetector
from .storage import (
    add_category,
    category_counts,
    save_image
)


# ============================================================
# CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "web"
CONFIG_FILE = ROOT / "config" / "config.json"

DEFAULT_CONFIG = {
    "camera_url": "http://192.168.1.100:81/stream"
}

if CONFIG_FILE.exists():
    with open(CONFIG_FILE, "r", encoding="utf-8") as file:
        CONFIG = json.load(file)
else:
    CONFIG = DEFAULT_CONFIG


# ============================================================
# INITIALISATION
# ============================================================

CAMERA = CameraStream(
    CONFIG["camera_url"],
    CONFIG.get("camera", {}).get("jpeg_quality", 80),
    CONFIG.get("performance", {}).get("max_fps", 15)
)
DETECTOR = ObjectDetector(
    CONFIG.get("detection", {}),
    CONFIG.get("performance", {})
)

flash_percent = 0
flash_available = True

app = Flask(__name__)


# ============================================================
# FLASH ESP32-CAM
# ============================================================

def apply_flash(percent):
    global flash_percent, flash_available

    camera_url = urlsplit(CONFIG["camera_url"])

    if not camera_url.hostname:
        raise ValueError("Adresse caméra invalide.")

    control_url = (
        f"http://{camera_url.hostname}:80/control"
        f"?var=led_intensity&val={round(percent * 255 / 100)}"
    )

    with urllib.request.urlopen(control_url, timeout=4) as response:
        if response.status != 200:
            raise RuntimeError("Réponse invalide de l'ESP32-CAM.")

    flash_percent = percent
    flash_available = True


def flash_response(percent):
    global flash_available

    try:
        percent = max(0, min(100, int(round(float(percent)))))
        apply_flash(percent)

        return jsonify({
            "success": True,
            "flash_available": True,
            "flash_percent": flash_percent,
            "flash_on": flash_percent > 0
        })

    except Exception as error:
        flash_available = False

        return jsonify({
            "success": False,
            "flash_available": False,
            "error": f"Commande flash impossible : {error}"
        }), 502


# ============================================================
# INTERFACE WEB
# ============================================================

@app.route("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.route("/css/<path:filename>")
def css(filename):
    return send_from_directory(WEB_DIR / "css", filename)


@app.route("/js/<path:filename>")
def javascript(filename):
    return send_from_directory(WEB_DIR / "js", filename)


# ============================================================
# FLUX VIDEO
# ============================================================

@app.route("/camera_feed")
def camera_feed():
    return Response(
        CAMERA.mjpeg(detector=DETECTOR),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


# ============================================================
# STATUT GENERAL
# ============================================================

@app.route("/api/status")
def status():
    return jsonify({
        "camera_active": CAMERA.is_active(),
        "camera_connected": CAMERA.is_connected(),
        "camera_url": CONFIG["camera_url"],
        "jpeg_quality": CAMERA.jpeg_quality,
        "max_fps": CAMERA.max_fps,

        "flash_available": flash_available,
        "flash_on": flash_percent > 0,
        "flash_percent": flash_percent,

        "detection_enabled": DETECTOR.is_enabled(),
        "detection_confidence": DETECTOR.confidence,
        "detection_imgsz": DETECTOR.imgsz,
        "analysis_interval_ms": DETECTOR.analysis_interval_ms,

        "categories": category_counts()
    })


# ============================================================
# CONTROLE CAMERA
# ============================================================

@app.route("/api/camera/on", methods=["POST"])
def camera_on():

    if CAMERA.is_active():
        return jsonify({
            "success": True,
            "camera_active": True,
            "message": "Caméra déjà activée."
        })

    if not CAMERA.start():
        return jsonify({
            "success": False,
            "error": "Le précédent flux est encore en cours d'arrêt."
        }), 409

    return jsonify({
        "success": True,
        "camera_active": True,
        "message": "Démarrage de la caméra demandé."
    })


@app.route("/api/camera/off", methods=["POST"])
def camera_off():

    if CAMERA.stop():
        return jsonify({
            "success": True,
            "camera_active": False,
            "message": "Caméra arrêtée."
        })

    return jsonify({
        "success": False,
        "camera_active": False,
        "error": "Le flux vidéo ne s'est pas arrêté dans le délai prévu."
    }), 503


@app.route("/api/camera/config", methods=["POST"])
def camera_config():
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not data:
        return jsonify({"success": False, "error": "Objet JSON invalide ou vide."}), 400

    jpeg_quality = data.get("jpeg_quality")
    max_fps = data.get("max_fps")

    try:
        if jpeg_quality is not None:
            if isinstance(jpeg_quality, bool) or not isinstance(jpeg_quality, int) or not 30 <= jpeg_quality <= 100:
                raise ValueError("jpeg_quality doit être un entier compris entre 30 et 100.")

        if max_fps is not None:
            if isinstance(max_fps, bool) or not isinstance(max_fps, int) or not 1 <= max_fps <= 60:
                raise ValueError("max_fps doit être un entier compris entre 1 et 60.")

        settings = CAMERA.configure(jpeg_quality=jpeg_quality, max_fps=max_fps)
        CONFIG.setdefault("camera", {})["jpeg_quality"] = settings["jpeg_quality"]
        CONFIG.setdefault("performance", {})["max_fps"] = settings["max_fps"]

        with open(CONFIG_FILE, "w", encoding="utf-8") as file:
            json.dump(CONFIG, file, indent=4, ensure_ascii=False)
            file.write("\n")

        return jsonify({"success": True, **settings})

    except (TypeError, ValueError) as error:
        return jsonify({"success": False, "error": str(error)}), 400



# ============================================================
# DETECTION YOLO
# ============================================================

@app.route("/api/detection", methods=["POST"])
def detection():

    data = request.get_json(silent=True) or {}

    enabled = data.get("enabled")
    confidence = data.get("confidence")
    imgsz = data.get("imgsz")
    analysis_interval_ms = data.get("analysis_interval_ms")

    try:

        if enabled is not None and not isinstance(enabled, bool):
            return jsonify({
                "success": False,
                "error": "Le paramètre enabled doit être booléen."
            }), 400

        if confidence is not None:
            confidence = float(confidence)

            if not 0.05 <= confidence <= 0.95:
                return jsonify({
                    "success": False,
                    "error": "La confiance doit être comprise entre 0.05 et 0.95."
                }), 400

        if imgsz is not None:
            imgsz = int(imgsz)
            if not 160 <= imgsz <= 1280:
                return jsonify({"success": False, "error": "imgsz doit être compris entre 160 et 1280."}), 400

        if analysis_interval_ms is not None:
            analysis_interval_ms = int(analysis_interval_ms)
            if not 0 <= analysis_interval_ms <= 10000:
                return jsonify({"success": False, "error": "Intervalle invalide (0 à 10000 ms)."}), 400

        DETECTOR.configure(
            enabled=enabled,
            confidence=confidence,
            imgsz=imgsz,
            analysis_interval_ms=analysis_interval_ms
        )

        CONFIG.setdefault("detection", {}).update({
            "enabled": DETECTOR.is_enabled(),
            "confidence": DETECTOR.confidence,
            "imgsz": DETECTOR.imgsz
        })
        CONFIG.setdefault("performance", {})["analysis_interval_ms"] = DETECTOR.analysis_interval_ms
        with open(CONFIG_FILE, "w", encoding="utf-8") as file:
            json.dump(CONFIG, file, indent=4, ensure_ascii=False)
            file.write("\n")

        return jsonify({
            "success": True,
            "detection_enabled": DETECTOR.is_enabled(),
            "detection_confidence": DETECTOR.confidence,
            "detection_imgsz": DETECTOR.imgsz,
            "analysis_interval_ms": DETECTOR.analysis_interval_ms
        })

    except (TypeError, ValueError) as error:

        return jsonify({
            "success": False,
            "error": str(error)
        }), 400


# ============================================================
# CONTROLE FLASH
# ============================================================

@app.route("/api/flash", methods=["POST"])
def flash_set():

    data = request.get_json(silent=True) or {}

    if "percent" not in data:
        return jsonify({
            "success": False,
            "error": "Pourcentage manquant."
        }), 400

    return flash_response(data["percent"])


@app.route("/api/flash/on", methods=["POST"])
def flash_on():
    return flash_response(100)


@app.route("/api/flash/off", methods=["POST"])
def flash_off():
    return flash_response(0)


# ============================================================
# GESTION DES CATEGORIES
# ============================================================

@app.route("/api/categories", methods=["GET"])
def categories():
    return jsonify(category_counts())


@app.route("/api/categories", methods=["POST"])
def create_category():

    data = request.get_json(silent=True) or {}
    name = data.get("name", "")

    try:
        category = add_category(name)

        return jsonify({
            "success": True,
            "category": category
        })

    except ValueError as error:

        return jsonify({
            "error": str(error)
        }), 400


# ============================================================
# CAPTURE DATASET
# ============================================================

@app.route("/api/capture", methods=["POST"])
def capture():

    if not CAMERA.is_active():
        return jsonify({
            "error": "La caméra est arrêtée."
        }), 503

    data = request.get_json(silent=True) or {}
    category = data.get("category", "")

    # Récupération de l'image ORIGINALE
    # Sans annotations YOLO
    frame = CAMERA.get_frame()

    if frame is None:
        return jsonify({
            "error": "Aucune image disponible depuis la caméra."
        }), 503

    try:
        destination = save_image(frame, category)

        return jsonify({
            "success": True,
            "category": category,
            "filename": destination.name
        })

    except (ValueError, IOError) as error:

        return jsonify({
            "error": str(error)
        }), 400


# ============================================================
# DEMARRAGE
# ============================================================

if __name__ == "__main__":

    print("[COLLECT] Serveur de collecte démarré.")
    print("[COLLECT] http://127.0.0.1:8000")
    print("[COLLECT] Caméra :", CONFIG["camera_url"])
    print("[COLLECT] YOLO :", "Chargé")
    print("[COLLECT] Détection :", "Désactivée")
    print("[COLLECT] Caméra en attente de commande ON.")

    app.run(
        host="0.0.0.0",
        port=8000,
        threaded=True,
        debug=False
    )
