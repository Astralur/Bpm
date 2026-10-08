-- Importar en OBS > Herramientas > Scripts. No necesita Python dentro de OBS.
obs = obslua
local source_name = "Platano BPM"
local port = 8767
local base_bpm = 120
local phase_ms = 0

function script_description()
    return "Plátano al ritmo: conecta una fuente de navegador al detector local. " ..
           "Inicia antes el puente Python. Puede servir tu MP4/WebM con --banana. " ..
           "La página existente en 8766 sigue necesitando su conector JavaScript."
end

local function configure_source()
    local source = obs.obs_get_source_by_name(source_name)
    if source ~= nil and obs.obs_source_get_id(source) ~= "browser_source" then
        obs.script_log(obs.LOG_WARNING, "El nombre elegido pertenece a una fuente que no es de navegador.")
        obs.obs_source_release(source)
        return false
    end
    local settings = obs.obs_data_create()
    obs.obs_data_set_string(settings, "url", string.format(
        "http://127.0.0.1:%d/?base=%d&phase=%d", port, base_bpm, phase_ms))
    obs.obs_data_set_bool(settings, "is_local_file", false)
    obs.obs_data_set_int(settings, "width", 600)
    obs.obs_data_set_int(settings, "height", 600)
    obs.obs_data_set_bool(settings, "shutdown", false)
    obs.obs_data_set_bool(settings, "restart_when_active", false)
    if source ~= nil then
        obs.obs_source_update(source, settings)
        obs.obs_source_release(source)
    else
        local scene_source = obs.obs_frontend_get_current_scene()
        if scene_source == nil then
            obs.obs_data_release(settings)
            obs.script_log(obs.LOG_WARNING, "Selecciona una escena antes de crear la fuente.")
            return false
        end
        source = obs.obs_source_create("browser_source", source_name, settings, nil)
        if source ~= nil then
            local scene = obs.obs_scene_from_source(scene_source)
            obs.obs_scene_add(scene, source)
            obs.obs_source_release(source)
        else
            obs.script_log(obs.LOG_WARNING, "OBS no pudo crear la fuente de navegador.")
        end
        obs.obs_source_release(scene_source)
    end
    obs.obs_data_release(settings)
    return false
end

function script_properties()
    local props = obs.obs_properties_create()
    obs.obs_properties_add_text(props, "source_name", "Fuente de navegador (crea o actualiza)", obs.OBS_TEXT_DEFAULT)
    obs.obs_properties_add_int(props, "port", "Puerto del puente", 1024, 65535, 1)
    obs.obs_properties_add_int(props, "base_bpm", "BPM de la animación a velocidad normal", 30, 300, 1)
    obs.obs_properties_add_int(props, "phase_ms", "Posición del bote en el vídeo (ms)", 0, 60000, 1)
    obs.obs_properties_add_button(props, "connect", "Crear / conectar fuente", configure_source)
    return props
end

function script_defaults(settings)
    obs.obs_data_set_default_string(settings, "source_name", "Platano BPM")
    obs.obs_data_set_default_int(settings, "port", 8767)
    obs.obs_data_set_default_int(settings, "base_bpm", 120)
    obs.obs_data_set_default_int(settings, "phase_ms", 0)
end

function script_update(settings)
    source_name = obs.obs_data_get_string(settings, "source_name")
    port = obs.obs_data_get_int(settings, "port")
    base_bpm = obs.obs_data_get_int(settings, "base_bpm")
    phase_ms = obs.obs_data_get_int(settings, "phase_ms")
end
