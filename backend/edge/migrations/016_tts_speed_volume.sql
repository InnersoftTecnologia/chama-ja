-- Migration 016: Controles de velocidade e volume do TTS por tenant
ALTER TABLE tenants
  ADD COLUMN tts_speed DECIMAL(4,2) NOT NULL DEFAULT 0.85 AFTER tts_voice,
  ADD COLUMN tts_volume DECIMAL(4,2) NOT NULL DEFAULT 1.00 AFTER tts_speed;
