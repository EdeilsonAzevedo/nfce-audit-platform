# Contexto do Projeto: Padronização de Itens em NFC-e da Bahia

## Workshop CEMEAI — SEI (Superintendência de Estudos Econômicos e Sociais da Bahia)

---

## 1. O PROBLEMA

A SEI, em articulação com a SEFAZ-BA, trabalha com dados de Notas Fiscais Eletrônicas ao Consumidor (NFC-e) da Bahia. As descrições dos produtos são inseridas livremente pelos emissores, gerando caos textual: abreviações ("FARIN", "MAND"), erros de digitação ("FARINHA BDE MANDIOCA"), variações regionais, ordens diferentes de atributos, marcas misturadas com nomes.

O NCM sozinho não resolve porque agrupa produtos distintos sob o mesmo código (ex: "2801.30.00 - Flúor; bromo").

**Exemplo do problema:** Todas estas descrições se referem ao mesmo produto:
- "FARIN KICALDO BRANCA 1KG MAND"
- "FARINHA DE MANDIOCA KICALDO 1KG"
- "FARINHA BDE MANDIOCA KICALDO 1KG"
- "FARINHA BRANCA FINA SECA 1 KG KICALDO"

---

## 2. OBJETIVOS DO PROJETO

1. **Padronizar descrições** — corrigir, limpar e unificar as variantes de `des_item`
2. **Adequar nomes ao NCM** — garantir coerência entre descrição e classificação
3. **Criar base de referência** — dicionário (descrição padronizada, NCM, GTIN) validado
4. **Analisar cesta básica** — usar a base limpa para análise de preços e consumo por período

---

## 3. ESTRUTURA DOS DADOS

### Colunas disponíveis:

| Coluna | Descrição | Confiabilidade | Uso estratégico |
|--------|-----------|----------------|-----------------|
| `data` | Data de emissão (YYYY-MM-DD) | Alta (sistema SEFAZ) | Eixo temporal para séries de preço |
| `des_item` | Descrição do produto (texto livre) | **Muito baixa** — campo mais problemático | Alvo principal do pipeline de padronização |
| `ncm` | Nomenclatura Comum do Mercosul (8 dígitos) | Média (pode ter erros, mas tem implicação fiscal) | Primeiro filtro de agrupamento, validação cruzada |
| `gtin` | Global Trade Item Number / código de barras | **Variável** — pode estar ausente, zerado, ou errado | Âncora quando válido, mas hipótese precisa ser testada |
| `unidade` | Unidade de medida (UN, KG, LT, CX, etc.) | Média (variações de formato) | Validação de coerência, comparação de preços |
| `valor_unit_liq` | Valor unitário líquido (R$) | Alta (fiscal) mas com outliers | Análise de preços, validação de clusters |
| `qtd_geral_item` | Quantidade total vendida (consolidada) | Alta | Priorização por volume, ponderação |
| `qtd_reg_consolid` | Nº de registros/notas consolidados naquela linha | Alta | Indica nível de agregação, peso estatístico |

**Obs:** A base já vem pré-agregada — cada linha é uma combinação única de (data, descrição, NCM, GTIN, unidade, valor), não é nota a nota.

---

## 4. ENTRADA E SAÍDA DO PIPELINE

### Entrada:
Cada registro com: `data`, `des_item`, `ncm`, `gtin`, `unidade`, `valor_unit_liq`, `qtd_geral_item`, `qtd_reg_consolid`

### Saída (campos novos gerados):

| Campo | Descrição |
|-------|-----------|
| `des_item_padronizada` | Descrição limpa e padronizada |
| `produto` | Nome genérico (ex: "FARINHA DE MANDIOCA") |
| `marca` | Extraída da descrição |
| `peso_volume` | Ex: "1KG", "500ML" |
| `variante` | Ex: "BRANCA", "INTEGRAL", "FINA" |
| `ncm_validado` | NCM corrigido quando necessário |
| `ncm_consistente` | Flag (o NCM original batia com o produto?) |
| `gtin_valido` | Flag (GTIN passou na validação?) |
| `cluster_id` | ID do grupo de produto |
| `metodo_resolucao` | Como foi padronizado: "gtin", "clustering", "llm", "nao_resolvido" |
| `confianca` | Score de 0 a 1 |
| `cesta_basica` | Flag (pertence à cesta básica?) |
| `categoria_cesta` | Se pertence: carnes, cereais, laticínios, etc. |

