<?php
/**
 * Kokoro TTS - Cliente PHP Robusto
 * 
 * Sistema completo de integração com Kokoro TTS API
 * Suporta português brasileiro com múltiplas vozes
 * 
 * @author Claude (IA)
 * @version 1.0.0
 * @license MIT
 * 
 * Requisitos:
 *   - PHP 8.0+
 *   - cURL extension
 *   - Servidor Kokoro rodando
 * 
 * Uso básico:
 *   $tts = new KokoroTTS();
 *   $tts->streamToClient("Olá mundo!");
 */

class KokoroTTS {
    
    // Configurações
    private string $baseUrl;
    private string $defaultVoice;
    private int $timeout;
    private array $voices;
    private array $config;
    
    // Log e debug
    private array $lastRequest;
    private array $lastResponse;
    private bool $debugMode;
    
    /**
     * Construtor
     * 
     * @param string $baseUrl URL base do servidor Kokoro
     * @param array $options Opções de configuração adicionais
     */
    public function __construct($baseUrl = 'http://localhost:8880', $options = []) {
        $this->baseUrl = rtrim($baseUrl, '/');
        $this->defaultVoice = $options['voice'] ?? 'pf_dora';
        $this->timeout = $options['timeout'] ?? 30;
        $this->debugMode = $options['debug'] ?? false;
        
        // Inicializar vozes pt-BR
        $this->voices = [
            'pf_dora' => [
                'name' => 'Dora',
                'gender' => 'Feminina',
                'language' => 'Português BR'
            ],
            'pm_alex' => [
                'name' => 'Alex',
                'gender' => 'Masculino',
                'language' => 'Português BR'
            ],
            'pm_santa' => [
                'name' => 'Santa',
                'gender' => 'Masculino',
                'language' => 'Português BR'
            ]
        ];
        
        $this->config = [
            'model' => 'kokoro',
            'response_format' => 'mp3',
            'speed' => 1.0
        ];
        
        $this->lastRequest = [];
        $this->lastResponse = [];
    }
    
    /**
     * Sintetiza texto em áudio
     * 
     * @param string $text Texto a sintetizar
     * @param array $options Opções (voice, speed, format)
     * @return string|false Dados de áudio ou false em erro
     */
    public function synthesize($text, $options = []) {
        
        if (empty($text)) {
            $this->logDebug('Erro: Texto vazio fornecido');
            throw new Exception('Texto não pode estar vazio');
        }
        
        $voice = $options['voice'] ?? $this->defaultVoice;
        $speed = floatval($options['speed'] ?? $this->config['speed']);
        $format = $options['format'] ?? $this->config['response_format'];
        
        // Validar voz
        if (!isset($this->voices[$voice])) {
            $this->logDebug("Voz '$voice' não encontrada, usando padrão");
            $voice = $this->defaultVoice;
        }
        
        // Validar velocidade
        if ($speed < 0.5 || $speed > 2.0) {
            $this->logDebug("Velocidade $speed inválida, usando 1.0");
            $speed = 1.0;
        }
        
        // Montar payload
        $payload = [
            'model' => $this->config['model'],
            'input' => $text,
            'voice' => $voice,
            'response_format' => $format,
            'speed' => $speed
        ];
        
        $this->lastRequest = [
            'url' => $this->baseUrl . '/v1/audio/speech',
            'payload' => $payload,
            'timestamp' => date('Y-m-d H:i:s')
        ];
        
        return $this->makeRequest($this->lastRequest['url'], $payload);
    }
    
