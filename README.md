# AchievementBackup

**AchievementBackup** é um plugin para **Millennium/Steam** criado por **Yuykkk** para proteger dados locais da Steam, conquistas, saves e capturas por jogo.

Ele foi feito para quem quer formatar o PC, reinstalar a Steam, trocar de disco, testar jogos ou guardar um estado importante sem depender apenas da nuvem.

## Instalação rápida

Requisito: Steam com [Millennium](https://steambrew.app/) instalado.

Abra o PowerShell e rode **um único comando**:

```powershell
irm "https://raw.githubusercontent.com/Yuykkk/AchievementBackup/main/install.ps1" | iex
```

O instalador tenta encontrar a pasta da Steam automaticamente, inclusive instalações fora do `C:`, usando registro do Windows, processo da Steam aberto e caminhos comuns como `D:\steam`.

Depois de instalar, ele reinicia a Steam sozinho para o plugin já aparecer funcionando.

Se quiser instalar sem reiniciar a Steam naquele momento:

```powershell
& ([scriptblock]::Create((irm "https://raw.githubusercontent.com/Yuykkk/AchievementBackup/main/install.ps1"))) -NoRestart
```

## Recursos

| Recurso | Descrição |
| --- | --- |
| Backup completo | Salva um pacote amplo dos dados locais importantes da Steam. |
| Captura por jogo | Salva somente os arquivos ligados a um AppID específico. |
| Restore guiado | Fecha a Steam, aplica os arquivos e mostra o resultado quando ela abre de novo. |
| Apps ignorados | Evita capturas automáticas em jogos/apps escolhidos por você. |
| Importar e exportar | Gera ou importa ZIPs com backups completos e capturas por jogo. |
| Pasta configurável | Permite salvar os backups no caminho padrão do plugin ou em outro disco. |
| Temas de cor | Personaliza o painel dentro da Steam. |
| Atualização pelo GitHub | Verifica versões novas, pergunta antes de atualizar e mostra o resultado depois. |

## O que pode ser salvo

AchievementBackup trabalha com duas ideias:

- **Backup completo**: bom antes de formatar, reinstalar a Steam ou mexer em arquivos grandes.
- **Captura por jogo**: boa para salvar/restaurar só um jogo sem tocar no resto da biblioteca.

Fontes protegidas:

- `appcache/stats`: conquistas e estatísticas locais.
- `userdata`: saves, preferências e dados vinculados à conta Steam.
- `config/stplug-in`: lista, estado e configurações locais usadas pela Steam.
- Caminhos conhecidos de saves no Windows, como `Documentos` e `AppData`, quando o manifest Ludusavi/PCGamingWiki estiver ativado.

## Atualizações

Quando a Steam abre, o plugin verifica se existe uma versão mais nova no GitHub.

Se encontrar, ele mostra:

- versão instalada;
- versão disponível;
- confirmação antes de baixar;
- aviso depois que a Steam reinicia.

O plugin preserva seus dados locais durante a atualização:

- `profile`;
- `backups`;
- `logs`;
- `cache`;
- configurações do usuário.

Também existe um botão em **Configurações** para checar atualização manualmente.

## Créditos

Criado por **Yuykkk**.

- GitHub: https://github.com/Yuykkk
- Discord: `yukiyot`

Este projeto foi desenvolvido com apoio de IA para acelerar implementação, revisão de código, organização de textos e melhorias de interface. As decisões, direção do projeto, testes e publicação são de autoria de **Yuykkk**.

### Dados e APIs públicas

AchievementBackup usa dados públicos para localizar saves e exibir informações dos jogos:

- [Ludusavi Manifest](https://github.com/mtkennerly/ludusavi-manifest): caminhos conhecidos de saves por jogo/AppID.
- [PCGamingWiki](https://www.pcgamingwiki.com/): base comunitária usada pelo ecossistema do Ludusavi.
- Steam Web/Store metadata: nomes e imagens públicas dos jogos.

O manifest do Ludusavi é distribuído sob licença MIT. Consulte o repositório original para detalhes.

## Licença

AchievementBackup é um projeto proprietário de **Yuykkk**. O uso pessoal é permitido, mas modificar e publicar, redistribuir, vender, reupar ou criar versões derivadas públicas exige autorização prévia do autor.

Consulte o arquivo [LICENSE](LICENSE) para os termos completos.

## Aviso

AchievementBackup mexe com arquivos locais da Steam e de jogos. Teste restaurações importantes com cuidado e mantenha uma cópia extra dos dados mais sensíveis.
