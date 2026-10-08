import numpy as np
import pytest

from bpm_bridge.__main__ import click_audio
from bpm_bridge.detector import TempoDetector


@pytest.mark.parametrize("bpm", [60, 70, 80, 90, 100, 120, 128, 150, 180, 200])
def test_tempo_and_phase_across_range(bpm):
    estimate = TempoDetector().estimate(click_audio(bpm, 8), end_time=1008)
    assert estimate.bpm == pytest.approx(bpm, abs=0.3)
    assert estimate.confidence > 0.7
    pulse_distance = (estimate.beat_at - 1000.2) % (60/bpm)
    assert min(pulse_distance, 60/bpm-pulse_distance) < 0.035


def test_tracks_new_section_instead_of_global_average():
    sr = 22050
    signal = np.r_[click_audio(90, 12), click_audio(150, 12)]
    detector = TempoDetector()
    old = detector.estimate(signal[4*sr:12*sr], 1012)
    new = detector.estimate(signal[16*sr:24*sr], 1024, old.bpm)
    assert old.bpm == pytest.approx(90, abs=0.3)
    assert new.bpm == pytest.approx(150, abs=0.3)


def test_noisy_polyphonic_signal():
    sr = 22050
    t = np.arange(8*sr)/sr
    rng = np.random.default_rng(11)
    samples = click_audio(128, 8) + 0.05*np.sin(2*np.pi*220*t) + 0.01*rng.normal(size=len(t))
    result = TempoDetector().estimate(samples, 1008)
    assert result.bpm == pytest.approx(128, abs=1)
    assert result.confidence > 0.4


@pytest.mark.parametrize("kind", ["empty", "silence", "tone", "noise"])
def test_non_rhythmic_audio_is_not_a_beat(kind):
    sr = 22050
    signal = {
        "empty": np.array([]),
        "silence": np.zeros(8*sr),
        "tone": np.sin(2*np.pi*440*np.arange(8*sr)/sr),
        "noise": np.random.default_rng(5).normal(0, 0.1, 8*sr),
    }[kind]
    estimate = TempoDetector().estimate(signal, 1008)
    assert estimate.bpm is None
    assert estimate.beat_at is None


def test_stereo_input_and_invalid_range():
    mono = click_audio(120, 8)
    result = TempoDetector().estimate(np.column_stack([mono, mono*0.8]), 1008)
    assert result.bpm == pytest.approx(120, abs=0.3)
    with pytest.raises(ValueError):
        TempoDetector(min_bpm=200, max_bpm=60)
