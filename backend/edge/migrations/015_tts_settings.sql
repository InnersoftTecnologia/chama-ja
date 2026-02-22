-- Migration 015: Configurações de TTS (anúncio de voz) por tenant
ALTER TABLE tenants
  ADD COLUMN tts_enabled TINYINT(1) NOT NULL DEFAULT 0 AFTER tv_call_sound,
  ADD COLUMN tts_voice VARCHAR(50) NOT NULL DEFAULT 'pf_dora' AFTER tts_enabled;
