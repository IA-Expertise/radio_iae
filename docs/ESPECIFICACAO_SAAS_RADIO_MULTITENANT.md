# Especificação: SaaS de Rádio Automatizada (Multi-tenant)

**Documento de referência**  
Baseado na atualização do projeto **Rádio IAE News** e destinado à criação do novo produto SaaS voltado a **rádios comunitárias** e **rádios indoor corporativas**.

---

## 1. Resumo da atualização do projeto atual (Rádio IAE News)

### 1.1 Objetivo do produto atual
- Rádio web automatizada que alterna **blocos de notícias/dicas** (voz sintética + opcional bed) com **músicas**.
- Público: demonstração e uso interno (IAExpertise).
- Interface: player para ouvintes, chat entre ouvintes, admin protegida por chave.

### 1.2 Funcionalidades implementadas

| Módulo | Função | Detalhe |
|--------|--------|--------|
| **Agente de notícias** | Fontes de conteúdo | RSS (Google News), scraping de site de prefeitura (Louveira). |
| **Roteirização** | Geração de texto | Gemini: roteiro ~2 min, 3 notícias distintas, persona locutor profissional, marcações `[pausa]`. |
| **Voz** | Texto → áudio | ElevenLabs (multilingual_v2), tratamento de `[pausa]`. |
| **Mixer** | Playlist e áudio | Ciclo notícia → música → música; mix voz + bed; normalização por segmentos; **normalização LUFS -23 LUFS + 7 dB (-16 LUFS)**; ducking (música -20 dB durante a voz). |
| **Programação** | Fila de blocos | Blocos em `output/blocks/`; ciclo fixo; modo “só músicas”. |
| **Atualização semanal** | Geração em lote | Toda segunda (ou manual via admin): 15 blocos (notícias + dicas), grava em disco, uso durante a semana (minimiza APIs). |
| **Admin** | Gestão restrita | Página `/admin?key=...`: Gerar blocos da semana; **Boletim Louveira**: gerar roteiro (scraping + Gemini) → exibir em textarea → gerar áudio → colocar na fila (opção “substituir fila”); player para ouvir último boletim; opção “Substituir fila por este boletim”. |
| **Ouvinte** | Player e chat | Play/Parar, modo só músicas, volume diferenciado (notícia 0,72 / música 1,0), chat compartilhado com moderação básica. |

### 1.3 Stack técnico atual
- **Backend:** Flask (Python).
- **Notícias:** feedparser, requests, BeautifulSoup4, google-generativeai.
- **Voz:** elevenlabs.
- **Áudio:** pydub, pyloudnorm, numpy.
- **Persistência:** arquivos (MP3 em `output/blocks/`), arquivo de data da última geração semanal.
- **Frontend:** HTML/CSS/JS (templates Flask), player `<audio>`, chamadas fetch às APIs.

### 1.4 Fluxos de áudio
1. **Boletim único (admin Louveira):** Scraping → 3 notícias → Gemini (3 matérias, ~2 min) → exibe roteiro → usuário pode editar → “Gerar áudio” → ElevenLabs → mix com bed (se houver) → normalização LUFS → grava em `output/blocks/` → adiciona ao início da fila ou substitui a fila.
2. **Lote semanal:** Job (segunda ou manual): N blocos (notícias RSS/dicas + encerramento) → voz → mix/normalize → grava em `output/blocks/`; rádio consome a fila carregada do disco.
3. **Reprodução:** Ciclo notícia → música → música; próximo bloco ou música conforme a fila e a playlist.

---

## 2. Visão do novo SaaS (multi-tenant)

### 2.1 Público-alvo
- **Rádios comunitárias:** programação automática com notícias locais (prefeitura, região), vinhetas, músicas licenciadas ou de acervo próprio.
- **Rádios indoor corporativas:** ambiente empresarial, comunicados, avisos, música de fundo, boletins institucionais ou notícias filtradas.

### 2.2 Premissas do multi-tenant
- Cada **tenant** = uma rádio (comunitária ou corporativa).
- Dados e mídia **isolados por tenant** (tenant_id em todas as entidades e no storage).
- Um único deploy da aplicação atende N rádios; configuração e limites por plano/tenant.
- Autenticação e autorização por tenant (admin da rádio, operador, etc.).

### 2.3 Objetivos do produto SaaS
- Permitir que cada rádio tenha: **fontes de notícias** (RSS, scraping de site), **roteiros editáveis**, **geração de áudio sob demanda ou agendada**, **playlist de músicas/vinhetas**, **programação automática** (ex.: boletim → música → música).
- Oferecer **admin por rádio**: roteiros, boletins gravados, fila de programação, configuração de voz e de loudness (ex.: -23 LUFS + 7 dB).
- **Escalabilidade e custo controlado:** geração em lote agendada (ex.: semanal), cache de áudio, limites de uso de API (Gemini/ElevenLabs) por tenant/plano.

