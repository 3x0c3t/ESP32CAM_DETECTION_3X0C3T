import cv2
import threading
import time


class CameraStream:

    def __init__(self, url, jpeg_quality=80, max_fps=15):
        self.url = url
        self.jpeg_quality = max(30, min(100, int(jpeg_quality)))
        self.max_fps = max(1, min(60, int(max_fps)))
        self.frame = None
        self.lock = threading.Lock()
        self.state_lock = threading.Lock()
        self.config_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.running = False
        self.last_frame_time = 0
        self.thread = None

    def configure(self, jpeg_quality=None, max_fps=None):
        with self.config_lock:
            if jpeg_quality is not None:
                quality = int(jpeg_quality)
                if not 30 <= quality <= 100:
                    raise ValueError("jpeg_quality doit être compris entre 30 et 100.")
                self.jpeg_quality = quality

            if max_fps is not None:
                fps = int(max_fps)
                if not 1 <= fps <= 60:
                    raise ValueError("max_fps doit être compris entre 1 et 60.")
                self.max_fps = fps

            return {
                "jpeg_quality": self.jpeg_quality,
                "max_fps": self.max_fps
            }

    # --------------------------------------------------------
    # DEMARRAGE
    # --------------------------------------------------------

    def start(self):
        with self.state_lock:
            if self.thread and self.thread.is_alive():
                return False

            self.stop_event.clear()
            self.running = True

            self.thread = threading.Thread(
                target=self._capture_loop,
                daemon=True
            )

            self.thread.start()

        print("[CAMERA] Démarrage demandé.")
        return True

    # --------------------------------------------------------
    # ARRET
    # --------------------------------------------------------

    def stop(self):
        with self.state_lock:
            self.running = False
            self.stop_event.set()
            thread = self.thread

        if thread and thread.is_alive():
            thread.join(timeout=3)

        with self.lock:
            self.frame = None
            self.last_frame_time = 0

        if thread and thread.is_alive():
            print("[CAMERA] Arrêt en attente du flux.")
            return False

        with self.state_lock:
            self.thread = None

        print("[CAMERA] Arrêtée.")
        return True

    # --------------------------------------------------------
    # ETAT CAMERA
    # --------------------------------------------------------

    def is_active(self):
        return self.running

    def is_connected(self):
        if not self.running:
            return False

        return time.time() - self.last_frame_time < 3

    # --------------------------------------------------------
    # CAPTURE DU FLUX ESP32-CAM
    # --------------------------------------------------------

    def _capture_loop(self):

        while self.running:

            cap = cv2.VideoCapture(self.url)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            try:
                if not cap.isOpened():
                    print(
                        "[CAMERA] Connexion impossible. "
                        "Nouvelle tentative."
                    )

                    self.stop_event.wait(2)
                    continue

                print("[CAMERA] Connexion établie.")

                while self.running:

                    success, frame = cap.read()

                    if not success:
                        print("[CAMERA] Flux interrompu.")
                        break

                    with self.lock:
                        self.frame = frame
                        self.last_frame_time = time.time()

            finally:
                cap.release()

            if self.running:
                self.stop_event.wait(1)

    # --------------------------------------------------------
    # RECUPERATION IMAGE ORIGINALE
    # --------------------------------------------------------

    def get_frame(self):

        with self.lock:
            if self.frame is None:
                return None

            return self.frame.copy()

    # --------------------------------------------------------
    # FLUX VIDEO MJPEG + YOLO
    # --------------------------------------------------------

    def mjpeg(self, detector=None):

        while self.running:
            frame_start = time.monotonic()
            with self.config_lock:
                jpeg_quality = self.jpeg_quality
                max_fps = self.max_fps
            frame = self.get_frame()

            if frame is None:
                time.sleep(0.1)
                continue

            # Détection uniquement sur l'image destinée
            # à l'affichage, jamais sur l'image originale.

            if detector is not None and detector.is_enabled():

                try:
                    frame = detector.process(frame)

                except Exception as error:
                    print(f"[YOLO] Erreur de détection : {error}")

            # Encodage JPEG

            success, buffer = cv2.imencode(
                ".jpg",
                frame,
                [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality]
            )

            if not success:
                continue

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + buffer.tobytes()
                + b"\r\n"
            )

            remaining = (1 / max_fps) - (time.monotonic() - frame_start)
            if remaining > 0:
                time.sleep(remaining)
