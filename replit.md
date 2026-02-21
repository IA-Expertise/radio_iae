# Rádio IA News

## Visao Geral
Sistema de radio automatizado que busca noticias reais de Inteligencia Artificial, gera roteiros jornalisticos via Google Gemini, sintetiza voz via ElevenLabs e intercala com uma biblioteca de 31 musicas MP3.

## Estado Atual
- Projeto funcional rodando em loop continuo
- Modelo Gemini atualizado para `gemini-2.5-flash` (modelos 1.5 e 2.0 foram descontinuados)
- 31 musicas MP3 carregadas em `assets/musicas/`
- Audio de noticias sendo gerado e salvo em `output/news_latest.mp3`
- Ducking funcionando (musica abaixa -20dB quando o locutor fala)

## Alteracoes Recentes
- 2026-02-21: Modelo Gemini atualizado de `gemini-1.5-pro` para `gemini-2.5-flash`
- 2026-02-21: Dependencias instaladas e projeto configurado no Replit
- 2026-02-21: 31 musicas MP3 enviadas para `assets/musicas/`

## Estrutura do Projeto
```
/
├── main.py                   # Loop principal (Orquestrador)
├── core/
│   ├── news_agent.py         # Busca noticias RSS + gera roteiro via Gemini
│   ├── voice_agent.py        # Sintese de voz via ElevenLabs
│   └── mixer.py              # Playlist aleatoria + Audio Ducking
├── assets/
│   ├── musicas/              # 31 MP3s (musicas da radio)
│   └── vinhetas/             # Vinhetas da radio (vazio)
├── output/
│   ├── news_latest.mp3       # Ultimo audio de noticias gerado
│   └── ducked_latest.mp3     # Ultimo mix com ducking
├── requirements.txt
├── .env.example
└── INSTRUCOES_DESENVOLVIMENTO # Documento original de planejamento
```

## Fluxo da Radio (main.py)
1. Tocar Musica 1 (aleatoria da playlist)
2. Tocar Musica 2 (aleatoria da playlist)
3. Buscar noticias de IA via RSS do Google News (`news_agent.py`)
4. Gerar roteiro de radio de 1 minuto via Gemini (`news_agent.py`)
5. Sintetizar voz do roteiro via ElevenLabs (`voice_agent.py`)
6. Tocar Musica 3 com Ducking - locutor fala sobre a musica tocando baixo (`mixer.py`)
7. Repetir o ciclo infinitamente

## Detalhes Tecnicos

### Dependencias (requirements.txt)
- `elevenlabs>=1.0.0` - API de sintese de voz
- `google-generativeai>=0.8.0` - API do Google Gemini
- `python-dotenv>=1.0.0` - Carregamento de variaveis de ambiente
- `pydub>=0.25.0` - Processamento de audio (ducking)
- `feedparser>=6.0.0` - Parser de RSS para noticias
- `pygame>=2.5.0` - Reproducao de audio

### Variaveis de Ambiente (Secrets)
- `GEMINI_API_KEY` - Chave da API do Google Gemini
- `ELEVENLABS_API_KEY` - Chave da API do ElevenLabs
- `ELEVENLABS_VOICE_ID` (opcional) - ID de voz customizada (padrao: Rachel "21m00Tcm4TlvDq8ikWAM")

### core/news_agent.py
- Busca as 3 noticias mais recentes de IA no Google News RSS (pt-BR)
- Envia para o Gemini com persona de jornalista de radio tech brasileiro
- Modelo: `gemini-2.5-flash`
- Retorna roteiro de ~1 minuto (150-180 palavras) com marcacoes `[pausa]`

### core/voice_agent.py
- Recebe o roteiro e converte `[pausa]` em `...` para pausas naturais
- Gera audio via ElevenLabs com modelo `eleven_multilingual_v2`
- Formato de saida: MP3 44100Hz 128kbps
- Salva em `output/news_latest.mp3`

### core/mixer.py
- Selecao aleatoria de musicas sem repetir nas ultimas 10 rodadas
- Funcao de ducking: musica baixa -20dB durante a voz do locutor
- Volta ao volume normal quando a voz termina
- Mix salvo em `output/ducked_latest.mp3`

## Como Executar
```bash
pip install -r requirements.txt
python3 main.py
```

## Limitacao Atual
- O audio e reproduzido via pygame no servidor (sem interface web para ouvir pelo navegador)
- Pasta `assets/vinhetas/` esta vazia (sem vinhetas implementadas)
