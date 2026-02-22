# 🎤 Kokoro TTS - Demonstração Completa

Sistema completo de demonstração: **Síntese de Voz em Português Brasileiro** com suporte a **Python**, **PHP** e **Node.js**.

---

## 📋 Índice

1. [Arquivos Inclusos](#arquivos-inclusos)
2. [Pré-requisitos](#pré-requisitos)
3. [Instalação Kokoro](#instalação-kokoro)
4. [Usar Python](#usar-python)
5. [Usar PHP](#usar-php)
6. [Usar Node.js](#usar-nodejs)
7. [Integração com n8n](#integração-com-n8n)
8. [Troubleshooting](#troubleshooting)

---

## 📦 Arquivos Inclusos

```
kokoro-demo/
├── kokoro_demo.py              # Script Python completo
├── kokoro_tts.php              # Classe PHP robusta
├── kokoro_tts_server.js        # Servidor Express Node.js
├── README.md                   # Este arquivo
├── docker-compose.yml          # Stack completa
├── package.json                # Dependências Node.js
└── audio_output/               # Diretório de áudio (criado automaticamente)
```

---

## 🔧 Pré-requisitos

### Instalação Base

**Ubuntu 22.04:**
```bash
# Atualizar sistema
sudo apt update && sudo apt upgrade -y

# Instalar Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Adicionar seu usuário ao grupo docker
sudo usermod -aG docker $USER
newgrp docker
```

**Windows (PowerShell como Admin):**
```powershell
# Instalar Docker Desktop
# https://www.docker.com/products/docker-desktop

# Verificar instalação
docker --version
docker compose version
```

---

## 🚀 Instalação Kokoro

### Opção 1: Docker (Recomendado)

**Iniciar servidor Kokoro em CPU:**
```bash
docker run -d -p 8880:8880 --name kokoro \
  ghcr.io/remsky/kokoro-fastapi-cpu:latest
```

**Com GPU (NVIDIA):**
```bash
docker run -d --gpus all -p 8880:8880 --name kokoro \
  ghcr.io/remsky/kokoro-fastapi-gpu:latest
```

**Verificar status:**
```bash
curl http://localhost:8880/health
# Resposta esperada: {"status":"ok"}
```

### Opção 2: Docker Compose Completo

```bash
cd kokoro-demo
docker compose up -d

# Verificar logs
docker compose logs -f kokoro-api
```

---

## 🐍 Usar Python

### Instalação

```bash
cd kokoro-demo

# Criar ambiente virtual
python3 -m venv venv

# Ativar ambiente
# Linux/Mac:
source venv/bin/activate
# Windows:
venv\Scripts\activate

# Instalar dependências
pip install requests python-dotenv
```

### Usar

```bash
# Executar demonstração completa
python kokoro_demo.py

# Salva áudio em: audio_output/
```

### Exemplo de Uso no Código

```python
from kokoro_demo import KokoroTTSClient, KokoroConfig

# Configurar
config = KokoroConfig(
    base_url="http://localhost:8880",
    default_voice="pf_dora"
)

# Criar cliente
client = KokoroTTSClient(config)

# Sintetizar
audio = client.synthesize("Olá, mundo!")

# Salvar arquivo
client.save_audio(audio, "meu_audio.mp3")

# Converter para base64 (para AJAX)
b64_audio = client.audio_to_base64(audio)
```

### Vozes Disponíveis

```python
client.voices  # Retorna dicionário com vozes pt-BR
# {
#   'pf_dora': {...},
#   'pm_alex': {...},
#   'pm_santa': {...}
# }
```

---

## 🐘 Usar PHP

### Instalação

**Requisitos:**
- PHP 8.0+
- cURL habilitado
- Servidor web (Apache/Nginx)

**Ubuntu:**
```bash
sudo apt install php php-curl php-cli

# Testar
php -v
```

### Usar

**CLI (Linha de comando):**
```bash
cd kokoro-demo
php -r "
  require 'kokoro_tts.php';
  \$tts = new KokoroTTS('http://localhost:8880');
  \$audio = \$tts->synthesize('Olá do PHP!');
  \$tts->saveToFile(\$audio, 'teste.mp3');
  echo 'Áudio gerado!';
"
```

**Em aplicação web:**
```php
<?php
require 'kokoro_tts.php';

// Crear instancia
$tts = new KokoroTTS('http://localhost:8880', ['debug' => true]);

// Sintetizar
try {
    $audio = $tts->synthesize("Bem-vindo ao sistema", [
        'voice' => 'pf_dora',
        'speed' => 1.0
    ]);
    
    // Salvar arquivo
    $tts->saveToFile($audio, 'boas_vindas.mp3');
    
    // Ou retornar como base64 para AJAX
    $result = $tts->synthesizeAsJSON("Sua mensagem", [
        'voice' => 'pf_dora'
    ]);
    header('Content-Type: application/json');
    echo json_encode($result);
    
} catch (Exception $e) {
    echo "Erro: " . $e->getMessage();
}
?>
```

**API REST:**
```bash
# Testar endpoint
curl -X POST http://localhost:7000/synthesize \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Olá, isso é um teste",
    "voice": "pf_dora",
    "speed": 1.0
  }'
```

### Métodos Principais

```php
// Sintetizar
$audio = $tts->synthesize("Texto", ['voice' => 'pm_alex']);

// Retornar como JSON com base64
$result = $tts->synthesizeAsJSON("Texto");

// Stream direto para cliente
$tts->streamToClient("Texto a falar");

// Salvar em arquivo
$tts->saveToFile($audio, 'arquivo.mp3');

// Processar múltiplos textos
$results = $tts->batchProcess([
    "Texto 1",
    "Texto 2",
    "Texto 3"
], './saida');

// Obter vozes disponíveis
$tts->getVoices();

// Testar conexão
if ($tts->testConnection()) {
    echo "Conectado!";
}
```

---

## 🟢 Usar Node.js

### Instalação

**Requisitos:**
- Node.js 14+
- npm ou yarn

**Ubuntu:**
```bash
curl -sL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install nodejs
```

**Instalar dependências:**
```bash
cd kokoro-demo
npm install

# Ou com yarn
yarn install
```

### package.json

```json
{
  "name": "kokoro-tts-demo",
  "version": "1.0.0",
  "description": "Kokoro TTS Node.js Demo",
  "main": "kokoro_tts_server.js",
  "dependencies": {
    "express": "^4.18.2",
    "axios": "^1.6.0",
    "cors": "^2.8.5",
    "dotenv": "^16.3.1",
    "node-cache": "^5.1.2"
  }
}
```

### Iniciar Servidor

```bash
# Modo desenvolvimento
npm start
# ou
node kokoro_tts_server.js

# Servidor ativo em http://localhost:7000
```

### Endpoints

**1. Health Check**
```bash
curl http://localhost:7000/health
```

**2. Status Detalhado**
```bash
curl http://localhost:7000/status
```

**3. Sintetizar Texto**
```bash
curl -X POST http://localhost:7000/synthesize \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Olá mundo!",
    "voice": "pf_dora",
    "speed": 1.0
  }'
```

**4. Processar Lote**
```bash
curl -X POST http://localhost:7000/batch \
  -H "Content-Type: application/json" \
  -d '{
    "texts": ["Texto 1", "Texto 2", "Texto 3"],
    "voice": "pf_dora",
    "maxParallel": 3
  }'
```

**5. Comparar Vozes**
```bash
curl -X POST http://localhost:7000/compare \
  -H "Content-Type: application/json" \
  -d '{"text": "Olá, teste de voz"}'
```

**6. Listar Vozes**
```bash
curl http://localhost:7000/voices
```

**7. Estatísticas**
```bash
curl http://localhost:7000/stats
```

### Usar em Código Node.js

```javascript
const axios = require('axios');

async function sintetizar() {
    try {
        const response = await axios.post('http://localhost:7000/synthesize', {
            text: 'Olá, teste em Node.js',
            voice: 'pf_dora',
            speed: 1.0
        });
        
        console.log('Áudio gerado:', response.data);
    } catch (error) {
        console.error('Erro:', error.message);
    }
}

sintetizar();
```

---

## 🔄 Integração com n8n

### Configurar Nó HTTP Request

1. Abra seu workflow no n8n
2. Adicione nó **"HTTP Request"**
3. Configure:
   - **Method:** POST
   - **URL:** `http://localhost:8880/v1/audio/speech`
   - **Authentication:** None
   - **Headers:** `Content-Type: application/json`

### Body (JSON)

```json
{
  "model": "kokoro",
  "input": "{{ $json.llm_response }}",
  "voice": "pf_dora",
  "response_format": "mp3",
  "speed": 1.0
}
```

### Workflow Completo (STT → LLM → TTS)

```
1. Webhook (recebe áudio)
   ↓
2. HTTP Request (Whisper STT)
   ↓
3. Function (processar resposta)
   ↓
4. AI Agent (Claude/ChatGPT)
   ↓
5. HTTP Request (Kokoro TTS) ← VOCÊ ESTÁ AQUI
   ↓
6. Respond to Webhook (retorna áudio)
```

---

## 📊 Vozes Disponíveis

| ID | Nome | Gênero | Qualidade |
|---|---|---|---|
| `pf_dora` | Dora | Feminina | Natural |
| `pm_alex` | Alex | Masculino | Natural |
| `pm_santa` | Santa | Masculino | Natural |

---

## ⚙️ Configurações Avançadas

### Variáveis de Ambiente

```bash
# .env
KOKORO_URL=http://localhost:8880
DEBUG=true
CACHE_DIR=./audio_cache
TIMEOUT=30000
MAX_CACHE_SIZE=100
```

### Docker Compose Personalizado

```yaml
version: '3.8'
services:
  kokoro-tts:
    image: ghcr.io/remsky/kokoro-fastapi-cpu:latest
    container_name: kokoro-demo
    ports:
      - "8880:8880"
    environment:
      - TARGET_MIN_TOKENS=175
      - TARGET_MAX_TOKENS=250
      - ABSOLUTE_MAX_TOKENS=450
    volumes:
      - ./audio_output:/app/outputs
    restart: always
```

---

## 🐛 Troubleshooting

### "Connection refused"

```bash
# Verificar se Kokoro está rodando
curl http://localhost:8880/health

# Se não estiver:
docker run -d -p 8880:8880 --name kokoro \
  ghcr.io/remsky/kokoro-fastapi-cpu:latest
```

### "Timeout" em requisições grandes

**Aumentar timeout:**

**Python:**
```python
config.timeout = 60  # 60 segundos
```

**PHP:**
```php
$tts = new KokoroTTS('http://localhost:8880', ['timeout' => 60]);
```

**Node.js:**
```javascript
// Variável de ambiente
TIMEOUT=60000
```

### Áudio com qualidade ruim

- ✅ Aumentar `speed` para 0.8x (mais tempo = melhor qualidade)
- ✅ Usar voz `pf_dora` (mais natural que outras)
- ✅ Texto claro sem caracteres especiais

### Erro "Voz não encontrada"

Use apenas as vozes pt-BR oficiais:
- `pf_dora`
- `pm_alex`
- `pm_santa`

### Server rodando lento

- Reduzir `maxParallel` no lote (Node.js)
- Usar CPU VPS melhor ou ativar GPU
- Limpar cache regularmente

```bash
# Limpar cache Node.js
curl -X POST http://localhost:7000/cache/clear
```

---

## 📈 Performance

### Latência Esperada

| Cenário | Latência |
|---------|----------|
| CPU Moderno (5 palavras) | ~0.5-1s |
| CPU Moderno (50 palavras) | ~2-4s |
| GPU RTX 4090 (100 palavras) | ~0.1s |

### Cache

- Python: Em memória (auto)
- PHP: Sessão ou arquivo
- Node.js: Redis/Node-Cache (1h TTL)

---

## 📚 Recursos Adicionais

- [GitHub Kokoro](https://github.com/hexgrad/kokoro)
- [HuggingFace Model Card](https://huggingface.co/hexgrad/Kokoro-82M)
- [Kokoro FastAPI](https://github.com/remsky/Kokoro-FastAPI)
- [n8n Workflows](https://n8n.io/workflows)

---

## 📝 Licença

MIT - Livre para uso comercial e pessoal

---

## 🤝 Suporte

Para problemas, dúvidas ou sugestões:
1. Verifique Troubleshooting acima
2. Consulte logs: `docker compose logs -f`
3. Abra issue no repositório

---

**Desenvolvido por:** Claude (IA Anthropic)  
**Data:** Outubro 2025  
**Versão:** 1.0.0

Bom teste! 🚀
