-- Migration 008: youtube_metadata.sql
-- Campos extras para metadados de vídeos YouTube

ALTER TABLE youtube_urls
ADD COLUMN description VARCHAR(255) NULL AFTER title,
ADD COLUMN author_name VARCHAR(100) NULL AFTER description,
ADD COLUMN thumbnail_url VARCHAR(512) NULL AFTER author_name,
ADD COLUMN duration_seconds INT UNSIGNED NULL AFTER thumbnail_url,
ADD COLUMN youtube_id VARCHAR(20) NULL AFTER duration_seconds,
ADD COLUMN metadata_fetched_at DATETIME(6) NULL AFTER youtube_id;

-- Índice para buscar por youtube_id
CREATE INDEX idx_youtube_urls_ytid ON youtube_urls(tenant_cpf_cnpj, youtube_id);
