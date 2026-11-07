# Publicar o Rolêflix de graça

Este caminho usa só planos gratuitos: Oracle Cloud para o servidor, DuckDNS para o endereço, Brevo para os e-mails e Google para o login.

**A Oracle pede cartão** para confirmar sua identidade. Na conta gratuita, o aviso dela é de que nada é cobrado enquanto você usar só os recursos marcados como *Always Free*.

## 1. Criar o servidor na Oracle

1. Crie a conta em [oracle.com/cloud/free](https://www.oracle.com/cloud/free/).
2. Na escolha da **região principal**, selecione Brasil, de preferência São Paulo. **Essa escolha não pode ser mudada depois.**
3. Abra **Compute → Instances → Create instance** e escolha:
   - **Image:** Canonical Ubuntu 24.04 (a versão aarch64).
   - **Shape:** Ampere, `VM.Standard.A1.Flex`, com 2 OCPUs e 12 GB de memória.
   - **Boot volume:** 150 GB. O limite grátis é de 200 GB somando todos os discos.
   - **SSH keys:** baixe a chave privada e guarde em `C:\Users\Nathan\.ssh\roleflix.key`.
4. Se aparecer `Out of host capacity`, tente outro *availability domain* ou tente de novo mais tarde.
5. Em **Networking → Reserved public IPs**, reserve um IP e ligue ao servidor. Sem isso, ele pode mudar.
6. Na rede do servidor, abra a **Security List** e adicione regras de entrada TCP para as portas **80** e **443**, com origem `0.0.0.0/0`.

Anote o IP.

## 2. Criar o endereço

1. Entre em [duckdns.org](https://www.duckdns.org/) com sua conta do Google.
2. Crie um nome, por exemplo `roleflix`, que vira `roleflix.duckdns.org`.
3. Coloque o IP do servidor no campo **current ip** e clique em **update ip**.

## 3. Criar o e-mail

1. Crie a conta grátis no [Brevo](https://www.brevo.com/).
2. Em **Senders**, adicione e confirme seu e-mail.
3. Em **SMTP & API**, gere uma chave SMTP e anote servidor, porta, login e chave.

Sem domínio próprio, as mensagens podem cair no spam. Avise a turma para olhar essa pasta.

## 4. Preparar o servidor

No seu computador, na pasta `roleflix`:

```powershell
powershell -File deploy\empacotar.ps1
scp -i $HOME\.ssh\roleflix.key ..\roleflix-deploy.tar.gz deploy\preparar_servidor.sh ubuntu@IP_DO_SERVIDOR:/tmp/
ssh -i $HOME\.ssh\roleflix.key ubuntu@IP_DO_SERVIDOR
```

Já no servidor:

```sh
sh /tmp/preparar_servidor.sh
exit
```

Entre de novo com o mesmo `ssh` e preencha as configurações:

```sh
nano /opt/roleflix/.env
```

| Campo | O que colocar |
|---|---|
| `ROLEFLIX_DOMAIN` | `roleflix.duckdns.org` |
| `DJANGO_ALLOWED_HOSTS` | `roleflix.duckdns.org` |
| `ROLEFLIX_CONTACT_EMAIL` | Seu e-mail |
| `ROLEFLIX_INVITE_CODE` | Um código para dar aos amigos |
| `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | Dados SMTP do Brevo |
| `DEFAULT_FROM_EMAIL` | `Rolêflix <seu-email-confirmado@gmail.com>` |
| `DJANGO_SECRET_KEY` | Já vem preenchida |

Salve com `Ctrl+O` e `Enter`, e saia com `Ctrl+X`.

## 5. Ligar o site

```sh
cd /opt/roleflix
docker compose up -d --build
docker compose logs web | tail -20
```

A primeira vez demora alguns minutos. O log precisa mostrar `Tudo pronto para o lançamento.` Depois, abra o endereço no navegador. O cadeado de HTTPS pode levar um minuto para aparecer.

## 6. Ativar os backups

```sh
chmod +x deploy/backup.sh
(crontab -l 2>/dev/null; echo "0 4 * * * /opt/roleflix/deploy/backup.sh") | crontab -
deploy/backup.sh && ls -lh backups
```

Essa cópia fica no mesmo servidor. **Baixe uma de vez em quando para o seu computador.** Em serviço gratuito, não há ninguém para recuperar seus dados se a conta for perdida:

```powershell
scp -i $HOME\.ssh\roleflix.key "ubuntu@IP_DO_SERVIDOR:/opt/roleflix/backups/*.tar.gz" .
```

## 7. Ligar o login com Google

1. No [Google Cloud Console](https://console.cloud.google.com/apis/credentials), crie um projeto e configure a tela de consentimento.
2. Crie **ID do cliente OAuth → Aplicativo da Web**.
3. Em **URIs de redirecionamento**, coloque `https://roleflix.duckdns.org/accounts/google/login/callback/`.
4. Publique a tela de consentimento, para funcionar com qualquer conta.
5. Coloque `GOOGLE_CLIENT_ID` e `GOOGLE_CLIENT_SECRET` no `.env` e rode `docker compose up -d`.

## 8. Publicar sozinho a cada git push

1. No servidor:

   ```sh
   ssh-keygen -t ed25519 -f ~/deploy_key -N ""
   cat ~/deploy_key.pub >> ~/.ssh/authorized_keys
   cat ~/deploy_key
   ```

2. No seu computador, rode `ssh-keyscan IP_DO_SERVIDOR` e copie a saída.
3. No GitHub, abra **Settings → Secrets and variables → Actions**.
4. Em **Secrets**, crie `VPS_SSH_KEY` com o conteúdo de `deploy_key` e `VPS_KNOWN_HOSTS` com a saída do `ssh-keyscan`.
5. Em **Variables**, crie `VPS_HOST` com o IP e `VPS_USER` com `ubuntu`.
6. No servidor, apague a cópia: `rm ~/deploy_key`.

## 9. Testar antes de convidar

- [ ] O site abre com cadeado.
- [ ] Criar conta com o código e receber o e-mail de confirmação.
- [ ] Recuperar a senha.
- [ ] Entrar com o Google.
- [ ] Enviar foto e vídeo, e abrir o álbum em outra conta sem acesso (precisa ser negado).
- [ ] Gerar trailer, ingresso e capa.

## Riscos do plano grátis

- **Servidor parado:** a Oracle pode recuperar instâncias gratuitas ociosas. Pelas regras dela, isso vale quando CPU, rede e memória ficam abaixo de 20% durante 7 dias, o que pode acontecer em um site pequeno. Não invente carga artificial para escapar da regra.
- **Conta parada:** relatos indicam que contas sem uso por muito tempo podem ser encerradas. Entre no painel de vez em quando.
- **Limites:** ultrapassar 2 OCPUs, 12 GB ou 200 GB deixa de ser grátis. A oferta já foi reduzida em 2026 e pode mudar de novo.
- **Sem suporte:** por isso os backups no seu computador são obrigatórios.
