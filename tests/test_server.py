import json
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from bpm_bridge.detector import Estimate
from bpm_bridge.server import make_server
from bpm_bridge.state import BeatState


@pytest.fixture
def running_server():
    state = BeatState(offset_ms=75)
    server = make_server(state, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield state, f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def test_publishes_rate_phase_and_cors(running_server):
    state, url = running_server
    beat = time.time()
    state.publish(Estimate(150, 0.9, beat, 0.1))
    with urlopen(url + "/state") as response:
        data = json.load(response)
        assert response.headers["Access-Control-Allow-Origin"] == "*"
    assert data["playback_rate"] == 1.25
    assert data["beat_at"] == pytest.approx(beat + 0.075)
    assert data["audio_active"]
    with state.lock:
        state.data["updated_at"] -= 4
    assert not state.snapshot()["audio_active"]
    assert state.snapshot()["status"] == "stale"


def test_static_routes_range_and_path_traversal(running_server):
    _, url = running_server
    with urlopen(url) as response:
        assert "Plátano" in response.read().decode()
    request = Request(url + "/bridge.js", headers={"Range": "bytes=0-9"})
    with urlopen(request) as response:
        assert response.status == 206
        assert len(response.read()) == 10
    with pytest.raises(HTTPError) as error:
        urlopen(url + "/../requirements.txt")
    assert error.value.code == 404
    with pytest.raises(HTTPError) as error:
        urlopen(Request(url + "/bridge.js", headers={"Range": "bytes=99999999-"}))
    assert error.value.code == 416


def test_silence_deactivates_animation(running_server):
    state, url = running_server
    state.publish(Estimate(120, 0.9, time.time(), 0.1))
    state.unavailable("silent")
    with urlopen(url + "/state") as response:
        data = json.load(response)
    assert data["status"] == "silent"
    assert not data["audio_active"]


def test_unsupported_asset_fails_explicitly(tmp_path):
    gif = tmp_path / "banana.gif"
    gif.write_bytes(b"GIF89a")
    with pytest.raises(ValueError, match="Convert animated GIFs"):
        make_server(BeatState(), port=0, banana=gif)
