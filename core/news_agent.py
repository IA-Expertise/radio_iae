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
    seen: set[str] = set()

    # Estratégia 1: na página de Louveira as notícias estão em h2; pegar os 3 primeiros h2 e seus links (as 3 mais recentes)
    for h2 in soup.find_all(["h2", "h3"]):
        if len(out) >= TOP_N:
            break
        t = h2.get_text(strip=True)
        if not t or len(t) < 15:
            continue
        link = h2.find_parent("a")
        if not link or not link.get("href"):
            continue
        href = (link.get("href") or "").strip()
        if not href.startswith("/noticias/") or "/busca/" in href or "/secao/" in href:
            continue
        full_url = urljoin(LOUVEIRA_BASE, href)
        if full_url in seen:
            continue
        seen.add(full_url)
        out.append({"title": t[:200], "url": full_url})

    # Fallback: varrer todos os <a> com /noticias/ (excl. paginação e seção) e pegar as 3 primeiras
    if len(out) < TOP_N:
        for a in soup.find_all("a", href=True):
            if len(out) >= TOP_N:
                break
            href = (a.get("href") or "").strip()
            if not href or not href.startswith("/noticias/"):
                continue
            full_url = urljoin(LOUVEIRA_BASE, href)
            if "/busca/" in href or href.rstrip("/") == "/noticias" or "/secao/" in href:
                continue
            if full_url in seen:
                continue
            title = (a.get_text(strip=True) or "").strip()
            if not title or len(title) < 15:
                continue
            seen.add(full_url)
            out.append({"title": title[:200], "url": full_url})

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


MIN_WORDS = 280
MAX_RETRIES = 2


def _count_words(text: str) -> int:
    clean = text.replace("[pausa]", " ").replace("...", " ")
    return len(clean.split())


def generate_radio_script(news: list[dict], long_form: bool = False) -> str:
    """
    Usa o Gemini para roteiro de rádio.
    long_form=True: exige ~2 min (320–380 palavras), para boletim Louveira.
    Faz retry automático se o texto vier com menos de MIN_WORDS palavras.
    """
    api_key = _get_api_key()
    genai.configure(api_key=api_key)

    if long_form:
        system_instruction = """Você é um locutor de rádio brasileiro experiente. Tom profissional, frases curtas e claras, focado em utilidade pública.
Regras OBRIGATÓRIAS (siga TODAS sem exceção):
1. O roteiro deve ter EXATAMENTE 3 MATÉRIAS, na mesma ordem em que as notícias são fornecidas: primeiro a Notícia 1 (completa), depois [pausa], depois a Notícia 2 (completa), depois [pausa], depois a Notícia 3 (completa). NUNCA junte as 3 em uma única matéria longa. Cada uma das 3 notícias deve ter seu próprio bloco desenvolvido (abertura, contexto, detalhes, desfecho).
2. Total: entre 320 e 380 palavras (~2 minutos). Distribua o tempo entre as 3 matérias (cada uma com ~1 minuto de leitura em mente, ou ~100–130 palavras por notícia).
3. Use a marcação [pausa] entre cada uma das 3 matérias e em transições.
4. Base apenas nas notícias fornecidas; não invente dados.
5. Otimizado para voz: evite siglas soletradas; números por extenso ou "mil" em vez de "1.000".
6. Saída: APENAS o texto do roteiro, sem título, sem contagem. Comece com abertura breve (ex.: "Bom dia, ouvintes. Notícias do dia.") e em seguida a primeira matéria."""
        user_head = "As notícias abaixo são 3 MATÉRIAS DIFERENTES da prefeitura. Escreva um roteiro de 2 MINUTOS com 3 BLOCOS DISTINTOS: bloco 1 = só a Notícia 1; bloco 2 = só a Notícia 2; bloco 3 = só a Notícia 3. Use [pausa] entre os blocos. NÃO misture as 3 em uma única história. Desenvolva cada notícia com contexto e desfecho. Total 320–380 palavras.\n\nNotícias:\n\n"
        max_tokens = 2000
    else:
        system_instruction = """Você é um locutor de rádio brasileiro experiente. Tom profissional, frases curtas e claras, focado em utilidade pública e informação objetiva.
Regras OBRIGATÓRIAS (siga TODAS sem exceção):
1. MÍNIMO ABSOLUTO: 320 palavras. O roteiro DEVE ter entre 320 e 380 palavras. Roteiros curtos serão REJEITADOS.
2. Desenvolva CADA notícia em parágrafos separados: abertura, contexto, detalhes e desfecho. NUNCA resuma uma notícia em uma ou duas frases.
3. Use a marcação [pausa] entre blocos para respiração e ritmo.
4. Base apenas nas notícias fornecidas; não invente dados.
5. Otimizado para voz: evite siglas soletradas; evite números longos; preferir "mil" a "1.000".
6. Saída: APENAS o texto do roteiro, sem título, sem contagem de palavras. Comece direto com a abertura (ex.: "Bom dia, ouvintes.")."""
        user_head = "ATENÇÃO: O roteiro DEVE ter NO MÍNIMO 320 palavras (cerca de 2 minutos de leitura). Desenvolva cada notícia com contexto e detalhes em parágrafos separados. NÃO resuma. Use [pausa] entre blocos.\n\nNotícias:\n\n"
        max_tokens = 2000

    model = genai.GenerativeModel(
        "gemini-2.5-flash",
        system_instruction=system_instruction,
    )

    news_text = build_script_prompt(news)
    if long_form:
        user_prompt = user_head + news_text + "\n\nGere somente o texto do roteiro. Três matérias distintas, [pausa] entre cada uma, total 320–380 palavras."
    else:
        user_prompt = user_head + news_text + "\n\nGere somente o texto do roteiro. Lembre-se: mínimo 320 palavras, desenvolva cada notícia."

    best_script = ""
    best_words = 0

    for attempt in range(MAX_RETRIES + 1):
        temp = 0.6 + (attempt * 0.15)
        response = model.generate_content(
            user_prompt,
            generation_config={
                "temperature": min(temp, 1.0),
                "max_output_tokens": max_tokens,
            },
        )

        if not response.text:
            continue

        script = response.text.strip()
        wc = _count_words(script)

        if wc > best_words:
            best_script = script
            best_words = wc

        if wc >= MIN_WORDS:
            return script

        if long_form:
            user_prompt = (
                f"O roteiro anterior ficou com apenas {wc} palavras. É MUITO CURTO. "
                f"Reescreva com 3 MATÉRIAS DISTINTAS (uma para cada notícia), [pausa] entre cada uma. "
                f"Mínimo 320 palavras no total. Desenvolva cada notícia com contexto e desfecho.\n\n" + news_text +
                "\n\nGere somente o texto do roteiro. Três blocos, um por notícia."
            )
        else:
            user_prompt = (
                f"O roteiro anterior ficou com apenas {wc} palavras. É MUITO CURTO. "
                f"Reescreva o roteiro com NO MÍNIMO 350 palavras. Desenvolva CADA notícia "
                f"com mais contexto, detalhes e explicações. Use [pausa] entre blocos.\n\n" + news_text +
                "\n\nGere somente o texto do roteiro completo. MÍNIMO 350 palavras."
            )

    if not best_script:
        raise RuntimeError("Gemini não retornou texto para o roteiro.")

    return best_script


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
    gera roteiro ~2 min (long_form), persona locutor profissional. Para uso na admin.
    """
    news = fetch_news_louveira()
    if not news:
        raise RuntimeError("Nenhuma notícia encontrada no site de Louveira.")
    return generate_radio_script(news, long_form=True)


if __name__ == "__main__":
    script = run()
    print(script)
