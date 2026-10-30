import json

from pathlib import Path
from flask import (
    Flask,
    Response,
    jsonify,
    request,
    send_from_directory
)

from .camera import CameraStream
from .storage import (
    add_category,
    category_counts,
    save_image
)

ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = ROOT / "web"
CONFIG_FILE = ROOT / "config" / "config.json"

DEFAULT_CONFIG = {
    "camera_url": "http://192.168.43.128:81/stream"
}

if CONFIG_FILE.exists():
    with open(CONFIG_FILE, "r", encoding="utf-8") as file:
        CONFIG = json.load(file)
else:
    CONFIG = DEFAULT_CONFIG

CAMERA = CameraStream(CONFIG["camera_url"])

app = Flask(__name__)


@app.route("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.route("/css/<path:filename>")
def css(filename):
    return send_from_directory(WEB_DIR / "css", filename)


@app.route("/js/<path:filename>")
def javascript(filename):
    return send_from_directory(WEB_DIR / "js", filename)


@app.route("/camera_feed")
def camera_feed():
    return Response(
        CAMERA.mjpeg(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@app.route("/api/status")
def status():
    return jsonify({
        "camera_active": CAMERA.is_active(),
        "camera_connected": CAMERA.is_connected(),
        "camera_url": CONFIG["camera_url"],
        "flash_available": False,
        "flash_on": False,
        "categories": category_counts()
    })


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


@app.route("/api/flash/on", methods=["POST"])
def flash_on():
    return jsonify({
        "success": False,
        "flash_available": False,
        "error": "Flash indisponible : firmware non configuré."
    }), 503


@app.route("/api/flash/off", methods=["POST"])
def flash_off():
    return jsonify({
        "success": False,
        "flash_available": False,
        "error": "Flash indisponible : firmware non configuré."
    }), 503


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
        return jsonify({"error": str(error)}), 400


@app.route("/api/capture", methods=["POST"])
def capture():
    if not CAMERA.is_active():
        return jsonify({
            "error": "La caméra est arrêtée."
        }), 503

    data = request.get_json(silent=True) or {}
    category = data.get("category", "")

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
        return jsonify({"error": str(error)}), 400


if __name__ == "__main__":
    print("[COLLECT] Serveur de collecte démarré.")
    print("[COLLECT] http://127.0.0.1:8000")
    print("[COLLECT] Caméra :", CONFIG["camera_url"])
    print("[COLLECT] Caméra en attente de commande ON.")

    app.run(
        host="0.0.0.0",
        port=8000,
        threaded=True,
        debug=False
    )
