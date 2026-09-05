import xml.etree.ElementTree as ET

from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator


SOURCE_URL = "https://www.lotuspharm.com/en/newsroom"
BASE_URL = "https://www.lotuspharm.com"
OUTPUT_FILE = Path("docs/feed.xml")
MAX_ITEMS = 80

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/130.0 Safari/537.36"
    )
}


def limpiar(texto):
    return " ".join((texto or "").split())


def convertir_fecha(texto):
    try:
        fecha = datetime.strptime(texto, "%b %d, %Y")
        return fecha.replace(
            hour=8,
            minute=0,
            second=0,
            tzinfo=timezone.utc
        )
    except ValueError:
        return datetime.now(timezone.utc)


def leer_anteriores():
    anteriores = {}

    if not OUTPUT_FILE.exists():
        return anteriores

    try:
        root = ET.parse(OUTPUT_FILE).getroot()

        for item in root.findall("./channel/item"):
            enlace = limpiar(item.findtext("link"))

            if enlace:
                anteriores[enlace] = {
                    "title": limpiar(item.findtext("title")),
                    "link": enlace,
                    "description": limpiar(
                        item.findtext("description")
                    ),
                    "pubDate": limpiar(item.findtext("pubDate")),
                }

    except Exception as error:
        print(f"No se pudo leer la RSS anterior: {error}")

    return anteriores


def obtener_noticias():
    respuesta = requests.get(
        SOURCE_URL,
        headers=HEADERS,
        timeout=45
    )
    respuesta.raise_for_status()

    soup = BeautifulSoup(respuesta.text, "html.parser")
    noticias = {}

    tarjetas = soup.select(
        'a.article-card[href*="/newsroom/news-page/"], '
        'a.lotus-news-card[href*="/newsroom/news-page/"]'
    )

    for tarjeta in tarjetas:
        href = tarjeta.get("href")

        if not href:
            continue

        enlace = urljoin(BASE_URL, href)
        enlace = enlace.split("?")[0].split("#")[0]

        titulo_elemento = tarjeta.select_one(
            ".article-title, .lotus-news-card-title"
        )
        fecha_elemento = tarjeta.select_one(".article-date")
        descripcion_elemento = tarjeta.select_one(
            ".article-desc, .lotus-news-card-description"
        )
        tipo_elemento = tarjeta.select_one(
            ".article-type, .lotus-news-card-meta "
            ".text-lotus-title-1"
        )

        titulo = limpiar(
            titulo_elemento.get_text(" ", strip=True)
            if titulo_elemento else ""
        )

        if not titulo:
            imagen = tarjeta.select_one("img[alt]")
            titulo = limpiar(imagen.get("alt")) if imagen else ""

        if not titulo:
            continue

        texto_fecha = limpiar(
            fecha_elemento.get_text(" ", strip=True)
            if fecha_elemento else ""
        )

        descripcion = limpiar(
            descripcion_elemento.get_text(" ", strip=True)
            if descripcion_elemento else ""
        )

        tipo = limpiar(
            tipo_elemento.get_text(" ", strip=True)
            if tipo_elemento else ""
        )

        if tipo and descripcion:
            descripcion = f"{tipo}: {descripcion}"
        elif tipo:
            descripcion = f"Categoría: {tipo}"
        elif not descripcion:
            descripcion = (
                "Noticia publicada por Lotus Pharmaceutical."
            )

        noticias[enlace] = {
            "title": titulo,
            "link": enlace,
            "description": descripcion,
            "date": convertir_fecha(texto_fecha),
        }

    if not noticias:
        raise RuntimeError(
            "No se encontraron noticias de Lotus. "
            "La RSS anterior no será eliminada."
        )

    return list(noticias.values())


def generar_rss(noticias):
    anteriores = leer_anteriores()
    combinadas = {}

    for noticia in noticias:
        combinadas[noticia["link"]] = {
            "title": noticia["title"],
            "link": noticia["link"],
            "description": noticia["description"],
            "pubDate": format_datetime(noticia["date"]),
        }

    for enlace, noticia in anteriores.items():
        if enlace not in combinadas:
            combinadas[enlace] = noticia

    def clave_fecha(noticia):
        try:
            return datetime.strptime(
                noticia["pubDate"],
                "%a, %d %b %Y %H:%M:%S %z"
            )
        except ValueError:
            return datetime(1970, 1, 1, tzinfo=timezone.utc)

    ordenadas = sorted(
        combinadas.values(),
        key=clave_fecha,
        reverse=True
    )[:MAX_ITEMS]

    feed = FeedGenerator()
    feed.title("Lotus Pharmaceutical - Newsroom")
    feed.link(href=SOURCE_URL, rel="alternate")
    feed.description(
        "Últimas noticias de Lotus Pharmaceutical"
    )
    feed.language("en")
    feed.id(SOURCE_URL)
    feed.lastBuildDate(datetime.now(timezone.utc))

    for noticia in reversed(ordenadas):
        entrada = feed.add_entry()
        entrada.id(noticia["link"])
        entrada.title(noticia["title"])
        entrada.link(href=noticia["link"])
        entrada.description(noticia["description"])
        entrada.pubDate(clave_fecha(noticia))

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    feed.rss_file(str(OUTPUT_FILE), pretty=True)

    print(f"RSS creada con {len(ordenadas)} noticias.")


if __name__ == "__main__":
    generar_rss(obtener_noticias())
