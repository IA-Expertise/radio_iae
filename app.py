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
from urllib.parse import quote

from flask import Flask, jsonify, render_template, request, send_file

import google.generativeai as genai

from core.mixer import get_next_track, mix_voice_with_bed, normalize_audio
from core.news_agent import run as news_run
from core.voice_agent import run as voice_run

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
BLOCKS_DIR = OUTPUT_DIR / "blocks"
NEWS_FILE = OUTPUT_DIR / "news_latest.mp3"
DUCKED_FILE = OUTPUT_DIR / "ducked_latest.mp3"
MUSICAS_DIR = BASE_DIR / "assets" / "musicas"
VINHETAS_DIR = BASE_DIR / "assets" / "vinhetas"
NEWS_BED_PATH = VINHETAS_DIR / "news_bed.mp3"

# Mensagens de encerramento (alternadas a cada bloco)
CLOSING_MESSAGES = [
    "A Rádio IAE News é uma criação da IAExpertise Inteligência Artificial. Para saber mais, visite iaexpertise.com.br. [pausa] Vamos de música!",
    "A Rádio IAE News é totalmente criada e executada por Inteligência Artificial e a sua empresa também pode ter uma rádio personalizada no seu site. Fale com a IAExpertise.",
]
_closing_index = 0

# Fila de blocos de notícia prontos (nomes de arquivo)
ready_blocks: list[str] = []
_lock = threading.Lock()
_block_counter = 0
# Ciclo: 0 = notícia, 1 = música, 2 = música, depois volta a 0
_cycle_index = 0
# Mínimo de blocos para manter em background
MIN_BLOCKS = 1
TARGET_BLOCKS = 2
# Intervalo entre gerações (evita muitas chamadas à ElevenLabs)
GENERATOR_INTERVAL_SEC = 90


def _next_block_id() -> int:
    global _block_counter
    with _lock:
        _block_counter += 1
        return _block_counter


def _get_next_closing() -> str:
    """Retorna a próxima mensagem de encerramento (alternada)."""
    global _closing_index
    with _lock:
        msg = CLOSING_MESSAGES[_closing_index % len(CLOSING_MESSAGES)]
        _closing_index += 1
    return msg


def _generate_one_block() -> bool:
    """Gera um bloco (notícias + encerramento → voz, opcionalmente com bed) e adiciona à fila."""
    global ready_blocks
    try:
        script = news_run()
        closing = _get_next_closing()
        full_script = script.strip() + " [pausa] " + closing
        voice_run(full_script)
        if not NEWS_FILE.is_file():
            return False
        BLOCKS_DIR.mkdir(parents=True, exist_ok=True)
        name = f"block_{_next_block_id():06d}.mp3"
        dest = BLOCKS_DIR / name
        if NEWS_BED_PATH.is_file():
            mix_voice_with_bed(NEWS_FILE, NEWS_BED_PATH, dest)
        else:
            normalize_audio(NEWS_FILE, dest)
        with _lock:
            ready_blocks.append(name)
        return True
    except Exception:
        return False


def _background_generator():
    """Thread: mantém a fila com blocos prontos, com intervalo para não sobrecarregar a API."""
    while True:
        try:
            with _lock:
                n = len(ready_blocks)
            if n < TARGET_BLOCKS:
                _generate_one_block()
            time.sleep(GENERATOR_INTERVAL_SEC)
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


def _music_title(track_path: Path) -> str:
    """Nome da faixa para exibição (sem .mp3, limpo)."""
    name = track_path.stem
    if name.endswith(" (1)") or name.endswith(" (2)"):
        name = name.rsplit(" (", 1)[0].strip()
    return name or track_path.name


