"""
Mixer (Sonoplasta) - Rádio IA
Escolhe faixas da playlist sem repetir nas últimas 10 e aplica ducking (música -20dB durante a voz).
"""

import random
from pathlib import Path

from pydub import AudioSegment

# Caminho da pasta de músicas
BASE_DIR = Path(__file__).resolve().parent.parent
MUSICAS_DIR = BASE_DIR / "assets" / "musicas"
# Quantas rodadas não repetir a mesma faixa
HISTORY_SIZE = 10
# Redução de volume da música quando a voz entra (dB)
DUCK_DB = -20

# Histórico das últimas faixas tocadas (paths)
_track_history: list[str] = []


def _get_music_files() -> list[Path]:
    """Lista todos os MP3 em assets/musicas/; se vazio, usa a raiz do projeto."""
    files: list[Path] = []
    if MUSICAS_DIR.is_dir():
        files = sorted(MUSICAS_DIR.glob("*.mp3"), key=lambda p: p.name)
    if not files:
        files = sorted(BASE_DIR.glob("*.mp3"), key=lambda p: p.name)
    return files


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


def normalize_audio(path: Path, output_path: Path, target_dBFS: float = -2.0) -> None:
    """Normaliza o áudio para target_dBFS e salva em output_path (equaliza volume)."""
    seg = AudioSegment.from_file(path)
    try:
        diff = target_dBFS - seg.dBFS
        seg = seg.apply_gain(min(max(diff, -12), 12))
    except Exception:
        pass
    output_path.parent.mkdir(parents=True, exist_ok=True)
    seg.export(output_path, format="mp3")


VINHETAS_DIR = BASE_DIR / "assets" / "vinhetas"
NEWS_BED_FILE = VINHETAS_DIR / "news_bed.mp3"
# Volume do fundo sob a locução (dB) – um pouco mais alto que antes
BED_DB = -25
# Intro: bed em volume quase normal (ms e dB), depois abaixa para a locução entrar
INTRO_SECONDS = 2.5
INTRO_BED_DB = -6


def mix_voice_with_bed(
    voice_path: Path,
    bed_path: Path,
    output_path: Path,
    bed_db: int = BED_DB,
    intro_seconds: float = INTRO_SECONDS,
    intro_bed_db: int = INTRO_BED_DB,
) -> AudioSegment:
    """
    Intro: bed sozinho em volume mais alto (intro_seconds).
    Depois: bed abaixa (bed_db) e a locução entra por cima até o fim.
    O bed é repetido se for mais curto que o total. Salva em output_path.
    """
    voice = AudioSegment.from_file(voice_path)
    bed_raw = AudioSegment.from_file(bed_path)
    voice_len_ms = len(voice)
    # Deixar a voz em nível estável (evita queda ao longo da narração)
    try:
        voice_diff = -3.0 - voice.dBFS
        voice = voice.apply_gain(min(voice_diff, 10))
    except Exception:
        pass
    intro_ms = int(intro_seconds * 1000)
    total_ms = voice_len_ms
    bed_len_ms = len(bed_raw)
    if bed_len_ms < total_ms:
        repeat = (total_ms // bed_len_ms) + 1
        bed_raw = bed_raw * repeat
    bed_raw = bed_raw[:total_ms]

    part1 = bed_raw[:intro_ms].apply_gain(intro_bed_db)
    bed_rest = bed_raw[intro_ms:voice_len_ms].apply_gain(bed_db)
    voice_rest = voice[intro_ms:]
    part2 = bed_rest.overlay(voice_rest)
    mixed = part1 + part2
    # Normalizar para volume estável (evita queda ao longo da narração e equaliza)
    TARGET_DBFS = -2.0
    try:
        diff = TARGET_DBFS - mixed.dBFS
        mixed = mixed.apply_gain(min(diff, 12))
    except Exception:
        pass
    output_path.parent.mkdir(parents=True, exist_ok=True)
    mixed.export(output_path, format="mp3")
    return mixed
