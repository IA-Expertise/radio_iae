"""
News Agent - Rádio IA
Busca notícias no RSS do Google News (URL configurável em GOOGLE_NEWS_RSS) e gera roteiro de rádio via Gemini.
Scraper Louveira: notícias locais do site da prefeitura para roteiro ~2 min, persona profissional.
"""

import os
import re
from urllib.parse import urljoin

from dotenv import load_dotenv
import feedparser
import google.generativeai as genai
import requests
from bs4 import BeautifulSoup

# URL do RSS Google News (pt-BR). Altere 'q=' para testar outras fontes:
# Ex.: "dicas+de+IA" | "Louveira+SP" | "notícias+Louveira"
GOOGLE_NEWS_RSS = (
    "https://news.google.com/rss/search?q=Louveira+SP"
    "&hl=pt-BR&gl=BR&ceid=BR:pt-419"
)

# Quantidade de notícias para o roteiro
TOP_N = 3

# Scraper Louveira (prefeitura)
LOUVEIRA_BASE = "https://www.louveira.sp.gov.br"
LOUVEIRA_NOTICIAS_URL = "https://www.louveira.sp.gov.br/noticias"
LOUVEIRA_TIMEOUT = 15
LOUVEIRA_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RadioIA/1.0)"}


def _get_api_key() -> str:
    """Carrega e retorna a GEMINI_API_KEY do arquivo .env."""
    load_dotenv()
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise ValueError(
            "GEMINI_API_KEY não encontrada. Defina no arquivo .env na raiz do projeto."
        )
    return key


def fetch_news_louveira() -> list[dict]:
    """
    Scraping do site da Prefeitura de Louveira: pega as 3 notícias mais recentes da listagem,
    entra em cada link e extrai título e texto completo. Retorna lista com 'title' e 'summary' (corpo).
    """
    out: list[dict] = []
    try:
        r = requests.get(LOUVEIRA_NOTICIAS_URL, timeout=LOUVEIRA_TIMEOUT, headers=LOUVEIRA_HEADERS)
        r.raise_for_status()
    except Exception as e:
        raise RuntimeError(f"Erro ao acessar página de notícias de Louveira: {e}") from e

    soup = BeautifulSoup(r.text, "html.parser")
    # Links que parecem ser de matéria: /noticias/... com slug longo (não paginação como /busca/2)
    seen = set()
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if not href or not href.startswith("/noticias/"):
            continue
        full_url = urljoin(LOUVEIRA_BASE, href)
        # Ignora paginação e links genéricos
        if "/busca/" in href or href.rstrip("/") == "/noticias":
            continue
        if full_url in seen:
            continue
        # Evita duplicata por URL
        if full_url in seen:
            continue
        # Título: texto do link ou do h2 dentro
        title = (a.get_text(strip=True) or "").strip()
        if not title or len(title) < 15:
            continue
        seen.add(full_url)
        out.append({"title": title[:200], "url": full_url})
        if len(out) >= TOP_N:
            break

    if len(out) < TOP_N:
        # Fallback: pega h2 da página (listagem sem links individuais claros)
        for h2 in soup.find_all(["h2", "h3"])[:TOP_N]:
            t = h2.get_text(strip=True)
            if t and len(t) > 10 and len(out) < TOP_N:
                link = h2.find_parent("a") if h2.find_parent("a") else None
                url = urljoin(LOUVEIRA_BASE, link["href"]) if link and link.get("href") else None
                if url and url not in seen:
                    seen.add(url)
                    out.append({"title": t[:200], "url": url})

    # Entrar em cada matéria e pegar o texto completo
    for i, item in enumerate(out):
        url = item.get("url")
        if not url:
            item["summary"] = ""
            continue
        try:
            r2 = requests.get(url, timeout=LOUVEIRA_TIMEOUT, headers=LOUVEIRA_HEADERS)
            r2.raise_for_status()
        except Exception:
            item["summary"] = ""
            continue
        soup2 = BeautifulSoup(r2.text, "html.parser")
        # Título da matéria (pode atualizar)
        h1 = soup2.find("h1")
        if h1:
            item["title"] = h1.get_text(strip=True)[:200]
        # Corpo: prioriza article, .content, .conteudo, main, .noticia
        body_el = (
            soup2.find("article")
            or soup2.find(class_=re.compile(r"content|conteudo|noticia|corpo|texto|post-body", re.I))
            or soup2.find("main")
        )
        if body_el:
            text = body_el.get_text(separator=" ", strip=True)
        else:
            # Fallback: todo o texto de parágrafos
            text = " ".join(p.get_text(strip=True) for p in soup2.find_all("p")[:20])
        text = re.sub(r"\s+", " ", text).strip()[:8000]
        item["summary"] = text or item.get("title", "")

    return out


