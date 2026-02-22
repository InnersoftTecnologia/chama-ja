-- Migration 004: Add TV settings to tenants table
-- tv_theme: dark or light mode for TV display
-- tv_audio_enabled: whether to play audio on ticket calls

ALTER TABLE tenants
ADD COLUMN tv_theme ENUM('dark', 'light') NOT NULL DEFAULT 'dark' AFTER situacao,
ADD COLUMN tv_audio_enabled TINYINT(1) NOT NULL DEFAULT 1 AFTER tv_theme;
