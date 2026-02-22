# Chama Já (Sistema de Senhas SaaS Multi-Tenant)

Sistema completo de gerenciamento de senhas e chamadas para atendimento, com painel administrativo, interface do operador e monitor TV.

**Repositório:** https://github.com/InnersoftTecnologia/chama-ja

## Página principal (dashboard)

**http://localhost:7077** — Painel com links para abrir cada interface em nova aba (TV, Operador, Admin, Totem, etc.), com tema dark/light.

## Instalação rápida

```bash
git clone https://github.com/InnersoftTecnologia/chama-ja.git
cd chama-ja
./install.sh
```

O script `install.sh` cria a estrutura de diretórios (`.run/prints`, `.run/slides`), ambiente virtual Python e instala as dependências. Com um argumento, instala em outro diretório: `./install.sh /caminho/destino`.

## Controle de versão

- A versão fica no arquivo **`.version`** (formato `major.minor.patch`).
- A cada **commit**, o hook **pre-commit** incrementa automaticamente o patch.
- Após clonar, instale os hooks: `./scripts/setup-git-hooks.sh`.

### Enviar para o GitHub

```bash
./scripts/setup-git-hooks.sh   # instala hook de .version
git add .
git commit -m "Versão inicial"
git push -u origin main
```

A pasta `docs/` não é versionada (está no `.gitignore`).

## Portas (7070–7079)

| Porta | Serviço | Descrição |
|-------|---------|-----------|
| 7077 | **Dashboard** | Página principal — links para todas as interfaces |
| 7071 | Edge API | Backend FastAPI |
| 7072 | Test UI | Interface de teste (legado) |
| 7073 | TV | Monitor/Painel de chamadas |
| 7074 | Operador | Interface do operador |
| 7075 | Admin Tenant | Portal de administração |
| 7076 | Totem | Emissão de senhas (touch) |

## Funcionalidades

### Admin Tenant (http://localhost:7075)
- **Dashboard**: Métricas de guichês, serviços, operadores, atendimentos
- **Branding**: Upload de logo do tenant
- **Operadores**: CRUD de usuários com ativar/desativar
- **Guichês**: CRUD de guichês com ativar/desativar
- **Serviços**: CRUD de serviços com prioridade normal/preferencial
- **Painel do Chamador**: Configurações da TV
  - Tema Dark/Light
  - Áudio de chamada (beep/mp3 configurável)
  - **Anúncio de voz TTS** (Kokoro) — anuncia a senha em português após a campainha; voz configurável (Dora, Alex, Santa), com sliders de velocidade (0.25×–2.0×) e volume (0.5×–2.0×); botão "Testar" reproduz amostra no navegador
  - Controle remoto do vídeo YouTube (mute/play/pause)
  - Avisos do rodapé (ticker)
  - Playlist de vídeos e slides (CRUD com metadados)
    - Vídeos do YouTube (com busca automática de título/thumbnail)
    - Slides/Imagens estáticas (upload ou URL externa, duração configurável)

### TV (http://localhost:7073)
- Exibição de senhas em atendimento (tickets `in_service`)
- Histórico (tickets finalizados: `completed/no_show/cancelled`)
- Player YouTube com playlist configurável (vídeos e slides)
- Slides/Imagens estáticas com duração configurável
- Transição automática entre vídeos e slides
- Ticker de avisos no rodapé
- Tema dark/light configurável remotamente
- Áudio e vídeo controláveis remotamente
- **Anúncio de voz TTS**: ao chamar uma senha, toca a campainha e em seguida anuncia em voz sintetizada (ex.: "Atenção! Senha A zero três quatro. Dirija-se ao Guichê cinco.") via Kokoro TTS (porta 8880), com cache em disco

### Operador (http://localhost:7074)
- Login com JWT
- Seleção de guichê no login (fixo até sair)
- Fila em duas colunas (Preferencial | Normal)
- Chamar próxima senha + iniciar/finalizar/não compareceu/cancelar

