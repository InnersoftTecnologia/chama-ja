# migrate — Roda migrations e/ou seed na VPS

Execute migrations e seed no banco de dados da VPS.

## Pré-requisito: obter EDGE_DEVICE_TOKEN

```bash
ssh -i ~/.ssh/id_ed25519_vps -o StrictHostKeyChecking=no cbruno@165.232.140.143 \
  "grep EDGE_DEVICE_TOKEN /home/bruno/chama-ja/.env"
```

## Rodar migrations (sem reset)

```bash
ssh -i ~/.ssh/id_ed25519_vps -o StrictHostKeyChecking=no cbruno@165.232.140.143 \
  "TOKEN=\$(grep EDGE_DEVICE_TOKEN /home/bruno/chama-ja/.env | cut -d= -f2) && \
   curl -s -X POST 'http://localhost:7071/admin/migrate?reset=0' \
     -H \"Authorization: Bearer \$TOKEN\" | python3 -m json.tool"
```

## Rodar seed

```bash
ssh -i ~/.ssh/id_ed25519_vps -o StrictHostKeyChecking=no cbruno@165.232.140.143 \
  "TOKEN=\$(grep EDGE_DEVICE_TOKEN /home/bruno/chama-ja/.env | cut -d= -f2) && \
   curl -s -X POST 'http://localhost:7071/admin/seed' \
     -H \"Authorization: Bearer \$TOKEN\" | python3 -m json.tool"
```

## Reset completo (CUIDADO: apaga todos os dados)

```bash
ssh -i ~/.ssh/id_ed25519_vps -o StrictHostKeyChecking=no cbruno@165.232.140.143 \
  "TOKEN=\$(grep EDGE_DEVICE_TOKEN /home/bruno/chama-ja/.env | cut -d= -f2) && \
   curl -s -X POST 'http://localhost:7071/admin/migrate?reset=1' \
     -H \"Authorization: Bearer \$TOKEN\" | python3 -m json.tool"
```

## Banco de dados

- DB: `chamador` (MariaDB local na VPS)
- User: `chamador` / `Cham@d0r2026`
- Migrations em: `backend/edge/migrations/001–017+`
