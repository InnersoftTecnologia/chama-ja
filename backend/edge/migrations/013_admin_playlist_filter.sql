-- Migration 013: admin_playlist_filter.sql
-- Adiciona campo para persistir preferência de filtro da playlist no painel admin

ALTER TABLE tenants
ADD COLUMN admin_playlist_filter ENUM('all', 'videos', 'slides') NOT NULL DEFAULT 'all' 
AFTER tv_video_paused;
