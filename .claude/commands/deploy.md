# deploy — Sincroniza e deploya na VPS

Sincronize os arquivos modificados localmente para a VPS da Innersoft e reinicie os serviços necessários.

## VPS
- Host: `165.232.140.143` — `cbruno@165.232.140.143`
- SSH key: `~/.ssh/id_ed25519_vps`
- Projeto na VPS: `/home/bruno/chama-ja/`
- Sudo password: `cbruno22`

## Passos

1. **Identifique** quais arquivos foram modificados (`git diff --stat` ou `git status`)
2. **Rsync** cada arquivo modificado:
   ```bash
   rsync -avz -e "ssh -i ~/.ssh/id_ed25519_vps -o StrictHostKeyChecking=no" \
     <arquivo_local> cbruno@165.232.140.143:/home/bruno/chama-ja/<caminho_relativo>
   ```
3. **Se `backend/edge/app.py` foi alterado**, reinicie o backend:
   ```bash
   ssh -i ~/.ssh/id_ed25519_vps cbruno@165.232.140.143 \
     "echo 'cbruno22' | sudo -S systemctl restart chama-ja.service && \
      echo 'cbruno22' | sudo -S systemctl is-active chama-ja.service"
   ```
4. **Se arquivos nginx foram alterados** (`deploy/nginx/`), faça o deploy da config e recarregue:
   ```bash
   ssh -i ~/.ssh/id_ed25519_vps cbruno@165.232.140.143 \
     "echo 'cbruno22' | sudo -S cp /home/bruno/chama-ja/deploy/nginx/server.conf \
       /etc/nginx/sites-available/chama-ja && \
      echo 'cbruno22' | sudo -S nginx -t && \
      echo 'cbruno22' | sudo -S systemctl reload nginx"
   ```
5. **Verifique** os endpoints principais após o deploy.

## Mapeamento de paths

| Local | VPS |
|-------|-----|
| `backend/edge/app.py` | `/home/bruno/chama-ja/backend/edge/app.py` |
| `frontend/tv/` | `/home/bruno/chama-ja/frontend/tv/` |
| `frontend/operator/` | `/home/bruno/chama-ja/frontend/operator/` |
| `frontend/admin-tenant/` | `/home/bruno/chama-ja/frontend/admin-tenant/` |
| `frontend/totem/` | `/home/bruno/chama-ja/frontend/totem/` |
| `frontend/dashboard/` | `/home/bruno/chama-ja/frontend/dashboard/` |
| `frontend/site/` | `/home/bruno/chama-ja/frontend/site/` |
| `deploy/nginx/server.conf` | `/etc/nginx/sites-available/chama-ja` (via cp) |
| `deploy/nginx/clients/` | `/home/bruno/chama-ja/deploy/nginx/clients/` |
