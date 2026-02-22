-- Migration 014: Som configurável para chamada na TV
-- tv_call_sound: nome do arquivo em sounds/ (ex: notification-1.mp3)

ALTER TABLE tenants
ADD COLUMN tv_call_sound VARCHAR(255) NULL DEFAULT 'notification-1.mp3' AFTER tv_audio_enabled;
