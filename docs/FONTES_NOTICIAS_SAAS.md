# Fontes de notícias no SaaS – opções e evolução

Documento de referência para o produto SaaS de scraping e produção de notícias locais: tipos de fonte, portais fechados e formas de o usuário **colar** ou **subir** a fonte.

---

## 1. Tipos de fonte que fazem sentido

| Tipo | Descrição | Quando usar | Complexidade |
|------|-----------|-------------|--------------|
| **RSS / Atom** | URL de feed (Google News, blog, site com feed). | Site expõe feed; busca ampla (ex.: "Louveira SP"). | Baixa |
| **Scraping por URL** | URL da página de listagem; o sistema extrai links e corpo (com regras por site ou genéricas). | Prefeitura, portais locais, sites sem RSS. | Média |
| **Colar texto** | Usuário cola no admin: texto puro ou trechos copiados do site. | Site fechado, paywall, ou quando o scraper não funciona. | Baixa |
| **Enviar arquivo** | Upload de arquivo: HTML (página salva) ou TXT com notícias. | Mesmo conteúdo que “colar”, em lote ou página complexa. | Média |
| **URL + receita (scraping configurável)** | URL + seletores CSS/XPath por tenant (ex.: “lista = .noticia, título = h2, link = a”). | Cada rádio configura seu portal; reutilizável. | Média–alta |
| **API externa** | Chave do tenant para GNews API, NewsAPI, etc. | Quando o cliente já tem assinatura. | Média |

Para **portais e sites fechados** (paywall, bloqueio por User-Agent, JS pesado, captcha), as opções mais viáveis são:

- **Colar fonte** (usuário copia o texto no navegador e cola no admin).
- **Enviar arquivo** (salva a página como HTML ou copia em TXT e envia).
- **Receita de scraping** só ajuda se o site abrir para o nosso scraper; para fechados, colar/enviar é a saída.

---

## 2. Soluções para o usuário “subir” ou “colar” a fonte

### 2.1 Colar fonte (recomendado como primeira evolução)

- **O quê:** Campo no admin (textarea ou editor) onde o usuário cola texto.
- **Formatos aceitos (sugestão):**
  - **Texto livre:** um bloco de texto; o backend tenta quebrar em “notícias” por parágrafos ou por marcadores (ex.: “---”, “Notícia 1:”, números).
  - **Lista estruturada:** uma notícia por linha ou por bloco, com título opcional (ex.: primeira linha = título, resto = resumo).
  - **HTML colado:** se o usuário colar HTML (ex.: copiar da página), o backend extrai texto (strip tags) e aplica a mesma lógica de “quebrar em notícias”.
- **Fluxo:** Colar → “Gerar roteiro a partir desta fonte” → mesmo pipeline (Gemini → roteiro → áudio).
- **Vantagem:** Funciona para qualquer site, inclusive fechados; zero configuração de scraping.

### 2.2 Enviar arquivo

- **O quê:** Upload de arquivo no admin.
- **Tipos sugeridos:**
  - **.txt:** conteúdo tratado como “fonte colada” (mesma lógica de parsing).
  - **.html:** página salva (File → Save as); backend usa BeautifulSoup para extrair texto (body, article, .content, etc.) e depois quebra em notícias.
- **Fluxo:** Escolher arquivo → enviar → backend parseia → gera roteiro (e opcionalmente lista “N notícias encontradas”) → usuário gera áudio.
- **Vantagem:** Bom para muitas notícias ou quando a página é grande; evita colar manualmente.

### 2.3 URL como fonte (RSS ou listagem)

- **RSS:** Usuário cola URL do feed (qualquer RSS/Atom). Backend usa `feedparser` com essa URL (já existe lógica similar para Google News).
- **Listagem (scraping genérico):** Usuário cola URL da página de notícias. Opções:
  - **Modo simples:** heurísticas genéricas (links em `article`, `h2`+`a`, etc.) para qualquer site.
  - **Modo “receita” (futuro):** por tenant, salvar seletores (lista, título, link, resumo) e reutilizar para aquele portal.

### 2.4 Resumo das opções por “entrada” do usuário

| O usuário… | Solução | Backend |
|------------|--------|--------|
| Cola texto/HTML no admin | **Colar fonte** | Parser de texto/HTML → lista `[{title, summary}]` → `generate_radio_script(news)` |
| Envia arquivo .txt ou .html | **Enviar arquivo** | Ler arquivo → extrair texto (HTML se for .html) → mesmo parser que “colar” |
| Cola URL de um feed RSS | **Fonte RSS (URL)** | `feedparser.parse(url)` → mesma estrutura já usada |
| Cola URL de página de listagem | **Scraping genérico** ou **receita** | Fetch URL → seletores genéricos ou config (tenant) → lista de notícias |

---

## 3. Modelo de dados (alinhado à especificação SaaS)

A entidade **FonteNoticia** já prevê:

- `tipo`: `rss` | `scraping` | **`manual`** (colar/enviar) | (futuro) `api`
- `config`: JSON
  - **RSS:** `{ "url": "https://..." }`
  - **Scraping:** `{ "url": "...", "selectors": { "list": "...", "title": "...", "link": "...", "summary": "..." } }` (opcional)
  - **Manual (colar/enviar):** não persiste URL; o conteúdo vem no momento da ação (colar no form ou upload). Pode-se guardar em **Roteiro** `origem: manual` e opcionalmente um snapshot do texto em `noticias_fonte` ou em campo separado.

Para “colar” e “enviar arquivo” não é obrigatório criar uma FonteNoticia persistida; pode ser um fluxo “ad hoc”: usuário cola/envia → backend devolve roteiro (e opcionalmente grava como rascunho com `origem: manual`).

---

## 4. Ordem sugerida de implementação

1. **Colar fonte** – API que recebe texto (ou HTML), parseia em até N “notícias”, chama `generate_radio_script(news)` e retorna o roteiro; no admin, abas ou seção “Boletim a partir de texto colado”.
2. **RSS por URL** – Campo “URL do feed” no admin; backend usa essa URL no lugar da fixa; opcionalmente salvar como FonteNoticia quando existir multi-tenant.
3. **Enviar arquivo** – Endpoint de upload (.txt / .html), mesmo parser que “colar”, depois mesmo fluxo de roteiro.
4. **Scraping genérico por URL** – Uma URL de listagem, heurísticas genéricas (article, h2, links); depois evoluir para seletores configuráveis por tenant (receita).

Com isso o app cobre: **RSS**, **scraping (Louveira hoje; amanhã qualquer URL + receita)**, **portais fechados (colar ou enviar)** e prepara o SaaS com fontes configuráveis por rádio.
