-- Migration 007: tickets_queue.sql
-- Sistema de fila de senhas com ciclo de vida completo

-- Tabela principal de tickets (senhas)
CREATE TABLE IF NOT EXISTS tickets (
  id CHAR(36) NOT NULL PRIMARY KEY,
  tenant_cpf_cnpj VARCHAR(20) NOT NULL,

  -- Identificação da senha
  ticket_code VARCHAR(20) NOT NULL,                    -- Ex: A-001, P-015

  -- Serviço e prioridade
  service_id CHAR(36) NOT NULL,
  service_name VARCHAR(64) NOT NULL,                   -- Desnormalizado para histórico
  priority ENUM('normal','preferential') NOT NULL DEFAULT 'normal',

  -- Status do ciclo de vida
  status ENUM('waiting','called','in_service','completed','no_show','cancelled')
         NOT NULL DEFAULT 'waiting',

  -- Timestamps do ciclo de vida
  issued_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  called_at DATETIME(6) NULL,
  service_started_at DATETIME(6) NULL,
  completed_at DATETIME(6) NULL,

  -- Operador e Guichê (preenchidos quando chamado)
  operator_id CHAR(36) NULL,
  operator_name VARCHAR(160) NULL,                     -- Desnormalizado para histórico
  counter_id CHAR(36) NULL,
  counter_name VARCHAR(64) NULL,                       -- Desnormalizado para histórico

  -- Controle
  recall_count INT NOT NULL DEFAULT 0,                 -- Quantas vezes foi rechamado
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),

  -- Índices para consultas frequentes
  KEY idx_tickets_tenant_status (tenant_cpf_cnpj, status),
  KEY idx_tickets_tenant_waiting (tenant_cpf_cnpj, status, priority, issued_at),
  KEY idx_tickets_tenant_inservice (tenant_cpf_cnpj, status, service_started_at),
  KEY idx_tickets_tenant_completed (tenant_cpf_cnpj, status, completed_at),
  KEY idx_tickets_operator (operator_id, status),
  KEY idx_tickets_counter (counter_id, status),

  -- Foreign Keys
  CONSTRAINT fk_ticket_tenant
    FOREIGN KEY (tenant_cpf_cnpj) REFERENCES tenants(cpf_cnpj) ON DELETE CASCADE,
  CONSTRAINT fk_ticket_service
    FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE RESTRICT,
  CONSTRAINT fk_ticket_operator
    FOREIGN KEY (operator_id) REFERENCES tenant_users(id) ON DELETE SET NULL,
  CONSTRAINT fk_ticket_counter
    FOREIGN KEY (counter_id) REFERENCES counters(id) ON DELETE SET NULL

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Sequência de senhas por tenant/prefixo/dia (reseta diariamente)
CREATE TABLE IF NOT EXISTS ticket_sequences (
  id CHAR(36) NOT NULL PRIMARY KEY,
  tenant_cpf_cnpj VARCHAR(20) NOT NULL,
  ticket_prefix CHAR(1) NOT NULL,                      -- A, B, C, P, etc.
  current_number INT NOT NULL DEFAULT 0,
  sequence_date DATE NOT NULL,

  UNIQUE KEY uk_sequence (tenant_cpf_cnpj, ticket_prefix, sequence_date),

  CONSTRAINT fk_sequence_tenant
    FOREIGN KEY (tenant_cpf_cnpj) REFERENCES tenants(cpf_cnpj) ON DELETE CASCADE

) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
