-- Migration 018: printer_config
-- Configuração de impressora térmica por tenant + campos de status no print_jobs

-- Colunas de impressora no tenant
ALTER TABLE tenants
  ADD COLUMN printer_enabled  TINYINT(1)       NOT NULL DEFAULT 0        AFTER admin_playlist_filter,
  ADD COLUMN printer_ip       VARCHAR(64)      NULL                      AFTER printer_enabled,
  ADD COLUMN printer_port     SMALLINT UNSIGNED NOT NULL DEFAULT 9100    AFTER printer_ip,
  ADD COLUMN print_agent_token CHAR(36)        NULL                      AFTER printer_port;

-- Gera token único para tenants já existentes
UPDATE tenants SET print_agent_token = UUID() WHERE print_agent_token IS NULL;

ALTER TABLE tenants MODIFY COLUMN print_agent_token CHAR(36) NOT NULL;

-- Campos de controle de status no job de impressão
ALTER TABLE ticket_print_jobs
  ADD COLUMN status       ENUM('pending','printed','failed') NOT NULL DEFAULT 'pending' AFTER output_mode,
  ADD COLUMN print_data_b64 MEDIUMTEXT NULL                                             AFTER status,
  ADD COLUMN printed_at   DATETIME(6) NULL                                              AFTER print_data_b64,
  ADD COLUMN error_msg    VARCHAR(255) NULL                                             AFTER printed_at,
  ADD KEY idx_tpj_pending (tenant_cpf_cnpj, status, created_at);
