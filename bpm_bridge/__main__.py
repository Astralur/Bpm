import argparse
import collections
import sys
import threading
import time

import numpy as np

from .detector import TempoDetector
from .capture import record_block
from .server import make_server
from .state import BeatState


def click_audio(bpm, duration, sample_rate=22050):
    """Synthetic demo/test signal; never used as a substitute for capture."""
    samples = np.zeros(round(duration*sample_rate), dtype=np.float32)
    t = np.arange(round(0.04*sample_rate))/sample_rate
    click = np.sin(2*np.pi*900*t)*np.exp(-t*110)
    for moment in np.arange(0.2, duration, 60/bpm):
        start = round(moment*sample_rate)
        length = min(len(click), len(samples)-start)
        samples[start:start+length] += click[:length]
    return samples


def audio_worker(args, state, stop, errors):
    rate = 22050
    detector = TempoDetector(rate, args.min_bpm, args.max_bpm)
    previous = None
    if args.demo_bpm is not None:
        started = time.time()
        demo = click_audio(args.demo_bpm, args.window, rate)
        while not stop.is_set():
            # Continuous phase with a moving demo window.
            estimate = detector.estimate(demo, started + args.window, previous)
            period = 60/args.demo_bpm
            from .detector import Estimate
            beat = estimate.beat_at
            if beat is not None:
                beat += np.floor((time.time()-beat)/period)*period
            state.publish(Estimate(estimate.bpm, estimate.confidence, beat, estimate.rms), "demo")
            stop.wait(args.interval)
        return
    try:
        import soundcard as sc
        if args.device:
            matches = [d for d in sc.all_microphones(include_loopback=True)
                       if args.device.casefold() in d.name.casefold()]
            if len(matches) != 1:
                raise ValueError("Device name must match exactly one entry from --list-devices")
            device = matches[0]
        else:
            speaker = sc.default_speaker()
            if speaker is None:
                raise RuntimeError("No default output device; select one with --device")
            device = sc.get_microphone(id=speaker.id, include_loopback=True)
        print(f"Audio: {device.name}", flush=True)
        if sys.platform != "win32":
            print("Real capture is intended for Windows WASAPI; this host uses its native backend.", flush=True)
        blocks = collections.deque(maxlen=round(args.window*10))
        condition = threading.Condition()
        captured = {"end": 0.0, "error": None, "finished": False, "generation": 0}

        def record():
            try:
                last_report = float("-inf")
                warning_category = getattr(sc, "SoundcardRuntimeWarning", RuntimeWarning)
                # Two channels avoids SoundCard's Windows single-channel issue.
                buffer_frames = round(rate * args.capture_buffer_ms / 1000)
                with device.recorder(samplerate=rate, channels=2, blocksize=buffer_frames) as recorder:
                    while not stop.is_set():
                        raw, gaps = record_block(recorder, 2205, warning_category)
                        end = time.time()
                        with condition:
                            if gaps:
                                blocks.clear()
                                captured["generation"] += 1
                                state.note_discontinuity(gaps)
                                condition.notify_all()
                                if time.monotonic() - last_report >= 5:
                                    print("Audio discontinuity: discarded the analysis window. "
                                          "If repeated, try --capture-buffer-ms 500 and check the output device.",
                                          file=sys.stderr, flush=True)
                                    last_report = time.monotonic()
                                # This returned block can itself straddle a gap.
                                continue
                            block = raw.mean(axis=1)
                            blocks.append(block)
                            captured["end"] = end
                            condition.notify_all()
            except Exception as exc:
                with condition:
                    captured["error"] = exc
                    condition.notify_all()
            finally:
                with condition:
                    captured["finished"] = True
                    condition.notify_all()

        capture = threading.Thread(target=record, daemon=True)
        capture.start()
        generation = 0
        while not stop.is_set():
            with condition:
                if captured["error"]:
                    raise captured["error"]
                if captured["finished"]:
                    raise RuntimeError("Audio capture stopped")
                samples = np.concatenate(tuple(blocks)) if blocks else np.array([])
                end = captured["end"]
                if generation != captured["generation"]:
                    previous = None
                generation = captured["generation"]
            # Detect silence from the most recent half second, not the old window.
            recent = samples[-rate//2:]
            recent_rms = float(np.sqrt(np.mean(recent**2))) if recent.size else 0
            if recent_rms < 0.0005:
                state.unavailable("silent")
                previous = None
                # Forget the previous song after silence; no stale tempo at resume.
                with condition:
                    blocks.clear()
            elif len(samples) >= rate*3:
                estimate = detector.estimate(samples, end, previous)
                with condition:
                    # A gap during analysis invalidates even a confident result.
                    if generation == captured["generation"]:
                        state.publish(estimate)
                        if estimate.bpm is not None:
                            previous = estimate.bpm
            else:
                state.unavailable("warming_up")
            stop.wait(args.interval)
    except Exception as exc:
        state.unavailable("capture_error")
        print(f"Audio capture failed: {exc}", file=sys.stderr, flush=True)
        errors.append(exc)


def parser():
    p = argparse.ArgumentParser(description="MusicBee audio BPM bridge for OBS on Windows")
    p.add_argument("--list-devices", action="store_true")
    p.add_argument("--device", help="Unique part of a device name; default: output loopback")
    p.add_argument("--banana", help="MP4/WebM or still PNG/JPG served to OBS")
    p.add_argument("--port", type=int, default=8767)
    p.add_argument("--window", type=float, default=8, help="Analysis window in seconds (4-20)")
    p.add_argument("--interval", type=float, default=0.5, help="Update interval in seconds")
    p.add_argument("--min-bpm", type=float, default=60)
    p.add_argument("--max-bpm", type=float, default=200)
    p.add_argument("--base-bpm", type=float, default=120)
    p.add_argument("--offset-ms", type=float, default=0, help="Positive delays the visual pulse")
    p.add_argument("--capture-buffer-ms", type=int, default=250,
                   help="Audio capture buffer in milliseconds (100-2000); try 500 for dropouts")
    p.add_argument("--demo-bpm", type=float, help="Synthetic demo WITHOUT MusicBee capture")
    return p


def main():
    p = parser()
    args = p.parse_args()
    if args.list_devices:
        try:
            import soundcard as sc
            for device in sc.all_microphones(include_loopback=True):
                print(f"{'loopback' if device.isloopback else 'input'}: {device.name}")
        except Exception as exc:
            print(f"Cannot enumerate audio devices ({type(exc).__name__}): {exc}. "
                  "Use Windows with an active output device; --demo-bpm works without audio hardware.",
                  file=sys.stderr)
            return 1
        return 0
    if not 4 <= args.window <= 20 or not 0.2 <= args.interval <= 2:
        p.error("Use --window 4..20 and --interval 0.2..2")
    if not 100 <= args.capture_buffer_ms <= 2000:
        p.error("Use --capture-buffer-ms 100..2000")
    if args.base_bpm <= 0 or not 1 <= args.port <= 65535:
        p.error("Invalid base BPM or port")
    if args.demo_bpm is not None and not args.min_bpm <= args.demo_bpm <= args.max_bpm:
        p.error("Demo BPM must be inside the detection range")
    try:
        TempoDetector(min_bpm=args.min_bpm, max_bpm=args.max_bpm)
        state = BeatState(args.base_bpm, args.offset_ms)
        server = make_server(state, args.port, args.banana)
    except (ValueError, OSError) as exc:
        p.error(str(exc))
    stop, errors = threading.Event(), []
    worker = threading.Thread(target=audio_worker, args=(args, state, stop, errors), daemon=True)
    web = threading.Thread(target=server.serve_forever, daemon=True)
    web.start()
    worker.start()
    print(f"Local bridge on port {args.port}; Ctrl+C to stop.", flush=True)
    try:
        while worker.is_alive():
            worker.join(timeout=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
