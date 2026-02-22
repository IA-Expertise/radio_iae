"""
Rádio IA News - Interface web
Programação contínua: notícia → música → música → notícia.
Blocos de notícia gerados toda segunda-feira em lote (RSS + dicas → voz → disco);
a rádio usa esses blocos durante a semana, minimizando uso de APIs (Gemini + ElevenLabs).
"""

import os
import random
import re
import shutil
import threading
import time
from datetime import datetime, timezone
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

# Dicas de IA (alternam com as notícias na programação)
DICA_INTROS = [
    "Você sabia? [pausa] ",
    "Dica de IA: [pausa] ",
    "Olha só: [pausa] ",
]
DICA_TIPS = [
    "A ferramenta Nano Banana do Google permite que você crie imagens incríveis e realistas a partir da sua foto.",
    "A BitDance acaba de lançar o Seedance2, uma IA incrível onde você pode gerar cenas de vídeo com qualidade cinematográfica.",
    "A ferramenta Imagen do Google permite criar imagens realistas a partir de uma descrição em texto.",
    "O ChatGPT da OpenAI pode ajudar a resumir documentos longos em segundos.",
    "Ferramentas como Midjourney e DALL-E transformam ideias em arte digital com poucas palavras.",
    "Assistentes de voz com IA já conseguem agendar compromissos e responder e-mails sozinhos.",
    "Você pode usar IA para gerar legendas e traduções automáticas em vídeos.",
    "Ferramentas de IA ajudam programadores a escrever código mais rápido e com menos erros.",
]

# Fila de blocos de notícia prontos (nomes de arquivo)
ready_blocks: list[str] = []
_lock = threading.Lock()
_block_counter = 0
# Ciclo: 0 = notícia, 1 = música, 2 = música, depois volta a 0
_cycle_index = 0

# Atualização semanal: toda segunda gera um lote e usa durante a semana (minimiza APIs)
LAST_WEEKLY_FILE = OUTPUT_DIR / "last_weekly_generation.txt"
BLOCKS_PER_WEEK = 15
WEEKLY_CHECK_INTERVAL_SEC = 6 * 3600  # verificar a cada 6h se é segunda e precisa gerar
DELAY_BETWEEN_BLOCKS_SEC = 3  # intervalo entre blocos no lote (evita rate limit)


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
    """Gera um bloco: notícias OU dica de IA (aleatório), + encerramento → voz, opcionalmente com bed."""
    global ready_blocks
    try:
        use_dica = random.random() < 0.35
        if use_dica:
            intro = random.choice(DICA_INTROS)
            tip = random.choice(DICA_TIPS)
            script = intro + tip
        else:
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


def _load_blocks_from_disk() -> None:
    """Carrega a lista de blocos já gravados em output/blocks/ para ready_blocks."""
    global ready_blocks, _block_counter
    if not BLOCKS_DIR.is_dir():
        return
    names = sorted(f.name for f in BLOCKS_DIR.glob("block_*.mp3") if _safe_block_filename(f.name))
    with _lock:
        ready_blocks.clear()
        ready_blocks.extend(names)
        # Atualiza contador para o próximo ID (evita sobrescrever arquivos)
        for n in names:
            try:
                num = int(n.replace("block_", "").replace(".mp3", ""))
                _block_counter = max(_block_counter, num)
            except ValueError:
                pass


def _should_run_weekly_generation() -> bool:
    """True se for segunda e (nunca gerou ou última geração foi há 6+ dias)."""
    now = datetime.now(timezone.utc)
    if now.weekday() != 0:
        return False
    if not LAST_WEEKLY_FILE.is_file():
        return True
    try:
        with open(LAST_WEEKLY_FILE) as f:
            s = f.read().strip()
        last = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return (now - last).days >= 6
    except Exception:
        return True


def _run_weekly_batch() -> None:
    """Gera um lote de blocos (notícias/dicas), grava em output/blocks/ e atualiza last_weekly."""
    global ready_blocks, _block_counter
    BLOCKS_DIR.mkdir(parents=True, exist_ok=True)
    with _lock:
        ready_blocks.clear()
        _block_counter = 0
    for f in BLOCKS_DIR.glob("block_*.mp3"):
        try:
            f.unlink()
        except Exception:
            pass
    for _ in range(BLOCKS_PER_WEEK):
        _generate_one_block()
        time.sleep(DELAY_BETWEEN_BLOCKS_SEC)
    now = datetime.now(timezone.utc)
    LAST_WEEKLY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LAST_WEEKLY_FILE, "w") as f:
        f.write(now.strftime("%Y-%m-%dT%H:%M:%SZ"))


