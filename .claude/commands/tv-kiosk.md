# tv-kiosk — Configurar Chrome para modo kiosk na TV

Configure o Chrome/Chromium na máquina da TV para abrir automaticamente o painel em modo kiosk, com autoplay de áudio sem necessidade de clique.

## Configuração recomendada

### Opção 1: Atalho/script de inicialização

Crie um script `start-tv.sh` na máquina da TV:

```bash
#!/bin/bash
# Fecha Chrome existente
pkill -f chrome 2>/dev/null
sleep 1

# Abre em modo kiosk com autoplay habilitado
google-chrome \
  --kiosk \
  --autoplay-policy=no-user-gesture-required \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --disable-restore-session-state \
  --noerrdialogs \
  --no-first-run \
  "https://innersoft.com.br/chama-ja/fcosta-gus/tv/"
```

```bash
chmod +x start-tv.sh
```

### Opção 2: Política do Chrome (persiste para sempre)

Crie o arquivo de política:

```bash
sudo mkdir -p /etc/opt/chrome/policies/managed/
sudo tee /etc/opt/chrome/policies/managed/chama-ja.json > /dev/null <<'EOF'
{
  "AutoplayAllowed": true,
  "AutoplayAllowlist": ["https://innersoft.com.br"]
}
EOF
```

Após isso, o Chrome permite autoplay no site sem flags adicionais.

### Opção 3: Configuração manual (uma vez no browser)

1. Acesse `chrome://settings/content/sound`
2. Em **"Permitido reproduzir som"**, adicione: `https://innersoft.com.br`
3. Pronto — persiste entre reinicializações do browser

## URL do painel TV

```
https://innersoft.com.br/chama-ja/fcosta-gus/tv/
```

## Comportamento esperado após configuração

- **Kiosk configurado**: overlay de áudio aparece por ~100ms e some automaticamente
- **Sem configuração**: overlay grande "Toque para ativar o áudio" fica visível até o primeiro toque
