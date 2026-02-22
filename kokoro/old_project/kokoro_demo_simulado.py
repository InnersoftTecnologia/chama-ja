#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kokoro TTS - Cliente Python com Simulação Local
===============================================

Sistema de síntese de voz em português brasileiro usando Kokoro TTS.
Versão com simulação local para teste sem servidor.

Autor: Bruno (Assistente IA)
Data: 27/01/2025
Versão: 1.0.0 (Simulação Local)
"""

import requests
import json
import base64
import os
import time
import hashlib
from typing import Dict, List, Optional, Union
from dataclasses import dataclass
from pathlib import Path
import logging
import wave
import struct
import math

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class KokoroConfig:
    """Configurações do cliente Kokoro TTS"""
    base_url: str = "http://localhost:8880"
    default_voice: str = "pf_dora"
    timeout: int = 30
    max_retries: int = 3
    cache_enabled: bool = True
    audio_format: str = "mp3"
    speed: float = 1.0
    simulation_mode: bool = True  # Modo simulação local

class KokoroTTSClient:
    """Cliente Python para Kokoro TTS com simulação local"""
    
    def __init__(self, config: KokoroConfig = None):
        self.config = config or KokoroConfig()
        self.session = requests.Session()
        self.cache = {} if self.config.cache_enabled else None
        self.stats = {
            'requests': 0,
            'cache_hits': 0,
            'errors': 0,
            'total_audio_time': 0,
            'simulation_mode': self.config.simulation_mode
        }
        
        # Criar diretório de saída
        self.output_dir = Path("audio_output")
        self.output_dir.mkdir(exist_ok=True)
        
        if self.config.simulation_mode:
            logger.info("🎭 Modo SIMULAÇÃO LOCAL ativado - Não precisa de servidor Kokoro")
        else:
            logger.info(f"🌐 Modo SERVIDOR - URL: {self.config.base_url}")
    
    def _get_cache_key(self, text: str, voice: str, speed: float) -> str:
        """Gerar chave de cache baseada no texto e parâmetros"""
        content = f"{text}|{voice}|{speed}|{self.config.audio_format}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def _generate_silence_audio(self, duration: float = 1.0) -> bytes:
        """Gerar áudio de silêncio para simulação"""
        sample_rate = 22050
        samples = int(sample_rate * duration)
        
        # Criar dados de áudio (silêncio)
        audio_data = []
        for i in range(samples):
            # Gerar um tom suave baseado no texto para simular "fala"
            frequency = 440 + (i % 100)  # Tom variável
            amplitude = 0.1  # Volume baixo
            sample = amplitude * math.sin(2 * math.pi * frequency * i / sample_rate)
            audio_data.append(int(sample * 32767))
        
        # Converter para bytes (formato WAV simples)
        wav_data = b''
        for sample in audio_data:
            wav_data += struct.pack('<h', sample)
        
        return wav_data
    
    def _simulate_audio_generation(self, text: str, voice: str) -> bytes:
        """Simular geração de áudio baseada no texto"""
        # Calcular duração baseada no número de palavras
        words = len(text.split())
        duration = max(1.0, words * 0.3)  # ~0.3s por palavra
        
        logger.info(f"🎭 Simulando áudio: '{text[:30]}...' ({words} palavras, {duration:.1f}s)")
        
        # Simular delay de processamento
        time.sleep(0.5)
        
        # Gerar áudio simulado
        audio_data = self._generate_silence_audio(duration)
        
        # Adicionar header WAV simples
        wav_header = self._create_wav_header(len(audio_data), 22050)
        return wav_header + audio_data
    
    def _create_wav_header(self, data_size: int, sample_rate: int = 22050) -> bytes:
        """Criar header WAV simples"""
        header = b'RIFF'
        header += struct.pack('<I', data_size + 36)  # File size
        header += b'WAVE'
        header += b'fmt '
        header += struct.pack('<I', 16)  # Format chunk size
        header += struct.pack('<H', 1)   # Audio format (PCM)
        header += struct.pack('<H', 1)   # Number of channels
        header += struct.pack('<I', sample_rate)  # Sample rate
        header += struct.pack('<I', sample_rate * 2)  # Byte rate
        header += struct.pack('<H', 2)   # Block align
        header += struct.pack('<H', 16)  # Bits per sample
        header += b'data'
        header += struct.pack('<I', data_size)  # Data size
        return header
    
    def _make_request(self, endpoint: str, data: dict = None, method: str = "GET") -> dict:
        """Fazer requisição HTTP ou simular"""
        if self.config.simulation_mode:
            return self._simulate_request(endpoint, data, method)
        
        url = f"{self.config.base_url}{endpoint}"
        
        for attempt in range(self.config.max_retries):
            try:
                self.stats['requests'] += 1
                
                if method.upper() == "POST":
                    response = self.session.post(
                        url, 
                        json=data, 
                        timeout=self.config.timeout,
                        headers={'Content-Type': 'application/json'}
                    )
                else:
                    response = self.session.get(url, timeout=self.config.timeout)
                
                response.raise_for_status()
                return response.json() if response.content else {}
                
            except requests.exceptions.RequestException as e:
                logger.warning(f"Tentativa {attempt + 1} falhou: {e}")
                if attempt == self.config.max_retries - 1:
                    self.stats['errors'] += 1
                    raise
                time.sleep(1)
    
    def _simulate_request(self, endpoint: str, data: dict = None, method: str = "GET") -> dict:
        """Simular requisições HTTP"""
        self.stats['requests'] += 1
        
        if endpoint == "/health":
            return {"status": "ok", "simulation": True}
        
        elif endpoint == "/voices":
            return {
                "voices": {
                    "pf_dora": {"name": "Dora", "gender": "female", "language": "pt-BR"},
                    "pm_alex": {"name": "Alex", "gender": "male", "language": "pt-BR"},
                    "pm_santa": {"name": "Santa", "gender": "male", "language": "pt-BR"}
                }
            }
        
        elif endpoint == "/v1/audio/speech":
            # Simular resposta de síntese
            return {"status": "success", "simulation": True}
        
        return {"status": "ok", "simulation": True}
    
    def test_connection(self) -> bool:
        """Testar conexão com o servidor Kokoro"""
        try:
            result = self._make_request("/health")
            return result.get("status") == "ok"
        except:
            return False
    
    def get_voices(self) -> Dict[str, dict]:
        """Obter vozes disponíveis"""
        try:
            result = self._make_request("/voices")
            return result.get("voices", {})
        except Exception as e:
            logger.error(f"Erro ao obter vozes: {e}")
            return {}
    
    def synthesize(self, text: str, voice: str = None, speed: float = None) -> bytes:
        """Sintetizar texto em áudio"""
        voice = voice or self.config.default_voice
        speed = speed or self.config.speed
        
        # Verificar cache
        if self.cache is not None:
            cache_key = self._get_cache_key(text, voice, speed)
            if cache_key in self.cache:
                self.stats['cache_hits'] += 1
                logger.info("Cache hit - áudio recuperado do cache")
                return self.cache[cache_key]
        
        if self.config.simulation_mode:
            # Modo simulação
            audio_data = self._simulate_audio_generation(text, voice)
        else:
            # Modo servidor real
            data = {
                "model": "kokoro",
                "input": text,
                "voice": voice,
                "response_format": self.config.audio_format,
                "speed": speed
            }
            
            try:
                logger.info(f"Sintetizando: '{text[:50]}...' com voz '{voice}'")
                
                url = f"{self.config.base_url}/v1/audio/speech"
                response = self.session.post(
                    url,
                    json=data,
                    timeout=self.config.timeout,
                    headers={'Content-Type': 'application/json'}
                )
                response.raise_for_status()
                audio_data = response.content
                
            except Exception as e:
                self.stats['errors'] += 1
                logger.error(f"Erro na síntese: {e}")
                raise
        
        # Salvar no cache
        if self.cache is not None:
            cache_key = self._get_cache_key(text, voice, speed)
            self.cache[cache_key] = audio_data
        
        # Atualizar estatísticas
        self.stats['total_audio_time'] += len(text.split()) * 0.5
        
        logger.info(f"Áudio {'simulado' if self.config.simulation_mode else 'sintetizado'} com sucesso - {len(audio_data)} bytes")
        return audio_data
    
    def save_audio(self, audio_data: bytes, filename: str) -> str:
        """Salvar áudio em arquivo"""
        filepath = self.output_dir / filename
        
        with open(filepath, 'wb') as f:
            f.write(audio_data)
        
        logger.info(f"Áudio salvo em: {filepath}")
        return str(filepath)
    
    def audio_to_base64(self, audio_data: bytes) -> str:
        """Converter áudio para base64 (útil para AJAX)"""
        return base64.b64encode(audio_data).decode('utf-8')
    
    def synthesize_and_save(self, text: str, filename: str = None, voice: str = None, speed: float = None) -> str:
        """Sintetizar e salvar em arquivo"""
        audio_data = self.synthesize(text, voice, speed)
        
        if filename is None:
            timestamp = int(time.time())
            filename = f"audio_{timestamp}.wav"
        
        return self.save_audio(audio_data, filename)
    
    def batch_process(self, texts: List[str], voice: str = None, speed: float = None) -> List[str]:
        """Processar múltiplos textos em lote"""
        results = []
        
        logger.info(f"Processando lote de {len(texts)} textos")
        
        for i, text in enumerate(texts, 1):
            try:
                filename = f"batch_{i:03d}.wav"
                filepath = self.synthesize_and_save(text, filename, voice, speed)
                results.append(filepath)
                logger.info(f"Processado {i}/{len(texts)}: {filename}")
                
            except Exception as e:
                logger.error(f"Erro no item {i}: {e}")
                results.append(None)
        
        return results
    
    def compare_voices(self, text: str, voices: List[str] = None) -> Dict[str, str]:
        """Comparar diferentes vozes com o mesmo texto"""
        if voices is None:
            voices = ["pf_dora", "pm_alex", "pm_santa"]
        
        results = {}
        
        logger.info(f"Comparando {len(voices)} vozes para: '{text[:30]}...'")
        
        for voice in voices:
            try:
                filename = f"compare_{voice}.wav"
                filepath = self.synthesize_and_save(text, filename, voice)
                results[voice] = filepath
                logger.info(f"Voz '{voice}' processada")
                
            except Exception as e:
                logger.error(f"Erro com voz '{voice}': {e}")
                results[voice] = None
        
        return results
    
    def get_stats(self) -> Dict[str, Union[int, float]]:
        """Obter estatísticas do cliente"""
        cache_hit_rate = 0
        if self.stats['requests'] > 0:
            cache_hit_rate = (self.stats['cache_hits'] / self.stats['requests']) * 100
        
        return {
            **self.stats,
            'cache_hit_rate': round(cache_hit_rate, 2),
            'cache_size': len(self.cache) if self.cache else 0
        }
    
    def clear_cache(self):
        """Limpar cache"""
        if self.cache is not None:
            self.cache.clear()
            logger.info("Cache limpo")

def demo_conversation():
    """Demonstração de conversa multi-turno"""
    print("\n🎤 DEMONSTRAÇÃO - CONVERSA MULTI-TURNO (SIMULAÇÃO)")
    print("=" * 60)
    
    config = KokoroConfig(
        base_url="http://localhost:8880",
        default_voice="pf_dora",
        simulation_mode=True  # Ativar simulação
    )
    
    client = KokoroTTSClient(config)
    
    # Testar conexão
    if not client.test_connection():
        print("❌ Erro: Não foi possível conectar ao servidor")
        return
    
    print("✅ Conectado (modo simulação)")
    
    # Obter vozes disponíveis
    voices = client.get_voices()
    print(f"📢 Vozes disponíveis: {list(voices.keys())}")
    
    # Conversa simulada
    conversation = [
        "Olá! Bem-vindo ao sistema Kokoro TTS.",
        "Eu sou a assistente virtual Dora.",
        "Como posso ajudá-lo hoje?",
        "Posso sintetizar qualquer texto em português brasileiro.",
        "Até logo! Tenha um ótimo dia!"
    ]
    
    print(f"\n🗣️ Processando conversa com {len(conversation)} mensagens...")
    
    for i, message in enumerate(conversation, 1):
        try:
            filename = f"conversa_{i:02d}.wav"
            filepath = client.synthesize_and_save(message, filename)
            print(f"✅ {i}/5: {message[:40]}... -> {filename}")
            
        except Exception as e:
            print(f"❌ {i}/5: Erro - {e}")
    
    # Estatísticas
    stats = client.get_stats()
    print(f"\n📊 Estatísticas:")
    print(f"   Requisições: {stats['requests']}")
    print(f"   Cache hits: {stats['cache_hits']}")
    print(f"   Taxa de cache: {stats['cache_hit_rate']}%")
    print(f"   Erros: {stats['errors']}")
    print(f"   Modo: {'Simulação' if stats['simulation_mode'] else 'Servidor'}")

def demo_voice_comparison():
    """Demonstração de comparação de vozes"""
    print("\n🎭 DEMONSTRAÇÃO - COMPARAÇÃO DE VOZES (SIMULAÇÃO)")
    print("=" * 60)
    
    config = KokoroConfig(
        base_url="http://localhost:8880",
        simulation_mode=True
    )
    client = KokoroTTSClient(config)
    
    if not client.test_connection():
        print("❌ Erro: Servidor não disponível")
        return
    
    text = "Olá! Esta é uma demonstração das diferentes vozes disponíveis no Kokoro TTS."
    
    voices = ["pf_dora", "pm_alex", "pm_santa"]
    results = client.compare_voices(text, voices)
    
    print(f"📝 Texto: '{text}'")
    print(f"🎤 Comparando {len(voices)} vozes:")
    
    for voice, filepath in results.items():
        if filepath:
            print(f"✅ {voice}: {filepath}")
        else:
            print(f"❌ {voice}: Erro na síntese")

def main():
    """Função principal"""
    print("🎤 KOKORO TTS - CLIENTE PYTHON (SIMULAÇÃO LOCAL)")
    print("=" * 50)
    print("Sistema de síntese de voz em português brasileiro")
    print("Modo: SIMULAÇÃO LOCAL (sem servidor)")
    print("Autor: Bruno (Assistente IA)")
    print("Data: 27/01/2025")
    print("=" * 50)
    
    try:
        # Demonstração 1: Conversa
        demo_conversation()
        
        # Demonstração 2: Comparação de vozes
        demo_voice_comparison()
        
        print("\n🎉 Demonstração concluída!")
        print("📁 Arquivos de áudio simulados salvos em: audio_output/")
        print("🎭 Nota: Estes são arquivos de áudio simulados para demonstração")
        
    except KeyboardInterrupt:
        print("\n\n⏹️ Demonstração interrompida pelo usuário")
    except Exception as e:
        print(f"\n❌ Erro inesperado: {e}")
        logger.exception("Erro na demonstração")

if __name__ == "__main__":
    main()
