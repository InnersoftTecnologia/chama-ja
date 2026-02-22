#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kokoro TTS - Cliente Python Completo
=====================================

Sistema de síntese de voz em português brasileiro usando Kokoro TTS.
Suporte a múltiplas vozes, cache inteligente e processamento em lote.

Autor: Bruno (Assistente IA)
Data: 27/01/2025
Versão: 1.0.0
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

class KokoroTTSClient:
    """Cliente Python para Kokoro TTS"""
    
    def __init__(self, config: KokoroConfig = None):
        self.config = config or KokoroConfig()
        self.session = requests.Session()
        self.cache = {} if self.config.cache_enabled else None
        self.stats = {
            'requests': 0,
            'cache_hits': 0,
            'errors': 0,
            'total_audio_time': 0
        }
        
        # Criar diretório de saída
        self.output_dir = Path("audio_output")
        self.output_dir.mkdir(exist_ok=True)
        
        logger.info(f"Cliente Kokoro TTS inicializado - URL: {self.config.base_url}")
    
    def _get_cache_key(self, text: str, voice: str, speed: float) -> str:
        """Gerar chave de cache baseada no texto e parâmetros"""
        content = f"{text}|{voice}|{speed}|{self.config.audio_format}"
        return hashlib.md5(content.encode()).hexdigest()
    
    def _make_request(self, endpoint: str, data: dict = None, method: str = "GET") -> dict:
        """Fazer requisição HTTP com retry automático"""
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
        
        # Preparar dados da requisição
        data = {
            "model": "kokoro",
            "input": text,
            "voice": voice,
            "response_format": self.config.audio_format,
            "speed": speed
        }
        
        try:
            logger.info(f"Sintetizando: '{text[:50]}...' com voz '{voice}'")
            
            # Fazer requisição
            url = f"{self.config.base_url}/v1/audio/speech"
            response = self.session.post(
                url,
                json=data,
                timeout=self.config.timeout,
                headers={'Content-Type': 'application/json'}
            )
            response.raise_for_status()
            
            audio_data = response.content
            
            # Salvar no cache
            if self.cache is not None:
                cache_key = self._get_cache_key(text, voice, speed)
                self.cache[cache_key] = audio_data
            
            # Atualizar estatísticas
            self.stats['total_audio_time'] += len(text.split()) * 0.5  # Estimativa
            
            logger.info(f"Áudio sintetizado com sucesso - {len(audio_data)} bytes")
            return audio_data
            
        except Exception as e:
            self.stats['errors'] += 1
            logger.error(f"Erro na síntese: {e}")
            raise
    
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
            filename = f"audio_{timestamp}.{self.config.audio_format}"
        
        return self.save_audio(audio_data, filename)
    
    def batch_process(self, texts: List[str], voice: str = None, speed: float = None) -> List[str]:
        """Processar múltiplos textos em lote"""
        results = []
        
        logger.info(f"Processando lote de {len(texts)} textos")
        
        for i, text in enumerate(texts, 1):
            try:
                filename = f"batch_{i:03d}.{self.config.audio_format}"
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
                filename = f"compare_{voice}.{self.config.audio_format}"
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
    print("\n🎤 DEMONSTRAÇÃO - CONVERSA MULTI-TURNO")
    print("=" * 50)
    
    config = KokoroConfig(
        base_url="http://localhost:8880",
        default_voice="pf_dora"
    )
    
    client = KokoroTTSClient(config)
    
    # Testar conexão
    if not client.test_connection():
        print("❌ Erro: Não foi possível conectar ao servidor Kokoro")
        print("   Certifique-se de que o servidor está rodando em http://localhost:8880")
        return
    
    print("✅ Conectado ao servidor Kokoro")
    
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
            filename = f"conversa_{i:02d}.mp3"
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

def demo_voice_comparison():
    """Demonstração de comparação de vozes"""
    print("\n🎭 DEMONSTRAÇÃO - COMPARAÇÃO DE VOZES")
    print("=" * 50)
    
    config = KokoroConfig(base_url="http://localhost:8880")
    client = KokoroTTSClient(config)
    
    if not client.test_connection():
        print("❌ Erro: Servidor Kokoro não disponível")
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
    print("🎤 KOKORO TTS - CLIENTE PYTHON")
    print("=" * 40)
    print("Sistema de síntese de voz em português brasileiro")
    print("Autor: Bruno (Assistente IA)")
    print("Data: 27/01/2025")
    print("=" * 40)
    
    try:
        # Demonstração 1: Conversa
        demo_conversation()
        
        # Demonstração 2: Comparação de vozes
        demo_voice_comparison()
        
        print("\n🎉 Demonstração concluída!")
        print("📁 Arquivos de áudio salvos em: audio_output/")
        
    except KeyboardInterrupt:
        print("\n\n⏹️ Demonstração interrompida pelo usuário")
    except Exception as e:
        print(f"\n❌ Erro inesperado: {e}")
        logger.exception("Erro na demonstração")

if __name__ == "__main__":
    main()

