"""Thread-safe state shared between capture, analysis and the HTTP server."""
import threading
import time


class BeatState:
    def __init__(self, base_bpm=120, offset_ms=0):
        self.lock = threading.Lock()
        self.base_bpm = base_bpm
        self.offset = offset_ms / 1000
        self.data = {"bpm": None, "confidence": 0, "beat_at": None,
                     "audio_active": False, "status": "waiting", "updated_at": 0}

    def publish(self, estimate, status="tracking"):
        with self.lock:
            self.data = {
                "bpm": estimate.bpm,
                "confidence": estimate.confidence,
                "beat_at": estimate.beat_at + self.offset if estimate.beat_at is not None else None,
                "audio_active": estimate.bpm is not None,
                "status": status if estimate.bpm is not None else "no_reliable_beat",
                "updated_at": time.time(),
            }

    def unavailable(self, status):
        with self.lock:
            self.data.update(audio_active=False, status=status, updated_at=time.time())

    def snapshot(self):
        with self.lock:
            result = dict(self.data)
        if time.time() - result["updated_at"] > 3:
            result.update(audio_active=False, status="stale")
        result.update(base_bpm=self.base_bpm,
                      playback_rate=(result["bpm"] / self.base_bpm if result["bpm"] else 1),
                      server_time=time.time())
        return result
