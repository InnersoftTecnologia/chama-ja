CREATE DATABASE IF NOT EXISTS chamador CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE chamador;

CREATE TABLE IF NOT EXISTS tenants (
  cpf_cnpj VARCHAR(20) NOT NULL PRIMARY KEY,
  nome_razao_social VARCHAR(160) NOT NULL,
  nome_fantasia VARCHAR(160) NULL,
  situacao ENUM('ativo','inativo') NOT NULL DEFAULT 'ativo',
  logo_base64 LONGTEXT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  KEY idx_tenants_situacao (situacao)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS calls (
  id CHAR(36) NOT NULL PRIMARY KEY,
  ticket_code VARCHAR(32) NOT NULL,
  service_name VARCHAR(64) NOT NULL,
  priority ENUM('normal','preferential') NOT NULL DEFAULT 'normal',
  counter_name VARCHAR(64) NOT NULL,
  status ENUM('waiting','called','in_service','done','absent') NOT NULL DEFAULT 'called',
  called_at DATETIME(6) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  KEY idx_calls_called_at (called_at),
  KEY idx_calls_status_called_at (status, called_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS announcements (
  id CHAR(36) NOT NULL PRIMARY KEY,
  message VARCHAR(255) NOT NULL,
  position INT NOT NULL DEFAULT 1,
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  KEY idx_ann_enabled_pos (enabled, position)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS youtube_urls (
  id CHAR(36) NOT NULL PRIMARY KEY,
  tenant_cpf_cnpj VARCHAR(20) NOT NULL,
  url VARCHAR(512) NOT NULL,
  title VARCHAR(128) NULL,
  position INT NOT NULL DEFAULT 1,
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  KEY idx_yu_tenant_enabled_pos (tenant_cpf_cnpj, enabled, position),
  CONSTRAINT fk_yu_tenant
    FOREIGN KEY (tenant_cpf_cnpj) REFERENCES tenants(cpf_cnpj)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS events (
  event_id CHAR(36) NOT NULL PRIMARY KEY,
  event_type VARCHAR(64) NOT NULL,
  payload_json JSON NOT NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  synced TINYINT(1) NOT NULL DEFAULT 0,
  KEY idx_events_created_at (created_at),
  KEY idx_events_synced_created_at (synced, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

