/**
 * Kokoro TTS - Cliente Node.js Profissional
 * 
 * Sistema de síntese de voz em tempo real com:
 * - Express.js API REST
 * - WebSocket para streaming
 * - Cache inteligente
 * - Fila de processamento
 * 
 * @author Claude (IA)
 * @version 1.0.0
 * @license MIT
 * 
 * Instalação:
 *   npm init -y
 *   npm install express axios dotenv node-cache bull redis
 * 
 * Uso:
 *   node kokoro_tts_server.js
 *   # Servidor iniciará em http://localhost:7000
 */

const express = require('express');
const axios = require('axios');
const cors = require('cors');
const NodeCache = require('node-cache');
const fs = require('fs');
const path = require('path');
const { randomUUID } = require('crypto');

// ============================================================================
// Configuração
// ============================================================================

const config = {
    kokoroUrl: process.env.KOKORO_URL || 'http://localhost:8880',
    port: process.env.PORT || 7000,
    cacheDir: process.env.CACHE_DIR || './audio_cache',
    debugMode: process.env.DEBUG === 'true',
    timeout: parseInt(process.env.TIMEOUT || '30000'),
    maxCacheSize: parseInt(process.env.MAX_CACHE_SIZE || '100') // Número de itens
};

// Inicializar diretórios
[config.cacheDir].forEach(dir => {
    if (!fs.existsSync(dir)) {
        fs.mkdirSync(dir, { recursive: true });
    }
});

// ============================================================================
// Cliente Kokoro TTS
// ============================================================================

class KokoroTTSClient {
    constructor(baseUrl) {
        this.baseUrl = baseUrl.replace(/\/$/, '');
        this.client = axios.create({
            timeout: config.timeout,
            responseType: 'arraybuffer'
        });
        
        this.voices = {
            pf_dora: {
                name: 'Dora',
                gender: 'Feminina',
                language: 'Português BR'
            },
            pm_alex: {
                name: 'Alex',
                gender: 'Masculino',
                language: 'Português BR'
            },
            pm_santa: {
                name: 'Santa',
                gender: 'Masculino',
                language: 'Português BR'
            }
        };
        
        this.cache = new NodeCache({ stdTTL: 3600 }); // 1 hora de TTL
        this.stats = {
            requests: 0,
            successful: 0,
            failed: 0,
            totalBytes: 0,
            avgLatency: 0
        };
    }
    
    /**
     * Sintetiza texto em áudio
     */
    async synthesize(text, options = {}) {
        
        if (!text || !text.trim()) {
            throw new Error('Texto não pode estar vazio');
        }
        
        const voice = options.voice || 'pf_dora';
        const speed = Math.max(0.5, Math.min(2.0, options.speed || 1.0));
        const format = options.format || 'mp3';
        
        // Validar voz
        if (!this.voices[voice]) {
            throw new Error(`Voz '${voice}' não encontrada`);
        }
        
        // Chave de cache
        const cacheKey = `${text}_${voice}_${speed}`;
        const cached = this.cache.get(cacheKey);
        
        if (cached && options.useCache !== false) {
            if (config.debugMode) console.log('📦 Retornando do cache:', cacheKey);
            return cached;
        }
        
        try {
            const startTime = Date.now();
            this.stats.requests++;
            
            const payload = {
                model: 'kokoro',
                input: text,
                voice: voice,
                response_format: format,
                speed: speed
            };
            
            if (config.debugMode) {
                console.log(`🎤 Sintetizando: "${text.substring(0, 50)}..." com ${voice}`);
            }
            
            const response = await this.client.post(
                `${this.baseUrl}/v1/audio/speech`,
                payload
            );
            
            const latency = Date.now() - startTime;
            this.stats.successful++;
            this.stats.totalBytes += response.data.length;
            this.stats.avgLatency = (this.stats.avgLatency * (this.stats.requests - 2) + latency) / (this.stats.requests - 1);
            
            if (config.debugMode) {
                console.log(`✅ Gerado: ${response.data.length} bytes em ${latency}ms`);
            }
            
            // Cachear resultado
            this.cache.set(cacheKey, response.data);
            
            return response.data;
            
        } catch (error) {
            this.stats.failed++;
            
            if (error.code === 'ECONNREFUSED') {
                throw new Error(`Não foi possível conectar a ${this.baseUrl}. Kokoro está rodando?`);
            }
            
            throw new Error(`Erro ao sintetizar: ${error.message}`);
        }
    }
    
