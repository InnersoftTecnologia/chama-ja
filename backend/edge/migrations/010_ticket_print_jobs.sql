-- Migration 010: ticket_print_jobs.sql
-- Auditoria de emissão/impressão de tickets pelo Totem (MVP)

CREATE TABLE IF NOT EXISTS ticket_print_jobs (
  id CHAR(36) NOT NULL PRIMARY KEY,
  tenant_cpf_cnpj VARCHAR(20) NOT NULL,

  ticket_id CHAR(36) NOT NULL,
  ticket_code VARCHAR(20) NOT NULL,

  service_id CHAR(36) NOT NULL,
  service_name VARCHAR(64) NOT NULL,
  priority ENUM('normal','preferential') NOT NULL DEFAULT 'normal',

  -- reservado para futuro (quando quiser amarrar emissão a guichê)
  counter_id CHAR(36) NULL,

  print_text TEXT NOT NULL,
  output_mode ENUM('download','server','both') NOT NULL DEFAULT 'both',
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),

  KEY idx_tpj_tenant_created (tenant_cpf_cnpj, created_at),
  KEY idx_tpj_ticket (ticket_id),
  KEY idx_tpj_service (service_id),

  CONSTRAINT fk_tpj_tenant
    FOREIGN KEY (tenant_cpf_cnpj) REFERENCES tenants(cpf_cnpj) ON DELETE CASCADE,
  CONSTRAINT fk_tpj_ticket
    FOREIGN KEY (ticket_id) REFERENCES tickets(id) ON DELETE CASCADE,
  CONSTRAINT fk_tpj_service
    FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

