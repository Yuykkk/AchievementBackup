param(
    [string]$SteamPath = "",
    [string]$PluginName = "AchievementBackup",
    [string]$Repo = "Yuykkk/AchievementBackup",
    [string]$Branch = "main"
)

$ErrorActionPreference = "Stop"

function Test-SteamRoot {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) { return $false }
    try {
        $full = [System.IO.Path]::GetFullPath(($Path -replace "/", "\"))
        return (Test-Path (Join-Path $full "steam.exe")) -or (Test-Path (Join-Path $full "steamapps"))
    } catch {
        return $false
    }
}

function Find-SteamPath {
    $candidates = New-Object System.Collections.Generic.List[string]

    if (-not [string]::IsNullOrWhiteSpace($SteamPath)) {
        $candidates.Add($SteamPath)
    }

    foreach ($regPath in @("HKCU:\Software\Valve\Steam", "HKLM:\SOFTWARE\WOW6432Node\Valve\Steam", "HKLM:\SOFTWARE\Valve\Steam")) {
        try {
            $props = Get-ItemProperty -Path $regPath -ErrorAction Stop
            foreach ($name in @("SteamPath", "InstallPath")) {
                if ($props.$name) { $candidates.Add($props.$name) }
            }
        } catch {}
    }

    try {
        $proc = Get-Process steam -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($proc -and $proc.Path) {
            $candidates.Add((Split-Path -Parent $proc.Path))
        }
    } catch {}

    foreach ($path in @(
        "$env:ProgramFiles(x86)\Steam",
        "$env:ProgramFiles\Steam",
        "C:\Steam",
        "D:\steam",
        "D:\Steam",
        "E:\steam",
        "E:\Steam"
    )) {
        if ($path) { $candidates.Add($path) }
    }

    foreach ($candidate in $candidates | Select-Object -Unique) {
        if (Test-SteamRoot $candidate) {
            return [System.IO.Path]::GetFullPath(($candidate -replace "/", "\"))
        }
    }

    throw "Nao consegui encontrar a pasta da Steam automaticamente. Rode novamente com -SteamPath `"D:\steam`"."
}

$SteamPath = Find-SteamPath
$pluginsDir = Join-Path $SteamPath "plugins"
$target = Join-Path $pluginsDir $PluginName
$tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("achievementbackup-install-" + [guid]::NewGuid().ToString("N"))
$zip = Join-Path $tmp "plugin.zip"
$url = "https://github.com/$Repo/archive/refs/heads/$Branch.zip"

Write-Host "AchievementBackup installer"
Write-Host "Steam detectada: $SteamPath"
Write-Host "Destino: $target"

New-Item -ItemType Directory -Force -Path $tmp | Out-Null
New-Item -ItemType Directory -Force -Path $pluginsDir | Out-Null

try {
    Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
    Expand-Archive -Path $zip -DestinationPath $tmp -Force
    $repoRoot = Get-ChildItem -Path $tmp -Directory | Where-Object { $_.Name -like "AchievementBackup-*" } | Select-Object -First 1
    if (-not $repoRoot) { throw "Pacote baixado sem pasta AchievementBackup." }
    $source = Join-Path $repoRoot.FullName "AchievementBackup"
    if (-not (Test-Path $source)) { $source = $repoRoot.FullName }

    $preserve = @("profile", "backups", "logs", "cache")
    foreach ($name in $preserve) {
        $existing = Join-Path $target $name
        if (Test-Path $existing) {
            $saved = Join-Path $tmp ("preserve-" + $name)
            Copy-Item -LiteralPath $existing -Destination $saved -Recurse -Force
        }
    }

    New-Item -ItemType Directory -Force -Path $target | Out-Null
    Copy-Item -LiteralPath (Join-Path $source "*") -Destination $target -Recurse -Force

    foreach ($name in $preserve) {
        $saved = Join-Path $tmp ("preserve-" + $name)
        if (Test-Path $saved) {
            Copy-Item -LiteralPath $saved -Destination (Join-Path $target $name) -Recurse -Force
        }
    }

    Write-Host "Instalado com sucesso."
    Write-Host "Reinicie a Steam para carregar o plugin."
} finally {
    Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
}