def _weekly_generator_thread():
    """
    Toda segunda-feira gera um lote de blocos (notícias/dicas), grava em output/blocks/
    e usa esses blocos durante a semana. Minimiza uso de Gemini + ElevenLabs.
    """
    global ready_blocks, _block_counter
    while True:
        try:
            need = _should_run_weekly_generation()
            if not need:
                # Primeira execução sem blocos: gera um lote para não ficar sem conteúdo
                with _lock:
                    n = len(ready_blocks)
                if n == 0:
                    need = True
            if need:
                _run_weekly_batch()
            time.sleep(WEEKLY_CHECK_INTERVAL_SEC)
        except Exception:
            time.sleep(3600)


def _safe_block_filename(name: str) -> bool:
    """Aceita só nomes como block_000001.mp3."""
    return bool(re.match(r"^block_\d{6}\.mp3$", name))


def _safe_music_filename(name: str) -> bool:
    """Aceita só basename sem path (ex: musica.mp3)."""
    return "/" not in name and "\\" not in name and name.endswith(".mp3")


# ---------- Geração semanal (manual ou automática) ----------

def _check_admin_secret() -> bool:
    """True se a requisição traz o ADMIN_SECRET (body ou header X-Admin-Key)."""
    secret_env = os.getenv("ADMIN_SECRET", "").strip()
    if not secret_env:
        return False
    data = request.get_json(silent=True) or {}
    secret = data.get("secret") or request.headers.get("X-Admin-Key") or ""
    return secret == secret_env


@app.route("/admin")
def admin_page():
    """Só quem acessar com ?key=ADMIN_SECRET vê o botão de gerar. Salve esse link nos favoritos do celular."""
    key = request.args.get("key", "")
    if key != os.getenv("ADMIN_SECRET", "").strip():
        return "Não encontrado.", 404
    return render_template("admin.html")


@app.route("/api/gerar-semana", methods=["POST"])
def api_gerar_semana():
    """
    Gera o lote semanal (15 blocos). Exige secret (só quem vem da página /admin?key=... envia).
    """
    if not _check_admin_secret():
        return jsonify({"ok": False, "error": "Acesso negado."}), 403
    def _run():
        try:
            _run_weekly_batch()
        except Exception:
            pass

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return jsonify({
        "ok": True,
        "message": "Geração da semana iniciada em background. Em alguns minutos os blocos estarão disponíveis. Atualize o status.",
    })


# ---------- Rotas da programação contínua ----------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    """Retorna se há blocos prontos (blocos da semana, gerados toda segunda)."""
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


def _chat_moderation(text: str) -> bool:
    """Retorna True se a mensagem for adequada; False se tiver xingamentos/besteiras."""
    bad = (
        "caralho", "porra", "merda", "puta", "vagabund", "fodase", "foda-se", "vai tomar",
        "cu ", " cu", "cus", "buceta", "bct", "piroca", "rola", "arrombad", "viado", "viad",
        "idiota", "imbecil", "estupido", "estúpido", "burro", "otario", "otário",
        "morre", "matar", "morte a", "ódio", "odeio",
    )
    t = text.lower().replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
    for w in bad:
        if w in t:
            return False
    return True


@app.route("/api/chat/send", methods=["POST"])
def api_chat_send():
    """Envia mensagem para o chat (entre humanos). Moderação: bloqueia xingamentos."""
    try:
        data = request.get_json() or {}
        msg = (data.get("message") or "").strip()
        user = (data.get("user") or "Ouvinte").strip()[:30]
        if not msg:
            return jsonify({"ok": False, "error": "Mensagem vazia"}), 400
        if not _chat_moderation(msg):
            return jsonify({"ok": False, "error": "Mensagem contém termos inadequados. Seja respeitoso."}), 400
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
    _load_blocks_from_disk()
    t = threading.Thread(target=_weekly_generator_thread, daemon=True)
    t.start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
