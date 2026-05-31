param(
    [string]$SteamPath = "",
    [string]$PluginName = "AchievementBackup",
    [string]$Repo = "Yuykkk/AchievementBackup",
    [string]$Branch = "main",
    [switch]$NoRestart
)

$ErrorActionPreference = "Stop"

function Write-ABHeader {
    Clear-Host
    Write-Host ""
    Write-Host "  ===============================================" -ForegroundColor Cyan
    Write-Host "        AchievementBackup - Instalador" -ForegroundColor White
    Write-Host "        Backups, capturas e saves da Steam" -ForegroundColor DarkGray
    Write-Host "  ===============================================" -ForegroundColor Cyan
    Write-Host ""
}

function Write-ABStep {
    param([string]$Text)
    Write-Host "  > " -NoNewline -ForegroundColor Cyan
    Write-Host $Text -ForegroundColor White
}

function Write-ABOk {
    param([string]$Text)
    Write-Host "  OK " -NoNewline -ForegroundColor Green
    Write-Host $Text -ForegroundColor DarkGray
}

function Write-ABWarn {
    param([string]$Text)
    Write-Host "  !  " -NoNewline -ForegroundColor Yellow
    Write-Host $Text -ForegroundColor Yellow
}

function Test-SteamRoot {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) { return $false }
    try {
        $full = [System.IO.Path]::GetFullPath(($Path -replace "/", "\"))
        return Test-Path (Join-Path $full "steam.exe")
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
        "E:\Steam",
        "F:\steam",
        "F:\Steam"
    )) {
        if ($path) { $candidates.Add($path) }
    }

    foreach ($candidate in $candidates | Select-Object -Unique) {
        if (Test-SteamRoot $candidate) {
            return [System.IO.Path]::GetFullPath(($candidate -replace "/", "\"))
        }
    }

    throw "Nao consegui encontrar a pasta da Steam automaticamente. Rode com -SteamPath `"D:\steam`"."
}

function Restart-Steam {
    param([string]$Root)
    $steamExe = Join-Path $Root "steam.exe"
    if (-not (Test-Path $steamExe)) {
        Write-ABWarn "steam.exe nao encontrado em $Root. Instalei o plugin, mas nao consegui abrir a Steam."
        return
    }

    Write-ABStep "Reiniciando a Steam para carregar o plugin..."
    Get-Process steam,steamwebhelper,steamerrorreporter -ErrorAction SilentlyContinue |
        Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3
    Start-Process -FilePath $steamExe -WorkingDirectory $Root | Out-Null
    Start-Sleep -Seconds 3
    Write-ABOk "Steam aberta novamente."
}

function Copy-PluginFiles {
    param(
        [string]$Source,
        [string]$Target
    )

    if (-not (Test-Path (Join-Path $Source "plugin.json"))) {
        throw "A pasta baixada nao contem plugin.json: $Source"
    }

    $items = Get-ChildItem -LiteralPath $Source -Force
    if (-not $items -or $items.Count -eq 0) {
        throw "A pasta baixada esta vazia: $Source"
    }

    foreach ($item in $items) {
        Copy-Item -LiteralPath $item.FullName -Destination $Target -Recurse -Force
    }

    if (-not (Test-Path (Join-Path $Target "plugin.json"))) {
        throw "Instalacao incompleta: plugin.json nao foi copiado para $Target"
    }
}

function Find-PluginsDir {
    param([string]$Root)

    $modern = Join-Path $Root "millennium\plugins"
    $legacy = Join-Path $Root "plugins"

    if (Test-Path (Join-Path $Root "millennium")) {
        return $modern
    }
    if (Test-Path $modern) {
        return $modern
    }
    return $legacy
}

function Preserve-PluginData {
    param(
        [string]$TempRoot,
        [string]$Target,
        [string]$LegacyTarget,
        [string[]]$Names
    )

    foreach ($name in $Names) {
        foreach ($base in @($Target, $LegacyTarget)) {
            if ([string]::IsNullOrWhiteSpace($base)) { continue }
            $existing = Join-Path $base $name
            if (Test-Path $existing) {
                $safeBase = (($base -replace "[:\\\/]", "_") -replace "__+", "_")
                $saved = Join-Path $TempRoot ("preserve-" + $safeBase + "-" + $name)
                Copy-Item -LiteralPath $existing -Destination $saved -Recurse -Force
            }
        }
    }
}

function Restore-PluginData {
    param(
        [string]$TempRoot,
        [string]$Target,
        [string[]]$Names
    )

    foreach ($name in $Names) {
        $matches = Get-ChildItem -LiteralPath $TempRoot -Force -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -like ("preserve-*-" + $name) } |
            Sort-Object LastWriteTime -Descending
        foreach ($match in $matches) {
            $destination = Join-Path $Target $name
            if ($match.PSIsContainer) {
                New-Item -ItemType Directory -Force -Path $destination | Out-Null
                Get-ChildItem -LiteralPath $match.FullName -Force | ForEach-Object {
                    Copy-Item -LiteralPath $_.FullName -Destination $destination -Recurse -Force
                }
            } else {
                Copy-Item -LiteralPath $match.FullName -Destination $destination -Force
            }
            break
        }
    }
}

Write-ABHeader

$SteamPath = Find-SteamPath
$pluginsDir = Find-PluginsDir -Root $SteamPath
$legacyPluginsDir = Join-Path $SteamPath "plugins"
$target = Join-Path $pluginsDir $PluginName
$legacyTarget = Join-Path $legacyPluginsDir $PluginName
$tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("achievementbackup-install-" + [guid]::NewGuid().ToString("N"))
$zip = Join-Path $tmp "plugin.zip"
$url = "https://github.com/$Repo/archive/refs/heads/$Branch.zip"

Write-ABStep "Steam detectada em:"
Write-Host "    $SteamPath" -ForegroundColor DarkGray
Write-ABStep "Plugin sera instalado em:"
Write-Host "    $target" -ForegroundColor DarkGray
if ($pluginsDir -ne $legacyPluginsDir) {
    Write-ABOk "Millennium novo detectado: usando millennium\plugins."
}
Write-Host ""

New-Item -ItemType Directory -Force -Path $tmp | Out-Null
New-Item -ItemType Directory -Force -Path $pluginsDir | Out-Null

try {
    Write-ABStep "Baixando a versao mais recente do GitHub..."
    Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
    Write-ABOk "Download concluido."

    Write-ABStep "Extraindo arquivos..."
    Expand-Archive -Path $zip -DestinationPath $tmp -Force
    $repoRoot = Get-ChildItem -Path $tmp -Directory | Where-Object { $_.Name -like "AchievementBackup-*" } | Select-Object -First 1
    if (-not $repoRoot) { throw "Pacote baixado sem pasta AchievementBackup." }
    $source = Join-Path $repoRoot.FullName "AchievementBackup"
    if (-not (Test-Path $source)) { $source = $repoRoot.FullName }
    Write-ABOk "Arquivos extraidos."

    Write-ABStep "Preservando configuracoes, backups e logs existentes..."
    $preserve = @("profile", "backups", "logs", "cache", "log.txt")
    Preserve-PluginData -TempRoot $tmp -Target $target -LegacyTarget $legacyTarget -Names $preserve

    Write-ABStep "Instalando o plugin..."
    New-Item -ItemType Directory -Force -Path $target | Out-Null
    Copy-PluginFiles -Source $source -Target $target

    Restore-PluginData -TempRoot $tmp -Target $target -Names $preserve
    Write-ABOk "AchievementBackup instalado."
    Write-ABOk "Manifest encontrado: $(Join-Path $target "plugin.json")"

    if ($NoRestart) {
        Write-ABWarn "Instalacao concluida sem reiniciar. Abra/reinicie a Steam manualmente para carregar o plugin."
    } else {
        Restart-Steam -Root $SteamPath
    }

    Write-Host ""
    Write-Host "  ===============================================" -ForegroundColor Cyan
    Write-Host "     Pronto! AchievementBackup esta instalado." -ForegroundColor Green
    Write-Host "  ===============================================" -ForegroundColor Cyan
    Write-Host ""
} finally {
    Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
}
