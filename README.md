# AchievementBackup

Um plugin para Millennium/Steam criado por **Yuykkk** para proteger dados locais da Steam, conquistas, saves e capturas por jogo.

AchievementBackup foi feito para quem quer formatar o PC, reinstalar a Steam, testar jogos ou guardar estados importantes sem depender só da nuvem.

## Destaques

- **Backup completo da Steam** com dados locais importantes.
- **Capturas por jogo** usando AppID, para restaurar só um jogo específico.
- **Lista de apps ignorados** com salvamento automático das preferências.
- **Importação e exportação em ZIP** para levar seus backups para outro PC.
- **Pasta de backup configurável**, ou uso do caminho padrão dentro do plugin.
- **Temas de cor** para personalizar o painel.
- **Atualização automática pelo GitHub**.
- **Imagens dos jogos** usando metadados públicos da Steam.

## Instalação rápida

Requisito: Steam com [Millennium](https://steambrew.app/) instalado.

Abra o PowerShell e execute:

```powershell
iwr https://raw.githubusercontent.com/Yuykkk/AchievementBackup/main/install.ps1 -UseB | iex
```

Se sua Steam estiver em outro caminho:

```powershell
& ([scriptblock]::Create((iwr https://raw.githubusercontent.com/Yuykkk/AchievementBackup/main/install.ps1 -UseB).Content)) -SteamPath "D:\steam"
```

Depois reinicie a Steam e abra o AchievementBackup pelo botão do plugin.

## O que o plugin salva

AchievementBackup organiza dois tipos principais de proteção:

| Tipo | O que faz |
| --- | --- |
| Backup completo | Salva o pacote principal da Steam, incluindo conquistas, estatísticas, saves e configurações locais. |
| Captura por jogo | Salva somente os arquivos ligados a um AppID, ideal para restaurar um jogo sem mexer no resto. |

Fontes usadas no backup:

- `appcache/stats`: conquistas e estatísticas locais.
- `userdata`: saves, preferências e dados vinculados à conta Steam.
- `config/stplug-in`: lista, estado e configurações locais usadas pela Steam.
- Caminhos conhecidos de saves no Windows, como `Documentos` e `AppData`, quando o manifest Ludusavi/PCGamingWiki estiver ativado.

## Importar e exportar

Use **Exportar tudo** para gerar um arquivo `.zip` com backups completos e capturas por jogo.

Use **Importar** para adicionar um `.zip` exportado anteriormente sem apagar seus backups atuais.

Essa função é útil para:

- mover dados para outro PC;
- guardar uma cópia fora da pasta da Steam;
- restaurar capturas depois de reinstalar o plugin.

## Atualização

O plugin verifica este repositório quando a Steam abre e depois periodicamente. Quando encontra uma versão mais nova em `plugin.json`, ele mostra a versão instalada e a versão disponível, pergunta se você quer atualizar naquele momento e só então baixa o pacote do GitHub.

Depois da instalação, a Steam é reiniciada para carregar os arquivos novos. Na próxima abertura, o plugin mostra uma mensagem confirmando de qual versão para qual versão ele atualizou.

Durante a atualização, ele preserva:

- `profile`;
- `backups`;
- `logs`;
- `cache`;
- configurações locais.

Para o auto update funcionar, este repositório precisa estar público ou acessível pelo GitHub raw.

## Créditos da API/manifest

AchievementBackup usa dados públicos para localizar saves e exibir informações dos jogos:

- [Ludusavi Manifest](https://github.com/mtkennerly/ludusavi-manifest): caminhos conhecidos de saves por jogo/AppID.
- [PCGamingWiki](https://www.pcgamingwiki.com/): base comunitária usada pelo ecossistema do Ludusavi.
- Steam Web/Store metadata: nomes e imagens públicas dos jogos.

O manifest do Ludusavi é distribuído sob licença MIT. Consulte o repositório original para detalhes.

## Autor

Criado por **Yuykkk**.

- GitHub: https://github.com/Yuykkk
- Discord: `yukiyot`

## Aviso

AchievementBackup mexe com arquivos locais da Steam e de jogos. Teste restaurações importantes com cuidado e mantenha uma cópia extra dos dados mais sensíveis.
