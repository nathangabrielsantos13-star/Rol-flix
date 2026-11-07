import io
import json
import re
import shutil
import smtplib
import tempfile
import zipfile
from datetime import date, datetime, timedelta
from unittest.mock import patch
from urllib.error import URLError
from urllib.parse import urlparse

from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.contrib.staticfiles import finders
from django.core import mail
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from PIL import Image

from . import accounts, covers, demo, homepage, tickets, trailers
from .middleware import DemoSetupMiddleware
from .models import Album, AlbumParticipant, Collection, CoverDesign, Favorite, FriendRequest, MediaItem, Notification, Profile, Ticket, Trailer

TMP = tempfile.mkdtemp()
SENHA = "SenhaForte!123"
GOOGLE = {"google": {"APP": {"client_id": "x", "secret": "y", "key": ""}}}


def png(name="foto.png"):
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


@override_settings(MEDIA_ROOT=TMP, PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"], ACCOUNT_EMAIL_VERIFICATION="optional")
class Base(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TMP, ignore_errors=True)

    def setUp(self):
        self.a = User.objects.create_user("ana", "ana@x.com", SENHA)
        self.b = User.objects.create_user("bia", "bia@x.com", SENHA)
        self.c = User.objects.create_user("caio", "caio@x.com", SENHA)

    def befriend(self, u, v):
        FriendRequest.objects.create(sender=u, receiver=v, status=FriendRequest.ACCEPTED)

    def album(self, vis=Album.PRIVATE, title="Guaratuba 2026", owner=None):
        return Album.objects.create(owner=owner or self.a, title=title, visibility=vis)

    def shared_album(self, title="Rolê Secreto", vis=Album.SHARED):
        album = self.album(vis, title)
        AlbumParticipant.objects.create(album=album, user=self.b)
        return album


class ContaTests(Base):
    def test_paginas_publicas(self):
        for url in ["/", "/cadastro/", "/accounts/login/"]:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_paginas_protegidas_exigem_login(self):
        for url in ["/album/novo/", "/amigos/", "/perfil/ana/"]:
            r = self.client.get(url)
            self.assertEqual(r.status_code, 302, url)
            self.assertIn("/accounts/login/", r["Location"])

    def test_cadastro_entra_na_conta(self):
        r = self.client.post("/cadastro/", {"first_name": "Nathan Gabriel", "email": "Novo@X.com", "password1": SENHA, "password2": SENHA})
        self.assertRedirects(r, "/")
        user = self.client.get("/").context["user"]
        self.assertEqual((user.first_name, user.email), ("Nathan Gabriel", "novo@x.com"))
        self.assertNotIn(" ", user.username)

    def test_nomes_iguais_geram_usuarios_diferentes(self):
        for email in ("n1@x.com", "n2@x.com"):
            self.client.post("/cadastro/", {"first_name": "Nathan", "email": email, "password1": SENHA, "password2": SENHA})
            self.client.logout()
        self.assertEqual(User.objects.filter(first_name="Nathan").values("username").distinct().count(), 2)

    def test_cadastro_exige_nome_e_email(self):
        self.client.post("/cadastro/", {"first_name": "Novo", "password1": SENHA, "password2": SENHA})
        self.client.post("/cadastro/", {"email": "n@x.com", "password1": SENHA, "password2": SENHA})
        self.assertEqual(User.objects.count(), 3)

    def test_cadastro_recusa_email_repetido(self):
        self.client.post("/cadastro/", {"first_name": "Novo", "email": "ANA@x.com", "password1": SENHA, "password2": SENHA})
        self.assertEqual(User.objects.count(), 3)

    def test_recusa_explica_que_a_conta_nao_foi_criada(self):
        r = self.client.post("/cadastro/", {"first_name": "Novo", "email": "n@x.com", "password1": "abc", "password2": "abc"})
        self.assertContains(r, "Sua conta ainda não foi criada")
        self.assertContains(r, "errorlist")

    def test_conta_do_cadastro_entra_por_email_e_recupera_senha(self):
        self.client.post("/cadastro/", {"first_name": "Novo", "email": "novo@x.com", "password1": SENHA, "password2": SENHA})
        self.client.logout()
        r = self.client.post("/accounts/login/", {"login": "ninguem@x.com", "password": SENHA})
        self.assertContains(r, "errorlist")
        self.assertEqual(self.client.post("/accounts/login/", {"login": "novo@x.com", "password": SENHA}).status_code, 302)
        self.assertTrue(self.client.get("/").context["user"].is_authenticated)
        self.client.logout()
        mail.outbox.clear()
        self.client.post("/accounts/password/reset/", {"email": "novo@x.com"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["novo@x.com"])

    def test_login_com_senha(self):
        r = self.client.post("/accounts/login/", {"login": "ana@x.com", "password": SENHA})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(self.client.get("/").context["user"].is_authenticated)

    def test_cadastro_do_allauth_envia_email(self):
        r = self.client.post("/accounts/signup/", {"first_name": "Novo", "email": "n@x.com", "password1": SENHA, "password2": SENHA})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(SOCIALACCOUNT_PROVIDERS={})
    def test_sem_credenciais_nao_mostra_botao_google(self):
        self.assertNotContains(self.client.get("/accounts/login/"), "Continuar com Google")

    @override_settings(SOCIALACCOUNT_PROVIDERS={"google": {"APP": {"client_id": "x", "secret": "y", "key": ""}}})
    def test_com_credenciais_mostra_botao_google(self):
        self.assertContains(self.client.get("/accounts/login/"), "Continuar com Google")

    def test_sair(self):
        self.client.force_login(self.a)
        self.assertEqual(self.client.post("/accounts/logout/").status_code, 302)
        self.assertFalse(self.client.get("/").context["user"].is_authenticated)

    def test_botao_google_mantem_o_destino_da_pessoa(self):
        with override_settings(SOCIALACCOUNT_PROVIDERS=GOOGLE):
            r = self.client.get("/accounts/login/?next=/album/5/")
        self.assertRegex(r.content.decode(), r'method="post" action="/accounts/google/login/\?[^"]*next=%2Falbum%2F5%2F')

    def test_google_so_inicia_por_post(self):
        with override_settings(SOCIALACCOUNT_PROVIDERS=GOOGLE):
            self.assertEqual(self.client.get("/accounts/google/login/").status_code, 200)
            r = self.client.post("/accounts/google/login/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("accounts.google.com", r["Location"])


@override_settings(ACCOUNT_EMAIL_VERIFICATION="mandatory")
class ConfirmarEmailTests(Base):
    def cadastrar(self):
        return self.client.post("/cadastro/", {"first_name": "Novo", "email": "novo@x.com", "password1": SENHA, "password2": SENHA})

    def test_conta_so_entra_depois_de_confirmar(self):
        self.cadastrar()
        self.assertFalse(self.client.get("/").context["user"].is_authenticated)
        self.client.post("/accounts/login/", {"login": "novo@x.com", "password": SENHA})
        self.assertFalse(self.client.get("/").context["user"].is_authenticated)

        link = re.search(r"https?://\S+/accounts/confirm-email/\S+", mail.outbox[-1].body).group()
        self.client.post(urlparse(link).path)
        self.client.logout()
        self.client.post("/accounts/login/", {"login": "novo@x.com", "password": SENHA})
        self.assertTrue(self.client.get("/").context["user"].is_authenticated)

    def test_email_de_outra_pessoa_nao_cria_conta_nem_entrega_acesso(self):
        self.cadastrar()
        total = User.objects.count()
        self.client.post("/cadastro/", {"first_name": "Golpe", "email": "novo@x.com", "password1": SENHA, "password2": SENHA})
        self.assertEqual(User.objects.count(), total)
        self.assertFalse(self.client.get("/").context["user"].is_authenticated)


class AlbumTests(Base):
    def test_criar_album_com_capa(self):
        self.client.force_login(self.a)
        r = self.client.post("/album/novo/", {"title": "Guaratuba 2026", "synopsis": "s", "description": "d", "event_date": "2026-01-10",
                                              "location": "PR", "visibility": "private", "cover": png("capa.png")})
        album = Album.objects.get()
        self.assertRedirects(r, f"/album/{album.pk}/")
        self.assertContains(self.client.get("/"), "Guaratuba 2026")

    def test_upload_foto_e_video(self):
        self.client.force_login(self.a)
        album = self.album()
        self.client.post(f"/album/{album.pk}/upload/", {"caption": "x", "files": [png(), SimpleUploadedFile("v.mp4", b"00", "video/mp4")]})
        self.assertEqual(sorted(MediaItem.objects.values_list("kind", flat=True)), ["photo", "video"])
        r = self.client.get(f"/album/{album.pk}/")
        self.assertContains(r, "<video")
        self.assertContains(r, "<img")

    def test_upload_vazio_mostra_erro(self):
        album = self.album()
        self.client.force_login(self.a)
        r = self.client.post(f"/album/{album.pk}/upload/", {"caption": "x"})
        self.assertEqual([str(m) for m in get_messages(r.wsgi_request)], ["Selecione pelo menos um arquivo."])

    def test_upload_recusa_arquivos_que_nao_sao_midia(self):
        album = self.album()
        self.client.force_login(self.a)
        ruins = [("x.html", b"<script>alert(1)</script>", "text/html"), ("x.svg", b"<svg onload='alert(1)'/>", "image/svg+xml"),
                 ("falsa.png", b"<script>alert(1)</script>", "image/png")]
        for name, content, ctype in ruins:
            self.client.post(f"/album/{album.pk}/upload/", {"files": [SimpleUploadedFile(name, content, ctype)]})
        self.assertFalse(MediaItem.objects.exists())

    def test_um_arquivo_ruim_cancela_o_envio_todo(self):
        album = self.album()
        self.client.force_login(self.a)
        self.client.post(f"/album/{album.pk}/upload/", {"files": [png(), SimpleUploadedFile("x.html", b"x", "text/html")]})
        self.assertFalse(MediaItem.objects.exists())

    def test_upload_recusa_foto_grande_demais(self):
        album = self.album()
        self.client.force_login(self.a)
        with patch("roleflix.forms.MAX_PHOTO_SIZE", 1):
            self.client.post(f"/album/{album.pk}/upload/", {"files": [png()]})
        self.assertFalse(MediaItem.objects.exists())


class AmizadeTests(Base):
    def test_fluxo_completo(self):
        self.client.force_login(self.a)
        self.assertContains(self.client.get("/amigos/", {"username": "bi"}), "@bia")
        self.client.post(f"/amigos/adicionar/{self.b.id}/")
        fr = FriendRequest.objects.get()
        self.client.force_login(self.b)
        self.assertContains(self.client.get("/amigos/"), "@ana")
        self.client.post(f"/amigos/solicitacao/{fr.id}/accept/")
        self.assertContains(self.client.get("/amigos/"), "/perfil/ana/")

    def test_so_o_destinatario_aceita(self):
        fr = FriendRequest.objects.create(sender=self.a, receiver=self.b)
        self.client.force_login(self.c)
        self.assertEqual(self.client.post(f"/amigos/solicitacao/{fr.id}/accept/").status_code, 404)

    def test_pedido_recusado_pode_ser_reenviado(self):
        FriendRequest.objects.create(sender=self.a, receiver=self.b, status=FriendRequest.REJECTED)
        self.client.force_login(self.a)
        self.client.post(f"/amigos/adicionar/{self.b.id}/")
        self.assertEqual(FriendRequest.objects.get().status, FriendRequest.PENDING)

    def test_quem_recusou_pode_pedir_depois(self):
        FriendRequest.objects.create(sender=self.a, receiver=self.b, status=FriendRequest.REJECTED)
        self.client.force_login(self.b)
        self.client.post(f"/amigos/adicionar/{self.a.id}/")
        fr = FriendRequest.objects.get()
        self.assertEqual((fr.sender, fr.receiver, fr.status), (self.b, self.a, FriendRequest.PENDING))

    def test_pedido_cruzado_vira_amizade(self):
        FriendRequest.objects.create(sender=self.a, receiver=self.b)
        self.client.force_login(self.b)
        self.client.post(f"/amigos/adicionar/{self.a.id}/")
        self.assertEqual(FriendRequest.objects.get().status, FriendRequest.ACCEPTED)

    def test_decisao_tomada_nao_pode_ser_refeita(self):
        recusado = FriendRequest.objects.create(sender=self.a, receiver=self.b, status=FriendRequest.REJECTED)
        aceito = FriendRequest.objects.create(sender=self.c, receiver=self.b, status=FriendRequest.ACCEPTED)
        self.client.force_login(self.b)
        self.assertEqual(self.client.post(f"/amigos/solicitacao/{recusado.id}/accept/").status_code, 404)
        self.assertEqual(self.client.post(f"/amigos/solicitacao/{aceito.id}/reject/").status_code, 404)

    def test_pedido_enviado_aparece_como_pendente(self):
        FriendRequest.objects.create(sender=self.a, receiver=self.b)
        self.client.force_login(self.a)
        r = self.client.get("/amigos/")
        self.assertContains(r, "Pedidos enviados")
        self.assertContains(r, "Aguardando resposta")

    def test_pedido_repetido_nao_duplica(self):
        FriendRequest.objects.create(sender=self.a, receiver=self.b)
        self.client.force_login(self.a)
        self.client.post(f"/amigos/adicionar/{self.b.id}/")
        self.assertEqual(FriendRequest.objects.get().status, FriendRequest.PENDING)


class CompartilhamentoTests(Base):
    def test_album_aparece_para_o_amigo_sem_copia(self):
        self.befriend(self.a, self.b)
        album = self.album()
        self.client.force_login(self.a)
        self.client.post(f"/album/{album.pk}/compartilhar/", {"participants": [self.b.id]})
        self.assertEqual(Album.objects.count(), 1)
        self.client.force_login(self.b)
        self.assertContains(self.client.get("/"), "Guaratuba 2026")
        self.assertContains(self.client.get("/perfil/bia/"), "Guaratuba 2026")
        self.assertEqual(self.client.get(f"/album/{album.pk}/").status_code, 200)

    def test_nao_compartilha_com_quem_nao_e_amigo(self):
        album = self.album()
        self.client.force_login(self.a)
        self.client.post(f"/album/{album.pk}/compartilhar/", {"participants": [self.c.id]})
        self.assertFalse(AlbumParticipant.objects.exists())
        album.refresh_from_db()
        self.assertEqual(album.visibility, Album.PRIVATE)

    def test_identificador_invalido_nao_quebra(self):
        album = self.album()
        self.client.force_login(self.a)
        r = self.client.post(f"/album/{album.pk}/compartilhar/", {"participants": ["abc"]})
        self.assertEqual(r.status_code, 302)

    def test_so_o_dono_compartilha(self):
        album = self.album()
        self.client.force_login(self.b)
        self.assertEqual(self.client.post(f"/album/{album.pk}/compartilhar/", {}).status_code, 404)

    def test_compartilhar_sem_ninguem_nao_muda_o_album(self):
        album = self.album()
        self.client.force_login(self.a)
        self.client.post(f"/album/{album.pk}/compartilhar/", {})
        album.refresh_from_db()
        self.assertEqual(album.visibility, Album.PRIVATE)

    def test_compartilhar_mantem_album_de_grupo(self):
        self.befriend(self.a, self.b)
        album = self.album(Album.GROUP)
        self.client.force_login(self.a)
        self.client.post(f"/album/{album.pk}/compartilhar/", {"participants": [self.b.id]})
        album.refresh_from_db()
        self.assertEqual(album.visibility, Album.GROUP)


class PrivacidadeTests(Base):
    def test_estranho_nao_abre_nem_envia_em_album_privado(self):
        album = self.album()
        self.client.force_login(self.c)
        self.assertRedirects(self.client.get(f"/album/{album.pk}/"), "/")
        self.client.post(f"/album/{album.pk}/upload/", {"files": [png()]})
        self.assertFalse(MediaItem.objects.exists())

    def test_terceiro_nao_ve_album_no_perfil_de_quem_recebeu(self):
        self.shared_album()
        self.client.force_login(self.c)
        self.assertNotContains(self.client.get("/perfil/bia/"), "Rolê Secreto")

    def test_participante_ve_album_no_perfil_do_dono(self):
        self.shared_album()
        self.client.force_login(self.b)
        self.assertContains(self.client.get("/perfil/ana/"), "Rolê Secreto")

    def test_album_privado_nao_aparece_para_participante_antigo(self):
        album = self.shared_album()
        album.visibility = Album.PRIVATE
        album.save()
        self.client.force_login(self.b)
        self.assertNotContains(self.client.get("/"), "Rolê Secreto")
        self.client.post(f"/album/{album.pk}/upload/", {"files": [png()]})
        self.assertFalse(MediaItem.objects.exists())

    def test_anonimo_nao_ve_album_de_grupo_na_home(self):
        self.album(Album.GROUP, "Rolê do Grupo")
        self.assertNotContains(self.client.get("/"), "Rolê do Grupo")

    def test_estranho_nao_ve_album_de_grupo_no_perfil(self):
        self.album(Album.GROUP, "Rolê do Grupo")
        self.client.force_login(self.c)
        self.assertNotContains(self.client.get("/perfil/ana/"), "Rolê do Grupo")

    def test_perfil_alheio_nao_diz_compartilhados_comigo(self):
        self.client.force_login(self.a)
        self.assertContains(self.client.get("/perfil/bia/"), "Compartilhados com bia")
        self.assertContains(self.client.get("/perfil/ana/"), "Compartilhados comigo")


class ElencoTests(Base):
    def elenco(self, html):
        return html.split('class="cast"')[1].split("</section>")[0]

    def test_capa_mostra_criador_e_participantes(self):
        album = self.shared_album()
        self.client.force_login(self.a)
        trecho = self.elenco(self.client.get(f"/album/{album.pk}/").content.decode())
        self.assertIn("/perfil/ana/", trecho)
        self.assertIn("/perfil/bia/", trecho)
        self.assertNotIn("/perfil/caio/", trecho)

    def test_elenco_usa_nome_e_foto_do_perfil(self):
        self.b.first_name = "Beatriz"
        self.b.save()
        perfil = Profile.objects.create(user=self.b, avatar=png("bia.png"))
        album = self.shared_album()
        self.client.force_login(self.a)
        trecho = self.elenco(self.client.get(f"/album/{album.pk}/").content.decode())
        self.assertIn("Beatriz", trecho)
        self.assertIn(perfil.avatar.url, trecho)

    def test_card_mostra_o_elenco(self):
        self.shared_album()
        self.shared_album("Outro rolê")
        self.client.force_login(self.b)
        self.assertContains(self.client.get("/"), 'class="card-cast"')

    def test_lista_nao_faz_uma_consulta_por_album(self):
        self.client.force_login(self.a)
        self.shared_album("Um")
        with CaptureQueriesContext(connection) as com_um:
            self.client.get("/")
        self.shared_album("Dois")
        self.shared_album("Três")
        with self.assertNumQueries(len(com_um)):
            self.client.get("/")


class EditarPerfilTests(Base):
    def test_exige_login(self):
        self.assertEqual(self.client.get("/conta/perfil/").status_code, 302)

    def test_salva_nome_bio_e_foto(self):
        self.client.force_login(self.a)
        self.assertEqual(self.client.get("/conta/perfil/").status_code, 200)
        r = self.client.post("/conta/perfil/", {"name": "Ana Lima", "bio": "Praia", "avatar": png("eu.png")})
        self.assertRedirects(r, "/perfil/ana/")
        self.a.refresh_from_db()
        self.assertEqual(self.a.first_name, "Ana Lima")
        self.assertEqual(self.a.profile.bio, "Praia")
        self.assertTrue(self.client.get(self.a.profile.avatar.url).status_code == 200)
        self.assertContains(self.client.get("/perfil/ana/"), "Ana Lima")

    def test_formulario_vem_com_o_nome_atual(self):
        self.a.first_name = "Ana Lima"
        self.a.save()
        self.client.force_login(self.a)
        self.assertContains(self.client.get("/conta/perfil/"), 'value="Ana Lima"')

    def test_recusa_foto_invalida(self):
        self.client.force_login(self.a)
        self.client.post("/conta/perfil/", {"name": "X", "avatar": SimpleUploadedFile("x.svg", b"<svg onload='alert(1)'/>", "image/svg+xml")})
        self.a.refresh_from_db()
        self.assertEqual(self.a.first_name, "")
        self.assertFalse(Profile.objects.get(user=self.a).avatar)

    def test_botao_de_editar_so_no_proprio_perfil(self):
        self.client.force_login(self.a)
        self.assertContains(self.client.get("/perfil/ana/"), "Editar perfil")
        self.assertNotContains(self.client.get("/perfil/bia/"), "Editar perfil")


class PaginaInicialTests(Base):
    def test_sem_album_de_ninguem_convida_a_procurar_amigos(self):
        self.client.force_login(self.a)
        r = self.client.get("/")
        self.assertContains(r, "Procurar amigos")
        self.assertContains(r, "Todo rolê merece")

    def test_compartilhado_substitui_o_convite(self):
        self.shared_album()
        self.client.force_login(self.b)
        r = self.client.get("/")
        self.assertNotContains(r, "Procurar amigos")
        self.assertContains(r, "Rolê Secreto")

    def test_destaque_prefere_album_com_capa(self):
        com_capa = self.album(title="Com capa")
        com_capa.cover = png("c.png")
        com_capa.save()
        self.album(title="Mais novo sem capa")
        self.client.force_login(self.a)
        self.assertEqual(self.client.get("/").context["featured"], com_capa)

    def test_continuar_explorando_segue_a_ordem_de_acesso(self):
        um, dois = self.album(title="Um"), self.album(title="Dois")
        self.client.force_login(self.a)
        self.assertNotContains(self.client.get("/"), "Continuar explorando")
        self.client.get(f"/album/{um.pk}/")
        self.client.get(f"/album/{dois.pk}/")
        self.client.get(f"/album/{um.pk}/")
        self.assertEqual(list(self.client.get("/").context["continue_exploring"]), [um, dois])

    def test_continuar_explorando_e_individual(self):
        album = self.shared_album()
        self.client.force_login(self.a)
        self.client.get(f"/album/{album.pk}/")
        self.client.force_login(self.b)
        self.assertEqual(list(self.client.get("/").context["continue_exploring"]), [])

    def test_continuar_explorando_some_quando_perde_o_acesso(self):
        album = self.shared_album()
        self.client.force_login(self.b)
        self.client.get(f"/album/{album.pk}/")
        AlbumParticipant.objects.all().delete()
        self.assertEqual(list(self.client.get("/").context["continue_exploring"]), [])


class CriarComAmigosTests(Base):
    def criar(self, **extra):
        return self.client.post("/album/novo/", {"title": "Novo", "visibility": "private", **extra})

    def test_amigo_marcado_ganha_acesso_e_aviso(self):
        self.befriend(self.a, self.b)
        self.client.force_login(self.a)
        self.assertContains(self.client.get("/album/novo/"), "Amigos que podem ver este álbum")
        self.criar(people=[self.b.id])
        album = Album.objects.get()
        self.assertEqual(album.visibility, Album.SHARED)
        self.assertEqual(list(album.participants.all()), [self.b])
        self.assertEqual(Notification.objects.get().recipient, self.b)

    def test_sem_marcar_ninguem_continua_privado(self):
        self.befriend(self.a, self.b)
        self.client.force_login(self.a)
        self.criar()
        self.assertEqual(Album.objects.get().visibility, Album.PRIVATE)

    def test_nao_aceita_quem_nao_e_amigo(self):
        self.befriend(self.a, self.b)
        self.client.force_login(self.a)
        self.criar(people=[self.c.id])
        self.assertFalse(Album.objects.exists())

    def test_quem_nao_tem_amigos_ve_o_convite(self):
        self.client.force_login(self.a)
        r = self.client.get("/album/novo/")
        self.assertContains(r, "Procure seus amigos")
        self.assertNotContains(r, "Amigos que podem ver")


class BuscaTests(Base):
    def setUp(self):
        super().setUp()
        self.b.first_name = "Beatriz"
        self.b.save()
        self.albume = self.shared_album("Guaratuba 2026")
        self.client.force_login(self.a)

    def achados(self, termo):
        return list(self.client.get("/busca/", {"q": termo}).context["albums"])

    def test_por_titulo(self):
        self.assertEqual(self.achados("guaratuba"), [self.albume])

    def test_por_nome_e_usuario_do_participante(self):
        self.assertEqual(self.achados("beatriz"), [self.albume])
        self.assertEqual(self.achados("bia"), [self.albume])

    def test_por_criador(self):
        self.client.force_login(self.b)
        self.assertEqual(self.achados("ana"), [self.albume])

    def test_sem_resultado(self):
        self.assertContains(self.client.get("/busca/", {"q": "nada"}), "Nenhum álbum encontrado")

    def test_nao_encontra_album_sem_acesso(self):
        self.client.force_login(self.c)
        self.assertEqual(self.achados("guaratuba"), [])
        self.assertEqual(self.achados("beatriz"), [])

    def test_album_com_dois_participantes_nao_repete(self):
        AlbumParticipant.objects.create(album=self.albume, user=self.c)
        self.assertEqual(self.achados("a"), [self.albume])

    def test_exige_login(self):
        self.client.logout()
        self.assertEqual(self.client.get("/busca/", {"q": "x"}).status_code, 302)


class BaixarTests(Base):
    def setUp(self):
        super().setUp()
        self.privado = self.album(title="Rolê de Verão")
        self.foto = MediaItem.objects.create(album=self.privado, file=png(), kind=MediaItem.PHOTO, uploaded_by=self.a)
        self.video = MediaItem.objects.create(album=self.privado, file=SimpleUploadedFile("v.mp4", b"video"), kind=MediaItem.VIDEO, uploaded_by=self.a)

    def test_baixar_um_arquivo(self):
        self.client.force_login(self.a)
        r = self.client.get(f"/album/{self.privado.pk}/midia/{self.foto.pk}/baixar/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("attachment", r["Content-Disposition"])
        self.assertEqual(b"".join(r.streaming_content)[:4], b"\x89PNG")

    def test_baixar_o_album_inteiro(self):
        self.client.force_login(self.a)
        r = self.client.get(f"/album/{self.privado.pk}/baixar/")
        self.assertIn("role-de-verao.zip", r["Content-Disposition"])
        with zipfile.ZipFile(io.BytesIO(b"".join(r.streaming_content))) as z:
            self.assertEqual(len(z.namelist()), 2)
            self.assertEqual(z.read(self.video.file.name.split("/")[-1]), b"video")

    def test_estranho_nao_baixa(self):
        self.client.force_login(self.c)
        self.assertEqual(self.client.get(f"/album/{self.privado.pk}/midia/{self.foto.pk}/baixar/").status_code, 404)
        self.assertEqual(self.client.get(f"/album/{self.privado.pk}/baixar/").status_code, 404)

    def test_arquivo_de_outro_album_nao_passa_por_album_acessivel(self):
        meu = self.album(owner=self.c, title="Meu")
        self.client.force_login(self.c)
        self.assertEqual(self.client.get(f"/album/{meu.pk}/midia/{self.foto.pk}/baixar/").status_code, 404)

    def test_participante_baixa(self):
        AlbumParticipant.objects.create(album=self.privado, user=self.b)
        self.privado.visibility = Album.SHARED
        self.privado.save()
        self.client.force_login(self.b)
        self.assertEqual(self.client.get(f"/album/{self.privado.pk}/baixar/").status_code, 200)

    def test_album_vazio_mostra_aviso(self):
        vazio = self.album(title="Vazio")
        self.client.force_login(self.a)
        self.assertRedirects(self.client.get(f"/album/{vazio.pk}/baixar/"), f"/album/{vazio.pk}/")

    def test_exige_login(self):
        self.assertEqual(self.client.get(f"/album/{self.privado.pk}/baixar/").status_code, 302)


class PwaTests(Base):
    def test_manifest_e_valido_e_tem_icones(self):
        r = self.client.get("/manifest.webmanifest")
        self.assertEqual(r["Content-Type"], "application/manifest+json")
        dados = json.loads(r.content)
        self.assertEqual(dados["display"], "standalone")
        self.assertEqual({i["sizes"] for i in dados["icons"]}, {"192x192", "512x512"})
        for icone in dados["icons"]:
            self.assertTrue(finders.find(icone["src"].removeprefix("/static/")), icone["src"])

    def test_service_worker_fica_na_raiz(self):
        r = self.client.get("/sw.js")
        self.assertEqual(r.status_code, 200)
        self.assertIn("javascript", r["Content-Type"])
        self.assertNotIn("{%", r.content.decode())

    def test_paginas_apontam_para_o_manifest(self):
        self.assertContains(self.client.get("/"), 'rel="manifest"')

    def test_tutorial_de_instalacao_cobre_cada_aparelho(self):
        r = self.client.get("/")
        self.assertContains(r, 'id="install-guide"')
        for aparelho in ("android", "ios", "desktop"):
            self.assertContains(r, f'data-steps="{aparelho}"')
            self.assertContains(r, f'data-tab="{aparelho}"')
        self.assertContains(r, "data-install")


class VisualTests(Base):
    def test_foto_do_inicio_existe(self):
        self.assertTrue(finders.find("img/hero-landscape.jpg"))
        self.assertIn("hero-landscape.jpg", open(finders.find("css/style.css"), encoding="utf-8").read())


class EditarAlbumTests(Base):
    def test_dono_edita_dados_e_troca_a_capa(self):
        album = self.album()
        self.client.force_login(self.a)
        self.assertContains(self.client.get(f"/album/{album.pk}/"), f"/album/{album.pk}/editar/")
        r = self.client.post(f"/album/{album.pk}/editar/", {"title": "Novo título", "visibility": "private", "cover": png("nova.png")})
        self.assertRedirects(r, f"/album/{album.pk}/")
        album.refresh_from_db()
        self.assertEqual(album.title, "Novo título")
        self.assertTrue(album.cover.name.startswith("album_covers/nova"))

    def test_editar_sem_enviar_capa_mantem_a_atual(self):
        album = self.album()
        album.cover = png("capa.png")
        album.save()
        nome = album.cover.name
        self.client.force_login(self.a)
        self.client.post(f"/album/{album.pk}/editar/", {"title": "Outro", "visibility": "private"})
        album.refresh_from_db()
        self.assertEqual(album.cover.name, nome)

    def test_formulario_traz_a_data_no_formato_do_navegador(self):
        album = self.album()
        album.event_date = "2026-01-10"
        album.save()
        self.client.force_login(self.a)
        self.assertContains(self.client.get(f"/album/{album.pk}/editar/"), 'value="2026-01-10"')

    def test_recusa_capa_invalida(self):
        album = self.album()
        self.client.force_login(self.a)
        buf = io.BytesIO()
        Image.new("RGB", (8, 8)).save(buf, "BMP")
        self.client.post(f"/album/{album.pk}/editar/", {"title": "X", "visibility": "private", "cover": SimpleUploadedFile("c.bmp", buf.getvalue(), "image/bmp")})
        album.refresh_from_db()
        self.assertEqual(album.title, "Guaratuba 2026")

    def test_so_o_dono_edita(self):
        album = self.shared_album()
        self.client.force_login(self.b)
        self.assertEqual(self.client.get(f"/album/{album.pk}/editar/").status_code, 404)
        self.assertEqual(self.client.post(f"/album/{album.pk}/editar/", {"title": "Hack", "visibility": "private"}).status_code, 404)
        self.assertNotContains(self.client.get(f"/album/{album.pk}/"), f"/album/{album.pk}/editar/")


class RespostaFalsa(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


GUARATUBA = {"name": "Guaratuba", "admin1": "Paraná", "country": "Brasil", "feature_code": "PPL", "latitude": -25.88, "longitude": -48.57}
BRASIL = {"name": "Brasil", "country": "Brasil", "feature_code": "PCLI", "latitude": -10.0, "longitude": -55.0}


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class BuscaDeLugaresTests(Base):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.client.force_login(self.a)

    def buscar(self, termo, lugares=()):
        corpo = json.dumps({"results": list(lugares)}).encode()
        with patch("roleflix.places.urlopen", return_value=RespostaFalsa(corpo)) as chamada:
            r = self.client.get("/lugares/", {"q": termo})
        return r.json()["results"], chamada

    def test_mostra_cidade_com_estado_e_pais_e_pais_sozinho(self):
        achados, _ = self.buscar("gua", [GUARATUBA, BRASIL])
        self.assertEqual([a["label"] for a in achados], ["Guaratuba, Paraná, Brasil", "Brasil"])
        self.assertEqual((achados[0]["latitude"], achados[0]["longitude"]), (-25.88, -48.57))

    def test_nao_repete_nomes(self):
        cidade = {"name": "São Paulo", "admin1": "São Paulo", "country": "Brasil", "latitude": 1, "longitude": 2}
        self.assertEqual(self.buscar("sao", [cidade])[0][0]["label"], "São Paulo, Brasil")

    def test_consulta_vai_em_portugues_e_codificada(self):
        _, chamada = self.buscar("são paulo & cia", [])
        url = chamada.call_args[0][0].full_url
        self.assertIn("language=pt", url)
        self.assertIn("name=s%C3%A3o+paulo+%26+cia", url)

    def test_termo_curto_nao_consulta(self):
        achados, chamada = self.buscar(" a ")
        self.assertEqual(achados, [])
        chamada.assert_not_called()

    def test_segunda_busca_vem_do_cache(self):
        self.buscar("guaratuba", [GUARATUBA])
        achados, chamada = self.buscar("GUARATUBA", [])
        self.assertEqual(len(achados), 1)
        chamada.assert_not_called()

    def test_servico_fora_do_ar_nao_quebra_nem_fica_guardado(self):
        with patch("roleflix.places.urlopen", side_effect=URLError("fora")):
            self.assertEqual(self.client.get("/lugares/", {"q": "guara"}).json()["results"], [])
        self.assertEqual(len(self.buscar("guara", [GUARATUBA])[0]), 1)

    def test_resposta_invalida_nao_quebra(self):
        with patch("roleflix.places.urlopen", return_value=RespostaFalsa(b"<html>")):
            self.assertEqual(self.client.get("/lugares/", {"q": "guara"}).json()["results"], [])

    def test_exige_login(self):
        self.client.logout()
        self.assertEqual(self.client.get("/lugares/", {"q": "guara"}).status_code, 302)


class LocalDoAlbumTests(Base):
    def salvar(self, **dados):
        self.client.force_login(self.a)
        self.client.post("/album/novo/", {"title": "Novo", "visibility": "private", **dados})
        return Album.objects.filter(title="Novo").first()

    def test_formulario_liga_a_busca(self):
        self.client.force_login(self.a)
        r = self.client.get("/album/novo/")
        self.assertContains(r, 'data-place-search="/lugares/"')
        self.assertContains(r, "js/location.js")

    def test_guarda_as_coordenadas_escolhidas(self):
        album = self.salvar(location="Guaratuba, Paraná, Brasil", latitude="-25.88", longitude="-48.57")
        self.assertEqual((album.latitude, album.longitude), (-25.88, -48.57))

    def test_local_digitado_a_mao_salva_sem_coordenadas(self):
        album = self.salvar(location="Sítio do Tio Zé")
        self.assertEqual(album.location, "Sítio do Tio Zé")
        self.assertIsNone(album.latitude)

    def test_coordenada_sem_local_ou_incompleta_e_descartada(self):
        self.assertIsNone(self.salvar(latitude="1", longitude="2").latitude)
        Album.objects.all().delete()
        self.assertIsNone(self.salvar(location="X", latitude="1").latitude)

    def test_coordenada_impossivel_e_recusada(self):
        self.assertIsNone(self.salvar(location="X", latitude="200", longitude="0"))


class MapaTests(Base):
    def marcar(self, album, lat=-25.88, lon=-48.57, local="Guaratuba, Paraná, Brasil"):
        album.latitude, album.longitude, album.location = lat, lon, local
        album.save()
        return album

    def lugares(self):
        return self.client.get("/mapa/").context["places"]

    def test_exige_login(self):
        self.assertEqual(self.client.get("/mapa/").status_code, 302)

    def test_menu_leva_ao_mapa(self):
        self.client.force_login(self.a)
        self.assertContains(self.client.get("/"), 'href="/mapa/"')

    def test_carrega_o_globo_e_o_mapa(self):
        self.client.force_login(self.a)
        r = self.client.get("/mapa/")
        for parte in ('id="globe"', 'id="map"', "js/globe.js", "js/globe-dots.js", "js/map.js", "vendor/leaflet/leaflet.js"):
            self.assertContains(r, parte)

    def test_arquivos_do_mapa_existem(self):
        for arquivo in ("vendor/leaflet/leaflet.js", "vendor/leaflet/leaflet.css", "js/globe-dots.js", "js/globe.js", "js/map.js", "js/location.js"):
            self.assertTrue(finders.find(arquivo), arquivo)

    def test_rolês_no_mesmo_lugar_viram_um_pino(self):
        self.marcar(self.album(title="Um"))
        self.marcar(self.album(title="Dois"))
        self.marcar(self.album(title="Longe"), lat=48.85, lon=2.35, local="Paris, França")
        self.client.force_login(self.a)
        self.assertEqual(sorted(len(p["albums"]) for p in self.lugares()), [1, 2])

    def test_estranho_nao_ve_pino_de_album_alheio(self):
        self.marcar(self.album(title="Rolê Secreto"))
        self.client.force_login(self.c)
        r = self.client.get("/mapa/")
        self.assertEqual(r.context["places"], [])
        self.assertNotContains(r, "Rolê Secreto")

    def test_participante_ve_e_quem_perdeu_acesso_nao(self):
        album = self.marcar(self.shared_album())
        self.client.force_login(self.b)
        self.assertEqual(len(self.lugares()), 1)
        AlbumParticipant.objects.update(has_access=False)
        self.assertEqual(self.lugares(), [])

    def test_titulo_nao_vira_codigo_na_pagina(self):
        self.marcar(self.album(title="</script><script>alert(1)</script>"))
        self.client.force_login(self.a)
        self.assertNotContains(self.client.get("/mapa/"), "<script>alert(1)")

    def test_avisa_album_sem_lugar_e_mapa_vazio(self):
        self.client.force_login(self.a)
        self.assertContains(self.client.get("/mapa/"), "Crie um álbum")
        self.marcar(self.album(title="Com lugar"))
        self.album(title="Sem lugar")
        self.assertContains(self.client.get("/mapa/"), "1 álbum sem lugar no mapa")

    def test_album_com_lugar_leva_ao_mapa(self):
        album = self.marcar(self.album())
        self.client.force_login(self.a)
        self.assertContains(self.client.get(f"/album/{album.pk}/"), f"/mapa/?album={album.pk}")


class BarraSuperiorTests(Base):
    def test_navegacao_principal(self):
        self.client.force_login(self.a)
        r = self.client.get("/")
        nav = r.content.decode().split('class="main-nav"')[1].split("</nav>")[0]
        self.assertEqual(re.findall(r">([^<>]+)</a>", nav), ["Início", "Meus rolês", "Mapa", "Amigos"])

    def test_logo_leva_ao_inicio(self):
        self.assertContains(self.client.get("/mapa/", follow=True), '<a class="brand" href="/"')

    def test_marca_a_pagina_atual(self):
        self.client.force_login(self.a)
        self.assertContains(self.client.get("/mapa/"), '<a href="/mapa/" aria-current="page">Mapa</a>')
        self.assertContains(self.client.get("/meus-roles/"), '<a href="/meus-roles/" aria-current="page">Meus rolês</a>')

    def test_perfil_e_sair_ficam_no_menu_da_foto(self):
        self.client.force_login(self.a)
        html = self.client.get("/").content.decode()
        menu = html.split('class="profile-menu"')[1].split("</details>")[0]
        for item in ("Meu perfil", "Sair", "Instalar app"):
            self.assertIn(item, menu)
        self.assertEqual(html.count("Meu perfil"), 1)
        self.assertEqual(html.count("data-install-open"), 1)

    def test_menu_usa_a_foto_quando_existe(self):
        perfil = Profile.objects.create(user=self.a, avatar=png("eu.png"))
        self.client.force_login(self.a)
        menu = self.client.get("/").content.decode().split('class="profile-menu"')[1].split("</summary>")[0]
        self.assertIn(perfil.avatar.url, menu)

    def test_sino_so_com_indicador_e_sem_numero_na_tela(self):
        album = self.shared_album()
        Notification.objects.create(recipient=self.b, actor=self.a, album=album)
        self.client.force_login(self.b)
        r = self.client.get("/")
        self.assertContains(r, 'class="notif-dot"')
        self.assertContains(r, 'aria-label="Notificações: 1 nova"')

    def test_visitante_ve_entrar_criar_conta_e_instalar_no_rodape(self):
        html = self.client.get("/").content.decode()
        self.assertIn("Criar conta", html)
        self.assertNotIn('class="profile-menu"', html)
        self.assertNotIn('class="nav-search', html)
        self.assertIn("Instalar app", html.split("<footer>")[1])

    def test_busca_fica_aberta_com_o_termo(self):
        self.client.force_login(self.a)
        r = self.client.get("/busca/", {"q": "praia"})
        self.assertContains(r, 'class="nav-search open"')
        self.assertContains(r, 'value="praia"')


class MeusRolesTests(Base):
    def test_exige_login(self):
        self.assertEqual(self.client.get("/meus-roles/").status_code, 302)

    def test_separa_criados_e_compartilhados_sem_album_alheio(self):
        meu = self.album(title="Meu")
        recebido = self.album(Album.SHARED, "Recebido", owner=self.b)
        AlbumParticipant.objects.create(album=recebido, user=self.a)
        self.album(title="De Caio", owner=self.c)
        self.client.force_login(self.a)
        r = self.client.get("/meus-roles/")
        self.assertEqual(list(r.context["mine"]), [meu])
        self.assertEqual(list(r.context["shared"]), [recebido])
        self.assertNotContains(r, "De Caio")

    def test_sem_nada_convida_a_criar_e_procurar_amigos(self):
        self.client.force_login(self.a)
        r = self.client.get("/meus-roles/")
        self.assertContains(r, "Procurar amigos")
        self.assertContains(r, "Você ainda não criou nenhum rolê")


class RetrospectivaTests(Base):
    def rolê(self, titulo, dia="2026-03-10", vis=Album.PRIVATE, dono=None, local="", capa=False):
        album = self.album(vis, titulo, owner=dono)
        album.event_date, album.location = date.fromisoformat(dia), local
        if capa:
            album.cover = png(f"{titulo}.png")
        album.save()
        return album

    def midia(self, album, fotos=0, videos=0):
        for _ in range(fotos):
            MediaItem.objects.create(album=album, file=png(), kind=MediaItem.PHOTO, uploaded_by=self.a)
        for _ in range(videos):
            MediaItem.objects.create(album=album, file=SimpleUploadedFile("v.mp4", b"0"), kind=MediaItem.VIDEO, uploaded_by=self.a)

    def ver(self, ano=2026):
        return self.client.get(f"/retrospectiva/{ano}/")

    def test_exige_login(self):
        self.assertEqual(self.ver().status_code, 302)
        self.assertEqual(self.client.get("/retrospectiva/").status_code, 302)

    def test_soma_roles_lugares_fotos_e_videos_do_ano(self):
        um = self.rolê("Um", local="Guaratuba, Paraná, Brasil")
        dois = self.rolê("Dois", "2026-08-01", local="Guaratuba, Paraná, Brasil")
        self.rolê("Três", "2026-09-01", local="Lisboa, Portugal")
        self.rolê("Outro ano", "2025-12-31", local="Paris, França")
        self.midia(um, fotos=2, videos=1)
        self.midia(dois, fotos=1)
        self.client.force_login(self.a)
        retro = self.ver().context["retro"]
        self.assertEqual(retro["album_count"], 3)
        self.assertEqual(retro["places"], ["Guaratuba, Paraná, Brasil", "Lisboa, Portugal"])
        self.assertEqual((retro["photos"], retro["videos"]), (3, 1))
        self.assertEqual(retro["summary"], "3 rolês • 2 lugares • 4 memórias")

    def test_singular_no_resumo(self):
        self.midia(self.rolê("Um", local="X"), fotos=1)
        self.client.force_login(self.a)
        self.assertEqual(self.ver().context["retro"]["summary"], "1 rolê • 1 lugar • 1 memória")

    def test_sem_data_vale_o_ano_em_que_foi_criado(self):
        album = self.album(title="Sem data")
        album.created_at = timezone.make_aware(datetime(2024, 6, 1, 12))
        album.save()
        self.client.force_login(self.a)
        self.assertEqual(self.ver(2024).context["retro"]["album_count"], 1)

    def test_conta_album_compartilhado_comigo_mas_nao_o_de_estranhos(self):
        meu = self.rolê("De Bia", vis=Album.SHARED, dono=self.b)
        AlbumParticipant.objects.create(album=meu, user=self.a)
        self.rolê("De Caio", vis=Album.PRIVATE, dono=self.c, local="Segredo")
        self.client.force_login(self.a)
        r = self.ver()
        self.assertEqual(r.context["retro"]["album_count"], 1)
        self.assertNotContains(r, "De Caio")
        self.assertNotContains(r, "Segredo")

    def test_quem_perdeu_acesso_nao_conta_o_album(self):
        album = self.rolê("Cortado", vis=Album.SHARED)
        AlbumParticipant.objects.create(album=album, user=self.b, has_access=False)
        self.client.force_login(self.b)
        self.assertEqual(self.ver().context["retro"]["album_count"], 0)

    def test_ranking_de_pessoas_sem_incluir_eu_mesmo(self):
        for titulo in ("A", "B"):
            AlbumParticipant.objects.create(album=self.rolê(titulo), user=self.b)
        AlbumParticipant.objects.create(album=self.rolê("C"), user=self.c)
        self.client.force_login(self.a)
        pessoas = [(p["person"], p["count"]) for p in self.ver().context["retro"]["people"]]
        self.assertEqual(pessoas, [(self.b, 2), (self.c, 1)])

    def test_melhores_capas_sao_as_com_mais_memorias(self):
        pequeno = self.rolê("Pequeno", capa=True)
        grande = self.rolê("Grande", capa=True)
        self.midia(grande, fotos=3)
        self.rolê("Sem capa")
        self.midia(pequeno, fotos=1)
        self.client.force_login(self.a)
        self.assertEqual(self.ver().context["retro"]["covers"], [grande, pequeno])

    def test_montagem_reveza_albuns_tem_limite_e_ignora_video(self):
        cheio = self.rolê("Cheio", "2026-02-01")
        self.midia(cheio, fotos=30, videos=2)
        outro = self.rolê("Outro", "2026-07-01")
        self.midia(outro, fotos=2)
        self.client.force_login(self.a)
        momentos = self.ver().context["retro"]["moments"]
        self.assertEqual(len(momentos), 24)
        self.assertEqual(sum(m["title"] == "Outro" for m in momentos), 2)
        self.assertEqual(momentos[-1]["title"], "Outro")
        self.assertFalse(any(m["url"].endswith(".mp4") for m in momentos))

    def test_titulo_nao_vira_codigo_na_pagina(self):
        self.midia(self.rolê("</script><script>alert(1)</script>"), fotos=1)
        self.client.force_login(self.a)
        self.assertNotContains(self.ver(), "<script>alert(1)")

    def test_ano_vazio_convida_a_criar_e_nao_carrega_a_montagem(self):
        self.client.force_login(self.a)
        r = self.ver(2031)
        self.assertContains(r, "Nenhum rolê registrado em 2031")
        self.assertNotContains(r, "retrospective.js")

    def test_troca_de_ano(self):
        self.rolê("Um", "2025-01-10")
        self.rolê("Dois", "2026-01-10")
        self.client.force_login(self.a)
        self.assertContains(self.ver(), 'href="/retrospectiva/2025/"')

    @patch("django.utils.timezone.localdate", return_value=date(2026, 11, 7))
    def test_ano_corrente_antes_de_dezembro_e_parcial(self, _):
        self.rolê("Um")
        self.client.force_login(self.a)
        self.assertContains(self.ver(), "ATÉ AGORA")
        self.assertRedirects(self.client.get("/retrospectiva/"), "/retrospectiva/2026/")

    @patch("django.utils.timezone.localdate", return_value=date(2027, 1, 15))
    def test_em_janeiro_o_destaque_e_o_ano_anterior(self, _):
        self.rolê("Um")
        self.client.force_login(self.a)
        r = self.client.get("/")
        self.assertContains(r, "JÁ ESTÁ PRONTA")
        self.assertContains(r, 'href="/retrospectiva/2026/"')
        self.assertNotContains(self.ver(), "ATÉ AGORA")

    @patch("django.utils.timezone.localdate", return_value=date(2026, 12, 2))
    def test_em_dezembro_fica_pronta(self, _):
        self.rolê("Um")
        self.client.force_login(self.a)
        self.assertContains(self.client.get("/"), "JÁ ESTÁ PRONTA")

    def test_sem_album_no_ano_nao_mostra_o_aviso_no_inicio(self):
        self.client.force_login(self.a)
        self.assertNotContains(self.client.get("/"), "retro-banner")

    def test_sem_nenhum_album_a_rota_geral_nao_quebra(self):
        self.client.force_login(self.a)
        self.assertEqual(self.client.get("/retrospectiva/", follow=True).status_code, 200)

    def test_perfil_proprio_leva_as_retrospectivas(self):
        self.client.force_login(self.a)
        self.assertContains(self.client.get("/perfil/ana/"), "Minhas retrospectivas")
        self.assertNotContains(self.client.get("/perfil/bia/"), "Minhas retrospectivas")


class CriadorDoAlbumTests(Base):
    def test_album_mostra_quem_criou_para_todos_que_abrem(self):
        self.a.first_name = "Ana Lima"
        self.a.save()
        album = self.shared_album()
        for pessoa in (self.a, self.b):
            self.client.force_login(pessoa)
            trecho = self.client.get(f"/album/{album.pk}/").content.decode().split('class="album-owner"')[1].split("</section>")[0]
            self.assertIn("Criado por", trecho)
            self.assertIn("Ana Lima", trecho)
            self.assertIn("/perfil/ana/", trecho)

    def test_so_o_criador_ve_editar_e_excluir(self):
        album = self.shared_album()
        self.client.force_login(self.a)
        r = self.client.get(f"/album/{album.pk}/")
        self.assertContains(r, f"/album/{album.pk}/editar/")
        self.assertContains(r, f"/album/{album.pk}/excluir/")
        self.client.force_login(self.b)
        r = self.client.get(f"/album/{album.pk}/")
        self.assertNotContains(r, f"/album/{album.pk}/editar/")
        self.assertNotContains(r, f"/album/{album.pk}/excluir/")


class ExcluirAlbumTests(Base):
    def setUp(self):
        super().setUp()
        self.alvo = self.shared_album()
        self.alvo.cover = png("capa.png")
        self.alvo.save()
        self.item = MediaItem.objects.create(album=self.alvo, file=png(), kind=MediaItem.PHOTO, uploaded_by=self.b)
        self.url = f"/album/{self.alvo.pk}/excluir/"

    def test_abrir_a_confirmacao_nao_apaga(self):
        self.client.force_login(self.a)
        r = self.client.get(self.url)
        self.assertContains(r, "não pode ser desfeito")
        self.assertContains(r, "Rolê Secreto")
        self.assertTrue(Album.objects.filter(pk=self.alvo.pk).exists())

    def test_criador_exclui_album_e_arquivos(self):
        capa, foto = self.alvo.cover, self.item.file
        Notification.objects.create(recipient=self.b, actor=self.a, album=self.alvo)
        self.client.force_login(self.a)
        self.assertTrue(capa.storage.exists(capa.name) and foto.storage.exists(foto.name))
        self.assertRedirects(self.client.post(self.url), "/")
        self.assertFalse(Album.objects.exists())
        self.assertFalse(MediaItem.objects.exists())
        self.assertFalse(Notification.objects.exists())
        self.assertFalse(capa.storage.exists(capa.name))
        self.assertFalse(foto.storage.exists(foto.name))

    def test_participante_e_estranho_nao_excluem(self):
        for pessoa in (self.b, self.c):
            self.client.force_login(pessoa)
            self.assertEqual(self.client.get(self.url).status_code, 404)
            self.assertEqual(self.client.post(self.url).status_code, 404)
        self.assertTrue(Album.objects.filter(pk=self.alvo.pk).exists())
        self.assertTrue(self.item.file.storage.exists(self.item.file.name))

    def test_exige_login(self):
        self.assertEqual(self.client.post(self.url).status_code, 302)
        self.assertTrue(Album.objects.filter(pk=self.alvo.pk).exists())

    def test_some_para_quem_participava(self):
        self.client.force_login(self.a)
        self.assertContains(self.client.post(self.url, follow=True), "Rolê Secreto")  # o aviso de excluído
        self.client.force_login(self.b)
        self.assertNotContains(self.client.get("/"), "Rolê Secreto")
        self.assertEqual(self.client.get(f"/album/{self.alvo.pk}/").status_code, 404)


class FotosDeCelularTests(Base):
    def mpo(self, name):
        buf = io.BytesIO()
        imagem = Image.new("RGB", (8, 8), "red")
        imagem.save(buf, "MPO", save_all=True, append_images=[imagem])
        return SimpleUploadedFile(name, buf.getvalue(), "image/jpeg")

    def test_aceita_jpg_com_varias_imagens(self):
        album = self.album()
        self.client.force_login(self.a)
        self.client.post(f"/album/{album.pk}/upload/", {"files": [self.mpo("foto.jpg")]})
        self.assertEqual(MediaItem.objects.count(), 1)

    def test_capa_e_foto_de_perfil_recusam_extensao_que_nao_e_de_imagem(self):
        album = self.album()
        self.client.force_login(self.a)
        self.client.post(f"/album/{album.pk}/editar/", {"title": "X", "visibility": "private", "cover": png("c.pdf")})
        self.client.post("/conta/perfil/", {"name": "X", "avatar": png("a.eps")})
        album.refresh_from_db()
        self.assertFalse(album.cover)
        self.assertFalse(Profile.objects.filter(user=self.a).exclude(avatar="").exclude(avatar__isnull=True).exists())


class TirarAcessoTests(Base):
    def setUp(self):
        super().setUp()
        self.befriend(self.a, self.b)
        self.befriend(self.a, self.c)
        self.alvo = self.shared_album()
        self.client.force_login(self.a)
        self.client.post(f"/album/{self.alvo.pk}/editar/", {"title": "Rolê Secreto", "visibility": "private"})

    def compartilhar(self, pessoa):
        self.client.force_login(self.a)
        self.client.post(f"/album/{self.alvo.pk}/compartilhar/", {"participants": [pessoa.id]})

    def test_compartilhar_com_outra_pessoa_nao_devolve_o_acesso(self):
        self.compartilhar(self.c)
        self.client.force_login(self.b)
        self.assertRedirects(self.client.get(f"/album/{self.alvo.pk}/"), "/")
        self.client.force_login(self.c)
        self.assertEqual(self.client.get(f"/album/{self.alvo.pk}/").status_code, 200)

    def test_continua_no_elenco_e_o_dono_ve_que_esta_sem_acesso(self):
        self.client.force_login(self.a)
        r = self.client.get(f"/album/{self.alvo.pk}/")
        self.assertContains(r, "sem acesso")
        self.assertIn("/perfil/bia/", r.content.decode().split('class="cast"')[1].split("</section>")[0])

    def test_pode_ser_compartilhado_de_novo_e_avisa(self):
        self.client.force_login(self.a)
        self.assertContains(self.client.get(f"/album/{self.alvo.pk}/"), f'name="participants" value="{self.b.id}"')
        self.compartilhar(self.b)
        self.assertEqual(AlbumParticipant.objects.get(user=self.b).has_access, True)
        self.assertEqual(Notification.objects.filter(recipient=self.b).count(), 1)
        self.client.force_login(self.b)
        self.assertEqual(self.client.get(f"/album/{self.alvo.pk}/").status_code, 200)

    def test_voltar_para_compartilhado_nao_devolve_sozinho(self):
        self.client.post(f"/album/{self.alvo.pk}/editar/", {"title": "Rolê Secreto", "visibility": "shared"})
        self.client.force_login(self.b)
        self.assertRedirects(self.client.get(f"/album/{self.alvo.pk}/"), "/")


class ParticipantesTests(Base):
    def test_dono_remove_e_a_pessoa_perde_o_acesso(self):
        album = self.shared_album()
        Notification.objects.create(recipient=self.b, actor=self.a, album=album)
        self.client.force_login(self.a)
        self.client.post(f"/album/{album.pk}/participantes/{self.b.id}/remover/")
        self.assertFalse(AlbumParticipant.objects.exists())
        self.assertFalse(Notification.objects.exists())
        self.client.force_login(self.b)
        self.assertRedirects(self.client.get(f"/album/{album.pk}/"), "/")
        self.assertNotContains(self.client.get("/"), "Rolê Secreto")

    def test_so_o_dono_remove(self):
        album = self.shared_album()
        AlbumParticipant.objects.create(album=album, user=self.c)
        self.client.force_login(self.b)
        self.assertEqual(self.client.post(f"/album/{album.pk}/participantes/{self.c.id}/remover/").status_code, 404)
        self.assertEqual(album.participants.count(), 2)

    def test_remover_exige_post(self):
        album = self.shared_album()
        self.client.force_login(self.a)
        self.assertEqual(self.client.get(f"/album/{album.pk}/participantes/{self.b.id}/remover/").status_code, 405)

    def test_botao_remover_so_para_o_dono(self):
        album = self.shared_album()
        self.client.force_login(self.a)
        self.assertContains(self.client.get(f"/album/{album.pk}/"), "Remover")
        self.client.force_login(self.b)
        self.assertNotContains(self.client.get(f"/album/{album.pk}/"), "Remover")

    def test_quem_ja_participa_sai_da_lista_de_compartilhar(self):
        self.befriend(self.a, self.b)
        album = self.shared_album()
        self.client.force_login(self.a)
        self.assertNotContains(self.client.get(f"/album/{album.pk}/"), f'name="participants" value="{self.b.id}"')


class NotificacoesTests(Base):
    def compartilhar(self, album):
        self.client.force_login(self.a)
        self.client.post(f"/album/{album.pk}/compartilhar/", {"participants": [self.b.id]})

    def test_compartilhar_avisa_e_mostra_contador(self):
        self.befriend(self.a, self.b)
        self.compartilhar(self.album())
        self.client.force_login(self.b)
        self.assertContains(self.client.get("/"), 'class="notif-dot"')
        self.assertContains(self.client.get("/notificacoes/"), "Guaratuba 2026")

    def test_abrir_a_pagina_zera_o_contador_e_mantem_o_historico(self):
        self.befriend(self.a, self.b)
        self.compartilhar(self.album())
        self.client.force_login(self.b)
        r = self.client.get("/notificacoes/")
        self.assertContains(r, "unread")
        self.assertNotContains(r, 'class="notif-dot"')
        r = self.client.get("/notificacoes/")
        self.assertContains(r, "Guaratuba 2026")
        self.assertNotContains(r, "notification unread")

    def test_compartilhar_de_novo_nao_repete_o_aviso(self):
        self.befriend(self.a, self.b)
        album = self.album()
        self.compartilhar(album)
        self.compartilhar(album)
        self.assertEqual(Notification.objects.count(), 1)

    def test_album_que_ficou_privado_some_das_notificacoes(self):
        album = self.shared_album()
        Notification.objects.create(recipient=self.b, actor=self.a, album=album)
        album.visibility = Album.PRIVATE
        album.title = "Título novo"
        album.save()
        self.client.force_login(self.b)
        self.assertNotContains(self.client.get("/"), 'class="notif-dot"')
        self.assertNotContains(self.client.get("/notificacoes/"), "Título novo")

    def test_cada_um_ve_so_as_suas(self):
        album = self.shared_album()
        Notification.objects.create(recipient=self.b, actor=self.a, album=album)
        self.client.force_login(self.c)
        self.assertNotContains(self.client.get("/notificacoes/"), "Rolê Secreto")

    def test_exige_login(self):
        self.assertEqual(self.client.get("/notificacoes/").status_code, 302)

    def test_aviso_oculto_nao_conta_como_lido(self):
        album = self.shared_album()
        aviso = Notification.objects.create(recipient=self.b, actor=self.a, album=album)
        album.visibility = Album.PRIVATE
        album.save()
        self.client.force_login(self.b)
        self.client.get("/notificacoes/")
        aviso.refresh_from_db()
        self.assertFalse(aviso.read)


class AberturaTests(Base):
    def test_todas_as_paginas_carregam_a_abertura(self):
        self.assertContains(self.client.get("/"), "js/intro.js")
        self.assertContains(self.client.get("/accounts/login/"), "js/intro.js")


class ArquivosProtegidosTests(Base):
    def setUp(self):
        super().setUp()
        self.privado = self.album()
        self.item = MediaItem.objects.create(album=self.privado, file=png(), kind=MediaItem.PHOTO, uploaded_by=self.a)
        self.url = f"/media/{self.item.file.name}"

    def test_anonimo_e_enviado_para_o_login(self):
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/accounts/login/", r["Location"])

    def test_estranho_recebe_404(self):
        self.client.force_login(self.c)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_dono_recebe_o_arquivo(self):
        self.client.force_login(self.a)
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "image/png")
        self.assertEqual(r["X-Content-Type-Options"], "nosniff")

    def test_participante_recebe_o_arquivo(self):
        album = self.shared_album()
        item = MediaItem.objects.create(album=album, file=png(), kind=MediaItem.PHOTO, uploaded_by=self.a)
        self.client.force_login(self.b)
        self.assertEqual(self.client.get(f"/media/{item.file.name}").status_code, 200)

    def test_capa_segue_a_permissao_do_album(self):
        self.privado.cover = png("capa.png")
        self.privado.save()
        url = f"/media/{self.privado.cover.name}"
        self.client.force_login(self.c)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.a)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_avatar_e_visivel_para_quem_esta_logado(self):
        perfil = Profile.objects.create(user=self.a, avatar=png("eu.png"))
        self.client.force_login(self.c)
        self.assertEqual(self.client.get(f"/media/{perfil.avatar.name}").status_code, 200)

    def test_webp_e_entregue_como_imagem(self):
        buf = io.BytesIO()
        Image.new("RGB", (8, 8)).save(buf, "WEBP")
        item = MediaItem.objects.create(album=self.privado, file=SimpleUploadedFile("w.webp", buf.getvalue()), kind=MediaItem.PHOTO, uploaded_by=self.a)
        self.client.force_login(self.a)
        self.assertEqual(self.client.get(f"/media/{item.file.name}")["Content-Type"], "image/webp")

    def video(self):
        item = MediaItem.objects.create(album=self.privado, file=SimpleUploadedFile("v.mp4", b"0123456789"), kind=MediaItem.VIDEO, uploaded_by=self.a)
        self.client.force_login(self.a)
        return f"/media/{item.file.name}"

    def trecho(self, url, faixa):
        return self.client.get(url, headers={"Range": faixa})

    def test_sem_range_anuncia_o_suporte(self):
        r = self.client.get(self.video())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Accept-Ranges"], "bytes")

    def test_entrega_o_trecho_pedido(self):
        r = self.trecho(self.video(), "bytes=2-5")
        self.assertEqual(r.status_code, 206)
        self.assertEqual(r["Content-Type"], "video/mp4")
        self.assertEqual(r["Content-Range"], "bytes 2-5/10")
        self.assertEqual(r["Content-Length"], "4")
        self.assertEqual(b"".join(r.streaming_content), b"2345")

    def test_formatos_abertos_de_range(self):
        url = self.video()
        self.assertEqual(b"".join(self.trecho(url, "bytes=7-").streaming_content), b"789")
        self.assertEqual(b"".join(self.trecho(url, "bytes=-3").streaming_content), b"789")
        self.assertEqual(self.trecho(url, "bytes=8-99")["Content-Range"], "bytes 8-9/10")

    def test_range_fora_do_arquivo_da_416(self):
        r = self.trecho(self.video(), "bytes=50-60")
        self.assertEqual(r.status_code, 416)
        self.assertEqual(r["Content-Range"], "bytes */10")

    def test_range_invalido_entrega_o_arquivo_inteiro(self):
        for faixa in ["bytes=-", "bytes=5-2", "bytes=0-1,3-4", "lixo"]:
            self.assertEqual(self.trecho(self.video(), faixa).status_code, 200, faixa)

    def test_range_nao_fura_a_permissao(self):
        url = self.video()
        self.client.force_login(self.c)
        self.assertEqual(self.trecho(url, "bytes=0-3").status_code, 404)

    def test_caminho_desconhecido_ou_fora_da_pasta_da_404(self):
        self.client.force_login(self.a)
        self.assertEqual(self.client.get("/media/nao-existe.png").status_code, 404)
        self.assertEqual(self.client.get("/media/../config/settings.py").status_code, 404)


class TrailerBase(Base):
    def setUp(self):
        super().setUp()
        self.dono = User.objects.create_user("dono_t", "dono_t@x.com", SENHA, first_name="Dona")
        self.outro = User.objects.create_user("outro_t", "outro_t@x.com", SENHA)
        self.album = Album.objects.create(owner=self.dono, title="Guaratuba 2026")
        self.foto = MediaItem.objects.create(album=self.album, kind="photo", uploaded_by=self.dono, file=SimpleUploadedFile("a.png", png_bytes(), content_type="image/png"))
        self.url = f"/album/{self.album.pk}/trailer/novo/"

    def dados(self, **extra):
        return {"style": "fun", "duration": "60", "music": "auto", "media": [self.foto.pk], **extra}

    def pronto(self, nome="album_trailers/t.mp4"):
        return Trailer.objects.create(album=self.album, created_by=self.dono, status=Trailer.READY, file=SimpleUploadedFile(nome.split("/")[-1], b"video"), media_ids=[self.foto.pk])


def png_bytes():
    buffer = io.BytesIO()
    Image.new("RGB", (800, 500), (200, 80, 40)).save(buffer, "PNG")
    return buffer.getvalue()


class TrailerPedidoTests(TrailerBase):
    @patch("roleflix.trailers.subprocess.Popen")
    def test_dono_pede_trailer_com_as_opcoes(self, popen):
        self.client.force_login(self.dono)
        r = self.client.post(self.url, self.dados(music="festa"))
        self.assertRedirects(r, f"/album/{self.album.pk}/")
        trailer = self.album.trailers.get()
        self.assertEqual((trailer.status, trailer.style, trailer.duration, trailer.music, trailer.media_ids), ("pending", "fun", 60, "festa", [self.foto.pk]))
        self.assertIn(str(trailer.pk), popen.call_args[0][0])

    def test_so_o_dono_cria_trailer(self):
        self.client.force_login(self.outro)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_album_sem_fotos_nao_abre_formulario(self):
        self.album.media.all().delete()
        self.client.force_login(self.dono)
        self.assertRedirects(self.client.get(self.url), f"/album/{self.album.pk}/")

    @patch("roleflix.trailers.subprocess.Popen")
    def test_ordem_escolhida_e_mantida_e_foto_de_outro_album_e_ignorada(self, popen):
        segunda = MediaItem.objects.create(album=self.album, kind="photo", uploaded_by=self.dono, file=SimpleUploadedFile("b.png", png_bytes()))
        alheio = Album.objects.create(owner=self.outro, title="Outro")
        intrusa = MediaItem.objects.create(album=alheio, kind="photo", uploaded_by=self.outro, file=SimpleUploadedFile("c.png", png_bytes()))
        self.client.force_login(self.dono)
        self.client.post(self.url, self.dados(media=[segunda.pk, intrusa.pk, self.foto.pk]))
        self.assertEqual(self.album.trailers.get().media_ids, [segunda.pk, self.foto.pk])

    @patch("roleflix.trailers.subprocess.Popen")
    def test_sem_nenhuma_foto_mostra_erro(self, popen):
        self.client.force_login(self.dono)
        r = self.client.post(self.url, self.dados(media=[]))
        self.assertContains(r, "Escolha pelo menos uma foto")
        popen.assert_not_called()

    @patch("roleflix.trailers.subprocess.Popen")
    def test_musica_enviada_precisa_ser_audio_e_existir(self, popen):
        self.client.force_login(self.dono)
        self.assertContains(self.client.post(self.url, self.dados(music="upload")), "Escolha o arquivo da música")
        ruim = SimpleUploadedFile("virus.exe", b"x")
        self.assertContains(self.client.post(self.url, self.dados(music="upload", music_file=ruim)), "Envie a música em MP3")
        popen.assert_not_called()

    @patch("roleflix.trailers.subprocess.Popen")
    def test_nao_gera_dois_ao_mesmo_tempo_no_album(self, popen):
        self.client.force_login(self.dono)
        self.client.post(self.url, self.dados())
        self.client.post(self.url, self.dados())
        self.assertEqual(self.album.trailers.count(), 1)
        self.assertEqual(popen.call_count, 1)

    @patch("roleflix.trailers.subprocess.Popen")
    def test_limite_de_trailers_no_site(self, popen):
        outro_album = Album.objects.create(owner=self.outro, title="Outro")
        for _ in range(trailers.MAX_ACTIVE):
            Trailer.objects.create(album=outro_album, created_by=self.outro, status=Trailer.PROCESSING)
        self.client.force_login(self.dono)
        self.client.post(self.url, self.dados())
        popen.assert_not_called()

    def test_geracao_morta_nao_trava_o_album(self):
        velho = Trailer.objects.create(album=self.album, created_by=self.dono, status=Trailer.PROCESSING, created_at=timezone.now() - trailers.STALE_AFTER * 2)
        self.client.force_login(self.dono)
        self.client.get(f"/album/{self.album.pk}/")
        velho.refresh_from_db()
        self.assertEqual(velho.status, Trailer.FAILED)

    @patch("roleflix.trailers.subprocess.Popen", side_effect=OSError)
    def test_falha_ao_iniciar_vira_mensagem(self, popen):
        self.client.force_login(self.dono)
        self.client.post(self.url, self.dados())
        self.assertEqual(self.album.trailers.get().status, Trailer.FAILED)


class TrailerAcessoTests(TrailerBase):
    def test_sem_acesso_nao_ve_nem_baixa(self):
        trailer = self.pronto()
        self.client.force_login(self.outro)
        self.assertEqual(self.client.get(trailer.file.url).status_code, 404)
        self.assertEqual(self.client.get(f"/album/{self.album.pk}/trailer/baixar/").status_code, 404)
        self.assertEqual(self.client.get(f"/album/{self.album.pk}/trailer/status/").status_code, 404)

    def test_visitante_nao_ve_o_trailer(self):
        trailer = self.pronto()
        self.assertEqual(self.client.get(trailer.file.url).status_code, 302)

    def test_participante_assiste_e_baixa_mas_nao_cria(self):
        trailer = self.pronto()
        self.album.visibility = Album.SHARED
        self.album.save()
        AlbumParticipant.objects.create(album=self.album, user=self.outro)
        self.client.force_login(self.outro)
        r = self.client.get(f"/album/{self.album.pk}/")
        self.assertContains(r, "Assistir trailer")
        self.assertNotContains(r, "Criar novo trailer")
        self.assertEqual(self.client.get(trailer.file.url).status_code, 200)
        baixar = self.client.get(f"/album/{self.album.pk}/trailer/baixar/")
        self.assertIn("guaratuba-2026-trailer.mp4", baixar["Content-Disposition"])

    def test_painel_para_o_dono(self):
        self.client.force_login(self.dono)
        self.assertContains(self.client.get(f"/album/{self.album.pk}/"), "Criar trailer")
        self.pronto()
        r = self.client.get(f"/album/{self.album.pk}/")
        self.assertContains(r, "TRAILER EXCLUSIVO")
        self.assertContains(r, "Criar novo trailer")

    def test_album_vazio_de_participante_nao_mostra_painel(self):
        self.album.media.all().delete()
        self.client.force_login(self.dono)
        self.assertNotContains(self.client.get(f"/album/{self.album.pk}/"), "TRAILER EXCLUSIVO")

    def test_erro_aparece_para_o_dono(self):
        Trailer.objects.create(album=self.album, created_by=self.dono, status=Trailer.FAILED, error="Deu ruim aqui")
        self.client.force_login(self.dono)
        self.assertContains(self.client.get(f"/album/{self.album.pk}/"), "Deu ruim aqui")

    def test_excluir_album_apaga_o_video_do_disco(self):
        trailer = self.pronto()
        caminho = trailer.file.path
        self.client.force_login(self.dono)
        self.client.post(f"/album/{self.album.pk}/excluir/")
        self.assertFalse(Trailer.objects.exists())
        with self.assertRaises(FileNotFoundError):
            open(caminho, "rb")


class TrailerMontagemTests(TrailerBase):
    def test_reduz_a_lista_mantendo_comeco_e_espalhando(self):
        escolhidos = trailers.evenly_pick(list(range(10)), 5)
        self.assertEqual(escolhidos, [0, 2, 4, 6, 8])
        self.assertEqual(trailers.evenly_pick([1, 2], 5), [1, 2])

    def test_cortes_caem_nas_batidas_e_respeitam_a_duracao(self):
        for estilo in trailers.STYLES.values():
            for alvo in (30, 60, 120):
                periodo = 0.5
                cortes = trailers.plan_cuts(int((alvo - trailers.INTRO - trailers.OUTRO - periodo) / estilo.shot), alvo, estilo, periodo)
                self.assertLessEqual(cortes[-1] + trailers.OUTRO, alvo)
                self.assertGreaterEqual(cortes[1], trailers.INTRO)
                self.assertTrue(all(abs(c / periodo - round(c / periodo)) < 1e-6 for c in cortes))

    def test_poucas_fotos_nao_esticam_alem_do_limite(self):
        estilo = trailers.STYLES[Trailer.CINEMATIC]
        cortes = trailers.plan_cuts(1, 120, estilo, 0.5)
        self.assertLessEqual(cortes[2] - cortes[1], trailers.MAX_SHOT)

    def test_descobre_a_batida_da_musica(self):
        janela = 0.032
        periodo = 0.5
        energia = [1000.0 if (i * janela) % periodo < janela else 10.0 for i in range(1800)]
        encontrado, _ = trailers.beat_grid(energia, janela)
        self.assertAlmostEqual(encontrado, periodo, delta=0.01)

    def test_audio_sem_ritmo_nao_quebra(self):
        self.assertEqual(trailers.beat_grid([0.0] * 500, 0.032), (0.5, 0.0))

    def test_titulo_enorme_cabe_na_abertura(self):
        self.album.title = "palavra " * 12
        destino = f"{TMP}/abertura.png"
        trailers.opening_card(self.album, destino)
        with Image.open(destino) as imagem:
            self.assertEqual(imagem.size, (trailers.WIDTH, trailers.HEIGHT))

    def test_arquivo_falso_nao_e_lido_como_video(self):
        falso = f"{TMP}/falso.mp4"
        with open(falso, "w", encoding="utf-8") as arquivo:
            arquivo.write("#EXTM3U\n#EXTINF:1.0,\nfile:///etc/passwd\n#EXT-X-ENDLIST\n")
        self.assertIsNone(trailers.video_duration(falso))

    def test_musicas_da_biblioteca_existem(self):
        for chave in trailers.MUSIC:
            self.assertIsNotNone(finders.find(f"music/{chave}.m4a"), chave)
        self.assertEqual(set(trailers.STYLE_MUSIC), set(trailers.STYLES))

    def _gerar(self):
        trailer = Trailer.objects.create(album=self.album, created_by=self.dono, status=Trailer.PROCESSING, duration=30, media_ids=[self.foto.pk])
        trailers.render(trailer)
        trailer.refresh_from_db()
        return trailer

    def test_gera_video_de_verdade_e_substitui_o_anterior(self):
        antigo = self.pronto()
        caminho_antigo = antigo.file.path
        trailer = self._gerar()
        self.assertEqual(trailer.status, Trailer.READY, trailer.error)
        self.assertGreater(trailer.length, trailers.INTRO + trailers.OUTRO)
        self.assertEqual(trailer.progress, 100)
        self.assertEqual(list(self.album.trailers.all()), [trailer])
        self.assertAlmostEqual(trailers.video_duration(trailer.file.path), trailer.length, delta=0.5)
        with self.assertRaises(FileNotFoundError):
            open(caminho_antigo, "rb")

    def test_foto_quebrada_e_ignorada_com_aviso_quando_nao_sobra_nada(self):
        with open(self.foto.file.path, "wb") as arquivo:
            arquivo.write(b"nao e imagem")
        trailer = self._gerar()
        self.assertEqual(trailer.status, Trailer.FAILED)
        self.assertIn("pôde ser aberto", trailer.error)

    def test_erro_no_ffmpeg_vira_falha_e_apaga_a_musica_enviada(self):
        musica = SimpleUploadedFile("m.mp3", b"nao e audio")
        trailer = Trailer.objects.create(album=self.album, created_by=self.dono, status=Trailer.PROCESSING, media_ids=[self.foto.pk], music_file=musica)
        caminho = trailer.music_file.path
        trailers.render(trailer)
        trailer.refresh_from_db()
        self.assertEqual(trailer.status, Trailer.FAILED)
        self.assertIn("música", trailer.error)
        with self.assertRaises(FileNotFoundError):
            open(caminho, "rb")

    def test_album_excluido_durante_a_geracao_nao_deixa_video_para_tras(self):
        trailer = Trailer.objects.create(album=self.album, created_by=self.dono, status=Trailer.PROCESSING, media_ids=[self.foto.pk])
        def apaga_e_devolve(alvo, pasta):
            saida = pasta / "t.mp4"
            saida.write_bytes(b"video")
            Trailer.objects.filter(pk=alvo.pk).delete()
            return saida, 10.0
        with patch("roleflix.trailers.build", apaga_e_devolve):
            trailers.render(trailer)
        with self.assertRaises(FileNotFoundError):
            open(trailer.file.path, "rb")

    def test_comando_nao_gera_duas_vezes(self):
        from django.core.management import call_command
        trailer = Trailer.objects.create(album=self.album, created_by=self.dono, status=Trailer.PROCESSING)
        with patch("roleflix.trailers.render") as render:
            call_command("render_trailer", trailer.pk)
        render.assert_not_called()


class InicioCatalogoTests(Base):
    def album_em(self, data, **campos):
        return Album.objects.create(owner=self.a, event_date=data, **campos)

    def contexto(self, usuario=None):
        self.client.force_login(usuario or self.a)
        return self.client.get("/").context

    def test_destaque_nao_repete_nas_fileiras_e_mostra_acoes(self):
        destaque = self.album(title="Destaque")
        destaque.cover = png("d.png")
        destaque.save()
        outro = self.album(title="Outro")
        self.client.force_login(self.a)
        r = self.client.get("/")
        self.assertEqual(r.context["featured"], destaque)
        self.assertEqual(r.context["mine"], [outro])
        self.assertContains(r, "Rever este rolê")
        self.assertNotContains(r, "Assistir trailer")

    def test_trailer_pronto_aparece_no_destaque(self):
        album = self.album(title="Com trailer")
        Trailer.objects.create(album=album, created_by=self.a, status=Trailer.READY, file=SimpleUploadedFile("t.mp4", b"v"))
        self.client.force_login(self.a)
        r = self.client.get("/")
        self.assertContains(r, "Assistir trailer")
        self.assertContains(r, 'id="trailer-player"')

    def test_ultimos_nao_repete_o_que_ja_apareceu(self):
        for numero in range(16):
            self.album(title=f"Rolê {numero}")
        contexto = self.contexto()
        vistos = {a.pk for a in contexto["mine"]}
        self.assertEqual(len(contexto["mine"]), homepage.ROW_SIZE)
        self.assertTrue(contexto["more_mine"])
        self.assertTrue(contexto["latest"])
        self.assertFalse(vistos & {a.pk for a in contexto["latest"]})

    def test_compartilhado_mostra_quem_criou(self):
        self.shared_album()
        extra = self.album(Album.SHARED, "Segundo")
        AlbumParticipant.objects.create(album=extra, user=self.b)
        self.client.force_login(self.b)
        self.assertContains(self.client.get("/"), "Compartilhado por")

    def test_poucos_albuns_mostram_proximos_passos(self):
        self.album()
        self.assertTrue(self.contexto()["few_albums"])
        self.assertContains(self.client.get("/"), "Sua próxima história")
        for numero in range(4):
            self.album(title=f"Rolê {numero}")
        self.assertNotContains(self.client.get("/"), "Sua próxima história")

    def test_verao_atravessa_a_virada_do_ano(self):
        self.assertEqual(homepage.summer_year(date(2025, 12, 28)), 2026)
        self.assertEqual(homepage.summer_year(date(2026, 2, 1)), 2026)
        self.assertIsNone(homepage.summer_year(date(2026, 7, 1)))

    def test_colecoes_automaticas(self):
        self.album_em(date(2026, 1, 10), title="Praia", location="Guaratuba")
        self.album_em(date(2026, 2, 10), title="Serra", location="Morretes")
        self.album_em(date(2026, 6, 1), title="Festa da Bia")
        self.album_em(date(2026, 7, 1), title="Aniversário do Léo")
        colecoes = {c["slug"]: [a.title for a in c["albums"]] for c in self.contexto()["collections"]}
        self.assertCountEqual(colecoes["verao-2026"], ["Praia", "Serra"])
        self.assertCountEqual(colecoes["viagens"], ["Praia", "Serra"])
        self.assertCountEqual(colecoes["festas-e-encontros"], ["Festa da Bia", "Aniversário do Léo"])

    def test_colecao_de_um_album_nao_aparece(self):
        self.album_em(date(2026, 1, 10), title="Sozinho", location="Guaratuba")
        self.assertEqual(self.contexto()["collections"], [])

    def test_palavra_parecida_nao_vira_festa(self):
        self.assertFalse(homepage.is_party(Album(title="Festival de barcos em Barra Velha")))

    def test_pagina_da_colecao_so_mostra_o_que_a_pessoa_pode_ver(self):
        self.album_em(date(2026, 1, 10), title="Meu 1", location="A")
        self.album_em(date(2026, 1, 11), title="Meu 2", location="B")
        self.client.force_login(self.a)
        self.assertContains(self.client.get("/colecoes/verao-2026/"), "Meu 1")
        self.client.force_login(self.b)
        self.assertEqual(self.client.get("/colecoes/verao-2026/").status_code, 404)

    def test_recordacao_de_aniversario_vem_primeiro(self):
        hoje = date(2026, 11, 7)
        antigo = self.album_em(date(2024, 3, 2), title="Antigo")
        marco = self.album_em(date(2025, 11, 10), title="Faz um ano")
        recente = self.album_em(date(2026, 10, 1), title="Recente")
        itens = homepage.build_memories(list(Album.objects.all()), hoje)
        self.assertEqual([i["album"] for i in itens], [marco, antigo])
        self.assertEqual(itens[0]["phrase"], "Há um ano você estava aqui")
        self.assertEqual(itens[1]["phrase"], "Em março de 2024")
        self.assertNotIn(recente, [i["album"] for i in itens])

    def test_recordacao_diz_voces_com_mais_gente_e_ignora_29_de_fevereiro(self):
        album = self.shared_album()
        album.event_date = date(2024, 2, 29)
        album.save()
        itens = homepage.build_memories([album], date(2026, 3, 1))
        self.assertEqual(itens[0]["phrase"], "Há 2 anos vocês estavam aqui")

    def test_destinos_juntam_o_mesmo_lugar(self):
        for numero in range(2):
            Album.objects.create(owner=self.a, title=f"G{numero}", location="Guaratuba", latitude=-25.88, longitude=-48.57)
        Album.objects.create(owner=self.a, title="Sem mapa", location="Só texto")
        contexto = self.contexto()
        self.assertEqual(len(contexto["destinations"]), 1)
        self.assertEqual(contexto["destination_labels"], ["Guaratuba"])

    def test_sem_lugar_nao_mostra_o_mapa(self):
        self.album()
        self.client.force_login(self.a)
        self.assertNotContains(self.client.get("/"), "EXPLORE SEUS DESTINOS")


class TutorialTests(Base):
    def test_perfil_proprio_tem_central_de_ajuda_e_sair(self):
        self.client.force_login(self.a)
        r = self.client.get("/perfil/ana/")
        for texto in ("Meu perfil", "Configurações da conta", "Meus amigos", "Como usar o Rolêflix", "Começar tutorial", "Sair da conta"):
            self.assertContains(r, texto)

    def test_perfil_de_outra_pessoa_nao_mostra_a_conta(self):
        self.client.force_login(self.a)
        r = self.client.get("/perfil/bia/")
        self.assertNotContains(r, "Sair da conta")
        self.assertNotContains(r, "Começar tutorial")

    def test_tutorial_exige_login(self):
        self.assertEqual(self.client.get("/ajuda/").status_code, 302)

    def test_tutorial_tem_sete_etapas(self):
        self.client.force_login(self.a)
        r = self.client.get("/ajuda/")
        self.assertContains(r, 'class="tutorial-step"', count=7)
        self.assertContains(r, "Concluir tutorial")
        self.assertContains(r, "Não mostrar novamente")

    def test_tutorial_so_cita_o_que_existe(self):
        self.client.force_login(self.a)
        pagina = self.client.get("/ajuda/").content.decode().lower()
        self.assertIn("favoritar", pagina)
        self.assertNotIn("curtid", pagina)
        self.assertNotIn("comentári", pagina)

    def test_convite_aparece_ate_ser_dispensado(self):
        self.client.force_login(self.a)
        self.assertContains(self.client.get("/"), "Novo por aqui?")
        self.assertRedirects(self.client.post("/ajuda/ocultar/", {"to": "home"}), "/")
        self.assertNotContains(self.client.get("/"), "Novo por aqui?")

    def test_concluir_volta_ao_perfil_e_tutorial_continua_aberto(self):
        self.client.force_login(self.a)
        self.assertRedirects(self.client.post("/ajuda/ocultar/", {"to": "profile"}), "/perfil/ana/")
        self.assertNotContains(self.client.get("/"), "Novo por aqui?")
        r = self.client.get("/ajuda/")
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "Não mostrar novamente")

    def test_dispensar_nao_afeta_outra_pessoa(self):
        self.client.force_login(self.a)
        self.client.post("/ajuda/ocultar/")
        self.client.force_login(self.b)
        self.assertContains(self.client.get("/"), "Novo por aqui?")

    def test_dispensar_exige_post(self):
        self.client.force_login(self.a)
        self.assertEqual(self.client.get("/ajuda/ocultar/").status_code, 405)

    def test_conta_sem_perfil_consegue_dispensar(self):
        Profile.objects.filter(user=self.a).delete()
        self.client.force_login(self.a)
        self.client.post("/ajuda/ocultar/")
        self.assertTrue(Profile.objects.get(user=self.a).tutorial_hidden)


class FavoritosTests(Base):
    def test_favoritar_e_desfavoritar(self):
        album = self.album()
        self.client.force_login(self.a)
        self.assertRedirects(self.client.post(f"/album/{album.pk}/favorito/"), f"/album/{album.pk}/")
        self.assertContains(self.client.get(f"/album/{album.pk}/"), "★ Nos favoritos")
        self.client.post(f"/album/{album.pk}/favorito/")
        self.assertFalse(Favorite.objects.exists())
        self.assertContains(self.client.get(f"/album/{album.pk}/"), "☆ Favoritar")

    def test_sem_acesso_nao_favorita(self):
        album = self.album()
        self.client.force_login(self.b)
        self.assertEqual(self.client.post(f"/album/{album.pk}/favorito/").status_code, 404)
        self.assertFalse(Favorite.objects.exists())

    def test_get_nao_muda_nada(self):
        album = self.album()
        self.client.force_login(self.a)
        self.assertEqual(self.client.get(f"/album/{album.pk}/favorito/").status_code, 405)

    def test_aparece_no_inicio_e_em_meus_roles(self):
        album = self.album(title="Preferido")
        Favorite.objects.create(user=self.a, album=album)
        self.client.force_login(self.a)
        self.assertEqual(self.client.get("/").context["favorites"], [album])
        self.assertContains(self.client.get("/"), "Meus favoritos")
        self.assertEqual(self.client.get("/meus-roles/").context["favorites"], [album])

    def test_favorito_e_pessoal_e_nao_mostra_contagem(self):
        album = self.shared_album()
        Favorite.objects.create(user=self.a, album=album)
        self.client.force_login(self.b)
        self.assertContains(self.client.get(f"/album/{album.pk}/"), "☆ Favoritar")
        self.assertEqual(self.client.get("/").context["favorites"], [])

    def test_perder_acesso_tira_dos_favoritos_sem_apagar(self):
        album = self.shared_album()
        Favorite.objects.create(user=self.b, album=album)
        AlbumParticipant.objects.all().delete()
        self.client.force_login(self.b)
        self.assertEqual(self.client.get("/").context["favorites"], [])
        self.assertTrue(Favorite.objects.exists())


class ColecoesManuaisTests(Base):
    def colecao(self, titulo="Família", dono=None):
        return Collection.objects.create(owner=dono or self.a, title=titulo)

    def test_criar_em_meus_roles(self):
        self.client.force_login(self.a)
        r = self.client.post("/colecoes/nova/", {"title": "Família"})
        colecao = Collection.objects.get()
        self.assertRedirects(r, f"/colecoes/{colecao.pk}/")
        self.assertEqual(colecao.owner, self.a)
        self.assertContains(self.client.get("/meus-roles/"), "Família")

    def test_nome_repetido_abre_a_existente(self):
        colecao = self.colecao()
        self.client.force_login(self.a)
        self.assertRedirects(self.client.post("/colecoes/nova/", {"title": "família"}), f"/colecoes/{colecao.pk}/")
        self.assertEqual(Collection.objects.count(), 1)

    def test_nome_vazio_ou_longo_nao_cria(self):
        self.client.force_login(self.a)
        self.client.post("/colecoes/nova/", {"title": ""})
        self.client.post("/colecoes/nova/", {"title": "x" * 61})
        self.assertFalse(Collection.objects.exists())

    def test_marcar_no_album_e_desmarcar(self):
        album, colecao = self.album(), self.colecao()
        self.client.force_login(self.a)
        self.client.post(f"/album/{album.pk}/colecoes/", {"collections": [colecao.pk]})
        self.assertIn(album, colecao.albums.all())
        self.client.post(f"/album/{album.pk}/colecoes/", {})
        self.assertNotIn(album, colecao.albums.all())

    def test_criar_nova_a_partir_do_album(self):
        album = self.album()
        self.client.force_login(self.a)
        self.client.post(f"/album/{album.pk}/colecoes/", {"title": "Faculdade"})
        self.assertIn(album, Collection.objects.get(title="Faculdade").albums.all())

    def test_nao_mexe_na_colecao_de_outra_pessoa(self):
        album = self.shared_album()
        alheia = self.colecao("Da Ana")
        alheia.albums.add(album)
        self.client.force_login(self.b)
        self.client.post(f"/album/{album.pk}/colecoes/", {"collections": []})
        self.assertIn(album, alheia.albums.all())
        self.assertEqual(self.client.get(f"/colecoes/{alheia.pk}/").status_code, 404)
        self.assertEqual(self.client.post(f"/colecoes/{alheia.pk}/", {"action": "delete"}).status_code, 404)
        self.assertTrue(Collection.objects.filter(pk=alheia.pk).exists())

    def test_sem_acesso_nao_guarda_o_album(self):
        album = self.album()
        minha = self.colecao("Minha", self.b)
        self.client.force_login(self.b)
        self.assertEqual(self.client.post(f"/album/{album.pk}/colecoes/", {"collections": [minha.pk]}).status_code, 404)
        self.client.post(f"/colecoes/{minha.pk}/", {"action": "add", "albums": [album.pk]})
        self.assertFalse(minha.albums.exists())

    def test_perder_acesso_esconde_e_nao_vaza_o_titulo(self):
        album = self.shared_album()
        colecao = self.colecao("Minha", self.b)
        colecao.albums.add(album)
        AlbumParticipant.objects.all().delete()
        self.client.force_login(self.b)
        self.assertNotContains(self.client.get(f"/colecoes/{colecao.pk}/"), "Rolê Secreto")

    def test_renomear_adicionar_tirar_e_excluir(self):
        album, colecao = self.album(), self.colecao()
        self.client.force_login(self.a)
        url = f"/colecoes/{colecao.pk}/"
        self.client.post(url, {"action": "rename", "title": "Turma"})
        colecao.refresh_from_db()
        self.assertEqual(colecao.title, "Turma")
        self.client.post(url, {"action": "add", "albums": [album.pk]})
        self.assertIn(album, colecao.albums.all())
        self.client.post(url, {"action": "remove", "album": album.pk})
        self.assertNotIn(album, colecao.albums.all())
        colecao.albums.add(album)
        self.assertRedirects(self.client.post(url, {"action": "delete"}), "/meus-roles/")
        self.assertFalse(Collection.objects.exists())
        self.assertTrue(Album.objects.filter(pk=album.pk).exists())

    def test_manual_aparece_no_inicio_antes_das_automaticas_e_vazia_nao(self):
        album = self.album(title="Rolê")
        self.colecao("Vazia")
        cheia = self.colecao("Cheia")
        cheia.albums.add(album)
        self.client.force_login(self.a)
        titulos = [c["title"] for c in self.client.get("/").context["collections"]]
        self.assertEqual(titulos, ["Cheia"])

    def test_excluir_album_tira_da_colecao(self):
        album, colecao = self.album(), self.colecao()
        colecao.albums.add(album)
        self.client.force_login(self.a)
        self.client.post(f"/album/{album.pk}/excluir/")
        self.assertTrue(Collection.objects.filter(pk=colecao.pk).exists())
        self.assertFalse(colecao.albums.exists())


def poster_jpg(size=(covers.WIDTH, covers.HEIGHT), formato="JPEG"):
    buffer = io.BytesIO()
    Image.new("RGB", size, (30, 60, 90)).save(buffer, formato)
    return SimpleUploadedFile("capa.jpg", buffer.getvalue(), content_type="image/jpeg")


class EditorDeCapasTests(Base):
    def setUp(self):
        super().setUp()
        self.capa = self.album(title="Guaratuba")
        self.capa.cover = png("original.png")
        self.capa.save()
        self.url = f"/album/{self.capa.pk}/capa/"
        self.client.force_login(self.a)

    def config(self, **extra):
        return json.dumps({**covers.default_config(self.capa), **extra})

    def salvar(self, **extra):
        dados = {"final": poster_jpg(), "config": self.config(), **extra}
        return self.client.post(self.url, dados)

    def test_so_o_criador_abre_o_editor(self):
        self.client.force_login(self.b)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(self.salvar().status_code, 404)

    def test_abre_com_modelos_e_album_com_link(self):
        r = self.client.get(self.url)
        self.assertContains(r, "Salvar capa")
        rotulos = [modelo["label"] for modelo in r.context["editor"]["templates"].values()]
        self.assertCountEqual(rotulos, ["Cinematográfico", "Praia", "Aventura", "Comédia"])
        self.assertContains(self.client.get(f"/album/{self.capa.pk}/"), "Personalizar capa")
        self.assertContains(self.client.get(f"/album/{self.capa.pk}/editar/"), "Abrir editor de capas")

    def test_participante_nao_ve_o_botao(self):
        album = self.shared_album()
        self.client.force_login(self.b)
        self.assertNotContains(self.client.get(f"/album/{album.pk}/"), "Personalizar capa")

    def test_salvar_guarda_poster_foto_limpa_e_opcoes(self):
        self.assertEqual(self.salvar(config=self.config(filter="ocean")).status_code, 200)
        self.capa.refresh_from_db()
        desenho = self.capa.cover_design
        self.assertTrue(self.capa.has_poster)
        self.assertEqual(desenho.config["filter"], "ocean")
        self.assertNotEqual(desenho.background.name, self.capa.cover.name)
        self.assertEqual(self.capa.backdrop, desenho.background)
        with Image.open(self.capa.cover.path) as imagem:
            self.assertEqual((imagem.format, imagem.size), ("JPEG", (covers.WIDTH, covers.HEIGHT)))

    def test_reabrir_continua_da_foto_limpa_e_das_opcoes(self):
        self.salvar(config=self.config(title="Outro nome"))
        limpa = CoverDesign.objects.get().background.name
        r = self.client.get(self.url)
        editor = r.context["editor"]
        self.assertEqual(editor["config"]["title"], "Outro nome")
        self.assertIn(limpa, editor["background"])
        self.salvar()
        self.assertEqual(CoverDesign.objects.get().background.name, limpa)

    def test_salvar_de_novo_nao_deixa_arquivo_velho(self):
        self.salvar()
        self.capa.refresh_from_db()
        antigo = self.capa.cover.path
        self.salvar()
        self.capa.refresh_from_db()
        self.assertNotEqual(antigo, self.capa.cover.path)
        with self.assertRaises(FileNotFoundError):
            open(antigo, "rb")

    def test_fundo_enviado_ou_do_album(self):
        self.assertEqual(self.salvar(background_file=png("novo.png")).status_code, 200)
        primeiro = CoverDesign.objects.get().background.name
        foto = MediaItem.objects.create(album=self.capa, kind="photo", uploaded_by=self.a, file=png("foto.png"))
        self.assertEqual(self.salvar(background_media=foto.pk).status_code, 200)
        self.assertNotEqual(CoverDesign.objects.get().background.name, primeiro)

    def test_foto_de_outro_album_e_recusada(self):
        outro = self.album(title="Outro", owner=self.b)
        alheia = MediaItem.objects.create(album=outro, kind="photo", uploaded_by=self.b, file=png("alheia.png"))
        self.assertEqual(self.salvar(background_media=alheia.pk).status_code, 400)
        self.assertFalse(CoverDesign.objects.exists())

    def test_fundo_que_nao_e_imagem_e_recusado(self):
        falso = SimpleUploadedFile("x.png", b"<svg onload=alert(1)>")
        r = self.salvar(background_file=falso)
        self.assertEqual(r.status_code, 400)
        self.assertIn("Envie uma foto", r.json()["error"])

    def test_sem_fundo_nenhum_pede_imagem(self):
        vazio = self.album(title="Sem capa")
        r = self.client.post(f"/album/{vazio.pk}/capa/", {"final": poster_jpg(), "config": self.config()})
        self.assertEqual(r.status_code, 400)
        self.assertIn("imagem de fundo", r.json()["error"])

    def test_imagem_final_invalida_e_recusada(self):
        for final in (poster_jpg((100, 100)), poster_jpg(formato="PNG"), SimpleUploadedFile("c.jpg", b"x")):
            self.assertEqual(self.salvar(final=final).status_code, 400)
        self.assertEqual(self.client.post(self.url, {"config": self.config()}).status_code, 400)
        self.capa.refresh_from_db()
        self.assertFalse(self.capa.has_poster)

    def test_opcoes_invalidas_sao_recusadas(self):
        for ruim in ({"font": "Comic"}, {"color": "red;"}, {"title": "  "}, {"title_size": 9999}, {"x": 5}, {"filter": "<b>"}, {"align": "x"}):
            self.assertEqual(self.salvar(config=self.config(**ruim)).status_code, 400, ruim)
        self.assertEqual(self.salvar(config="{").status_code, 400)
        self.assertEqual(self.salvar(config="[]").status_code, 400)

    def test_campos_desconhecidos_nao_sao_guardados(self):
        self.salvar(config=self.config(extra="<script>"))
        self.assertNotIn("extra", CoverDesign.objects.get().config)

    def test_foto_limpa_respeita_o_acesso_do_album(self):
        self.salvar()
        url = CoverDesign.objects.get().background.url
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.force_login(self.b)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_pagina_usa_a_foto_limpa_e_mostra_o_poster(self):
        self.salvar()
        self.capa.refresh_from_db()
        r = self.client.get(f"/album/{self.capa.pk}/")
        self.assertContains(r, self.capa.cover_design.background.url)
        self.assertContains(r, 'class="hero-poster"')

    def test_cartao_com_poster_nao_repete_o_titulo_visivel(self):
        self.salvar()
        self.album(title="Destaque novo").save()
        Album.objects.filter(title="Destaque novo").update(cover="album_covers/x.png")
        self.assertContains(self.client.get("/"), "poster custom")

    def test_restaurar_volta_a_foto(self):
        self.salvar()
        self.assertRedirects(self.client.post(f"/album/{self.capa.pk}/capa/restaurar/"), f"/album/{self.capa.pk}/")
        self.capa.refresh_from_db()
        self.assertFalse(self.capa.has_poster)
        self.assertFalse(CoverDesign.objects.exists())
        with Image.open(self.capa.cover.path) as imagem:
            self.assertEqual(imagem.format, "PNG")

    def test_trocar_a_capa_pelo_formulario_descarta_o_desenho(self):
        self.salvar()
        self.client.post(f"/album/{self.capa.pk}/editar/", {"title": "Guaratuba", "visibility": "private", "cover": png("nova.png")})
        self.capa.refresh_from_db()
        self.assertFalse(self.capa.has_poster)
        self.assertFalse(CoverDesign.objects.exists())

    def test_editar_texto_do_album_mantem_o_poster(self):
        self.salvar()
        self.client.post(f"/album/{self.capa.pk}/editar/", {"title": "Novo título", "visibility": "private"})
        self.capa.refresh_from_db()
        self.assertTrue(self.capa.has_poster)

    def test_excluir_album_apaga_a_foto_limpa_do_disco(self):
        self.salvar()
        caminho = CoverDesign.objects.get().background.path
        self.client.post(f"/album/{self.capa.pk}/excluir/")
        with self.assertRaises(FileNotFoundError):
            open(caminho, "rb")

    def test_fontes_do_editor_existem(self):
        for arquivo in ("bebas-neue", "anton", "bangers", "playfair-display", "inter"):
            self.assertIsNotNone(finders.find(f"fonts/{arquivo}.woff2"), arquivo)


class FotoDePerfilRapidaTests(Base):
    def test_perfil_proprio_convida_a_colocar_foto(self):
        self.client.force_login(self.a)
        self.assertContains(self.client.get("/perfil/ana/"), "Adicionar foto")
        self.assertNotContains(self.client.get("/perfil/bia/"), "Adicionar foto")

    def test_enviar_foto_aparece_no_perfil_e_na_barra(self):
        self.client.force_login(self.a)
        self.assertRedirects(self.client.post("/conta/foto/", {"avatar": png("eu.png")}), "/perfil/ana/")
        perfil = Profile.objects.get(user=self.a)
        self.assertTrue(perfil.avatar)
        r = self.client.get("/perfil/ana/")
        self.assertContains(r, "Trocar foto")
        self.assertContains(r, perfil.avatar.url, count=2)

    def test_trocar_apaga_a_foto_antiga(self):
        self.client.force_login(self.a)
        self.client.post("/conta/foto/", {"avatar": png("um.png")})
        antiga = Profile.objects.get(user=self.a).avatar.path
        self.client.post("/conta/foto/", {"avatar": png("dois.png")})
        with self.assertRaises(FileNotFoundError):
            open(antiga, "rb")

    def test_arquivo_que_nao_e_foto_e_recusado(self):
        self.client.force_login(self.a)
        r = self.client.post("/conta/foto/", {"avatar": SimpleUploadedFile("x.svg", b"<svg onload='alert(1)'/>", "image/svg+xml")}, follow=True)
        self.assertFalse(Profile.objects.get_or_create(user=self.a)[0].avatar)
        self.assertEqual(len(list(r.context["messages"])), 1)

    def test_sem_arquivo_avisa(self):
        self.client.force_login(self.a)
        r = self.client.post("/conta/foto/", {}, follow=True)
        self.assertContains(r, "Escolha uma foto")

    def test_exige_login_e_post(self):
        self.assertEqual(self.client.post("/conta/foto/").status_code, 302)
        self.client.force_login(self.a)
        self.assertEqual(self.client.get("/conta/foto/").status_code, 405)


class IngressoTests(Base):
    def setUp(self):
        super().setUp()
        self.rol = Album.objects.create(owner=self.a, title="Guaratuba 2026", event_date=date(2026, 1, 10), location="Guaratuba, Paraná", synopsis="Sol e mar.")
        self.url = f"/album/{self.rol.pk}/ingresso/novo/"
        self.client.force_login(self.a)

    def gerar(self, **extra):
        return self.client.post(self.url, {"style": "classic", "tagline": "", **extra})

    def futuro(self):
        return timezone.localdate() + timedelta(days=30)

    def test_gera_png_transparente_com_numero(self):
        self.assertRedirects(self.gerar(), f"/album/{self.rol.pk}/#ingressos", fetch_redirect_response=False)
        ingresso = Ticket.objects.get()
        self.assertEqual(ingresso.number, "RF-2026-001")
        self.assertEqual(ingresso.tagline, "Sol e mar.")
        with Image.open(ingresso.image.path) as imagem:
            self.assertEqual((imagem.format, imagem.mode, imagem.size), ("PNG", "RGBA", (tickets.WIDTH, tickets.HEIGHT)))
            self.assertEqual(imagem.getpixel((2, 2))[3], 0)

    def test_os_quatro_modelos_com_textos_dificeis(self):
        album = Album.objects.create(owner=self.a, title="Título muito comprido " * 4, location="Lugar bem comprido " * 6)
        for chave, _ in Ticket.STYLE:
            imagem = tickets.render(album, chave, "", "Frase comprida " * 6, "RF-2026-999", False)
            self.assertEqual(imagem.size, (tickets.WIDTH, tickets.HEIGHT))

    def test_elenco_sem_foto_e_com_foto(self):
        Profile.objects.update_or_create(user=self.b, defaults={"avatar": png("b.png")})
        AlbumParticipant.objects.create(album=self.rol, user=self.b)
        self.assertEqual(self.gerar().status_code, 302)

    def test_album_sem_capa_data_ou_local(self):
        vazio = Album.objects.create(owner=self.a, title="Sem nada")
        self.assertEqual(self.client.post(f"/album/{vazio.pk}/ingresso/novo/", {"style": "retro"}).status_code, 302)

    def test_numeracao_sobe_por_ano(self):
        self.gerar()
        self.gerar(style="retro")
        outro = Album.objects.create(owner=self.a, title="Antigo", event_date=date(2024, 3, 1))
        self.client.post(f"/album/{outro.pk}/ingresso/novo/", {"style": "classic"})
        self.assertEqual(sorted(t.number for t in Ticket.objects.all()), ["RF-2024-001", "RF-2026-001", "RF-2026-002"])

    def test_gerar_outro_nao_apaga_o_anterior(self):
        self.gerar()
        self.gerar(style="vintage")
        self.assertEqual(self.rol.tickets.count(), 2)

    def test_personalizar_cor_e_frase(self):
        self.gerar(accent="#123456", tagline="Nossa frase")
        ingresso = Ticket.objects.get()
        self.assertEqual((ingresso.accent, ingresso.tagline), ("#123456", "Nossa frase"))

    def test_cor_invalida_e_recusada(self):
        self.assertContains(self.gerar(accent="red;"), "Informe um valor válido")
        self.assertFalse(Ticket.objects.exists())

    def test_limite_por_pessoa(self):
        with patch("roleflix.tickets.MAX_PER_PERSON", 1):
            self.gerar()
            self.gerar()
        self.assertEqual(Ticket.objects.count(), 1)

    def test_rol_e_futuro_sai_como_pre_estreia(self):
        self.rol.event_date = self.futuro()
        self.rol.save()
        self.assertContains(self.client.get(f"/album/{self.rol.pk}/"), "Ingresso de pré-estreia")
        self.assertContains(self.client.get(self.url), "ainda vai acontecer")
        self.gerar()
        ingresso = Ticket.objects.get()
        self.assertTrue(ingresso.upcoming)
        self.assertIn("próximo rolê", ingresso.tagline)

    def test_rol_e_de_hoje_nao_e_futuro(self):
        self.assertFalse(tickets.is_upcoming(Album(event_date=date(2026, 5, 1)), date(2026, 5, 1)))
        self.assertTrue(tickets.is_upcoming(Album(event_date=date(2026, 5, 2)), date(2026, 5, 1)))
        self.assertFalse(tickets.is_upcoming(Album(), date(2026, 5, 1)))

    def test_criar_album_futuro_com_a_opcao_leva_ao_gerador(self):
        dados = {"title": "Próxima viagem", "visibility": "private", "event_date": self.futuro().isoformat(), "make_ticket": "on"}
        r = self.client.post("/album/novo/", dados)
        album = Album.objects.get(title="Próxima viagem")
        self.assertRedirects(r, f"/album/{album.pk}/ingresso/novo/")

    def test_opcao_e_ignorada_para_data_passada(self):
        r = self.client.post("/album/novo/", {"title": "Já foi", "visibility": "private", "event_date": "2020-01-01", "make_ticket": "on"})
        self.assertRedirects(r, f"/album/{Album.objects.get(title='Já foi').pk}/")

    def test_opcao_so_existe_ao_criar(self):
        self.assertContains(self.client.get("/album/novo/"), "Criar o ingresso deste rolê")
        self.assertNotContains(self.client.get(f"/album/{self.rol.pk}/editar/"), "Criar o ingresso deste rolê")

    def test_participante_tambem_gera_o_seu(self):
        album = self.shared_album()
        self.client.force_login(self.b)
        self.assertEqual(self.client.post(f"/album/{album.pk}/ingresso/novo/", {"style": "premium"}).status_code, 302)
        self.assertEqual(Ticket.objects.get().created_by, self.b)

    def test_sem_acesso_nao_gera_nem_ve(self):
        self.gerar()
        ingresso = Ticket.objects.get()
        self.client.force_login(self.b)
        self.assertEqual(self.gerar().status_code, 404)
        self.assertEqual(self.client.get(f"/album/{self.rol.pk}/ingresso/previa/").status_code, 404)
        self.assertEqual(self.client.get(ingresso.image.url).status_code, 404)
        self.assertEqual(self.client.get(f"/ingressos/{ingresso.pk}/baixar/png/").status_code, 404)
        self.assertEqual(self.client.get(f"/ingressos/{ingresso.pk}/baixar/pdf/").status_code, 404)

    def test_perder_acesso_tira_da_colecao(self):
        album = self.shared_album()
        self.client.force_login(self.b)
        self.client.post(f"/album/{album.pk}/ingresso/novo/", {"style": "classic"})
        self.assertEqual(len(self.client.get("/ingressos/").context["tickets"]), 1)
        AlbumParticipant.objects.all().delete()
        self.assertEqual(len(self.client.get("/ingressos/").context["tickets"]), 0)

    def test_baixar_png_e_pdf(self):
        self.gerar()
        ingresso = Ticket.objects.get()
        r = self.client.get(f"/ingressos/{ingresso.pk}/baixar/png/")
        self.assertIn("ingresso-rf-2026-001.png", r["Content-Disposition"])
        r = self.client.get(f"/ingressos/{ingresso.pk}/baixar/pdf/")
        self.assertEqual(r["Content-Type"], "application/pdf")
        self.assertTrue(r.content.startswith(b"%PDF"))
        self.assertEqual(self.client.get(f"/ingressos/{ingresso.pk}/baixar/exe/").status_code, 404)

    def test_previa_nao_guarda_nada(self):
        r = self.client.get(f"/album/{self.rol.pk}/ingresso/previa/?style=retro&accent=%23123456")
        self.assertEqual(r["Content-Type"], "image/png")
        self.assertFalse(Ticket.objects.exists())
        self.assertEqual(self.client.get(f"/album/{self.rol.pk}/ingresso/previa/?style=x").status_code, 400)

    def test_um_favorito_por_album(self):
        self.gerar()
        self.gerar()
        um, dois = Ticket.objects.order_by("pk")
        self.client.post(f"/ingressos/{um.pk}/favorito/")
        self.client.post(f"/ingressos/{dois.pk}/favorito/")
        um.refresh_from_db()
        dois.refresh_from_db()
        self.assertEqual((um.is_favorite, dois.is_favorite), (False, True))
        self.assertEqual(self.rol.tickets.first(), dois)

    def test_so_quem_gerou_favorita_e_exclui(self):
        album = self.shared_album()
        self.client.post(f"/album/{album.pk}/ingresso/novo/", {"style": "classic"})
        ingresso = Ticket.objects.get()
        self.client.force_login(self.b)
        self.assertEqual(self.client.post(f"/ingressos/{ingresso.pk}/excluir/").status_code, 404)
        self.assertEqual(self.client.post(f"/ingressos/{ingresso.pk}/favorito/").status_code, 404)

    def test_excluir_apaga_o_arquivo(self):
        self.gerar()
        ingresso = Ticket.objects.get()
        caminho = ingresso.image.path
        self.client.post(f"/ingressos/{ingresso.pk}/excluir/")
        self.assertFalse(Ticket.objects.exists())
        with self.assertRaises(FileNotFoundError):
            open(caminho, "rb")

    def test_excluir_album_apaga_os_ingressos_do_disco(self):
        self.gerar()
        caminho = Ticket.objects.get().image.path
        self.client.post(f"/album/{self.rol.pk}/excluir/")
        with self.assertRaises(FileNotFoundError):
            open(caminho, "rb")

    def test_ingresso_avisa_que_e_lembranca(self):
        origem = open(tickets.__file__, encoding="utf-8").read()
        self.assertIn("Não vale como entrada.", origem)

    def test_fontes_do_ingresso_existem(self):
        for estilo in tickets.STYLES.values():
            self.assertIsNotNone(finders.find(f"fonts/ttf/{estilo.title_font}.ttf"))


class ExcluirContaTests(Base):
    def test_exige_login_e_confirmacao(self):
        self.assertEqual(self.client.get("/conta/excluir/").status_code, 302)
        self.client.force_login(self.a)
        self.assertContains(self.client.post("/conta/excluir/", {"confirm": "excluir"}), "Digite EXCLUIR")
        self.assertTrue(User.objects.filter(pk=self.a.pk).exists())

    def test_apaga_conta_album_e_todos_os_arquivos(self):
        Profile.objects.update_or_create(user=self.a, defaults={"avatar": png("eu.png")})
        album = self.album()
        album.cover = png("capa.png")
        album.save()
        foto = MediaItem.objects.create(album=album, kind="photo", uploaded_by=self.a, file=png("f.png"))
        trailer = Trailer.objects.create(album=album, created_by=self.a, status=Trailer.READY, file=SimpleUploadedFile("t.mp4", b"v"))
        design = CoverDesign.objects.create(album=album, background=png("limpa.png"))
        ingresso = tickets.create_ticket(album, self.a, "classic", "", "Frase")
        caminhos = [Profile.objects.get(user=self.a).avatar.path, album.cover.path, foto.file.path, trailer.file.path, design.background.path, ingresso.image.path]
        self.client.force_login(self.a)
        self.assertRedirects(self.client.post("/conta/excluir/", {"confirm": "EXCLUIR"}), "/")
        self.assertFalse(User.objects.filter(pk=self.a.pk).exists())
        self.assertFalse(Album.objects.exists())
        for caminho in caminhos:
            with self.assertRaises(FileNotFoundError):
                open(caminho, "rb")

    def test_apaga_o_que_enviou_ao_album_de_amigo_e_preserva_o_album(self):
        album = self.shared_album()
        minha = MediaItem.objects.create(album=album, kind="photo", uploaded_by=self.b, file=png("b.png"))
        da_ana = MediaItem.objects.create(album=album, kind="photo", uploaded_by=self.a, file=png("a.png"))
        ingresso = tickets.create_ticket(album, self.b, "retro", "", "Frase")
        caminho, caminho_ingresso = minha.file.path, ingresso.image.path
        self.client.force_login(self.b)
        self.client.post("/conta/excluir/", {"confirm": "EXCLUIR"})
        self.assertTrue(Album.objects.filter(pk=album.pk).exists())
        self.assertEqual(list(album.media.all()), [da_ana])
        for alvo in (caminho, caminho_ingresso):
            with self.assertRaises(FileNotFoundError):
                open(alvo, "rb")
        self.assertTrue(open(da_ana.file.path, "rb").close() is None)

    def test_quem_foi_excluido_sai_do_login(self):
        self.client.force_login(self.a)
        self.client.post("/conta/excluir/", {"confirm": "EXCLUIR"})
        self.assertEqual(self.client.get("/meus-roles/").status_code, 302)


class LancamentoTests(Base):
    CADASTRO = {"first_name": "Nova", "email": "nova@x.com", "password1": SENHA, "password2": SENHA}

    def test_paginas_legais_publicas(self):
        self.assertContains(self.client.get("/privacidade/"), "Lei Geral de Proteção de Dados")
        self.assertContains(self.client.get("/termos/"), "18 anos")
        self.assertContains(self.client.get("/cadastro/"), "termos de uso")

    @override_settings(ROLEFLIX_CONTACT_EMAIL="contato@roleflix.test")
    def test_contato_aparece_nos_documentos(self):
        self.assertContains(self.client.get("/privacidade/"), "contato@roleflix.test")

    @override_settings(ROLEFLIX_INVITE_CODE="turma-2026")
    def test_convite_errado_nao_cria_conta(self):
        r = self.client.post("/cadastro/", {**self.CADASTRO, "invite_code": "errado"})
        self.assertContains(r, "Código de convite incorreto")
        self.assertFalse(User.objects.filter(email="nova@x.com").exists())

    @override_settings(ROLEFLIX_INVITE_CODE="turma-2026")
    def test_sem_convite_nao_cria_conta(self):
        self.client.post("/cadastro/", self.CADASTRO)
        self.assertFalse(User.objects.filter(email="nova@x.com").exists())

    @override_settings(ROLEFLIX_INVITE_CODE="turma-2026")
    def test_convite_certo_cria_conta(self):
        self.client.post("/cadastro/", {**self.CADASTRO, "invite_code": "turma-2026"})
        self.assertTrue(User.objects.filter(email="nova@x.com").exists())

    def test_sem_convite_configurado_cadastro_e_aberto(self):
        self.assertNotContains(self.client.get("/cadastro/"), "Código de convite")
        self.client.post("/cadastro/", self.CADASTRO)
        self.assertTrue(User.objects.filter(email="nova@x.com").exists())

    @override_settings(ROLEFLIX_INVITE_CODE="turma-2026")
    def test_google_nao_fura_o_convite(self):
        from .adapters import InviteOnlySocialAdapter
        self.assertFalse(InviteOnlySocialAdapter().is_open_for_signup(None, None))

    def test_disco_quase_cheio_recusa_envio(self):
        album = self.album()
        self.client.force_login(self.a)
        with override_settings(ROLEFLIX_MIN_FREE_DISK=10 ** 18):
            r = self.client.post(f"/album/{album.pk}/upload/", {"files": png("f.png")}, follow=True)
        self.assertContains(r, "espaço do site")
        self.assertFalse(album.media.exists())

    def test_senha_comum_e_recusada(self):
        self.client.post("/cadastro/", {**self.CADASTRO, "password1": "12345678", "password2": "12345678"})
        self.assertFalse(User.objects.filter(email="nova@x.com").exists())

    def test_preparar_lancamento_grava_o_dominio(self):
        from django.contrib.sites.models import Site
        from django.core.management import call_command
        saida = io.StringIO()
        with override_settings(ALLOWED_HOSTS=["roleflix.test", "127.0.0.1"]):
            call_command("preparar_lancamento", stdout=saida)
        self.assertEqual(Site.objects.get().domain, "roleflix.test")
        self.assertIn("PENDENTE", saida.getvalue())

    def test_pagina_404_usa_o_visual_do_site(self):
        with override_settings(DEBUG=False):
            self.assertContains(self.client.get("/nao-existe/"), "Essa cena não existe", status_code=404)


class FalhaDeEmailTests(Base):
    @override_settings(ACCOUNT_EMAIL_VERIFICATION="mandatory")
    def test_servico_de_email_fora_do_ar_nao_derruba_o_cadastro(self):
        with patch("django.core.mail.backends.locmem.EmailBackend.send_messages", side_effect=OSError("sem conexão")):
            with self.assertLogs("roleflix.adapters", level="ERROR"):
                r = self.client.post("/cadastro/", {"first_name": "Nova", "email": "nova@x.com", "password1": SENHA, "password2": SENHA})
        self.assertLess(r.status_code, 400)
        self.assertTrue(User.objects.filter(email="nova@x.com").exists())


class DemonstracaoTests(Base):
    @override_settings(ROLEFLIX_DEMO=True)
    def test_cadastro_fechado_em_todas_as_entradas(self):
        for caminho in ("/cadastro/", "/accounts/signup/"):
            self.assertContains(self.client.get(caminho), "Cadastro fechado na demonstração")
            dados = {"first_name": "Novo", "email": "novo@x.com", "password1": SENHA, "password2": SENHA}
            self.assertContains(self.client.post(caminho, dados), "Cadastro fechado na demonstração")
        self.assertFalse(User.objects.filter(email="novo@x.com").exists())

    @override_settings(ROLEFLIX_DEMO=True)
    def test_paginas_nao_oferecem_cadastro_e_mostram_a_conta_de_teste(self):
        r = self.client.get("/accounts/login/")
        self.assertNotContains(r, "Criar cadastro")
        self.assertNotContains(r, "Criar conta")
        self.assertNotContains(self.client.get("/"), "/cadastro/")
        self.assertContains(r, demo.DEMO_EMAIL)
        self.assertContains(r, demo.DEMO_PASSWORD)

    @override_settings(ROLEFLIX_DEMO=True)
    def test_conta_de_teste_entra_com_email_e_senha(self):
        demo.seed()
        r = self.client.post("/accounts/login/", {"login": demo.DEMO_EMAIL, "password": demo.DEMO_PASSWORD})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.client.get("/").context["user"].username, demo.DEMO_USERNAME)

    @override_settings(ROLEFLIX_DEMO=True)
    def test_conta_de_teste_tem_a_mesma_senha_em_todas_as_instancias(self):
        primeira = demo.seed().password
        User.objects.filter(username__in=["demo", "beatriz", "leo"]).delete()
        self.assertEqual(demo.seed().password, primeira)

    def test_fora_da_demonstracao_o_cadastro_continua_aberto_e_sem_conta_de_teste(self):
        self.assertContains(self.client.get("/cadastro/"), "Criar sua conta")
        r = self.client.get("/accounts/login/")
        self.assertContains(r, "Criar cadastro")
        self.assertNotContains(r, demo.DEMO_PASSWORD)

    def test_fora_da_vercel_nao_existe_faixa_nem_entrada(self):
        self.assertNotContains(self.client.get("/"), "Demonstração.")
        self.assertEqual(self.client.post("/demo/entrar/").status_code, 404)

    @override_settings(ROLEFLIX_DEMO=True)
    def test_entrar_cria_os_exemplos_uma_vez_so(self):
        self.assertContains(self.client.get("/"), "Entrar na demonstração")
        self.assertRedirects(self.client.post("/demo/entrar/"), "/")
        r = self.client.get("/")
        self.assertContains(r, "Não envie fotos pessoais")
        self.assertNotContains(r, "Entrar na demonstração")
        self.assertTrue(r.context["featured"])
        total = Album.objects.count()
        self.client.logout()
        self.client.post("/demo/entrar/")
        self.assertEqual(Album.objects.count(), total)

    @override_settings(ROLEFLIX_DEMO=True)
    def test_trailer_fica_desligado(self):
        album = self.album()
        foto = MediaItem.objects.create(album=album, kind="photo", uploaded_by=self.a, file=png("f.png"))
        self.client.force_login(self.a)
        dados = {"style": "fun", "duration": "30", "music": "auto", "media": [foto.pk]}
        with patch("roleflix.trailers.subprocess.Popen") as popen:
            r = self.client.post(f"/album/{album.pk}/trailer/novo/", dados, follow=True)
        popen.assert_not_called()
        self.assertContains(r, "trailers ficam desligados")
        self.assertFalse(album.trailers.exists())


class PreparoDaDemonstracaoTests(Base):
    def setUp(self):
        super().setUp()
        DemoSetupMiddleware.ready = False
        self.addCleanup(setattr, DemoSetupMiddleware, "ready", False)

    def test_fora_da_demonstracao_nao_prepara_nada(self):
        with patch("roleflix.demo.prepare") as prepare:
            self.client.get("/")
        prepare.assert_not_called()

    @override_settings(ROLEFLIX_DEMO=True)
    def test_prepara_na_primeira_visita_e_so_uma_vez(self):
        with patch("roleflix.demo.prepare") as prepare:
            self.assertEqual(self.client.get("/").status_code, 200)
            self.client.get("/termos/")
        prepare.assert_called_once()

    @override_settings(ROLEFLIX_DEMO=True)
    def test_falha_no_preparo_mostra_a_causa_e_tenta_de_novo(self):
        with patch("roleflix.demo.prepare", side_effect=OSError("disco cheio")):
            with self.assertLogs("roleflix.middleware", level="ERROR"):
                r = self.client.get("/")
        self.assertEqual(r.status_code, 503)
        self.assertIn("OSError: disco cheio", r.content.decode())
        with patch("roleflix.demo.prepare"):
            self.assertEqual(self.client.get("/").status_code, 200)

    @override_settings(ROLEFLIX_DEMO=True)
    def test_sem_a_imagem_da_paisagem_a_demonstracao_sobe(self):
        with patch("roleflix.demo.finders.find", return_value=None):
            demo.seed()
        self.assertTrue(Album.objects.filter(title="Guaratuba 2026").exists())


class DemonstracaoEntreInstanciasTests(Base):
    @override_settings(ROLEFLIX_DEMO=True)
    def test_conta_e_arquivos_sao_iguais_em_qualquer_instancia(self):
        demo.seed()
        senha = User.objects.get(username="demo").password
        capas = sorted(Album.objects.values_list("cover", flat=True))
        for album in Album.objects.all():
            album.cover.storage.delete(album.cover.name)
        for item in MediaItem.objects.all():
            item.file.storage.delete(item.file.name)
        User.objects.filter(username__in=["demo", "beatriz", "leo"]).delete()
        demo.seed()
        self.assertEqual(User.objects.get(username="demo").password, senha)
        self.assertEqual(sorted(Album.objects.values_list("cover", flat=True)), capas)


class RecuperarSenhaTests(Base):
    NOVA = "OutraSenhaForte!456"

    def setUp(self):
        super().setUp()
        cache.clear()  # O limite de pedidos por e-mail não pode passar de um teste para outro.

    def pedir(self, email="ana@x.com"):
        return self.client.post("/accounts/password/reset/", {"email": email})

    def link(self):
        return re.search(r"https?://\S+/accounts/password/reset/key/\S+", mail.outbox[-1].body).group(0)

    def test_login_tem_o_link(self):
        self.assertContains(self.client.get("/accounts/login/"), "Esqueceu a senha?")
        self.assertContains(self.client.get("/accounts/password/reset/"), "Enviar link")

    def test_email_em_portugues_com_link_limpo(self):
        self.assertRedirects(self.pedir(), "/accounts/password/reset/done/")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].subject, "Recupere sua senha do Rolêflix")
        self.assertEqual(mail.outbox[0].to, ["ana@x.com"])
        self.assertTrue(self.link().endswith("/"))

    def test_fluxo_completo_troca_a_senha(self):
        self.pedir()
        r = self.client.get(self.link(), follow=True)
        self.assertContains(r, "Criar senha nova")
        destino = r.redirect_chain[-1][0]
        r = self.client.post(destino, {"password1": self.NOVA, "password2": self.NOVA}, follow=True)
        self.assertContains(r, "Senha alterada!")
        self.a.refresh_from_db()
        self.assertTrue(self.a.check_password(self.NOVA))
        self.assertFalse(self.a.check_password(SENHA))

    def test_link_so_vale_uma_vez(self):
        self.pedir()
        url = self.link()
        destino = self.client.get(url, follow=True).redirect_chain[-1][0]
        self.client.post(destino, {"password1": self.NOVA, "password2": self.NOVA})
        self.client.logout()
        self.assertContains(self.client.get(url, follow=True), "Link inválido")

    def test_link_adulterado_e_recusado(self):
        self.assertContains(self.client.get("/accounts/password/reset/key/1-abc-def/", follow=True), "Link inválido")

    def test_email_sem_conta_nao_recebe_nada_e_nao_revela(self):
        r = self.pedir("ninguem@x.com")
        self.assertRedirects(r, "/accounts/password/reset/done/")
        self.assertEqual(mail.outbox, [])

    def test_servico_de_email_fora_do_ar_avisa_e_deixa_tentar_de_novo(self):
        for erro in (OSError("sem conexão"), smtplib.SMTPAuthenticationError(535, b"recusado")):
            with patch("django.core.mail.backends.locmem.EmailBackend.send_messages", side_effect=erro):
                with self.assertLogs("roleflix.adapters", level="ERROR"):
                    r = self.pedir()
            self.assertContains(r, "Não conseguimos enviar o e-mail agora")
        self.assertRedirects(self.pedir(), "/accounts/password/reset/done/")
        self.assertEqual(len(mail.outbox), 1)

    def test_excesso_de_pedidos_mostra_pagina_em_portugues(self):
        for _ in range(5):
            self.pedir()
        r = self.pedir()
        self.assertContains(r, "Muitas tentativas seguidas", status_code=429)

    def test_email_sem_conta_nao_depende_do_servico_de_email(self):
        with patch("django.core.mail.backends.locmem.EmailBackend.send_messages", side_effect=OSError("sem conexão")):
            self.assertRedirects(self.pedir("ninguem@x.com"), "/accounts/password/reset/done/")

    @override_settings(ROLEFLIX_DEMO=True)
    def test_demonstracao_avisa_quando_nao_envia_email(self):
        DemoSetupMiddleware.ready = True
        self.addCleanup(setattr, DemoSetupMiddleware, "ready", False)
        self.assertContains(self.client.get("/accounts/password/reset/"), "envio de e-mails está desligado")


