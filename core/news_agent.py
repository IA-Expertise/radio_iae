"""
News Agent - Rádio IA
Busca notícias de IA no RSS do Google News e gera roteiro de rádio via Gemini.
"""

import os
import re
from dotenv import load_dotenv
import feedparser
import google.generativeai as genai

# URL do RSS Google News – busca "dicas de IA" (pt-BR)
# Equivalente a: https://news.google.com/search?q=dicas+de+IA&hl=pt-BR&gl=BR&ceid=BR:pt-419
GOOGLE_NEWS_IA_RSS = (
    "https://news.google.com/rss/search?q=dicas+de+IA"
    "&hl=pt-BR&gl=BR&ceid=BR:pt-419"
)

# Quantidade de notícias para o roteiro
TOP_N = 3


def _get_api_key() -> str:
    """Carrega e retorna a GEMINI_API_KEY do arquivo .env."""
    load_dotenv()
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise ValueError(
            "GEMINI_API_KEY não encontrada. Defina no arquivo .env na raiz do projeto."
        )
    return key


def fetch_news() -> list[dict]:
    """
    Busca as notícias de IA no RSS do Google News.
    Retorna lista de entradas com 'title' e 'summary' (ou 'description').
    """
    feed = feedparser.parse(GOOGLE_NEWS_IA_RSS)
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
    Usa o Gemini para transformar as notícias em roteiro de rádio de 1 minuto.
    Persona: jornalista de rádio tech brasileiro, tom dinâmico, frases curtas,
    marcações [pausa] e texto otimizado para leitura na ElevenLabs.
    """
    api_key = _get_api_key()
    genai.configure(api_key=api_key)

    system_instruction = """Você é a locutora da Rádio IAE News: jovem, descolada e antenada em tech. Tom informal mas confiável, como uma amiga que entende do assunto.
Regras para o roteiro:
- Linguagem jovem: pode usar expressões como "galera", "olha só", "fechou?", "bombando", "tá ligado?" com moderação. Frases curtas e diretas.
- Use a marcação [pausa] entre blocos para respiração e ritmo.
- Duração: aproximadamente 1 minuto de leitura (200 a 250 palavras). NOTÍCIA COMPLETA: desenvolva cada ponto, contexto e desfecho.
- Base apenas nas 3 notícias fornecidas; não invente dados.
- Otimizado para voz (ElevenLabs): evite siglas soletradas; evite números longos.
- Saída: só o texto do roteiro, sem título. Comece direto com a abertura (ex.: "Oi, pessoal!", "E aí, galera!")."""

    model = genai.GenerativeModel(
        "gemini-2.5-flash",
        system_instruction=system_instruction,
    )

    news_text = build_script_prompt(news)
    user_prompt = f"""Com base nas notícias abaixo, escreva um roteiro de rádio COMPLETO, tom jovem e descolado, até 1 min de leitura. Desenvolva cada notícia. Use [pausa] onde fizer sentido.

{news_text}

Gere somente o texto do roteiro."""

    response = model.generate_content(
        user_prompt,
        generation_config={
            "temperature": 0.7,
            "max_output_tokens": 1500,
        },
    )

    if not response.text:
        raise RuntimeError("Gemini não retornou texto para o roteiro.")

    return response.text.strip()


def run() -> str:
    """
    Fluxo principal: busca notícias, gera roteiro e retorna o texto.
    """
    news = fetch_news()
    if not news:
        raise RuntimeError("Nenhuma notícia encontrada no RSS.")
    return generate_radio_script(news)


if __name__ == "__main__":
    script = run()
    print(script)
