# Como publicar o Rolêflix

Para publicar sem pagar nada, siga o [DEPLOY-GRATIS.md](DEPLOY-GRATIS.md). Este guia é para um VPS pago.

Guia para colocar o site no ar em um VPS Linux com Ubuntu 24.04. Os comandos das partes 4 em diante rodam no servidor.

## 1. Contratar

1. **VPS:** pelo menos 2 vCPU, 8 GB de RAM e 100 GB de disco, de preferência em São Paulo.
2. **Domínio:** por exemplo, no Registro.br.
3. **E-mail:** Brevo ou Resend. Sem isso, ninguém conclui o cadastro.

## 2. Apontar o domínio

No painel do domínio, crie um registro DNS do tipo **A** para o domínio, com o IP do VPS.

## 3. Configurar o e-mail

No serviço de e-mail, adicione o domínio e copie os registros DNS que ele indicar. Depois, anote os dados SMTP: servidor, usuário e senha.

## 4. Preparar o servidor

No computador, gere o pacote e envie:

```powershell
powershell -File deploy\empacotar.ps1
scp ..\roleflix-deploy.tar.gz root@IP_DO_SERVIDOR:/root/
ssh root@IP_DO_SERVIDOR
```

No servidor:

```sh
curl -fsSL https://get.docker.com | sh
ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw --force enable
mkdir -p /opt/roleflix && tar -xzf /root/roleflix-deploy.tar.gz -C /opt/roleflix
cd /opt/roleflix
mkdir -p data && chown 1000:1000 data
cp .env.production.example .env
nano .env
```

Preencha o `.env`. A chave secreta sai deste comando:

```sh
python3 -c "import secrets; print(secrets.token_urlsafe(50))"
```

## 5. Subir o site

```sh
docker compose up -d --build
docker compose logs web | tail -20
```

O log precisa mostrar `Tudo pronto para o lançamento.` Se aparecer `PENDENTE`, corrija o `.env` e rode `docker compose up -d`.

## 6. Criar o administrador

```sh
docker compose exec web python manage.py createsuperuser
```

## 7. Ativar os backups

```sh
chmod +x deploy/backup.sh
(crontab -l 2>/dev/null; echo "0 4 * * * /opt/roleflix/deploy/backup.sh") | crontab -
deploy/backup.sh && ls -lh backups
```

Essa cópia fica no mesmo servidor. Ative também os backups do painel da hospedagem.

## 8. Testar antes de convidar

- [ ] O site abre com cadeado em `https://SEU-DOMINIO`.
- [ ] Criar conta com o código de convite e receber o e-mail de confirmação.
- [ ] Recuperar a senha.
- [ ] Criar álbum, enviar foto e vídeo, e abrir em outra conta sem acesso (precisa ser negado).
- [ ] Gerar um trailer, um ingresso e uma capa.
- [ ] Instalar o app no celular.
- [ ] Restaurar um backup em uma pasta de teste.

## Atualizar o site

Gere e envie um novo pacote, depois rode:

```sh
cd /opt/roleflix
tar -xzf /root/roleflix-deploy.tar.gz
docker compose up -d --build
```

## Publicar sozinho a cada git push

Depois que o site estiver no ar, o GitHub pode atualizar o servidor sozinho. Fica assim:

1. No servidor, crie uma chave só para isso:

   ```sh
   ssh-keygen -t ed25519 -f /root/deploy_key -N ""
   cat /root/deploy_key.pub >> /root/.ssh/authorized_keys
   cat /root/deploy_key
   ```

2. No GitHub, abra **Settings → Secrets and variables → Actions**.
3. Em **Secrets**, crie `VPS_SSH_KEY` com o conteúdo de `deploy_key`, e `VPS_KNOWN_HOSTS` com a saída de `ssh-keyscan IP_DO_SERVIDOR`, rodado no seu computador.
4. Em **Variables**, crie `VPS_HOST` com o IP do servidor.
5. Apague a chave do servidor: `rm /root/deploy_key`.

A partir daí, cada `git push` publica o site. Acompanhe em **Actions**, no GitHub. Se o site passar para o VPS, desligue a Vercel para não ter dois sites no ar.

## Login com Google (opcional)

No Google Cloud Console, crie credenciais OAuth com o redirecionamento `https://SEU-DOMINIO/accounts/google/login/callback/`. Coloque os dados no `.env` e rode `docker compose up -d`. Com o código de convite ativo, o Google só entra em contas que já existem.
