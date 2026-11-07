"""Busca de cidades e países pelo Open-Meteo (dados do GeoNames, CC BY 4.0).

A consulta passa pelo servidor para não expor o IP de quem digita e para guardar as respostas.
"""
import hashlib
import json
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.core.cache import cache

API_URL = "https://geocoding-api.open-meteo.com/v1/search"
CACHE_SECONDS = 60 * 60 * 24
TIMEOUT_SECONDS = 3
MAX_RESULTS = 8
MIN_QUERY_LENGTH = 2
COUNTRY_CODES = {"PCLI", "PCLD", "PCLF", "PCLS", "PCL"}


def place_label(place):
    if place.get("feature_code") in COUNTRY_CODES:
        return place.get("country") or place["name"]
    parts = [place["name"], place.get("admin1"), place.get("country")]
    unique = [part for index, part in enumerate(parts) if part and part not in parts[:index]]
    return ", ".join(unique)


def search_places(query):
    query = query.strip()[:60]
    if len(query) < MIN_QUERY_LENGTH:
        return []
    key = "place:" + hashlib.sha256(query.casefold().encode()).hexdigest()
    cached = cache.get(key)
    if cached is not None:
        return cached
    url = f"{API_URL}?{urlencode({'name': query, 'count': MAX_RESULTS, 'language': 'pt', 'format': 'json'})}"
    try:
        with urlopen(Request(url, headers={"User-Agent": "Roleflix/1.0"}), timeout=TIMEOUT_SECONDS) as response:
            data = json.load(response)
    except (URLError, OSError, ValueError):
        return []  # Sem a lista, a pessoa ainda pode digitar o local à mão.
    results = [
        {"label": place_label(place), "latitude": place["latitude"], "longitude": place["longitude"]}
        for place in data.get("results", [])
        if "latitude" in place and "longitude" in place and place.get("name")
    ]
    cache.set(key, results, CACHE_SECONDS)
    return results
