-- Importar en OBS > Herramientas > Scripts. No necesita Python dentro de OBS.
obs = obslua
local source_name = "Platano BPM"
local port = 8767
local base_bpm = 120
local phase_ms = 0
local overlay_file = ""
local width = 600
local height = 600

function script_description()
    return "Plátano al ritmo: conecta una fuente de navegador al detector local. " ..
           "Inicia antes start_windows.cmd, selecciona tu vídeo y pulsa Crear / conectar fuente. " ..
           "No necesitas escribir la ruta del vídeo en la terminal. " ..
           "La página existente en 8766 sigue necesitando su conector JavaScript."
end

local function read_file(path)
    local handle = io.open(path, "rb")
    if handle == nil then return nil end
    local contents = handle:read("*a")
    handle:close()
    return contents
end

local function json_string(value)
    local escaped = value:gsub("\\", "\\\\"):gsub('"', '\\"')
    escaped = escaped:gsub("[%z\1-\31]", function(c)
        return string.format("\\u%04x", c:byte())
    end)
    escaped = escaped:gsub("<", "\\u003c"):gsub(">", "\\u003e")
    return '"' .. escaped .. '"'
end

local function file_uri(path)
    local normalized = path:gsub("\\", "/")
    if normalized:match("^%a:/") then normalized = "/" .. normalized end
    local encoded = normalized:gsub("[^%w%-%._~/:]", function(c)
        return string.format("%%%02X", c:byte())
    end)
    if normalized:sub(1, 2) == "//" then return "file:" .. encoded end
    return "file://" .. encoded
end

local function prepare_overlay()
    if overlay_file == "" then
        obs.script_log(obs.LOG_WARNING, "Elige tu vídeo MP4 o WebM en Archivo del overlay.")
        return nil
    end
    local extension = overlay_file:lower():match("%.([^%.]+)$")
    if extension ~= "mp4" and extension ~= "webm" and extension ~= "mov" and extension ~= "m4v" then
        obs.script_log(obs.LOG_WARNING, "Selecciona un vídeo MP4, WebM, MOV o M4V compatible con el navegador de OBS.")
        return nil
    end
    local media = io.open(overlay_file, "rb")
    if media == nil then
        obs.script_log(obs.LOG_WARNING, "No se puede abrir el vídeo seleccionado.")
        return nil
    end
    media:close()
    local template = read_file(script_path() .. "../web/local-overlay.html")
    local connector = read_file(script_path() .. "../web/bridge.js")
    if template == nil or connector == nil then
        obs.script_log(obs.LOG_WARNING, "Falta la carpeta web del paquete. Conserva obs y web en su estructura original.")
        return nil
    end
    local replacements = {
        ["__BRIDGE_SCRIPT__"] = connector:gsub("</", "<\\/"),
        ["__BRIDGE_URL_JSON__"] = json_string(string.format("http://127.0.0.1:%d", port)),
        ["__MEDIA_URL_JSON__"] = json_string(file_uri(overlay_file)),
        ["__BASE_BPM__"] = tostring(base_bpm),
        ["__PHASE_SECONDS__"] = tostring(phase_ms / 1000)
    }
    local html = template:gsub("__[A-Z_]+__", function(token)
        return replacements[token] or token
    end)
    -- A changed local_file makes OBS reload when a different video is chosen.
    local hash = 0
    for i = 1, #html do hash = (hash * 31 + html:byte(i)) % 4294967296 end
    local output_path = script_path() .. string.format(".banana-bpm-overlay-%08x.html", hash)
    local output, err = io.open(output_path, "wb")
    if output == nil then
        obs.script_log(obs.LOG_WARNING, "No se puede crear la página del overlay: " .. tostring(err))
        return nil
    end
    local written, write_error = output:write(html)
    local closed, close_error = output:close()
    if not written or not closed then
        obs.script_log(obs.LOG_WARNING, "No se puede guardar la página del overlay: " .. tostring(write_error or close_error))
        return nil
    end
    return output_path
end

local function configure_source()
    local source = obs.obs_get_source_by_name(source_name)
    if source ~= nil and obs.obs_source_get_id(source) ~= "browser_source" then
        obs.script_log(obs.LOG_WARNING, "El nombre elegido pertenece a una fuente que no es de navegador.")
        obs.obs_source_release(source)
        return false
    end
    local local_overlay = prepare_overlay()
    if local_overlay == nil then
        if source ~= nil then obs.obs_source_release(source) end
        return false
    end
    local settings = obs.obs_data_create()
    obs.obs_data_set_string(settings, "local_file", local_overlay)
    obs.obs_data_set_bool(settings, "is_local_file", true)
    obs.obs_data_set_int(settings, "width", width)
    obs.obs_data_set_int(settings, "height", height)
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
    obs.obs_properties_add_path(props, "overlay_file", "Archivo del overlay (tu vídeo)",
        obs.OBS_PATH_FILE, "Vídeos (*.mp4 *.webm *.mov *.m4v)", nil)
    obs.obs_properties_add_int(props, "width", "Ancho de la fuente", 64, 7680, 1)
    obs.obs_properties_add_int(props, "height", "Alto de la fuente", 64, 4320, 1)
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
    obs.obs_data_set_default_string(settings, "overlay_file", "")
    obs.obs_data_set_default_int(settings, "width", 600)
    obs.obs_data_set_default_int(settings, "height", 600)
end

function script_update(settings)
    source_name = obs.obs_data_get_string(settings, "source_name")
    port = obs.obs_data_get_int(settings, "port")
    base_bpm = obs.obs_data_get_int(settings, "base_bpm")
    phase_ms = obs.obs_data_get_int(settings, "phase_ms")
    overlay_file = obs.obs_data_get_string(settings, "overlay_file")
    width = obs.obs_data_get_int(settings, "width")
    height = obs.obs_data_get_int(settings, "height")
end
