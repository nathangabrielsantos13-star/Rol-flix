# Rolêflix — primeira versão

Aplicação web em Python/Django para criar álbuns de viagens e rolês, com fotos, vídeos, perfis, amizades e compartilhamento.

## Requisitos
- Python 3.10 ou superior
- pip

## Instalação (Windows PowerShell)
```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env   # e preencha DJANGO_SECRET_KEY
py manage.py migrate
py manage.py createsuperuser
py manage.py runserver
```
Abra http://127.0.0.1:8000

Para rodar os testes: `py manage.py test`

## Login Google
O projeto já inclui django-allauth e o botão "Continuar com Google". Para ativar:
1. Crie um OAuth Client ID no Google Cloud Console.
2. Configure a URL de redirecionamento autorizada: `http://127.0.0.1:8000/accounts/google/login/callback/`
3. Cole as credenciais no arquivo `.env`, na mesma pasta do `manage.py` (use `.env.example` como modelo), e reinicie o servidor:
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET`
4. Não cadastre o Google também em Social applications no `/admin/`: com as duas configurações, o login dá erro.
5. Em produção, configure domínio HTTPS, cookies seguros e credenciais OAuth de produção.

O botão "Continuar com Google" só aparece quando as credenciais estão configuradas.

## Instalar como app (PWA)
O site já traz manifesto, ícones, service worker e tela offline. No computador, o Chrome oferece a instalação em `http://127.0.0.1:8000`. No celular, a instalação exige que o site esteja publicado em HTTPS: pelo endereço local da rede, o navegador não permite.

O service worker guarda só CSS e JavaScript públicos. Páginas, fotos e vídeos nunca ficam no cache, porque são privados.

## Observações importantes
- Esta é uma base inicial/MVP, não uma aplicação pronta para publicar na internet.
- Para simplificar o primeiro teste, usa SQLite. Antes de produção, migre para PostgreSQL.
- Arquivos enviados ficam em `media/` localmente e passam pela view `protected_media`, que confere a permissão do álbum. Para produção, use armazenamento privado compatível com S3 ou serviço equivalente, com URLs assinadas.
- Uploads aceitam fotos JPG, PNG, WEBP e GIF de até 20 MB e vídeos MP4, WEBM, MOV e M4V de até 300 MB. Os limites ficam em `roleflix/forms.py`.
- A localização é um campo manual nesta primeira versão. Geolocalização do navegador deve ser adicionada com consentimento explícito.
- A seção de participantes permite selecionar amigos já aceitos. O dono do álbum mantém controle do compartilhamento.
- Configure proteção contra abuso, backups e permissões de armazenamento antes de disponibilizar para outras pessoas.
- A capa do álbum e as fotos/vídeos usam `ImageField`/`FileField`; vídeos não são guardados no banco, apenas o caminho do arquivo.

## Mapa e lugares
- As sugestões de cidades e países vêm do [Open-Meteo](https://open-meteo.com/) (dados GeoNames, CC BY 4.0), consultado pelo servidor. O plano gratuito é só para uso não comercial e permite menos de 10 mil chamadas por dia.
- O mapa usa [Leaflet](https://leafletjs.com/), incluído em `static/vendor/leaflet`, com mapas do [OpenStreetMap](https://www.openstreetmap.org/copyright). Esses mapas são para uso leve: se o site crescer, troque por um provedor com chave em `static/js/map.js`.
- Só álbuns com um lugar escolhido da lista aparecem no mapa, porque são eles que têm coordenadas.

## Créditos
- Pontos do globo: [Natural Earth](https://www.naturalearthdata.com/), domínio público.
- Foto do início: Arraial do Cabo (RJ), por Leticia Azevedo, no [Pexels](https://www.pexels.com/photo/scenic-view-of-a-beach-during-sunset-9318206/). Licença Pexels, recortada para o site.

## Trailers

Na página do álbum, o criador usa **Criar trailer** para escolher estilo, duração, música, fotos, vídeos e ordem. Quem tem acesso ao álbum assiste e baixa.

- O vídeo é montado por `roleflix/trailers.py` com FFmpeg, que vem no pacote `imageio-ffmpeg`.
- O site dispara `manage.py render_trailer <id>` em um processo separado, então não é preciso rodar um worker. Até 2 trailers são gerados ao mesmo tempo.
- Um processo interrompido é marcado como falha depois de 30 minutos.
- As faixas de `static/music/` são sintetizadas por `tools/gerar_musicas.py`, sem amostras de terceiros. Se mudar um andamento, ajuste também `MUSIC` em `roleflix/trailers.py`.
- A música enviada pelo usuário é apagada ao terminar e nunca é servida pelo site.
- `SAFE_INPUT` limita o que o FFmpeg lê nos arquivos enviados. Não remova: sem ele, um arquivo falso poderia fazer o FFmpeg ler arquivos do servidor.
- A geração lê os arquivos pelo caminho no disco. Para guardar a mídia em um serviço externo, será preciso baixá-los antes.
## Página inicial

`roleflix/homepage.py` monta o catálogo. Seções sem conteúdo não aparecem. As coleções são automáticas e não existem no banco: Verão (dezembro a março), Viagens (álbuns com local), Festas e encontros (palavras em `PARTY_WORDS` no título, sinopse ou descrição) e Melhores momentos (mais fotos, vídeos e pessoas). Uma coleção precisa de pelo menos 2 álbuns. As Recordações usam só a data do rolê.
Favoritos e coleções manuais são pessoais: não há contagem nem visualização por outras pessoas, e a página filtra pelo acesso atual a cada álbum.

## Editor de capas

`static/js/cover-editor.js` desenha o pôster no Canvas, e `roleflix/covers.py` valida e regrava o JPG. A foto limpa e as opções ficam em `CoverDesign`; o pôster fica em `Album.cover`, com `has_poster` ligado. Atrás de textos da página, use `album.backdrop`, para o título não aparecer duas vezes. As fontes de `static/fonts/` estão sob a SIL Open Font License.
## Ingressos

`roleflix/tickets.py` desenha o ingresso com Pillow, usando as fontes TTF de `static/fonts/ttf/`, e guarda a imagem pronta: mudar o álbum depois não altera os ingressos antigos. O PDF é gerado na hora do download. Quando a data do rolê é futura, o ingresso sai como pré-estreia. É uma lembrança: não tem QR nem código de barras, e não vale como entrada.