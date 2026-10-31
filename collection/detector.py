from pathlib import Path
import time
from threading import Lock

from ultralytics import YOLO


ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = ROOT / "models" / "yolov8n.pt"


class ObjectDetector:

    def __init__(self, config=None, performance=None):
        config = config or {}
        performance = performance or {}
        self.model = YOLO(str(MODEL_PATH))
        self.enabled = bool(config.get("enabled", False))
        self.confidence = max(0.05, min(0.95, float(config.get("confidence", 0.45))))
        self.imgsz = max(160, min(1280, int(config.get("imgsz", 640))))
        self.analysis_interval_ms = max(0, min(10000, int(performance.get("analysis_interval_ms", 0))))
        self.lock = Lock()
        self.inference_lock = Lock()
        self.last_result = None
        self.last_analysis_time = 0

    def configure(self, enabled=None, confidence=None, imgsz=None, analysis_interval_ms=None):
        with self.lock:
            if enabled is not None:
                self.enabled = bool(enabled)

            if confidence is not None:
                self.confidence = max(
                    0.05,
                    min(0.95, float(confidence))
                )

            if imgsz is not None:
                self.imgsz = max(160, min(1280, int(imgsz)))

            if analysis_interval_ms is not None:
                self.analysis_interval_ms = max(0, min(10000, int(analysis_interval_ms)))

            self.last_result = None
            self.last_analysis_time = 0

    def is_enabled(self):
        with self.lock:
            return self.enabled

    def process(self, frame):
        with self.inference_lock:
            now = time.monotonic()

            with self.lock:
                if not self.enabled:
                    return frame

                interval = self.analysis_interval_ms / 1000

                if (
                    interval > 0
                    and self.last_result is not None
                    and now - self.last_analysis_time < interval
                ):
                    return self.last_result.copy()

                confidence = self.confidence
                imgsz = self.imgsz

            results = self.model.predict(
                frame,
                conf=confidence,
                imgsz=imgsz,
                verbose=False
            )
            annotated = results[0].plot()

            with self.lock:
                self.last_result = annotated.copy()
                self.last_analysis_time = time.monotonic()

            return annotated
