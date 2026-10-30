import cv2
import threading
import time


class CameraStream:
    def __init__(self, url):
        self.url = url
        self.frame = None
        self.lock = threading.Lock()
        self.state_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.running = False
        self.last_frame_time = 0
        self.thread = None

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

    def is_active(self):
        return self.running

    def _capture_loop(self):
        while self.running:
            cap = cv2.VideoCapture(self.url)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            try:
                if not cap.isOpened():
                    print("[CAMERA] Connexion impossible. Nouvelle tentative.")
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

    def get_frame(self):
        with self.lock:
            if self.frame is None:
                return None
            return self.frame.copy()

    def is_connected(self):
        if not self.running:
            return False

        return time.time() - self.last_frame_time < 3

    def mjpeg(self):
        while self.running:
            frame = self.get_frame()

            if frame is None:
                time.sleep(0.1)
                continue

            success, buffer = cv2.imencode(
                ".jpg",
                frame,
                [cv2.IMWRITE_JPEG_QUALITY, 80]
            )

            if not success:
                continue

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + buffer.tobytes()
                + b"\r\n"
            )
