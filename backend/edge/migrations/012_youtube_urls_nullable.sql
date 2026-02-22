-- Migration 012: youtube_urls_nullable.sql
-- Permite que a coluna 'url' seja NULL para suportar slides (que não têm URL)

ALTER TABLE youtube_urls
MODIFY COLUMN url VARCHAR(512) NULL;