### Artefatos gerados no processo:
- **Dicionário GTIN** → (descrição canônica, NCM, produto, marca, peso) — reutilizável permanentemente
- **Vocabulário de abreviações por NCM** — reutilizável
- **Mapa de inconsistências NCM** — útil para SEFAZ
- **Taxa de qualidade por emissor/município**
- **Base de preços da cesta básica** por município e período

---

## 5. ARQUITETURA DO PIPELINE (LangGraph)

### Fluxo condicional por registro:

```
Registro bruto
    ↓
[Limpeza textual] — regex, acentos, uppercase, normalização
    ↓
[Valida GTIN] — formato + dígito verificador + testes de confiança
    ↓
GTIN válido e confiável? ──SIM──→ [Dicionário GTIN] → RESOLVIDO (método: gtin)
    │
   NÃO
    ↓
[Clustering por NCM] — TF-IDF ou SBERT + HDBSCAN
    ↓
Confiança alta? ──SIM──→ RESOLVIDO (método: cluster)
    │
   NÃO
    ↓
[LLM extrai atributos] — produto, marca, peso via API
    ↓
LLM confiante? ──SIM──→ RESOLVIDO (método: llm)
    │
   NÃO
    ↓
NÃO RESOLVIDO (flag para revisão)
    ↓
Base padronizada + relatórios de qualidade
```

---

## 6. PLANO DE IMPLEMENTAÇÃO EM 4 ETAPAS

### Notebook 01 — Exploração e validação do GTIN
**Objetivo:** Testar a hipótese "se o GTIN é informado, está certo"
**Ferramentas:** pandas, numpy
**Testes a implementar:**
1. **Consistência GTIN × descrição** — agrupar por GTIN, medir entropia das descrições (alta entropia = GTIN suspeito)
2. **Consistência GTIN × NCM** — mesmo GTIN com múltiplos NCMs indica erro
3. **Consistência GTIN × preço** — variação de preço excessiva no mesmo GTIN pode indicar produtos diferentes
4. **Formato e estrutura** — GTINs com "2" no início (internos de balança), sequências repetidas, dígito verificador inválido
5. **Unicidade esperada** — descrições com pesos claramente diferentes dentro do mesmo GTIN
**Saída:** Score de confiança por GTIN, separação em GTIN confiável vs suspeito

### Notebook 02 — Dicionário GTIN + limpeza textual (Fase 1)
**Objetivo:** Construir o dicionário e resolver todos os registros com GTIN confiável
**Ferramentas:** pandas, regex, unicodedata
**Passos:**
1. Limpeza textual (acentos, uppercase, espaços, caracteres especiais)
2. Para GTINs confiáveis: eleição de descrição canônica por voto ponderado (`qtd_reg_consolid`)
3. Validação do NCM por voto majoritário dentro de cada GTIN
4. Propagação: todos os registros com GTIN confiável recebem descrição padronizada + NCM validado
**Saída:** Dicionário GTIN como artefato, base parcialmente padronizada, relatório de cobertura

### Notebook 03 — Clustering por NCM (Fase 2)
**Objetivo:** Resolver registros sem GTIN válido via agrupamento de descrições similares
**Ferramentas:** scikit-learn (TF-IDF), sentence-transformers (SBERT), hdbscan
**Passos:**
1. Segmentar registros não resolvidos por NCM
2. Vetorizar descrições limpas (TF-IDF para começar rápido, SBERT para mais qualidade)
3. HDBSCAN para clustering (descobre nº de clusters automaticamente, identifica outliers)
4. Eleição de descrição canônica por cluster
5. Usar registros já resolvidos pelo GTIN como "sementes" dos clusters (semi-supervised)
6. Validação com `valor_unit_liq` (cluster com preços muito dispersos → possível mistura)
**Saída:** Mais registros resolvidos, relatório de cobertura acumulada (Fase 1 + 2 = estimativa 70-85%)

### Pipeline LangGraph (.py) — Orquestração completa (Fase 3 + integração)
**Objetivo:** Juntar tudo em fluxo automatizado com LLM para casos difíceis
**Ferramentas:** langgraph, langchain, API OpenAI (GPT-4o Mini)
**Componentes:**
1. Cada função testada nos notebooks vira um nó do grafo
2. Condições de transição calibradas com thresholds descobertos na exploração
3. Nó LLM: manda descrições difíceis em lotes para API, extrai atributos estruturados
4. Nó de validação: checa coerência da resposta do LLM com NCM e preço
5. Nó final: consolida resultados, gera base limpa e relatórios
**Saída:** Pipeline completo e escalável, cobertura 90-95%+

