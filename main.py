"""
Rádio IA News - Loop principal (Orquestrador)
Fluxo: Música 1 → Música 2 → Notícias + Voz → Música 3 com Ducking (locutor) → Repetir.
"""

import time
from pathlib import Path

import pygame

from core.mixer import create_ducked_mix, get_next_track
from core.news_agent import run as news_run
from core.voice_agent import run as voice_run

# Pasta de saída para áudio da locução e mix com ducking
OUTPUT_DIR = Path(__file__).resolve().parent / "output"
DUCKED_FILE = OUTPUT_DIR / "ducked_latest.mp3"


def _play_audio(path: Path, block: bool = True) -> None:
    """Toca um arquivo de áudio (MP3) e, se block=True, espera terminar."""
    if not path.is_file():
        return
    pygame.mixer.music.load(str(path))
    pygame.mixer.music.play()
    if block:
        while pygame.mixer.music.get_busy():
            time.sleep(0.1)


def _play_music_track() -> bool:
    """Toca a próxima faixa da playlist. Retorna True se tocou, False se não houver músicas."""
    track = get_next_track()
    if track is None:
        return False
    _play_audio(track)
    return True


def _play_news_with_ducking() -> bool:
    """
    Toca a Música 3 com ducking: locutor fala sobre a introdução da música.
    Usa output/news_latest.mp3 como voz e a próxima faixa como trilha.
    Retorna True se tocou, False se faltar música ou voz.
    """
    voice_path = OUTPUT_DIR / "news_latest.mp3"
    if not voice_path.is_file():
        return False
    track = get_next_track()
    if track is None:
        _play_audio(voice_path)
        return True
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    create_ducked_mix(track, voice_path, DUCKED_FILE)
    _play_audio(DUCKED_FILE)
    return True


def run_cycle() -> None:
    """Executa um ciclo completo do fluxo da rádio."""
    # 1. Tocar Música 1
    _play_music_track()
    # 2. Tocar Música 2
    _play_music_track()
    # 3. Atualizar notícias e gerar áudio da locução
    script = news_run()
    voice_run(script)
    # 4. Tocar Música 3 com Ducking (locutor na introdução)
    _play_news_with_ducking()


def main() -> None:
    pygame.mixer.init()
    try:
        while True:
            run_cycle()
    except KeyboardInterrupt:
        print("\nRádio IA encerrada.")
    finally:
        pygame.mixer.quit()


if __name__ == "__main__":
    main()
