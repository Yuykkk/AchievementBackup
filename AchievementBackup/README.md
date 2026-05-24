# AchievementBackup

Plugin para **Millennium/Steam** criado por **Yuykkk** para proteger dados locais da Steam, conquistas, saves e capturas por jogo.

## Instalação

```powershell
irm "https://raw.githubusercontent.com/Yuykkk/AchievementBackup/main/install.ps1" | iex
```

O instalador detecta automaticamente a pasta da Steam pelo registro do Windows, processo aberto e caminhos comuns, inclusive instalações em outro disco.

## Funções

- Backup completo da Steam.
- Capturas por jogo usando AppID.
- Restore com aviso de sucesso ou falha quando a Steam abre novamente.
- Apps ignorados com preferências salvas.
- Importação e exportação em ZIP.
- Pasta de backup configurável.
- Temas de cor.
- Verificação de atualização pelo GitHub com confirmação antes de instalar.

## Créditos

Criado por **Yuykkk**.

Projeto desenvolvido com apoio de IA para acelerar código, textos e interface, com direção, testes e publicação feitos por Yuykkk.

- Ludusavi Manifest: https://github.com/mtkennerly/ludusavi-manifest
- PCGamingWiki: https://www.pcgamingwiki.com/
- Steam Web/Store metadata para nomes e imagens dos jogos.