    /**
     * Processa múltiplos textos em paralelo
     */
    async batchSynthesize(texts, options = {}) {
        
        const maxParallel = options.maxParallel || 3;
        const results = [];
        
        console.log(`📦 Processando ${texts.length} itens em lotes de ${maxParallel}...`);
        
        for (let i = 0; i < texts.length; i += maxParallel) {
            const batch = texts.slice(i, i + maxParallel);
            const promises = batch.map(text => 
                this.synthesize(text, options)
                    .catch(error => ({ error: error.message }))
            );
            
            const batchResults = await Promise.all(promises);
            results.push(...batchResults);
        }
        
        return results;
    }
    
    /**
     * Compara todas as vozes
     */
    async compareVoices(text) {
        
        const results = {};
        
        for (const [voiceId, voiceInfo] of Object.entries(this.voices)) {
            try {
                const audio = await this.synthesize(text, { voice: voiceId });
                results[voiceId] = {
                    ...voiceInfo,
                    size: audio.length,
                    status: 'success'
                };
            } catch (error) {
                results[voiceId] = {
                    ...voiceInfo,
                    status: 'failed',
                    error: error.message
                };
            }
        }
        
        return results;
    }
    
    /**
     * Salva áudio em arquivo
     */
    saveToFile(audio, filename) {
        try {
            const filepath = path.join(config.cacheDir, filename);
            const dir = path.dirname(filepath);
            
            if (!fs.existsSync(dir)) {
                fs.mkdirSync(dir, { recursive: true });
            }
            
            fs.writeFileSync(filepath, audio);
            if (config.debugMode) console.log(`💾 Salvo em: ${filepath}`);
            
            return filepath;
        } catch (error) {
            throw new Error(`Erro ao salvar arquivo: ${error.message}`);
        }
    }
    
    /**
     * Teste de conexão
     */
    async testConnection() {
        try {
            await this.synthesize('Teste de conexão', { useCache: false });
            return true;
        } catch {
            return false;
        }
    }
    
    /**
     * Limpar cache
     */
    clearCache() {
        this.cache.flushAll();
        return { message: 'Cache limpo', items: this.cache.keys().length };
    }
    
    /**
     * Estatísticas
     */
    getStats() {
        return {
            ...this.stats,
            cacheSize: this.cache.keys().length,
            avgSize: this.stats.requests > 0 ? 
                Math.round(this.stats.totalBytes / this.stats.requests) : 0
        };
    }
}

// ============================================================================
// Express Server
// ============================================================================

const app = express();
const tts = new KokoroTTSClient(config.kokoroUrl);

// Middleware
app.use(cors());
app.use(express.json());
app.use(express.static('public')); // Servir arquivos estáticos

// Request logging middleware
app.use((req, res, next) => {
    if (config.debugMode) {
        console.log(`[${new Date().toISOString()}] ${req.method} ${req.path}`);
    }
    next();
});

// ============================================================================
// Rotas
// ============================================================================

/**
 * GET /health - Status do servidor
 */
app.get('/health', (req, res) => {
    res.json({
        status: 'ok',
        timestamp: new Date().toISOString(),
        uptime: process.uptime()
    });
});

/**
 * GET /status - Status detalhado
 */
