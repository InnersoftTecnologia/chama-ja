# Chama Já (Sistema de Senhas SaaS Multi-Tenant)

Sistema completo de gerenciamento de senhas e chamadas para atendimento, com painel administrativo, interface do operador e monitor TV.

**Repositório:** https://github.com/InnersoftTecnologia/chama-ja

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
  - Áudio de chamada (beep)
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
cd /home/cbruno/projetos/chamador
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
python3 -m http.server 7070 --directory /home/cbruno/projetos/chamador/frontend/tv
```

Se a 7070 estiver ocupada no seu host, use a 7073:

```bash
python3 -m http.server 7073 --directory /home/cbruno/projetos/chamador/frontend/tv
```

```bash
python3 -m http.server 7072 --directory /home/cbruno/projetos/chamador/frontend/operator-test
```

Abra:

- TV: `http://localhost:7070/`
- (fallback) TV: `http://localhost:7073/`
- Teste: `http://localhost:7072/`

Se estiver usando o `gerenciar.sh`, ele já sobe também:
- Operador: `http://localhost:7074/`
- Admin: `http://localhost:7075/`
- Totem: `http://localhost:7076/`

## Notas do MVP

- SSE usa `?token=...` porque `EventSource` não consegue enviar header Authorization.
- Áudio: por enquanto é **bip** (WebAudio). Depois evolui para voz (Kokoro/API ou composição por áudios).

