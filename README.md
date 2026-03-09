# Chama Já — Sistema de Senhas SaaS Multi-Tenant

Sistema completo de gerenciamento de senhas e chamadas para atendimento, com painel administrativo, interface do operador, monitor TV e totem de emissão.

**Repositório:** https://github.com/InnersoftTecnologia/chama-ja
**Empresa:** Innersoft Tecnologia
**Primeiro cliente:** Ferreira Costa (slug `fcosta-gus`)

---

## Arquitetura de produção

```
Usuário → HTTPS → nginx (innersoft.com.br) → frontend estático
                                            → /chama-ja/<slug>/api/ → FastAPI :7071
```

### URLs públicas (produção)

| Interface | URL |
|-----------|-----|
| Dashboard | `https://innersoft.com.br/chama-ja/fcosta-gus/` |
| TV / Painel | `https://innersoft.com.br/chama-ja/fcosta-gus/tv/` |
| Operador | `https://innersoft.com.br/chama-ja/fcosta-gus/op/` |
| Admin Tenant | `https://innersoft.com.br/chama-ja/fcosta-gus/admin/` |
| Totem | `https://innersoft.com.br/chama-ja/fcosta-gus/totem/` |
| API | `https://innersoft.com.br/chama-ja/fcosta-gus/api/` |
| Landing Innersoft | `https://innersoft.com.br/` |

### Infraestrutura

| Serviço | Host | Detalhe |
|---------|------|---------|
| Backend FastAPI | 165.232.140.143 | porta 7071, systemd `chama-ja.service` |
| Nginx | 165.232.140.143 | proxy reverso + arquivos estáticos |
| Kokoro TTS | 147.79.86.7 | Docker `kokoro-tts`, porta 8880 |
| Banco | localhost (VPS) | MariaDB, banco `chamador` |

---

## Stack

- **Backend:** Python 3.12 + FastAPI + MariaDB (`mysql-connector-python`)
- **Frontend:** HTML/CSS Vanilla + Bootstrap 5 (admin/operador/totem) + CSS próprio (TV)
- **Auth:** JWT (PyJWT + bcrypt) para rotas de operador/admin
- **Sem frameworks JS** — vanilla fetch + SSE
- **TTS:** Kokoro (Docker) — vozes BR: `pf_dora` (fem.) e `pm_alex` (masc.)

---

## Funcionalidades

### TV (`/tv/`)
- Exibição de senha atual em atendimento + histórico
- Fila de espera em tempo real (polling 3s)
- Player YouTube com playlist configurável (vídeos e slides)
- Ticker de avisos no rodapé
- **Anúncio de voz TTS**: campainha + voz sintetizada ao chamar senha
- Tema dark/light configurável remotamente
- Overlay "Toque para ativar áudio" (auto-dismiss em kiosks configurados)
- SSE para chamadas em tempo real (`ticket.called`, `ticket.recalled`)

### Operador (`/op/`)
- Login JWT + seleção de guichê
- Fila em duas colunas: Preferencial | Normal
- Filtro por serviço: operador vê apenas os serviços que lhe foram atribuídos (sem atribuição = vê todos)
- Chamar próxima / chamar senha específica / rechamar / iniciar / finalizar / não compareceu / cancelar

### Admin Tenant (`/admin/`)
- Métricas: guichês, serviços, operadores, atendimentos
- Branding: upload de logo do tenant
- CRUD de operadores com atribuição de serviços por operador
- CRUD de guichês e serviços (prioridade Normal e/ou Preferencial por checkboxes)
- Configurações da TV: tema, áudio, TTS (voz/velocidade/volume), controle remoto YouTube
- Playlist: vídeos YouTube (metadados automáticos) e slides/imagens
- Avisos do rodapé (ticker)

### Totem (`/totem/`)
- Tela touch com botões grandes por serviço (público, sem auth)
- Emite tickets na fila e registra `ticket_print_jobs`
- Suporte a impressora térmica ESC/POS via TCP

