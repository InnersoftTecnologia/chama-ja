-- Migration 006: services_ticket_prefix.sql
-- Permite serviços com mesmo nome + adiciona prefixo de senha

-- 1. Remover constraint UNIQUE que impede nomes duplicados
ALTER TABLE services DROP INDEX uq_service_tenant_name;

-- 2. Criar novo índice (não unique) para buscas
CREATE INDEX idx_service_tenant_name ON services(tenant_cpf_cnpj, name);

-- 3. Adicionar prefixo de senha (letra que identifica o serviço)
ALTER TABLE services
ADD COLUMN ticket_prefix CHAR(1) NOT NULL DEFAULT 'A' AFTER priority_mode;

-- 4. Adicionar descrição opcional do serviço
ALTER TABLE services
ADD COLUMN description VARCHAR(255) NULL AFTER ticket_prefix;