---

## 3. Modelo de dados sugerido (multi-tenant)

### 3.1 Entidades principais

```
Tenant (rádio)
├── id, nome, slug, plano (free/pro/empresa), ativo
├── config: timezone, ciclo_programacao (ex.: noticia-musica-musica), LUFS_target, extra_db
├── api_keys: gemini, elevenlabs (ou uso de chaves globais do SaaS com cota por tenant)
└── created_at, updated_at

Usuario
├── id, tenant_id, email, senha_hash, nome, role (owner/admin/operador)
└── created_at, updated_at

FonteNoticia
├── id, tenant_id, tipo (rss | scraping), nome
├── config: url (RSS ou página), se scraping: seletores/regras
├── ativo, ultima_sincronizacao
└── created_at, updated_at

Roteiro
├── id, tenant_id, titulo, texto (editável), origem (fonte_id ou manual)
├── status (rascunho | aprovado | gravado), palavras_aprox
├── created_at, updated_at
└── (opcional) noticias_fonte: JSON com títulos/links usados

Bloco (áudio gerado)
├── id, tenant_id, roteiro_id (opcional), arquivo_path (relativo ao storage do tenant)
├── duracao_seg, lufs_medido (opcional), tipo (boletim | vinheta | dica)
├── created_at
└── usado na ProgramacaoFila ou equivalente

ProgramacaoFila
├── id, tenant_id, ordem, bloco_id ou musica_id (referência)
├── tipo (bloco | musica), data_entrada
└── (permite “substituir fila” = limpar e inserir novo boletim)

PlaylistMusicas
├── id, tenant_id, nome (ex.: “Padrão”), arquivo_path (por faixa)
├── ativo, ordem
└── (ou tabela Musica com tenant_id + playlist_id)

AgendamentoGeracao
├── id, tenant_id, tipo (lote_semanal | diario | sob_demanda)
├── cron_ou_horario, quantidade_blocos, fontes_ids
└── ativo
```

### 3.2 Storage por tenant
- **Arquivos de áudio:** `storage/tenants/{tenant_id}/blocks/`, `.../musicas/`, `.../vinhetas/`.
- **Evitar** misturar arquivos de tenants no mesmo diretório; uso de tenant_id no path ou em bucket (ex.: S3) com prefixo `tenants/{tenant_id}/`.

### 3.3 Isolamento e limites
- Todas as queries filtradas por `tenant_id` (e, se houver, por `organization_id`).
- Limites por plano: número de blocos gerados/mês, minutos de áudio ElevenLabs, fontes de notícia ativas, usuários, etc.
- Cota de APIs: contador por tenant (ex.: gemini_requests_mes, elevenlabs_chars_mes) e checagem antes de gerar.

---

## 4. Arquitetura sugerida do SaaS

### 4.1 Camadas
- **API (Backend):** FastAPI ou Flask com blueprints por domínio (tenants, roteiros, blocos, programação, player).
- **Autenticação:** JWT ou sessão; middleware que resolve `tenant_id` a partir do usuário ou do subdomínio/slug (ex.: `radio-x.saasradio.com` → tenant “radio-x”).
- **Serviços (core):** Reutilizar e adaptar módulos do projeto atual:
  - **News agent:** abstrair fontes (RSS, scraping) e roteirização (Gemini) com config por tenant (URLs, persona, duração).
  - **Voice agent:** ElevenLabs com voz/config por tenant, tratamento de `[pausa]`.
  - **Mixer:** normalização LUFS (-23 + 7 dB ou configurável), mix voz+bed, normalização por segmentos, ducking; playlist por tenant.
- **Fila de programação:** por tenant; ciclo configurável (ex.: notícia → música → música); consumo da fila no player.
- **Jobs:** worker ou cron que executa geração agendada (lote semanal/diário) por tenant, respeitando cotas.

### 4.2 Banco de dados
- **Recomendado:** PostgreSQL (ou MySQL) com schema multi-tenant (tenant_id em todas as tabelas); ou schema separado por tenant, conforme estratégia de isolamento.
- **Cache:** Redis (opcional) para fila em memória por tenant, sessões, rate limit.

### 4.3 Frontend
- **Admin (por tenant):** painel para gestão de fontes, roteiros (lista + editor), geração de áudio (por roteiro ou lote), fila de programação (“substituir fila”, “colocar no início”), upload de músicas/vinhetas, configuração de voz e LUFS, player para ouvir último boletim/blocos.
- **Player público (por tenant):** página de ouvinte da rádio (play/stop, modo só músicas se houver), opcionalmente chat, identificação visual por rádio (logo, cores).