---

## 7. CUSTOS ESTIMADOS (API LLM)

Base de 400.000 linhas, usando GPT-4o Mini ($0.15/M input, $0.60/M output):
- **Com deduplicação** (descrições únicas, ~30-80k): **R$5-15**
- **Sem deduplicação** (todas as linhas): **~R$50**
- **Com Batch API** (assíncrono 24h): metade do preço
- **Obs:** LLM só é chamado para registros que GTIN e clustering não resolveram (~10-20% da base)

---

## 8. TRABALHOS DE REFERÊNCIA

### Diretamente relacionados (Brasil, NFC-e):
1. **"Redes Heterogêneas para Classificação de Produtos em NF-e de Compras Públicas"** — USP São Carlos, 2020. Algoritmo IMBHN com mineração de texto em descrições de NF-e.
2. **"Mineração de Dados Textuais para Classificação da Atividade Econômica"** — IME-USP, 2022. Bag-of-Words, NB, SVM, Boosting para classificar textos em taxonomias hierárquicas.
3. **"Categorização Automática de Produtos"** — UFES, 2022. BERT + ML no dataset do Mercado Libre (20M amostras), 86.57% precisão.
4. **Nota Fiscal Gaúcha / Mapa de Preço DF** — Projetos estaduais que usam NF-e/NFC-e para monitoramento de preços (mesmos desafios de padronização).

### Pipeline NLP (técnicas aplicáveis):
5. **"Multi-level Product Category Prediction"** (arxiv, 2024) — LSTM+GloVe e BERT para classificação hierárquica de produtos no varejo brasileiro, F1 até 93%.
6. **"Using LLMs for Extraction and Normalization of Product Attribute Values"** (arxiv, 2024) — GPT-3.5/4 zero-shot e few-shot para extrair atributos de descrições de produtos.
7. **"Clustering Product Names with Python"** (Towards Data Science) — NLP + K-means em nomes de alimentos australianos, tutorial prático.
8. **"LLMs para classificação UNSPSC"** (IJNLC, 2025) — GPT-4 para classificar itens em taxonomia padronizada, 90% acurácia.
9. **"Product Matching using Sentence-BERT"** — Abordagem leve com all-MiniLM-L6-v2.
10. **"Optimizing Product Deduplication with Multimodal Embeddings"** (arxiv, 2025) — Deduplicação em larga escala com BERT 128-dim.

---

## 9. TÉCNICAS-CHAVE

### NER customizado (extração de entidades):
- Entidades: PRODUTO, MARCA, VARIANTE, PESO, UNIDADE
- Opções: spaCy (leve, treinar com anotações), BERTimbau (fine-tuning), LLM zero-shot (sem treino)
- Estratégia: LLM anota amostra → treina modelo leve → roda em escala

### Clustering para agrupamento:
- TF-IDF + HDBSCAN (rápido, bom baseline)
- Sentence-BERT + HDBSCAN (mais preciso, entende semântica)
- Sempre dentro de cada NCM (reduz complexidade, melhora qualidade)
- HDBSCAN > K-means porque descobre nº de clusters e identifica outliers

### Dicionário GTIN (auto-construído):
- Agrupar por GTIN → eleger descrição canônica por frequência → validar NCM por voto
- Score de confiança por GTIN baseado em: concordância de descrição, NCM único, preço coerente, formato válido
- **Hipótese a testar:** GTIN informado pode estar errado — não assumir como verdade

### LangChain vs LangGraph:
- **LangChain:** pipelines lineares, bom para tarefas uniformes
- **LangGraph:** grafos com estado e decisões condicionais, cada registro pode seguir caminho diferente
- **No projeto:** LangGraph na orquestração final (Fase 4), porque registros têm níveis diferentes de dificuldade

---

## 10. DECISÕES TÉCNICAS TOMADAS

- **Notebooks para exploração, .py com LangGraph para pipeline final**
- **Não usar LangGraph nos notebooks** — overengineering nessa fase
- **Funções nos notebooks escritas como funções Python normais** (recebem DataFrame, retornam DataFrame) para fácil extração depois
- **3 notebooks + 1 pipeline .py** como estrutura de entrega
- **GPT-4o Mini** como modelo custo-eficiente para extração de atributos via API
- **Deduplicar descrições antes de mandar para LLM** para minimizar custo