"""Functional Chromium tests; no OBS/Windows hardware is claimed by these."""
import os
import shutil
import subprocess
import threading
import time

import pytest
from playwright.sync_api import sync_playwright

from bpm_bridge.detector import Estimate
from bpm_bridge.server import make_server
from bpm_bridge.state import BeatState


@pytest.fixture
def browser():
    with sync_playwright() as p:
        executable = os.environ.get("CHROMIUM_EXECUTABLE") or shutil.which("chromium")
        browser = p.chromium.launch(executable_path=executable, headless=True,
                                    args=["--no-sandbox", "--autoplay-policy=no-user-gesture-required"])
        yield browser
        browser.close()


def serve(state, banana=None):
    server = make_server(state, port=0, banana=banana)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_port}"


def test_animation_follows_tempo_phase_and_stops(browser):
    state = BeatState()
    state.publish(Estimate(90, 0.9, time.time(), 0.1))
    server, url = serve(state)
    page = browser.new_page()
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    try:
        page.goto(url)
        page.wait_for_function("window.bananaBridge && bananaBridge.active()")
        for bpm in (90, 150):
            state.publish(Estimate(bpm, 0.9, time.time(), 0.1))
            page.wait_for_function(f"bananaBridge.state.bpm === {bpm}")
            page.wait_for_timeout(50)
            data = page.evaluate("""() => {
              const b = bananaBridge, a = b.targets[0].element;
              return {actual:a.currentTime, expected:
                (Date.now()/1000+b.clockOffset-b.state.beat_at)*(b.state.bpm/120)*1000};
            }""")
            assert abs(data["actual"]-data["expected"]) < 50
        state.unavailable("silent")
        page.wait_for_function("!bananaBridge.active()")
        page.wait_for_timeout(50)
        old = page.evaluate("bananaBridge.targets[0].element.currentTime")
        page.wait_for_timeout(150)
        assert page.evaluate("bananaBridge.targets[0].element.currentTime") == old
        # An interrupted bridge must also freeze the animation.
        assert not errors
    finally:
        page.close()
        server.shutdown()
        server.server_close()


def test_video_rate_and_bridge_disconnect(browser, tmp_path):
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg is needed to generate the functional video fixture")
    video = tmp_path / "clip.webm"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                    "testsrc2=size=128x128:rate=30:duration=2", "-c:v", "libvpx",
                    "-an", str(video)], check=True)
    state = BeatState()
    state.publish(Estimate(150, 0.9, time.time(), 0.1))
    server, url = serve(state, video)
    page = browser.new_page()
    try:
        page.goto(url)
        page.wait_for_function("window.bananaBridge && bananaBridge.targets.length && "
                               "bananaBridge.targets[0].element.readyState >= 2")
        page.wait_for_function("!bananaBridge.targets[0].element.paused")
        rate = page.evaluate("bananaBridge.targets[0].element.playbackRate")
        assert 1.18 <= rate <= 1.32
        state.publish(Estimate(90, 0.9, time.time(), 0.1))
        page.wait_for_function("bananaBridge.targets[0].element.playbackRate < 0.8")
        server.shutdown()
        server.server_close()
        page.wait_for_function("bananaBridge.targets[0].element.paused", timeout=5000)
    finally:
        page.close()
        server.shutdown()
        server.server_close()
