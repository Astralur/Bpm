"""Windowed onset tempo estimation. No network services or GPU required."""
from dataclasses import dataclass

import numpy as np
from scipy.signal import find_peaks, stft


@dataclass(frozen=True)
class Estimate:
    bpm: float | None
    confidence: float
    beat_at: float | None
    rms: float


class TempoDetector:
    def __init__(self, sample_rate=22050, min_bpm=60, max_bpm=200):
        if not 30 <= min_bpm < max_bpm <= 300:
            raise ValueError("BPM range must satisfy 30 <= min < max <= 300")
        self.sample_rate = sample_rate
        self.min_bpm = min_bpm
        self.max_bpm = max_bpm

    def estimate(self, samples, end_time, previous_bpm=None):
        """end_time is the epoch time of the final input sample.

        beat_at is a pulse near that time, for animation phase synchronization.
        previous_bpm is only an octave tie-breaker, never a fixed tempo.
        """
        samples = np.asarray(samples, dtype=np.float64)
        if samples.ndim == 2:
            samples = samples.mean(axis=1)
        rms = float(np.sqrt(np.mean(samples**2))) if samples.size else 0.0
        empty = Estimate(None, 0.0, None, rms)
        if samples.size < self.sample_rate * 3 or rms < 0.0005:
            return empty
        nfft, hop = 1024, 256
        freqs, times, spectrum = stft(
            samples, fs=self.sample_rate, nperseg=nfft,
            noverlap=nfft-hop, boundary=None, padded=False,
        )
        # Log compression lets quiet percussion contribute alongside bass.
        mag = np.log1p(100 * np.abs(spectrum[(freqs >= 35) & (freqs <= 9000)]))
        onset = np.maximum(np.diff(mag, axis=1), 0).mean(axis=0)
        times = times[1:]
        # A stationary tone has tiny periodic FFT leakage, not musical accents.
        # Reject it before normalizing that leakage into apparently strong beats.
        if np.max(onset) < max(1e-7, float(mag.mean()) * 0.005):
            return empty
        onset = np.maximum(onset - np.median(onset), 0)
        if np.max(onset) < 1e-7:
            return empty
        # Keep sharp local accents, suppress long sustained changes.
        onset /= np.max(onset)
        onset_rate = self.sample_rate / hop
        centered = onset - onset.mean()
        size = 1 << (2 * onset.size - 1).bit_length()
        transform = np.fft.rfft(centered, n=size)
        ac = np.fft.irfft(transform * transform.conj(), n=size)[:onset.size]
        ac /= np.arange(onset.size, 0, -1)
        if ac[0] <= 0:
            return empty
        ac /= ac[0]
        low = int(np.ceil(60 * onset_rate / self.max_bpm))
        high = min(int(60 * onset_rate / self.min_bpm), (len(ac)-1)//3)
        if high <= low:
            return empty
        lags = np.arange(low, high + 1)
        scores = ac[lags] + 0.5 * ac[2*lags] + 0.25 * ac[3*lags]
        peaks, _ = find_peaks(scores)
        candidates = np.unique(np.r_[peaks, np.argmax(scores), 0, len(scores)-1])
        candidates = sorted(candidates, key=lambda i: -scores[i])[:8]
        # Refine ALL plausible peaks: integer-lag quantization can favor half
        # tempo. Coherent onset phase distinguishes a pulse from its multiples.
        grids = []
        for candidate in candidates:
            guess = 60 * onset_rate / lags[candidate]
            grids.append(np.linspace(max(self.min_bpm, guess*0.96),
                                     min(self.max_bpm, guess*1.04), 161))
        grid = np.concatenate(grids)
        phase = np.exp(2j * np.pi * grid[:, None] / 60 * times[None, :])
        vectors = phase @ onset
        coherence = np.abs(vectors) / max(float(onset.sum()), 1e-9)
        interpolated_ac = np.maximum(0, np.interp(60*onset_rate/grid, np.arange(len(ac)), ac))
        refined = np.array([i*161 + int(np.argmax(coherence[i*161:(i+1)*161]))
                            for i in range(len(grids))])
        quality = (0.55*interpolated_ac + 0.45*coherence) * (0.5 + 0.5*coherence)
        tied = refined[quality[refined] >= quality[refined].max()*0.97]
        reference = previous_bpm or 120
        index = min(tied, key=lambda i: abs(np.log2(grid[i]/reference)))
        bpm = float(grid[index])
        confidence = float(np.clip(
            0.55 * interpolated_ac[index] + 0.45 * coherence[index], 0, 1
        ))
        if confidence < 0.28:
            return empty
        period = 60 / bpm
        phase_time = (np.angle(vectors[index]) / (2*np.pi) * period) % period
        start_time = end_time - len(samples) / self.sample_rate
        beat_at = start_time + phase_time
        beat_at += np.floor((end_time-beat_at)/period) * period
        return Estimate(round(bpm, 2), round(confidence, 3), float(beat_at), rms)