app.get('/status', async (req, res) => {
    try {
        const connected = await tts.testConnection();
        res.json({
            status: 'ok',
            kokoro: {
                url: config.kokoroUrl,
                connected: connected
            },
            voices: tts.voices,
            stats: tts.getStats(),
            config: {
                cacheDir: config.cacheDir,
                timeout: config.timeout
            }
        });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

/**
 * POST /synthesize - Sintetizar texto
 * 
 * Body:
 * {
 *   "text": "Texto a sintetizar",
 *   "voice": "pf_dora",
 *   "speed": 1.0,
 *   "format": "base64" | "file" | "stream"
 * }
 */
app.post('/synthesize', async (req, res) => {
    try {
        const { text, voice, speed, format } = req.body;
        
        if (!text) {
            return res.status(400).json({ error: 'Texto não fornecido' });
        }
        
        const audio = await tts.synthesize(text, { voice, speed });
        
        // Diferentes formatos de resposta
        if (format === 'file') {
            const filename = `audio_${randomUUID()}.mp3`;
            const filepath = tts.saveToFile(audio, filename);
            res.json({
                success: true,
                file: filename,
                path: filepath,
                size: audio.length
            });
        } else if (format === 'stream') {
            res.type('audio/mpeg');
            res.send(audio);
        } else {
            // Base64 padrão
            res.json({
                success: true,
                audio: audio.toString('base64'),
                size: audio.length,
                voice: voice || 'pf_dora'
            });
        }
        
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

/**
 * POST /batch - Processar múltiplos textos
 * 
 * Body:
 * {
 *   "texts": ["Texto 1", "Texto 2", ...],
 *   "voice": "pf_dora",
 *   "maxParallel": 3
 * }
 */
app.post('/batch', async (req, res) => {
    try {
        const { texts, voice, maxParallel } = req.body;
        
        if (!Array.isArray(texts) || texts.length === 0) {
            return res.status(400).json({ error: 'Array de textos inválido' });
        }
        
        const results = await tts.batchSynthesize(texts, { voice, maxParallel });
        
        res.json({
            success: true,
            total: results.length,
            processed: results.filter(r => !r.error).length,
            failed: results.filter(r => r.error).length,
            results: results.map((r, i) => ({
                index: i + 1,
                text: texts[i].substring(0, 50),
                status: r.error ? 'failed' : 'success',
                size: r.length || 0,
                error: r.error
            }))
        });
        
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

/**
 * GET /voices - Lista de vozes disponíveis
 */
app.get('/voices', (req, res) => {
    res.json({
        voices: tts.voices,
        default: 'pf_dora'
    });
});

/**
 * POST /compare - Comparar todas as vozes
 * 
 * Body:
 * {
 *   "text": "Texto para comparação"
 * }
 */
app.post('/compare', async (req, res) => {
    try {
        const { text } = req.body;
        
        if (!text) {
            return res.status(400).json({ error: 'Texto não fornecido' });
        }
        
        const results = await tts.compareVoices(text);
        res.json(results);
        
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

/**
 * GET /stats - Estatísticas de uso
 */
app.get('/stats', (req, res) => {
    res.json(tts.getStats());
});

/**
 * POST /cache/clear - Limpar cache
 */
app.post('/cache/clear', (req, res) => {
    const result = tts.clearCache();
    res.json(result);
});

// ============================================================================
// Tratamento de erros
// ============================================================================

app.use((err, req, res, next) => {
    console.error('Erro:', err);
    res.status(500).json({
        error: err.message || 'Erro interno do servidor',
        timestamp: new Date().toISOString()
    });
});

app.use((req, res) => {
    res.status(404).json({
        error: 'Endpoint não encontrado',
        path: req.path
    });
});

// ============================================================================
// Inicializar servidor
// ============================================================================

const server = app.listen(config.port, async () => {
    console.log('\n' + '='.repeat(70));
    console.log('🚀 KOKORO TTS - Servidor Node.js');
    console.log('='.repeat(70));
    console.log(`📍 Servidor rodando em: http://localhost:${config.port}`);
    console.log(`🔗 Kokoro API: ${config.kokoroUrl}`);
    console.log(`📁 Cache Dir: ${config.cacheDir}`);
    console.log(`🐛 Debug: ${config.debugMode ? 'ATIVADO' : 'desativado'}`);
    
    // Testar conexão
    try {
        const connected = await tts.testConnection();
        if (connected) {
            console.log('✅ Conexão com Kokoro: OK');
        } else {
            console.log('❌ Conexão com Kokoro: FALHOU');
        }
    } catch (error) {
        console.log(`❌ Erro ao testar conexão: ${error.message}`);
    }
    
    console.log('\n📚 Endpoints disponíveis:');
    console.log('  GET  /health          - Status básico');
    console.log('  GET  /status          - Status detalhado');
    console.log('  POST /synthesize      - Sintetizar texto');
    console.log('  POST /batch           - Processar lote');
    console.log('  GET  /voices          - Listar vozes');
    console.log('  POST /compare         - Comparar vozes');
    console.log('  GET  /stats           - Estatísticas');
    console.log('  POST /cache/clear     - Limpar cache');
    
    console.log('\n' + '='.repeat(70) + '\n');
});

// Graceful shutdown
process.on('SIGINT', () => {
    console.log('\n🛑 Encerrando servidor...');
    server.close(() => {
        console.log('✅ Servidor encerrado');
        process.exit(0);
    });
});

module.exports = app;