def fetch_news() -> list[dict]:
    """
    Busca as notícias no RSS do Google News (GOOGLE_NEWS_RSS).
    Retorna lista de entradas com 'title' e 'summary' (ou 'description').
    """
    feed = feedparser.parse(GOOGLE_NEWS_RSS)
    entries = []
    for entry in feed.entries[:TOP_N]:
        title = entry.get("title", "").strip()
        summary = (
            entry.get("summary", "")
            or entry.get("description", "")
            or ""
        ).strip()
        # Remove HTML básico se vier no summary
        if summary and "<" in summary:
            summary = re.sub(r"<[^>]+>", " ", summary)
            summary = " ".join(summary.split())
        entries.append({"title": title, "summary": summary})
    return entries


def build_script_prompt(news: list[dict]) -> str:
    """Monta o texto das notícias para enviar ao Gemini."""
    parts = []
    for i, item in enumerate(news, 1):
        parts.append(f"**Notícia {i}:** {item['title']}")
        if item.get("summary"):
            parts.append(f"Resumo: {item['summary']}")
    return "\n".join(parts)


def generate_radio_script(news: list[dict]) -> str:
    """
    Usa o Gemini para roteiro de rádio ~2 min (~350 palavras).
    Persona: locutor brasileiro experiente, tom profissional, utilidade pública, [pausa].
    """
    api_key = _get_api_key()
    genai.configure(api_key=api_key)

    system_instruction = """Você é um locutor de rádio brasileiro experiente. Tom profissional, frases curtas e claras, focado em utilidade pública e informação objetiva.
Regras para o roteiro:
- Use a marcação [pausa] entre blocos para respiração e ritmo.
- Duração: aproximadamente 2 minutos de leitura (320 a 380 palavras). Desenvolva cada notícia com contexto e desfecho.
- Base apenas nas notícias fornecidas; não invente dados.
- Otimizado para voz: evite siglas soletradas; evite números longos; preferir "mil" a "1.000".
- Saída: só o texto do roteiro, sem título. Comece com abertura breve (ex.: "Bom dia, ouvintes.", "Notícias do dia.")."""

    model = genai.GenerativeModel(
        "gemini-2.5-flash",
        system_instruction=system_instruction,
    )

    news_text = build_script_prompt(news)
    user_prompt = f"""Com base nas notícias abaixo, escreva um roteiro de rádio COMPLETO de aproximadamente 2 minutos (320 a 380 palavras). Tom profissional, utilidade pública. Desenvolva cada notícia. Use [pausa] entre blocos.

{news_text}

Gere somente o texto do roteiro."""

    response = model.generate_content(
        user_prompt,
        generation_config={
            "temperature": 0.6,
            "max_output_tokens": 1200,
        },
    )

    if not response.text:
        raise RuntimeError("Gemini não retornou texto para o roteiro.")

    return response.text.strip()


def run() -> str:
    """
    Fluxo principal (RSS Google News): busca notícias, gera roteiro e retorna o texto.
    """
    news = fetch_news()
    if not news:
        raise RuntimeError("Nenhuma notícia encontrada no RSS.")
    return generate_radio_script(news)


def run_louveira() -> str:
    """
    Fluxo Louveira: scraping do site da prefeitura, 3 notícias mais recentes,
    gera roteiro ~2 min, persona locutor profissional. Para uso na admin (ver roteiro e gerar áudio).
    """
    news = fetch_news_louveira()
    if not news:
        raise RuntimeError("Nenhuma notícia encontrada no site de Louveira.")
    return generate_radio_script(news)


if __name__ == "__main__":
    script = run()
    print(script)
