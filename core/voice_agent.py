"""
Voice Agent - Rádio IA
Transforma o roteiro em áudio usando ElevenLabs e salva em output/news_latest.mp3.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs

# Modelo e voz conforme instruções
MODEL_ID = "eleven_multilingual_v2"
# Rachel: voz estável (alternativa: Brian)
DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"
OUTPUT_FILE = OUTPUT_DIR / "news_latest.mp3"

# Client reutilizado para evitar muitas requisições GET (voices/models) a cada bloco
_client: ElevenLabs | None = None


def _get_client() -> ElevenLabs:
    """Retorna o client ElevenLabs (criado uma vez e reutilizado)."""
    global _client
    if _client is None:
        load_dotenv()
        key = os.getenv("ELEVENLABS_API_KEY")
        if not key:
            raise ValueError(
                "ELEVENLABS_API_KEY não encontrada. Defina no arquivo .env na raiz do projeto."
            )
        _client = ElevenLabs(api_key=key)
    return _client


def _get_api_key() -> str:
    """Carrega e retorna a ELEVENLABS_API_KEY do arquivo .env."""
    load_dotenv()
    key = os.getenv("ELEVENLABS_API_KEY")
    if not key:
        raise ValueError(
            "ELEVENLABS_API_KEY não encontrada. Defina no arquivo .env na raiz do projeto."
        )
    return key


def _text_for_tts(script: str) -> str:
    """Prepara o roteiro para TTS: [pausa] vira pausa natural na fala."""
    return script.replace("[pausa]", " ... ").strip()


def generate_audio(script: str, voice_id: str | None = None) -> Path:
    """
    Gera áudio do roteiro via ElevenLabs e salva em output/news_latest.mp3.
    Retorna o path do arquivo gerado.
    """
    client = _get_client()
    voice_id = voice_id or os.getenv("ELEVENLABS_VOICE_ID") or DEFAULT_VOICE_ID
    text = _text_for_tts(script)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    audio = client.text_to_speech.convert(
        voice_id=voice_id,
        text=text,
        model_id=MODEL_ID,
        output_format="mp3_44100_128",
    )

    # SDK pode retornar bytes ou generator de chunks
    data = b""
    if hasattr(audio, "read"):
        data = audio.read()
    elif isinstance(audio, bytes):
        data = audio
    else:
        for chunk in audio:
            if isinstance(chunk, bytes):
                data += chunk
            else:
                data += getattr(chunk, "content", chunk) or b""

    OUTPUT_FILE.write_bytes(data)
    return OUTPUT_FILE


def run(script: str) -> Path:
    """
    Fluxo principal: gera áudio do roteiro e retorna o path do MP3.
    """
    return generate_audio(script)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(OUTPUT_DIR.parent))
    from core.news_agent import run as news_run

    script = news_run()
    path = run(script)
    print(f"Áudio salvo em: {path}")
