"""
Mixer (Sonoplasta) - Rádio IA
Escolhe faixas da playlist sem repetir nas últimas 10 e aplica ducking (música -20dB durante a voz).
"""

import random
from pathlib import Path

from pydub import AudioSegment

# Caminho da pasta de músicas (32 MP3s)
MUSICAS_DIR = Path(__file__).resolve().parent.parent / "assets" / "musicas"
# Quantas rodadas não repetir a mesma faixa
HISTORY_SIZE = 10
# Redução de volume da música quando a voz entra (dB)
DUCK_DB = -20

# Histórico das últimas faixas tocadas (paths)
_track_history: list[str] = []


def _get_music_files() -> list[Path]:
    """Lista todos os MP3 em assets/musicas/."""
    if not MUSICAS_DIR.is_dir():
        return []
    return sorted(MUSICAS_DIR.glob("*.mp3"), key=lambda p: p.name)


def get_next_track() -> Path | None:
    """
    Escolhe aleatoriamente uma das 32 músicas sem repetir a mesma nas últimas 10 rodadas.
    Retorna None se não houver músicas ou pasta inexistente.
    """
    global _track_history
    files = _get_music_files()
    if not files:
        return None

    # Paths como string para comparar no histórico
    allowed = [f for f in files if str(f.resolve()) not in _track_history]
    if not allowed:
        allowed = files
        _track_history.clear()

    chosen = random.choice(allowed)
    _track_history.append(str(chosen.resolve()))
    if len(_track_history) > HISTORY_SIZE:
        _track_history.pop(0)
    return chosen


def create_ducked_mix(
    music_path: Path,
    voice_path: Path,
    output_path: Path | None = None,
) -> AudioSegment:
    """
    Cria um mix com ducking: a trilha musical baixa -20dB quando a voz entra
    e volta ao volume normal quando a voz termina.
    Retorna o segmento misturado (AudioSegment).
    Se output_path for passado, salva o MP3 lá.
    """
    music = AudioSegment.from_file(music_path)
    voice = AudioSegment.from_file(voice_path)
    voice_len_ms = len(voice)

    # Parte 1: do início até o fim da voz = música em -20dB + voz por cima
    music_during_voice = music[:voice_len_ms].apply_gain(DUCK_DB)
    part1 = music_during_voice.overlay(voice)

    # Parte 2: resto da música em volume normal
    part2 = music[voice_len_ms:]

    mixed = part1 + part2
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        mixed.export(output_path, format="mp3")
    return mixed


def get_duck_db() -> int:
    """Retorna o valor de ducking em dB (negativo)."""
    return DUCK_DB
