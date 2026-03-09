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
- Fila em lista compacta scrollável: Preferencial (badge âmbar) | Normal
- Filtro por serviço: operador vê apenas os serviços que lhe foram atribuídos
- Chamar próxima / chamar senha específica / rechamar / iniciar / finalizar / não compareceu / cancelar

### Admin Tenant (`/admin/`)
- Métricas: guichês, serviços, operadores, atendimentos
- Branding: upload de logo do tenant
- CRUD de operadores com atribuição de serviços por operador
- CRUD de guichês e serviços (prioridade Normal e/ou Preferencial)
- Configurações da TV: tema, áudio, TTS (voz/velocidade/volume), controle remoto YouTube
- Playlist: vídeos YouTube (metadados automáticos) e slides/imagens
- Avisos do rodapé (ticker)
- **Impressora Térmica**: configurar IP/porta, habilitar, copiar token do print agent, testar impressão

### Totem (`/totem/`)
- Tela touch com botões grandes por serviço (público, sem auth)
- Emite tickets na fila
- Ao emitir: gera bytes ESC/POS e enfileira job de impressão (`ticket_print_jobs`)

### Dashboard (`/`)
- Painel do tenant com links para TV, Operador, Admin e Totem
- Cards com QR code de acesso para o Totem

---

## Impressão Térmica — Print Agent

A VPS está em nuvem e não enxerga a rede local do cliente. A impressão funciona via **polling reverso**:

```
[Totem] → emite ticket → [VPS: job pending em ticket_print_jobs]
                                    ↑
          [Print Agent — máquina na rede local do cliente]
          polls HTTPS a cada 2s (saída, não entrada)
                                    ↓
          [Impressora TCP RAW 192.168.1.100:9100]
```

### Scripts zero-install (sem instalação)

| Script | Sistema | Como executar |
|--------|---------|--------------|
| `deploy/print-agent/print-agent.py` | **Linux / Rocky Linux 8** | `python3 print-agent.py` |
| `deploy/print-agent/print-agent.ps1` | **Windows 10+** | `powershell -ExecutionPolicy Bypass -File .\print-agent.ps1` |

Ambos usam apenas recursos nativos do sistema — sem pip, sem instalação.

### Configuração (uma vez)

1. No Admin Tenant → aba "Painel do Chamador" → seção **Impressora Térmica**
2. Informar IP e porta da impressora, habilitar impressão, copiar o **Token do Print Agent**
3. Colar o token na variável `TOKEN` do script correspondente
4. Executar o script na máquina da rede local do cliente
5. Clicar **Testar Impressão** para validar o fluxo completo

### Endpoints da API

| Endpoint | Auth | Descrição |
|----------|------|-----------|
| `GET /tenant/printer-settings` | JWT admin | Lê configurações + token |
| `POST /tenant/printer-settings` | JWT admin | Salva IP, porta, habilitado |
| `POST /tenant/printer-settings/rotate-token` | JWT admin | Gera novo token |
| `POST /tenant/printer-settings/test-print` | JWT admin | Enfileira job de teste |
| `GET /print-agent/jobs` | print_agent_token | Jobs pendentes (para o script) |
| `POST /print-agent/jobs/{id}/ack` | print_agent_token | Confirma printed/failed |

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
python3 -m http.server 7073 --directory frontend/tv
python3 -m http.server 7074 --directory frontend/operator
python3 -m http.server 7075 --directory frontend/admin-tenant
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
# Sync arquivo e reiniciar backend
rsync -avz -e "ssh -i ~/.ssh/id_ed25519_vps" arquivo.py cbruno@165.232.140.143:/home/bruno/chama-ja/...
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
- **TTS**: o botão "Testar TTS" no admin funciona mesmo com `tts_enabled=false`. Na TV ao vivo o flag é verificado — se TTS não falar, checar se está habilitado no admin
- Impressão térmica: `ticket_print_jobs` armazena bytes ESC/POS em base64 (`print_data_b64`); status `pending` → print agent busca e imprime → `printed` ou `failed`
