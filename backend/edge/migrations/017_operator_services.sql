-- Migration 017: Tabela de atribuição de serviços por operador
-- Permite configurar quais serviços/setores cada operador atende.
-- Operador sem registros nesta tabela continua vendo todos os tickets (retrocompatível).

CREATE TABLE IF NOT EXISTS operator_services (
  operator_id CHAR(36) NOT NULL,
  service_id  CHAR(36) NOT NULL,
  PRIMARY KEY (operator_id, service_id),
  CONSTRAINT fk_os_operator FOREIGN KEY (operator_id)
    REFERENCES tenant_users(id) ON DELETE CASCADE,
  CONSTRAINT fk_os_service FOREIGN KEY (service_id)
    REFERENCES services(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