### Dashboard (`/`)
- Painel do tenant com links para TV, Operador, Admin e Totem
- Cards com QR code de acesso para o Totem

---

## Desenvolvimento local

### 1. Pré-requisitos

- Python 3.12+
- MariaDB local rodando

### 2. Instalação

```bash
git clone https://github.com/InnersoftTecnologia/chama-ja.git
cd chama-ja
./install.sh
```

### 3. Variáveis de ambiente

Crie `.env` na raiz do projeto:

```env
DB_HOST=localhost
DB_PORT=3306
DB_USER=mysql
DB_PASSWORD=mysql
DB_NAME=chamador
EDGE_DEVICE_TOKEN=dev-edge-token
KOKORO_TTS_URL=http://localhost:8880/v1/audio/speech
```

### 4. Subir o backend

```bash
source .venv/bin/activate
python backend/edge/app.py
```

### 5. Inicializar banco + seed

```bash
curl -X POST 'http://localhost:7071/admin/migrate?reset=1' -H 'Authorization: Bearer dev-edge-token'
curl -X POST 'http://localhost:7071/admin/seed' -H 'Authorization: Bearer dev-edge-token'
```

### 6. Servir frontends (dev)

```bash
# TV
python3 -m http.server 7073 --directory frontend/tv

# Operador
python3 -m http.server 7074 --directory frontend/operator

# Admin
python3 -m http.server 7075 --directory frontend/admin-tenant

# Totem
python3 -m http.server 7076 --directory frontend/totem
```

Ou use `./gerenciar.sh start` para subir todos os serviços de uma vez.

---

## Credenciais de teste (seed)

| Perfil | Email | Senha |
|--------|-------|-------|
| Admin | admin@ferreiracosta.com.br | admin123 |
| Operador | amanda@ferreiracosta.com.br | amanda123 |

---

## Deploy na VPS

Ver [`.claude/commands/deploy.md`](.claude/commands/deploy.md) para o fluxo completo.

```bash
# Restart backend
echo 'cbruno22' | sudo -S systemctl restart chama-ja.service

# Reload nginx
echo 'cbruno22' | sudo -S nginx -t && echo 'cbruno22' | sudo -S systemctl reload nginx
```

---

## TV em modo kiosk (produção)

Para eliminar a necessidade do clique de ativação de áudio, configure o Chrome na máquina da TV. Ver [`.claude/commands/tv-kiosk.md`](.claude/commands/tv-kiosk.md).

**Opção mais simples (uma vez):** `chrome://settings/content/sound` → adicionar `https://innersoft.com.br` em "Permitido reproduzir som".

---

## Controle de versão

- Versão em **`.version`** (formato `major.minor.patch`)
- Hook pre-commit incrementa o patch automaticamente
- Instalar hooks: `./scripts/setup-git-hooks.sh`

---

## Dependências externas

| Serviço | Detalhe |
|---------|---------|
| Kokoro TTS | Docker `kokoro-tts` em 147.79.86.7:8880. Se offline, opera só com campainha (falha silenciosa) |
| MariaDB | Local na VPS, banco `chamador` |
| YouTube IFrame API | Carregada dinamicamente pelo painel TV |

### Variáveis Kokoro

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `KOKORO_TTS_URL` | `http://localhost:8880/v1/audio/speech` | URL do serviço TTS |

---

## Notas técnicas

- SSE (`/tv/events`) é público — `EventSource` não suporta headers, logo sem auth
- Totem e TV são endpoints públicos (sem JWT) — kiosks sem login
- Operadores por serviço: se `operator_services` está vazio para o operador, ele vê todas as filas
- Cache de TTS em `.run/tts_cache/` (MP3 por hash MD5 de texto+voz+speed+volume)
- Impressão térmica: tabela `ticket_print_jobs` + arquivo em `.run/prints/`