### 4.4 Segurança
- HTTPS; envio de senhas apenas hasheadas; JWT com expiração e refresh.
- Admin apenas para usuários do tenant com role adequada.
- Validação de upload (tipo, tamanho); sanitização de URLs em fontes (RSS/scraping).
- Chaves de API (Gemini, ElevenLabs) por tenant ou centralizadas no SaaS com cota; nunca expor chaves no frontend.

---

## 5. Funcionalidades a portar e a estender

### 5.1 Do projeto atual → SaaS (por tenant)
- Scraping de notícias (ex.: site de prefeitura) e RSS; 3 notícias → roteiro ~2 min, 3 matérias distintas.
- Geração de roteiro (Gemini) com persona e duração configuráveis.
- Geração de áudio (ElevenLabs), mix com bed (se configurado), normalização LUFS (-23 + 7 dB ou configurável).
- Fila de blocos: adicionar ao início ou substituir fila; ciclo notícia → música → música.
- Admin: “Gerar roteiro” → exibir/editar → “Gerar áudio e colocar na rádio” + opção “Substituir fila” + player para ouvir último áudio.
- Geração em lote (ex.: semanal) com N blocos, minimizando uso de APIs.
- Player para ouvintes com volume diferenciado e modo só músicas.

### 5.2 Extensões desejáveis no SaaS
- Múltiplas **fontes de notícias** por tenant (vários RSS, vários scrapers) e agendamento de sincronização.
- **Histórico de roteiros** e de blocos; reutilizar bloco gravado em mais de uma inserção na fila.
- **Voz e bed** configuráveis por tenant (ID voz ElevenLabs, arquivo de bed).
- **Planos e limites:** número de blocos/mês, minutos de TTS, fontes ativas; bloqueio ou aviso ao estourar.
- **Relatórios simples:** uso de API, blocos gerados, minutos de áudio no mês.
- **White-label:** domínio próprio ou subdomínio, logo e cores por tenant (rádios comunitárias e corporativas).

---

## 6. Estrutura sugerida do novo projeto

```
radio-saas/
├── README.md
├── requirements.txt
├── .env.example
├── config/
│   └── settings.py
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── auth/
│   ├── tenants/
│   ├── roteiros/
│   ├── blocos/
│   ├── programacao/
│   ├── player/
│   └── admin/
├── core/
│   ├── news_agent.py      # adaptado: fontes + Gemini por tenant
│   ├── voice_agent.py     # adaptado: ElevenLabs por tenant
│   ├── mixer.py           # reutilizar: LUFS, bed, normalize, ducking
│   └── storage.py         # paths por tenant, uploads
├── models/
│   ├── tenant.py
│   ├── usuario.py
│   ├── roteiro.py
│   ├── bloco.py
│   ├── fonte_noticia.py
│   └── programacao_fila.py
├── jobs/
│   └── geracao_lote.py    # worker/cron por tenant
├── storage/
│   └── tenants/
│       └── {tenant_id}/
│           ├── blocks/
│           ├── musicas/
│           └── vinhetas/
├── docs/
│   └── ESPECIFICACAO_SAAS_RADIO_MULTITENANT.md  # este doc
└── tests/
```

---

## 7. Referência rápida: parâmetros de áudio (atual)

| Parâmetro | Valor atual | Uso no SaaS |
|-----------|-------------|-------------|
| LUFS alvo | -23 LUFS + 7 dB → -16 LUFS | Configurável por tenant (ex.: -23, -16, ou só +7 dB). |
| Normalização por segmentos | 5000 ms, target_dBFS -3 (voz) / -1.5 (mix) | Manter ou expor em config. |
| Bed (vinheta de fundo) | -25 dB durante voz, intro 2,5 s a -6 dB | Caminho do arquivo e dB por tenant. |
| Ducking (música sob voz) | -20 dB | Opcional por tenant. |
| Marcação de pausa | `[pausa]` → “...” na TTS | Manter. |

---

## 8. Glossário

- **Tenant:** uma rádio (comunitária ou corporativa) no SaaS.
- **Bloco:** arquivo de áudio pronto (boletim, vinheta, dica) usado na programação.
- **Roteiro:** texto gerado ou editado que será convertido em áudio (bloco).
- **Fila de programação:** ordem dos itens (blocos e músicas) a tocar na rádio.
- **LUFS:** Loudness Units Full Scale; normalização de volume para padrão de broadcast/streaming.
- **Bed:** trilha de fundo durante a locução (vinheta).
- **Ducking:** abaixar o volume da música quando a voz entra.

---

*Documento gerado a partir da atualização do projeto Rádio IAE News para suporte à criação do SaaS multi-tenant de rádios comunitárias e indoor corporativas.*
