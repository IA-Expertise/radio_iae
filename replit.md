# Rádio IAE News

## Visao Geral
Sistema de radio automatizado com interface web. Busca noticias via RSS do Google News e scraping do site da Prefeitura de Louveira, gera roteiros via Google Gemini, sintetiza voz via ElevenLabs e intercala com musicas MP3. Geracao de blocos semanal (toda segunda-feira) para minimizar consumo de APIs.

## Estado Atual
- Interface web com Play/Stop/Modo so musicas
- Geracao semanal de 15 blocos (noticias + dicas de IA)
- Blocos persistentes em disco (sobrevivem a reinicializacao)
- Pagina admin protegida por ADMIN_SECRET
- Scraper de noticias de Louveira (prefeitura) na admin
- Chat moderado entre ouvintes
- 13 musicas MP3 em assets/musicas/
- Normalizacao de volume por segmentos (evita queda de volume)
- Vinhetas promocionais da IAExpertise alternadas

## Alteracoes Recentes
- 2026-02-24: Scraper Louveira (prefeitura) + gerador de boletim na admin
- 2026-02-24: RSS alterado para "Louveira+SP"
- 2026-02-24: Persona do roteiro alterada para locutor profissional (~2 min, 320-380 palavras)
- 2026-02-22: Sistema semanal de geracao de blocos (15 blocos toda segunda)
- 2026-02-22: Pagina admin com botao para gerar blocos e boletim Louveira
- 2026-02-22: Blocos persistentes carregados do disco ao reiniciar
- 2026-02-22: Dependencias requests e beautifulsoup4 adicionadas
- 2026-02-21: Modelo Gemini atualizado para gemini-2.5-flash
- 2026-02-21: 31 musicas MP3 (agora 13 apos troca)

## Estrutura do Projeto
```
/
├── app.py                    # Servidor Flask (rotas, geracao semanal, chat, admin)
├── core/
│   ├── news_agent.py         # RSS Google News + Scraper Louveira + roteiro via Gemini
│   ├── voice_agent.py        # Sintese de voz via ElevenLabs
│   └── mixer.py              # Playlist aleatoria + normalizacao + bed musical
├── templates/
│   ├── index.html            # Interface do ouvinte (player + chat)
│   └── admin.html            # Painel admin (gerar blocos + boletim Louveira)
├── assets/
│   ├── musicas/              # 13 MP3s (musicas da radio)
│   └── vinhetas/
│       └── news_bed.mp3      # Musica de fundo da locucao
├── output/
│   ├── blocks/               # Blocos gerados (block_000001.mp3, ...)
│   ├── news_latest.mp3       # Ultimo audio gerado
│   ├── ducked_latest.mp3     # Ultimo mix com ducking
│   └── last_weekly_generation.txt  # Data da ultima geracao semanal
├── requirements.txt
└── replit.md
```

## Fluxo da Radio
1. Ao iniciar, carrega blocos existentes do disco
2. Thread em background verifica toda segunda se precisa gerar novos blocos
3. Ciclo para o ouvinte: noticia → musica → musica → noticia → ...
4. Modo "So musicas" disponivel
5. Dicas de IA (35% chance) intercaladas com noticias

## Admin (/admin?key=ADMIN_SECRET)
- Botao "Gerar blocos da semana" (15 blocos em background)
- Boletim Louveira: scraping da prefeitura → roteiro Gemini → revisar → gerar audio
- Protegido por ADMIN_SECRET

## Detalhes Tecnicos

### Dependencias
- flask, elevenlabs, google-generativeai, python-dotenv, pydub
- feedparser, requests, beautifulsoup4, pygame

### Variaveis de Ambiente (Secrets)
- GEMINI_API_KEY - API do Google Gemini
- ELEVENLABS_API_KEY - API do ElevenLabs
- ADMIN_SECRET - Senha para acesso ao painel admin

### Audio
- Voz: ElevenLabs, modelo eleven_multilingual_v2, voz Rachel (21m00Tcm4TlvDq8ikWAM)
- Normalizacao por segmentos (5s voz, 8s mix final)
- Bed musical: intro 2.5s a -6dB, depois -25dB sob a locucao
- Volume no player: musica 100%, noticias 72%

### Geracao Semanal
- 15 blocos por semana (BLOCKS_PER_WEEK)
- Verifica a cada 6h se e segunda e precisa gerar
- Se nao tem blocos ao iniciar, gera um lote automaticamente
- Intervalo de 3s entre blocos (evita rate limit)
