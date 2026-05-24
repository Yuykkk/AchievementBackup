# AchievementBackup

Plugin para Millennium/Steam criado por **Yuykkk** para proteger dados locais da Steam, conquistas, saves e capturas por jogo.

## Funções

- Backup completo da Steam.
- Capturas por jogo usando AppID.
- Apps ignorados com preferências salvas.
- Importação e exportação em ZIP.
- Pasta de backup configurável.
- Temas de cor.
- Verificação de atualização pelo GitHub com confirmação antes de instalar.

## Instalação

```powershell
irm "https://raw.githubusercontent.com/Yuykkk/AchievementBackup/main/install.ps1" | iex
```

Com Steam em outro caminho:

```powershell
$p="$env:TEMP\AchievementBackup-install.ps1"; iwr "https://raw.githubusercontent.com/Yuykkk/AchievementBackup/main/install.ps1" -OutFile $p -UseB; powershell -NoProfile -ExecutionPolicy Bypass -File $p -SteamPath "D:\steam"
```

## O que pode ser salvo

- `appcache/stats`: conquistas e estatísticas locais.
- `userdata`: saves e preferências da conta Steam.
- `config/stplug-in`: lista e configurações locais dos jogos.
- Caminhos conhecidos de saves no Windows, como `Documentos` e `AppData`, quando o manifest Ludusavi/PCGamingWiki estiver ativado.

## Créditos

- Ludusavi Manifest: https://github.com/mtkennerly/ludusavi-manifest
- PCGamingWiki: https://www.pcgamingwiki.com/
- Steam Web/Store metadata para nomes e imagens dos jogos.

Criado por **Yuykkk**.
