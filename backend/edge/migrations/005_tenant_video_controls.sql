-- Migration 005: Add video controls to tenants table
-- tv_video_muted: whether YouTube video is muted (0=unmuted, 1=muted)
-- tv_video_paused: whether YouTube video is paused (0=playing, 1=paused)

ALTER TABLE tenants
ADD COLUMN tv_video_muted TINYINT(1) NOT NULL DEFAULT 1 AFTER tv_audio_enabled,
ADD COLUMN tv_video_paused TINYINT(1) NOT NULL DEFAULT 0 AFTER tv_video_muted;