### Totem (http://localhost:7076)
- Tela touch (tablet/celular) com botões grandes por serviço
- Layout em 2 colunas (Normal | Preferencial) baseado no modelo
- Cards com bordas laterais coloridas (azul/laranja)
- Fonte Montserrat aplicada em todo o Totem
- Lista serviços do tenant ativo e emite tickets na fila
- "Impressão" MVP: download de `.txt` + salvar arquivo em `.run/prints/`
- Auditoria em banco: tabela `ticket_print_jobs`

## Credenciais de Teste
- **Admin**: admin@ferreiracosta.com.br / admin123
- **Operador**: amanda@ferreiracosta.com.br / amanda123

## Banco (MariaDB local)

Você informou que já existe MariaDB local:

```bash
mysql -u mysql -pmysql localhost
```

## Rodar (dev)

### 1) Instalar deps

```bash
cd /home/cbruno/projetos/chama-ja
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Subir Edge API (7071)

```bash
export DB_HOST=localhost
export DB_PORT=3306
export DB_USER=mysql
export DB_PASSWORD=mysql
export DB_NAME=chamador
export EDGE_DEVICE_TOKEN=dev-edge-token

python backend/edge/app.py
```

### 3) Inicializar schema + seed

```bash
curl -X POST 'http://localhost:7071/admin/migrate?reset=1' -H 'Authorization: Bearer dev-edge-token'
curl -X POST http://localhost:7071/admin/seed -H 'Authorization: Bearer dev-edge-token'
```

### 4) Servir os frontends (7070 e 7072)

Em dois terminais:

```bash
python3 -m http.server 7070 --directory /home/cbruno/projetos/chama-ja/frontend/tv
```

Se a 7070 estiver ocupada no seu host, use a 7073:

```bash
python3 -m http.server 7073 --directory /home/cbruno/projetos/chama-ja/frontend/tv
```

```bash
python3 -m http.server 7072 --directory /home/cbruno/projetos/chama-ja/frontend/operator-test
```

Abra:

- TV: `http://localhost:7070/`
- (fallback) TV: `http://localhost:7073/`
- Teste: `http://localhost:7072/`

Se estiver usando o `gerenciar.sh`, ele já sobe também:
- Operador: `http://localhost:7074/`
- Admin: `http://localhost:7075/`
- Totem: `http://localhost:7076/`

## Dependências externas

- **Kokoro TTS** (porta 8880) — microserviço de síntese de voz em português BR rodando via Docker. Se offline, o sistema opera normalmente apenas com a campainha (falha silenciosa). O diretório do Kokoro pode estar em **qualquer caminho** do servidor.

### Gerenciando o Kokoro

```bash
# Subir o container Kokoro (padrão: <projeto>/kokoro/docker-compose.yml)
./gerenciar.sh kokoro start

# Para subir de outro caminho:
export KOKORO_DIR=/opt/kokoro
./gerenciar.sh kokoro start

# Parar
./gerenciar.sh kokoro stop

# Verificar status
./gerenciar.sh kokoro status
```

O status do Kokoro também aparece em `./gerenciar.sh status` e na verificação pós-`start`.

### Variáveis de ambiente do Kokoro

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `KOKORO_DIR` | `<projeto>/kokoro` | Caminho do diretório com o `docker-compose.yml` |
| `KOKORO_PORT` | `8880` | Porta em que o Kokoro escuta |
| `KOKORO_TTS_URL` | `http://localhost:8880/v1/audio/speech` | URL completa usada pelo backend |

## Notas

- SSE usa `?token=...` porque `EventSource` não consegue enviar header Authorization.
- Cache de áudios TTS em `.run/tts_cache/` (MP3 por hash MD5 de texto+voz+speed+volume). Limpar com `./scripts/testar_voz.sh --limpar-cache` ou `rm -f .run/tts_cache/*.mp3`.