@app.route("/api/next")
def api_next():
    """
    Próximo item: notícia ou música. Query: mode=music_only para só músicas.
    Ciclo normal: notícia → música → música → notícia → ...
    """
    global _cycle_index
    music_only = request.args.get("mode") == "music_only"
    with _lock:
        if music_only:
            track = get_next_track()
            if track is None:
                return jsonify({"ready": False, "message": "Nenhuma música disponível."}), 503
            return jsonify({
                "ready": True,
                "url": "/audio/music/" + quote(track.name, safe=""),
                "type": "music",
                "title": _music_title(track),
            })
        if _cycle_index % 3 == 0:
            if not ready_blocks:
                return jsonify({"ready": False, "message": "Preparando primeiro bloco..."}), 503
            block_name = ready_blocks.pop(0)
            _cycle_index += 1
            return jsonify({
                "ready": True,
                "url": f"/audio/block/{block_name}",
                "type": "news",
                "title": "Notícias IA",
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
                    "title": "Notícias IA",
                })
            return jsonify({"ready": False, "message": "Nenhuma música e nenhum bloco disponível."}), 503
        return jsonify({
            "ready": True,
            "url": "/audio/music/" + quote(track.name, safe=""),
            "type": "music",
            "title": _music_title(track),
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
    """Serve uma música: primeiro assets/musicas, depois raiz do projeto."""
    if not _safe_music_filename(filename):
        return jsonify({"error": "invalid"}), 404
    path = MUSICAS_DIR / filename
    if not path.is_file():
        path = BASE_DIR / filename
    if not path.is_file():
        return jsonify({"error": "not found"}), 404
    return send_file(path, mimetype="audio/mpeg", as_attachment=False)


# ---------- Chat (humanos compartilhado; IA só quando solicitar) ----------

CHAT_MESSAGES: list[dict] = []
CHAT_MAX = 100

CHAT_AI_SYSTEM = """Você é a locutora da Rádio IAE News: jovem, descolada e antenada. Alguém pediu sua opinião no chat. Responda em 1 ou 2 frases curtas, tom amigável. Se perguntarem sobre a rádio ou IA, pode mencionar que a rádio é feita com IA pela IAExpertise."""


@app.route("/api/chat/messages")
def api_chat_messages():
    """Lista as últimas mensagens do chat (compartilhado entre ouvintes)."""
    with _lock:
        last = CHAT_MESSAGES[-50:] if len(CHAT_MESSAGES) > 50 else CHAT_MESSAGES
    return jsonify({"messages": last})


@app.route("/api/chat/send", methods=["POST"])
def api_chat_send():
    """Envia mensagem para o chat (entre humanos)."""
    try:
        data = request.get_json() or {}
        msg = (data.get("message") or "").strip()
        user = (data.get("user") or "Ouvinte").strip()[:30]
        if not msg:
            return jsonify({"ok": False, "error": "Mensagem vazia"}), 400
        if len(msg) > 300:
            msg = msg[:300]
        with _lock:
            CHAT_MESSAGES.append({"user": user or "Ouvinte", "text": msg, "kind": "human"})
            if len(CHAT_MESSAGES) > CHAT_MAX:
                CHAT_MESSAGES.pop(0)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/chat/ask-ai", methods=["POST"])
def api_chat_ask_ai():
    """Pergunta à IA (locutora) quando o usuário solicita. Resposta aparece no chat."""
    try:
        data = request.get_json() or {}
        msg = (data.get("message") or "").strip()
        if not msg:
            return jsonify({"ok": False, "error": "Mensagem vazia"}), 400
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            return jsonify({"ok": False, "error": "GEMINI_API_KEY não configurada"}), 500
        genai.configure(api_key=key)
        model = genai.GenerativeModel("gemini-2.5-flash", system_instruction=CHAT_AI_SYSTEM)
        response = model.generate_content(msg, generation_config={"temperature": 0.8, "max_output_tokens": 150})
        reply = (response.text or "").strip()
        with _lock:
            CHAT_MESSAGES.append({"user": "IA", "text": reply, "kind": "ai"})
            if len(CHAT_MESSAGES) > CHAT_MAX:
                CHAT_MESSAGES.pop(0)
        return jsonify({"ok": True, "reply": reply})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


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
