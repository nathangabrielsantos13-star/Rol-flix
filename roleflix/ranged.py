"""Entrega de arquivos com suporte a Range, exigido para avançar vídeos e tocá-los no iPhone."""
import mimetypes
import re

from django.http import FileResponse, HttpResponse, StreamingHttpResponse

RANGE_HEADER = re.compile(r"^bytes=(\d*)-(\d*)$")
CHUNK_SIZE = 64 * 1024


def parse_range(header, size):
    """Devolve (início, fim) inclusivos; None para ignorar o pedido; False se estiver fora do arquivo."""
    match = RANGE_HEADER.match(header.strip())
    if not match or match.groups() == ("", ""):
        return None
    first, last = match.groups()
    if first:
        start = int(first)
        end = min(int(last), size - 1) if last else size - 1
    else:
        start = max(size - int(last), 0)
        end = size - 1
    if start >= size or (not first and not int(last)):
        return False
    return None if start > end else (start, end)


def read_chunks(file, start, length):
    with file:
        file.seek(start)
        while length > 0:
            data = file.read(min(CHUNK_SIZE, length))
            if not data:
                return
            length -= len(data)
            yield data


def ranged_response(request, field):
    file = field.open("rb")
    size = file.file.size  # Já aberto: perguntar a field.size gastaria uma operação da loja de arquivos.
    wanted = parse_range(request.headers.get("Range", ""), size)
    if wanted is None:
        response = FileResponse(file)
        response["Accept-Ranges"] = "bytes"
        return response
    if wanted is False:
        file.close()
        response = HttpResponse(status=416)
        response["Content-Range"] = f"bytes */{size}"
        return response
    start, end = wanted
    length = end - start + 1
    response = StreamingHttpResponse(
        read_chunks(file, start, length), status=206,
        content_type=mimetypes.guess_type(field.name)[0] or "application/octet-stream",
    )
    response["Content-Length"] = str(length)
    response["Content-Range"] = f"bytes {start}-{end}/{size}"
    response["Accept-Ranges"] = "bytes"
    return response