    /**
     * Realiza requisição HTTP à API
     * 
     * @param string $url URL da requisição
     * @param array $payload Dados a enviar
     * @return string|false Resposta ou false em erro
     */
    private function makeRequest($url, $payload) {
        
        try {
            $ch = curl_init($url);
            
            curl_setopt_array($ch, [
                CURLOPT_RETURNTRANSFER => true,
                CURLOPT_POST => true,
                CURLOPT_POSTFIELDS => json_encode($payload),
                CURLOPT_HTTPHEADER => [
                    'Content-Type: application/json',
                    'User-Agent: PHP-KokoroTTS/1.0'
                ],
                CURLOPT_TIMEOUT => $this->timeout,
                CURLOPT_CONNECTTIMEOUT => 10,
                CURLOPT_FAILONERROR => false
            ]);
            
            $response = curl_exec($ch);
            $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
            $error = curl_error($ch);
            $errorCode = curl_errno($ch);
            
            curl_close($ch);
            
            $this->lastResponse = [
                'http_code' => $httpCode,
                'error' => $error,
                'error_code' => $errorCode,
                'timestamp' => date('Y-m-d H:i:s')
            ];
            
            if ($errorCode != 0) {
                $this->logDebug("Erro cURL #$errorCode: $error");
                throw new Exception("Erro de conexão: $error");
            }
            
            if ($httpCode !== 200) {
                $this->logDebug("HTTP $httpCode retornado pela API");
                throw new Exception("API retornou HTTP $httpCode");
            }
            
            $this->logDebug("Requisição bem-sucedida - " . strlen($response) . " bytes");
            return $response;
            
        } catch (Exception $e) {
            $this->logDebug("Erro ao fazer requisição: " . $e->getMessage());
            return false;
        }
    }
    
    /**
     * Salva áudio em arquivo
     * 
     * @param string $audio Dados de áudio
     * @param string $filename Caminho do arquivo
     * @return bool Sucesso ou falha
     */
    public function saveToFile($audio, $filename) {
        
        try {
            // Criar diretório se não existir
            $dir = dirname($filename);
            if (!is_dir($dir)) {
                mkdir($dir, 0755, true);
            }
            
            $bytes = file_put_contents($filename, $audio);
            
            if ($bytes === false) {
                throw new Exception("Falha ao escrever arquivo");
            }
            
            $this->logDebug("Arquivo salvo: $filename ($bytes bytes)");
            return true;
            
        } catch (Exception $e) {
            $this->logDebug("Erro ao salvar arquivo: " . $e->getMessage());
            return false;
        }
    }
    
    /**
     * Stream de áudio diretamente para cliente HTTP
     * 
     * @param string $text Texto a sintetizar
     * @param array $options Opções de síntese
     * @return void
     */
    public function streamToClient($text, $options = []) {
        
        try {
            $audio = $this->synthesize($text, $options);
            
            if ($audio === false) {
                http_response_code(500);
                header('Content-Type: application/json');
                echo json_encode([
                    'error' => 'Falha ao gerar áudio',
                    'details' => $this->lastResponse
                ]);
                return;
            }
            
            // Headers para stream
            header('Content-Type: audio/mpeg');
            header('Content-Length: ' . strlen($audio));
            header('Cache-Control: no-cache, no-store, must-revalidate');
            header('Content-Disposition: inline; filename="audio.mp3"');
            header('X-Kokoro-Voice: ' . ($options['voice'] ?? $this->defaultVoice));
            header('X-Kokoro-Speed: ' . ($options['speed'] ?? $this->config['speed']));
            
            echo $audio;
            exit;
            
        } catch (Exception $e) {
            http_response_code(500);
            echo "Erro: " . $e->getMessage();
            exit;
        }
    }
    
    /**
     * Retorna áudio como base64 (para AJAX)
     * 
     * @param string $text Texto a sintetizar
     * @param array $options Opções de síntese
     * @return array Resposta JSON
     */
    public function synthesizeAsJSON($text, $options = []) {
        
        try {
            $audio = $this->synthesize($text, $options);
            
            if ($audio === false) {
                return [
                    'success' => false,
                    'error' => 'Falha ao gerar áudio',
                    'details' => $this->lastResponse
                ];
            }
            
            return [
                'success' => true,
                'audio' => base64_encode($audio),
                'size' => strlen($audio),
                'format' => 'mp3',
                'voice' => $options['voice'] ?? $this->defaultVoice,
                'speed' => $options['speed'] ?? $this->config['speed']
            ];
            
        } catch (Exception $e) {
            return [
                'success' => false,
                'error' => $e->getMessage()
            ];
        }
    }
    
