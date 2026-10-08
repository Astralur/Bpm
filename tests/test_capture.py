import queue
import threading
import types
import warnings

import numpy as np
import pytest

from bpm_bridge.capture import record_block
from bpm_bridge.detector import Estimate
from bpm_bridge.state import BeatState
from bpm_bridge import __main__ as bridge


class BackendWarning(RuntimeWarning):
    pass


def test_reports_gaps_without_repeating_raw_warnings_and_preserves_other_warnings():
    class Recorder:
        def record(self, numframes):
            warnings.warn("data discontinuity in recording", BackendWarning)
            warnings.warn("data discontinuity in recording", BackendWarning)
            warnings.warn("different backend problem", BackendWarning)
            return np.ones((numframes, 2))

    with pytest.warns(BackendWarning, match="different backend problem") as caught:
        samples, gaps = record_block(Recorder(), 10, BackendWarning)
    assert gaps == 2
    assert samples.shape == (10, 2)
    assert len(caught) == 1


def test_capture_error_propagates():
    class Recorder:
        def record(self, numframes):
            raise OSError("device disconnected")
    with pytest.raises(OSError, match="disconnected"):
        record_block(Recorder(), 10, BackendWarning)


def test_capture_discards_old_window_and_result_computed_during_gap(monkeypatch):
    chunks = queue.Queue()
    analyzing = threading.Event()
    finish_analysis = threading.Event()
    gap_seen = threading.Event()
    recovered = threading.Event()
    stop = threading.Event()
    calls = []
    options = {}

    class Recorder:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def record(self, numframes):
            chunk = chunks.get(timeout=3)
            if chunk == "gap":
                warnings.warn("data discontinuity in recording", BackendWarning)
                return np.ones((numframes, 2)) * 99
            return np.ones((numframes, 2)) * chunk

    class Device:
        name = "test loopback"
        def recorder(self, **kwargs):
            options.update(kwargs)
            return Recorder()

    fake_backend = types.SimpleNamespace(
        SoundcardRuntimeWarning=BackendWarning,
        default_speaker=lambda: types.SimpleNamespace(id="test"),
        get_microphone=lambda **kwargs: Device(),
    )
    monkeypatch.setitem(__import__('sys').modules, "soundcard", fake_backend)

    class Detector:
        def __init__(self, *args):
            pass
        def estimate(self, samples, end, previous):
            calls.append(samples.copy())
            if len(calls) == 1:
                analyzing.set()
                assert finish_analysis.wait(3)
                return Estimate(120, 0.9, end, 0.2)
            return Estimate(150, 0.9, end, 0.7)

    monkeypatch.setattr(bridge, "TempoDetector", Detector)

    class State(BeatState):
        def note_discontinuity(self, count=1):
            super().note_discontinuity(count)
            gap_seen.set()
        def publish(self, estimate, status="tracking"):
            # The stale 120 BPM estimate must never be published after the gap.
            assert estimate.bpm == 150
            super().publish(estimate, status)
            recovered.set()

    state = State()
    args = bridge.parser().parse_args([])
    args.interval = 0.01
    errors = []
    worker = threading.Thread(target=bridge.audio_worker, args=(args, state, stop, errors), daemon=True)
    worker.start()
    try:
        for _ in range(35):
            chunks.put(0.2)
        assert analyzing.wait(3)
        chunks.put("gap")
        assert gap_seen.wait(3)
        assert state.snapshot()["bpm"] is None
        assert not state.snapshot()["audio_active"]
        finish_analysis.set()
        for _ in range(35):
            chunks.put(0.7)
        assert recovered.wait(3)
        assert np.allclose(calls[-1], 0.7)
        assert state.snapshot()["capture_discontinuities"] == 1
        assert state.snapshot()["bpm"] == 150
        assert options["blocksize"] == round(22050*0.25)
    finally:
        finish_analysis.set()
        stop.set()
        chunks.put(0)
        worker.join(timeout=3)
    assert not worker.is_alive()
    assert errors == []
