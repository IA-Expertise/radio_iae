"""
Rádio IA News - Interface web
Programação contínua: notícia → música → música → notícia.
Blocos de notícia gerados em background; usuário aperta Play e ouve a rádio.
"""

import os
import re
import shutil
import threading
import time
from pathlib import Path

from flask import Flask, jsonify, render_template, send_file

from core.mixer import get_next_track
from core.news_agent import run as news_run
from core.voice_agent import run as voice_run

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
BLOCKS_DIR = OUTPUT_DIR / "blocks"
NEWS_FILE = OUTPUT_DIR / "news_latest.mp3"
DUCKED_FILE = OUTPUT_DIR / "ducked_latest.mp3"
MUSICAS_DIR = BASE_DIR / "assets" / "musicas"

# Fila de blocos de notícia prontos (nomes de arquivo)
ready_blocks: list[str] = []
_lock = threading.Lock()
_block_counter = 0
# Ciclo: 0 = notícia, 1 = música, 2 = música, depois volta a 0
_cycle_index = 0
# Mínimo de blocos para manter em background
MIN_BLOCKS = 2
TARGET_BLOCKS = 3


def _next_block_id() -> int:
    global _block_counter
    with _lock:
        _block_counter += 1
        return _block_counter


def _generate_one_block() -> bool:
    """Gera um bloco (notícias → voz) e adiciona à fila. Retorna True se ok."""
    global ready_blocks
    try:
        script = news_run()
        voice_run(script)
        if not NEWS_FILE.is_file():
            return False
        BLOCKS_DIR.mkdir(parents=True, exist_ok=True)
        name = f"block_{_next_block_id():06d}.mp3"
        dest = BLOCKS_DIR / name
        shutil.copy2(NEWS_FILE, dest)
        with _lock:
            ready_blocks.append(name)
        return True
    except Exception:
        return False


def _background_generator():
    """Thread: mantém a fila com TARGET_BLOCKS blocos prontos."""
    while True:
        try:
            with _lock:
                n = len(ready_blocks)
            if n < MIN_BLOCKS:
                _generate_one_block()
            time.sleep(2)
            with _lock:
                n = len(ready_blocks)
            if n < TARGET_BLOCKS:
                _generate_one_block()
            time.sleep(30)
        except Exception:
            time.sleep(60)


def _safe_block_filename(name: str) -> bool:
    """Aceita só nomes como block_000001.mp3."""
    return bool(re.match(r"^block_\d{6}\.mp3$", name))


def _safe_music_filename(name: str) -> bool:
    """Aceita só basename sem path (ex: musica.mp3)."""
    return "/" not in name and "\\" not in name and name.endswith(".mp3")


# ---------- Rotas da programação contínua ----------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    """Retorna se há blocos prontos para iniciar a programação."""
    with _lock:
        n = len(ready_blocks)
    return jsonify({
        "blocksReady": n,
        "canPlay": n > 0,
    })


@app.route("/api/next")
def api_next():
    """
    Próximo item da programação: notícia ou música.
    Ciclo: notícia → música → música → notícia → ...
    """
    global _cycle_index
    with _lock:
        if _cycle_index % 3 == 0:
            if not ready_blocks:
                return jsonify({"ready": False, "message": "Preparando primeiro bloco..."}), 503
            block_name = ready_blocks.pop(0)
            _cycle_index += 1
            return jsonify({
                "ready": True,
                "url": f"/audio/block/{block_name}",
                "type": "news",
            })
        track = get_next_track()
        _cycle_index += 1
        if track is None:
            if ready_blocks:
                block_name = ready_blocks.pop(0)
                return jsonify({
                    "ready": True,
                    "url": f"/audio/block/{block_name}",
                    "type": "news",
                })
            return jsonify({"ready": False, "message": "Nenhuma música em assets/musicas e nenhum bloco disponível."}), 503
        return jsonify({
            "ready": True,
            "url": f"/audio/music/{track.name}",
            "type": "music",
        })


@app.route("/audio/block/<filename>")
def audio_block(filename):
    """Serve um bloco de notícia."""
    if not _safe_block_filename(filename):
        return jsonify({"error": "invalid"}), 404
    path = BLOCKS_DIR / filename
    if not path.is_file():
        return jsonify({"error": "not found"}), 404
    return send_file(path, mimetype="audio/mpeg", as_attachment=False)


@app.route("/audio/music/<filename>")
def audio_music(filename):
    """Serve uma música de assets/musicas."""
    if not _safe_music_filename(filename):
        return jsonify({"error": "invalid"}), 404
    path = MUSICAS_DIR / filename
    if not path.is_file():
        return jsonify({"error": "not found"}), 404
    return send_file(path, mimetype="audio/mpeg", as_attachment=False)


# ---------- Rotas legadas (gerar sob demanda e ouvir último) ----------

@app.route("/audio/news")
def audio_news():
    if not NEWS_FILE.is_file():
        return jsonify({"error": "Nenhum boletim gerado ainda"}), 404
    return send_file(NEWS_FILE, mimetype="audio/mpeg", as_attachment=False)


@app.route("/api/gerar", methods=["POST"])
def api_gerar():
    try:
        script = news_run()
        voice_run(script)
        return jsonify({"ok": True, "message": "Boletim gerado."})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/gerar-duck", methods=["POST"])
def api_gerar_duck():
    from core.mixer import create_ducked_mix
    try:
        script = news_run()
        voice_run(script)
        if not NEWS_FILE.is_file():
            return jsonify({"ok": False, "error": "Áudio não gerado"}), 500
        track = get_next_track()
        if track is None:
            return jsonify({"ok": True, "message": "Boletim gerado (sem músicas)."})
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        create_ducked_mix(track, NEWS_FILE, DUCKED_FILE)
        return jsonify({"ok": True, "message": "Boletim e mix com ducking gerados."})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/audio/ducked")
def audio_ducked():
    if not DUCKED_FILE.is_file():
        return jsonify({"error": "Nenhum mix gerado ainda"}), 404
    return send_file(DUCKED_FILE, mimetype="audio/mpeg", as_attachment=False)


def main():
    BLOCKS_DIR.mkdir(parents=True, exist_ok=True)
    t = threading.Thread(target=_background_generator, daemon=True)
    t.start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
