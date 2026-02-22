# Changelog — Chama Já

Alterações notáveis do projeto. Versão atual em [.version](.version).

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.0.0/).

---

## [Unreleased]

### Adicionado — Gerenciamento do Kokoro no gerenciar.sh
- **Variáveis de ambiente** `KOKORO_PORT` (padrão 8880), `KOKORO_DIR` (padrão `<projeto>/kokoro`) e `KOKORO_TTS_URL` — o Kokoro pode ser movido para qualquer caminho no servidor (`/opt/kokoro`, `/home/kokoro`, etc.) sem alterar código
- **`./gerenciar.sh kokoro start`** — sobe o container `kokoro-api` via `docker compose up -d` a partir de `KOKORO_DIR`; aguarda até 60 s o `/health` responder
- **`./gerenciar.sh kokoro stop`** — para o container Kokoro
- **`./gerenciar.sh kokoro status`** — exibe ATIVO/INATIVO com URL
- **`./gerenciar.sh status`** agora exibe linha do Kokoro (ATIVO/INATIVO) com o diretório configurado
- **`./gerenciar.sh start`** — após subir todos os serviços, a verificação HTTP já inclui o Kokoro como item informativo (não bloqueia o start se estiver inativo)
- **Menu interativo** — opções 13 (Kokoro Iniciar) e 14 (Kokoro Parar) adicionadas

### Alterado
- `backend/edge/app.py`: URL do Kokoro TTS agora lida de `KOKORO_TTS_URL` (env var); padrão inalterado `http://localhost:8880/v1/audio/speech`
- `gerenciar.sh` `start_edge`: exporta `PUBLIC_HOST` para o processo uvicorn

---

## [1.0.1] - 2026-02-22

### Adicionado — TTS (Anúncio de Voz via Kokoro)
- **Anúncio de voz TTS** — ao chamar uma senha na TV, após a campainha é reproduzido um anúncio em português BR: "Atenção! Senha A zero três quatro. Dirija-se ao Guichê cinco."
- **Endpoint `GET /api/tts/call`** — proxy para o Kokoro TTS (porta 8880) com cache de MP3 em disco (`.run/tts_cache/` por hash MD5 de texto+voz+speed+volume); segunda chamada idêntica é instantânea
- **Migration 015** — colunas `tts_enabled` e `tts_voice` na tabela `tenants`
- **Migration 016** — colunas `tts_speed` (padrão 0.85) e `tts_volume` (padrão 1.0) na tabela `tenants`
- **Controles de TTS no Admin Tenant** — card "Anúncio de Voz (TTS)" na aba TV com:
  - Toggle Ativado/Desativado
  - Seletor de voz: Dora (Feminina), Alex (Masculino), Santa (Masculino)
  - Slider de Velocidade (0.25× a 2.0×, padrão 0.85×)
  - Slider de Volume (0.5× a 2.0×, padrão 1.0×)
  - Botão "Testar" — reproduz amostra no navegador com os valores atuais dos sliders
- **`GET /tenant/tv-settings`** e **`POST /tenant/tv-settings`** agora incluem `tts_enabled`, `tts_voice`, `tts_speed` e `tts_volume`
- **`scripts/testar_voz.sh`** — script de teste de TTS via linha de comando com flags `-t`, `-voz` e `--limpar-cache`

### Alterado
- `frontend/tv/tv.js`: `playCallAudio()` agora executa beep → voz TTS em sequência (TTS opcional, falha silenciosa se Kokoro offline); passa `speed` e `volume` na URL
- **Botões "Testar"** (Som da Chamada e TTS): substituídos os SweetAlerts por spinner Bootstrap no botão durante a reprodução — UX mais fluida

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
