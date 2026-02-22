-- Migration 009: calls_tenant_scope.sql
-- Adiciona tenant_cpf_cnpj à tabela calls para isolamento multi-tenant

-- Adicionar coluna (permite NULL temporariamente para dados existentes)
ALTER TABLE calls
ADD COLUMN tenant_cpf_cnpj VARCHAR(20) NULL AFTER id;

-- Atualizar registros existentes com o tenant padrão (se houver)
UPDATE calls SET tenant_cpf_cnpj = '10230480000130' WHERE tenant_cpf_cnpj IS NULL;

-- Tornar NOT NULL após atualização
ALTER TABLE calls MODIFY COLUMN tenant_cpf_cnpj VARCHAR(20) NOT NULL;

-- Adicionar campos que faltam para rastreabilidade
ALTER TABLE calls
ADD COLUMN operator_id CHAR(36) NULL AFTER counter_name,
ADD COLUMN operator_name VARCHAR(160) NULL AFTER operator_id,
ADD COLUMN counter_id CHAR(36) NULL AFTER operator_name,
ADD COLUMN service_started_at DATETIME(6) NULL AFTER called_at,
ADD COLUMN completed_at DATETIME(6) NULL AFTER service_started_at;

-- Índices para consultas por tenant
CREATE INDEX idx_calls_tenant_status ON calls(tenant_cpf_cnpj, status, called_at);

-- Foreign Key
ALTER TABLE calls
ADD CONSTRAINT fk_calls_tenant
  FOREIGN KEY (tenant_cpf_cnpj) REFERENCES tenants(cpf_cnpj) ON DELETE CASCADE;
