-- Migration 011: playlist_slides.sql
-- Adiciona suporte a slides/imagens estáticas na playlist
-- A tabela youtube_urls agora suporta tanto vídeos do YouTube quanto slides

ALTER TABLE youtube_urls
ADD COLUMN media_type ENUM('youtube', 'slide') NOT NULL DEFAULT 'youtube' AFTER tenant_cpf_cnpj,
ADD COLUMN image_url VARCHAR(512) NULL AFTER youtube_id,
ADD COLUMN slide_duration_seconds INT UNSIGNED NULL DEFAULT 10 AFTER image_url;

-- Índice para buscar por media_type
CREATE INDEX idx_youtube_urls_media_type ON youtube_urls(tenant_cpf_cnpj, media_type, enabled, position);

-- Atualizar registros existentes para garantir que sejam do tipo 'youtube'
UPDATE youtube_urls SET media_type = 'youtube' WHERE media_type IS NULL OR media_type = '';
