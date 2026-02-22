# Changelog — Chama Já

Alterações notáveis do projeto. Versão atual em [.version](.version).

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/).

---

## [1.0.0] - 2026-02-22

### Controle de versão e instalação
- Controle de versão com Git; repositório: https://github.com/InnersoftTecnologia/chama-ja
- Arquivo `.version` incrementado automaticamente a cada commit (hook pre-commit)
- Script `install.sh` para clone, criação de estrutura e instalação de dependências
- Script `scripts/setup-git-hooks.sh` para instalar hooks de versão
- `CHANGELOG.md` na raiz do projeto

### Sistema
- **Edge API (7071)**: Backend FastAPI, JWT, CRUD tenant, tickets, playlist (YouTube + slides), totem, TV state
- **TV (7073)**: Painel de chamadas, Em Atendimento / Histórico, tema dark/light, áudio, playlist (vídeos + slides), ticker
- **Operador (7074)**: Login, seleção de guichê, fila Preferencial/Normal, chamar/iniciar/finalizar/não compareceu
- **Admin Tenant (7075)**: Dashboard, branding/logo, CRUD operadores/guichês/serviços/avisos, Painel do Chamador (playlist, configurações da TV)
- **Totem (7076)**: Emissão de senhas por serviço, layout Normal/Preferencial, “impressão” em `.run/prints/`
- **Test UI (7072)**: Interface de teste legada

### Backend
- Autenticação JWT (PyJWT, bcrypt)
- Migrations 001–011 (tenants, users, counters, services, tickets, ticket_sequences, youtube_urls com slides, tv_settings, ticket_print_jobs)
- Endpoints: `/auth/login`, `/auth/me`, `/tenant/*`, `/tv/state`, `/totem/services`, `/totem/emit`, `/api/slides/*`

### Frontend
- TV: CSS vanilla, tema light/dark remoto, controle remoto de vídeo/áudio
- Admin: Bootstrap 5, abas, SweetAlert2, upload de logo
- Operador: Login modal, fila em duas colunas
- Totem: Fonte Montserrat, cards por serviço, overlay de senha

---

[1.0.0]: https://github.com/InnersoftTecnologia/chama-ja/releases/tag/v1.0.0