    /**
     * Processa múltiplos textos em lote
     * 
     * @param array $texts Array de textos
     * @param string $outputDir Diretório de saída
     * @return array Resultados
     */
    public function batchProcess($texts, $outputDir = './audio_batch') {
        
        if (!is_dir($outputDir)) {
            mkdir($outputDir, 0755, true);
        }
        
        $results = [];
        
        foreach ($texts as $idx => $text) {
            
            $filename = $outputDir . '/batch_' . str_pad($idx + 1, 3, '0', STR_PAD_LEFT) . '.mp3';
            
            $audio = $this->synthesize($text);
            
            if ($audio !== false && $this->saveToFile($audio, $filename)) {
                $results[] = [
                    'index' => $idx + 1,
                    'text' => substr($text, 0, 50),
                    'status' => 'success',
                    'file' => $filename,
                    'size' => strlen($audio)
                ];
            } else {
                $results[] = [
                    'index' => $idx + 1,
                    'text' => substr($text, 0, 50),
                    'status' => 'failed',
                    'file' => null,
                    'size' => 0
                ];
            }
        }
        
        return $results;
    }
    
    /**
     * Retorna informações sobre vozes disponíveis
     * 
     * @return array Dados das vozes
     */
    public function getVoices() {
        return $this->voices;
    }
    
    /**
     * Define voz padrão
     * 
     * @param string $voice ID da voz
     * @return bool Sucesso
     */
    public function setDefaultVoice($voice) {
        
        if (!isset($this->voices[$voice])) {
            $this->logDebug("Voz '$voice' não encontrada");
            return false;
        }
        
        $this->defaultVoice = $voice;
        return true;
    }
    
    /**
     * Teste de conectividade
     * 
     * @return bool Servidor acessível
     */
    public function testConnection() {
        
        try {
            $result = $this->synthesize('Teste de conexão');
            return $result !== false;
        } catch (Exception $e) {
            return false;
        }
    }
    
    /**
     * Log para debug
     * 
     * @param string $message Mensagem a logar
     * @return void
     */
    private function logDebug($message) {
        
        if (!$this->debugMode) {
            return;
        }
        
        $timestamp = date('Y-m-d H:i:s');
        error_log("[$timestamp] KokoroTTS: $message");
    }
    
    /**
     * Retorna informações de debug
     * 
     * @return array Dados de debug
     */
    public function getDebugInfo() {
        return [
            'base_url' => $this->baseUrl,
            'default_voice' => $this->defaultVoice,
            'last_request' => $this->lastRequest,
            'last_response' => $this->lastResponse,
            'config' => $this->config
        ];
    }
}

// ============================================================================
// EXEMPLO DE USO - API REST Endpoint
// ============================================================================

// Habilitar apenas se acessado via AJAX ou API
if (php_sapi_name() !== 'cli' && basename(__FILE__) === basename($_SERVER['SCRIPT_FILENAME'] ?? '')) {
    
    header('Content-Type: application/json');
    header('Access-Control-Allow-Origin: *');
    header('Access-Control-Allow-Methods: POST, GET');
    
    if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
        http_response_code(200);
        exit;
    }
    
    try {
        $tts = new KokoroTTS('http://localhost:8880', ['debug' => true]);
        
        // Rota: GET /status
        if ($_SERVER['REQUEST_METHOD'] === 'GET' && strpos($_SERVER['REQUEST_URI'] ?? '', 'status') !== false) {
            echo json_encode([
                'status' => 'ok',
                'connected' => $tts->testConnection(),
                'voices' => $tts->getVoices(),
                'debug_info' => $tts->getDebugInfo()
            ]);
            exit;
        }
        
        // Rota: POST /synthesize
        if ($_SERVER['REQUEST_METHOD'] === 'POST') {
            
            $input = json_decode(file_get_contents('php://input'), true) ?? $_POST;
            
            if (empty($input['text'])) {
                http_response_code(400);
                echo json_encode(['error' => 'Texto não fornecido']);
                exit;
            }
            
            $result = $tts->synthesizeAsJSON($input['text'], [
                'voice' => $input['voice'] ?? 'pf_dora',
                'speed' => floatval($input['speed'] ?? 1.0)
            ]);
            
            http_response_code($result['success'] ? 200 : 500);
            echo json_encode($result);
            exit;
        }
        
        // Rota padrão
        http_response_code(405);
        echo json_encode(['error' => 'Método não permitido']);
        
    } catch (Exception $e) {
        http_response_code(500);
        echo json_encode(['error' => $e->getMessage()]);
    }
}