@override_settings(SOCIALACCOUNT_PROVIDERS=GOOGLE)
class LoginGoogleTests(Base):
    def entrar_pelo_google(self, email="nova@gmail.com", verificado=True, uid="108"):
        from allauth.account.models import EmailAddress
        from allauth.core import context
        from allauth.socialaccount.helpers import complete_social_login
        from allauth.socialaccount.models import SocialAccount, SocialLogin
        from django.contrib.auth.models import AnonymousUser
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.contrib.sessions.middleware import SessionMiddleware
        from django.test import RequestFactory
        request = RequestFactory().get("/accounts/google/login/callback/")
        SessionMiddleware(lambda r: None).process_request(request)
        request.session.save()
        request.user = AnonymousUser()
        request._messages = FallbackStorage(request)
        conta = SocialAccount(provider="google", uid=uid, extra_data={"email": email, "given_name": "Nova", "name": "Nova Pessoa"})
        login = SocialLogin(user=User(email=email, first_name="Nova"), account=conta, email_addresses=[EmailAddress(email=email, verified=verificado, primary=True)])
        login.state = {"process": "login", "next": "/"}
        with context.request_context(request):
            login.provider = conta.get_provider(request)
            return complete_social_login(request, login)

    @override_settings(ACCOUNT_EMAIL_VERIFICATION="mandatory")
    def test_primeiro_acesso_cria_conta_sem_pedir_confirmacao(self):
        r = self.entrar_pelo_google()
        self.assertEqual(r.status_code, 302)
        self.assertNotIn("confirm", r["Location"])
        pessoa = User.objects.get(email="nova@gmail.com")
        self.assertEqual(pessoa.first_name, "Nova")
        self.assertFalse(pessoa.has_usable_password())

    def test_conta_com_o_mesmo_email_entra_na_mesma_pessoa(self):
        total = User.objects.count()
        self.entrar_pelo_google(email=self.a.email)
        self.assertEqual(User.objects.count(), total)
        self.assertTrue(self.a.socialaccount_set.exists())

    @override_settings(ROLEFLIX_INVITE_CODE="turma-2026")
    def test_convite_ativo_barra_conta_nova(self):
        self.entrar_pelo_google()
        self.assertFalse(User.objects.filter(email="nova@gmail.com").exists())

    def test_quem_entrou_pelo_google_pode_criar_senha_pelo_recuperar(self):
        self.entrar_pelo_google()
        self.client.post("/accounts/password/reset/", {"email": "nova@gmail.com"})
        self.assertEqual(len(mail.outbox), 1)



class MensagemDeLoginTests(Base):
    def test_entrar_nao_mostra_aviso(self):
        r = self.client.post("/accounts/login/", {"login": "ana@x.com", "password": SENHA}, follow=True)
        self.assertTrue(r.context["user"].is_authenticated)
        self.assertEqual(list(r.context["messages"]), [])
        self.assertNotContains(r, "Conectado")

    def test_senha_errada_continua_avisando(self):
        r = self.client.post("/accounts/login/", {"login": "ana@x.com", "password": "errada"})
        self.assertFalse(r.context["user"].is_authenticated)
        self.assertContains(r, "errorlist")
