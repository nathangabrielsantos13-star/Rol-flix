"""A integração da Vercel pode prefixar as variáveis, como STORAGE_DATABASE_URL. Aqui elas viram os nomes que o site usa."""
NOMES = {
    "DATABASE_URL": ("DATABASE_URL", "POSTGRES_URL"),
    "DATABASE_URL_UNPOOLED": ("DATABASE_URL_UNPOOLED", "POSTGRES_URL_NON_POOLING"),
    "BLOB_READ_WRITE_TOKEN": ("BLOB_READ_WRITE_TOKEN",),
    "BLOB_STORE_ID": ("BLOB_STORE_ID",),
}


def reconhecer(environ):
    for nome, aceitos in NOMES.items():
        if environ.get(nome):
            continue
        achados = sorted(k for k, v in environ.items() if v and any(k == a or k.endswith(f"_{a}") for a in aceitos))
        if achados:
            environ[nome] = environ[achados[0]]
