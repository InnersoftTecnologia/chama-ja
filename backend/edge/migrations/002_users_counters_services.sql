-- 002_users_counters_services.sql
-- Tenant management basics (users/operators, counters, services)

CREATE TABLE IF NOT EXISTS tenant_users (
  id CHAR(36) NOT NULL PRIMARY KEY,
  tenant_cpf_cnpj VARCHAR(20) NOT NULL,
  email VARCHAR(190) NOT NULL,
  full_name VARCHAR(160) NULL,
  role ENUM('admin','operator') NOT NULL DEFAULT 'operator',
  password_hash VARCHAR(255) NOT NULL,
  active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_user_tenant_email (tenant_cpf_cnpj, email),
  KEY idx_user_tenant_role (tenant_cpf_cnpj, role, active),
  CONSTRAINT fk_user_tenant
    FOREIGN KEY (tenant_cpf_cnpj) REFERENCES tenants(cpf_cnpj)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS counters (
  id CHAR(36) NOT NULL PRIMARY KEY,
  tenant_cpf_cnpj VARCHAR(20) NOT NULL,
  name VARCHAR(64) NOT NULL,
  active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_counter_tenant_name (tenant_cpf_cnpj, name),
  KEY idx_counter_tenant_active (tenant_cpf_cnpj, active),
  CONSTRAINT fk_counter_tenant
    FOREIGN KEY (tenant_cpf_cnpj) REFERENCES tenants(cpf_cnpj)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS services (
  id CHAR(36) NOT NULL PRIMARY KEY,
  tenant_cpf_cnpj VARCHAR(20) NOT NULL,
  name VARCHAR(64) NOT NULL,
  priority_mode ENUM('normal','preferential') NOT NULL DEFAULT 'normal',
  active TINYINT(1) NOT NULL DEFAULT 1,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  UNIQUE KEY uq_service_tenant_name (tenant_cpf_cnpj, name),
  KEY idx_service_tenant_active (tenant_cpf_cnpj, active),
  CONSTRAINT fk_service_tenant
    FOREIGN KEY (tenant_cpf_cnpj) REFERENCES tenants(cpf_cnpj)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

