local millennium = require("millennium")

local runner_pid = ""

local function q(value)
  value = tostring(value or "")
  return '"' .. value:gsub("\\", "\\\\"):gsub('"', '\\"') .. '"'
end

local function plugin_root()
  local source = debug.getinfo(1, "S").source or ""
  source = source:gsub("^@", ""):gsub("\\", "/")
  return source:gsub("/backend/main%.lua$", "")
end

local function steam_path()
  local ok, value = pcall(millennium.steam_path)
  if ok and value and tostring(value) ~= "" then
    return tostring(value):gsub("/", "\\")
  end
  return ""
end

local function ensure_ui(root, steam)
  local source = root .. "\\public\\index.js"
  local target_dir = steam .. "\\steamui\\AchievementBackup"
  local target = target_dir .. "\\index.js"
  os.execute('powershell.exe -NoProfile -WindowStyle Hidden -Command "New-Item -ItemType Directory -Force -Path ' .. q(target_dir) .. ' | Out-Null; Copy-Item -LiteralPath ' .. q(source) .. ' -Destination ' .. q(target) .. ' -Force"')
  millennium.add_browser_js("AchievementBackup/index.js")
end

local function start_python_runner(root, steam)
  local runner = root .. "\\backend\\runner.py"
  local pid_file = root .. "\\logs\\runner.pid"
  local log_file = root .. "\\logs\\runner-launch.log"
  local err_file = root .. "\\logs\\runner-error.log"
  local command = table.concat({
    "$ErrorActionPreference='SilentlyContinue';",
    "New-Item -ItemType Directory -Force -Path " .. q(root .. "\\logs") .. " | Out-Null;",
    "$env:ACHIEVEMENTBACKUP_STEAM_PATH=" .. q(steam) .. ";",
    "$script=" .. q(runner) .. ";",
    "$log=" .. q(log_file) .. ";",
    "$err=" .. q(err_file) .. ";",
    "$p = Start-Process -FilePath 'py' -ArgumentList @('-3', $script) -WorkingDirectory " .. q(root .. "\\backend") .. " -WindowStyle Hidden -RedirectStandardOutput $log -RedirectStandardError $err -PassThru;",
    "if ($p) { Set-Content -LiteralPath " .. q(pid_file) .. " -Value $p.Id -Encoding ASCII }"
  }, " ")
  os.execute("powershell.exe -NoProfile -ExecutionPolicy Bypass -Command " .. q(command))
  local f = io.open(pid_file, "rb")
  if f then
    runner_pid = f:read("*a") or ""
    f:close()
  end
end

local function stop_python_runner()
  if runner_pid and runner_pid:match("%d+") then
    os.execute('powershell.exe -NoProfile -WindowStyle Hidden -Command "Stop-Process -Id ' .. runner_pid:gsub("%D", "") .. ' -Force -ErrorAction SilentlyContinue"')
  end
end

function frontend_log(args)
  local message = ""
  if type(args) == "table" then
    message = tostring(args[1] or args.message or "")
  else
    message = tostring(args or "")
  end
  print("[AchievementBackup:Frontend] " .. message)
  return '{"ok":true}'
end

local function on_load()
  local root = plugin_root():gsub("/", "\\")
  local steam = steam_path()
  if steam ~= "" then
    ensure_ui(root, steam)
  end
  start_python_runner(root, steam)
  millennium.ready()
end

local function on_unload()
  stop_python_runner()
end

return {
  on_load = on_load,
  on_unload = on_unload,
  frontend_log = frontend_log
}
