# logs — Ver logs da VPS em tempo real

Exibe logs do backend, nginx ou serviço Kokoro TTS.

## Backend (chama-ja.service)

```bash
ssh -i ~/.ssh/id_ed25519_vps -o StrictHostKeyChecking=no cbruno@165.232.140.143 \
  "echo 'cbruno22' | sudo -S journalctl -u chama-ja.service -f --no-pager -n 50"
```

## Nginx (access + error)

```bash
ssh -i ~/.ssh/id_ed25519_vps -o StrictHostKeyChecking=no cbruno@165.232.140.143 \
  "echo 'cbruno22' | sudo -S tail -f /var/log/nginx/access.log /var/log/nginx/error.log"
```

## Status geral dos serviços

```bash
ssh -i ~/.ssh/id_ed25519_vps -o StrictHostKeyChecking=no cbruno@165.232.140.143 \
  "echo 'cbruno22' | sudo -S systemctl is-active chama-ja.service nginx && \
   echo 'cbruno22' | sudo -S systemctl status chama-ja.service --no-pager -l"
```

## Kokoro TTS (VPS Hostinger)

```bash
ssh -i ~/.ssh/id_ed25519_vps -o StrictHostKeyChecking=no cbruno@147.79.86.7 \
  "docker logs kokoro-tts --tail 50 -f"
```
