param(
    [string]$SteamPath = "",
    [string]$PluginName = "AchievementBackup",
    [string]$Repo = "Yuykkk/AchievementBackup",
    [string]$Branch = "main"
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($SteamPath)) {
    try {
        $SteamPath = (Get-ItemProperty -Path "HKCU:\Software\Valve\Steam" -Name "SteamPath").SteamPath
    } catch {
        $SteamPath = "C:\Program Files (x86)\Steam"
    }
}

$SteamPath = [System.IO.Path]::GetFullPath($SteamPath)
$pluginsDir = Join-Path $SteamPath "plugins"
$target = Join-Path $pluginsDir $PluginName
$tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("achievementbackup-install-" + [guid]::NewGuid().ToString("N"))
$zip = Join-Path $tmp "plugin.zip"
$url = "https://github.com/$Repo/archive/refs/heads/$Branch.zip"

Write-Host "AchievementBackup installer"
Write-Host "Steam: $SteamPath"
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
