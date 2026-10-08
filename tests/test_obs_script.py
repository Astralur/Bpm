"""Execute the OBS Lua script in LuaJIT with API stubs.

This verifies generated HTML and file selection, not OBS/CEF itself.
"""
import json
import re
import shutil
from pathlib import Path

from lupa.luajit21 import LuaRuntime
import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def obs_script(tmp_path):
    scripts = tmp_path / "obs"
    web = tmp_path / "web"
    scripts.mkdir()
    web.mkdir()
    for name in ("local-overlay.html", "bridge.js"):
        shutil.copyfile(ROOT / "web" / name, web / name)
    runtime = LuaRuntime(unpack_returned_tuples=True)
    runtime.globals().script_path = lambda: str(scripts) + "/"
    runtime.execute("""
        obslua = {LOG_WARNING=1, OBS_TEXT_DEFAULT=1, OBS_PATH_FILE=1}
        buttons = {}; paths = {}; logs = {}; existing_source = {id='browser_source'}
        function obslua.script_log(level, message) table.insert(logs, message) end
        function obslua.obs_get_source_by_name(name) return existing_source end
        function obslua.obs_source_get_id(source) return source.id end
        function obslua.obs_source_release(source) end
        function obslua.obs_data_create() return {} end
        function obslua.obs_data_release(data) end
        function obslua.obs_data_set_string(data, key, value) data[key] = value end
        function obslua.obs_data_set_bool(data, key, value) data[key] = value end
        function obslua.obs_data_set_int(data, key, value) data[key] = value end
        obslua.obs_data_set_default_string = obslua.obs_data_set_string
        obslua.obs_data_set_default_int = obslua.obs_data_set_int
        function obslua.obs_data_get_string(data, key) return data[key] or '' end
        function obslua.obs_data_get_int(data, key) return data[key] or 0 end
        function obslua.obs_source_update(source, settings) updated = settings end
        function obslua.obs_frontend_get_current_scene() return {id='scene'} end
        function obslua.obs_scene_from_source(source) return source end
        function obslua.obs_source_create(id, name, settings, hotkeys)
            updated = settings; return {id=id, name=name}
        end
        function obslua.obs_scene_add(scene, source) added = source end
        function obslua.obs_properties_create() return {} end
        function obslua.obs_properties_add_text(...) end
        function obslua.obs_properties_add_int(...) end
        function obslua.obs_properties_add_path(props, name, label, kind, filter, default)
            paths[name] = {kind=kind, filter=filter}
        end
        function obslua.obs_properties_add_button(props, name, label, callback)
            buttons[name] = callback
        end
    """)
    runtime.execute((ROOT / "obs" / "banana_bpm.lua").read_text())
    settings = runtime.table()
    runtime.globals().script_defaults(settings)
    runtime.globals().script_properties()
    return runtime, settings, scripts


def connect(runtime, settings):
    runtime.globals().script_update(settings)
    runtime.globals().buttons["connect"]()


def test_picker_generates_page_for_selected_video_and_reloads_on_change(obs_script, tmp_path):
    runtime, settings, scripts = obs_script
    first = tmp_path / "plátano con espacios #100%.webm"
    first.write_bytes(b"local video fixture")
    settings["overlay_file"] = str(first)
    settings["port"] = 8877
    settings["phase_ms"] = 250
    assert runtime.globals().paths["overlay_file"]["kind"] == 1
    connect(runtime, settings)
    update = runtime.globals().updated
    assert update["is_local_file"]
    path = Path(update["local_file"])
    assert path.parent == scripts
    html = path.read_text()
    url = json.loads(re.search(r"video.src = (.*);", html)[1])
    assert url == first.as_uri()
    assert 'url:"http://127.0.0.1:8877"' in html
    assert "baseBpm:120, phaseOffset:0.25" in html
    assert "__BRIDGE_SCRIPT__" not in html
    # The connector's documentation comment must not close the script early.
    assert html.count("</script>") == 2
    second = tmp_path / "otro vídeo.mp4"
    second.write_bytes(b"other video")
    settings["overlay_file"] = str(second)
    connect(runtime, settings)
    new_path = Path(runtime.globals().updated["local_file"])
    assert new_path != path
    assert second.as_uri() in new_path.read_text()


@pytest.mark.parametrize("selection", ["", "missing.mp4", "wrong.gif"])
def test_invalid_selection_preserves_existing_source(obs_script, selection):
    runtime, settings, _ = obs_script
    settings["overlay_file"] = selection
    connect(runtime, settings)
    assert runtime.globals().updated is None
    assert len(runtime.globals().logs) == 1


def test_creates_browser_source_without_replacing_media_source(obs_script, tmp_path):
    runtime, settings, _ = obs_script
    video = tmp_path / "banana.webm"
    video.write_bytes(b"fixture")
    settings["overlay_file"] = str(video)
    runtime.globals().existing_source = runtime.table(id="ffmpeg_source")
    connect(runtime, settings)
    assert runtime.globals().updated is None
    runtime.globals().existing_source = None
    connect(runtime, settings)
    assert runtime.globals().added["id"] == "browser_source"
    assert runtime.globals().updated["is_local_file"]
