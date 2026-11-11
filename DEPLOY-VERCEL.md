# Rolêflix na Vercel com dados permanentes

O site precisa do banco (Neon) e dos arquivos (Blob) ligados para guardar contas, álbuns e fotos.

## Ligar

No projeto da Vercel, abra **Storage**:

1. **Create Database**, escolha **Neon** e o plano **Free**. Conecte ao projeto. Isso cria `DATABASE_URL`.
2. **Create Storage**, escolha **Blob** e o acesso **Private**. Conecte ao projeto. Isso cria `BLOB_READ_WRITE_TOKEN`.

Em **Settings > Environment Variables**, adicione `ROLEFLIX_INVITE_CODE` com um código escolhido por você.
Sem ele, qualquer pessoa pode criar conta e gastar o espaço grátis.

Em **Deployments**, abra a publicação mais recente e use **Redeploy**. Variáveis novas só valem depois disso.

## Limites do plano grátis

- **Neon:** 1 GB de banco.
- **Blob:** 1 GB de arquivos, 10 GB de transferência e 2.000 envios por mês. Passou do limite, a loja fica bloqueada por até 30 dias.
- O site recusa envios ao chegar a 900 MB de fotos e vídeos.
- **Cada arquivo:** até 4 MB. As fotos são reduzidas no navegador. Vídeos maiores são recusados.
- **Baixar o álbum inteiro:** só até 4 MB no total. Acima disso, baixe uma foto por vez.
- **Trailers:** desligados, porque precisam de um processo longo.

## E-mail

Sem `EMAIL_HOST`, o cadastro entra sem confirmar o e-mail, e a recuperação de senha fica desligada.
Com o Brevo ligado, a confirmação passa a ser exigida. Variáveis: `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`,
`EMAIL_HOST_PASSWORD` e `DEFAULT_FROM_EMAIL`.
