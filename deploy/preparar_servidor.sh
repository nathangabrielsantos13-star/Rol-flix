#!/bin/sh
# Prepara um servidor Ubuntu novo. Pode rodar de novo sem estragar nada.
# Uso, no servidor: sh preparar_servidor.sh /tmp/roleflix-deploy.tar.gz
set -eu
pacote="${1:-/tmp/roleflix-deploy.tar.gz}"
pasta=/opt/roleflix

if ! command -v docker >/dev/null 2>&1; then
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker "$(id -un)"
fi

# As imagens Ubuntu da Oracle bloqueiam as portas no próprio sistema, além do painel.
for porta in 80 443; do
    sudo iptables -C INPUT -p tcp --dport "$porta" -j ACCEPT 2>/dev/null ||
        sudo iptables -I INPUT 1 -p tcp --dport "$porta" -j ACCEPT
done
sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y iptables-persistent >/dev/null
sudo netfilter-persistent save >/dev/null

sudo mkdir -p "$pasta"
sudo chown "$(id -un):$(id -gn)" "$pasta"
tar -xzf "$pacote" -C "$pasta"
cd "$pasta"
mkdir -p data backups
sudo chown 1000:1000 data

if [ ! -f .env ]; then
    cp .env.production.example .env
    chave=$(python3 -c "import secrets; print(secrets.token_urlsafe(50))")
    sed -i "s|^DJANGO_SECRET_KEY=.*|DJANGO_SECRET_KEY=$chave|" .env
    chmod 600 .env
    echo "Criei o .env com uma chave secreta. Agora preencha o resto: nano $pasta/.env"
fi
echo "Servidor pronto. Se o Docker acabou de ser instalado, saia e entre de novo no SSH."
