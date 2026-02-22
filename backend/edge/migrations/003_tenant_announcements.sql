-- 003_tenant_announcements.sql
-- Announcements per tenant (ticker messages)

CREATE TABLE IF NOT EXISTS tenant_announcements (
  id CHAR(36) NOT NULL PRIMARY KEY,
  tenant_cpf_cnpj VARCHAR(20) NOT NULL,
  message VARCHAR(255) NOT NULL,
  position INT NOT NULL DEFAULT 1,
  enabled TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  KEY idx_ta_tenant_enabled_pos (tenant_cpf_cnpj, enabled, position),
  CONSTRAINT fk_ta_tenant
    FOREIGN KEY (tenant_cpf_cnpj) REFERENCES tenants(cpf_cnpj)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

