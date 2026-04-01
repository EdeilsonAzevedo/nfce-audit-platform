# Perspectivas Futuras — Padronização de Itens NFC-e Bahia

---

## O que foi implementado

| Notebook | O que existe |
|----------|-------------|
| `01` — Exploração GTIN | Validação de formato EAN-13, score de confiança por GTIN, análise de consistência (GTIN × descrição × NCM × preço) |
| `02` — Clustering | Embeddings com SentenceTransformer, DBSCAN, análise de Pareto por volume |
| `03` — LLM | **Vazio** — não implementado |
| Pipeline LangGraph | **Não iniciado** |

---

## O que ainda falta do plano original

### 1. Extração de atributos via LLM (Notebook 03)
O nó mais importante do pipeline está em branco. Isso inclui:
- Prompt estruturado para extrair `produto`, `marca`, `peso`, `variante`
- Envio em lotes (batching) para reduzir custo
- Deduplicação de descrições antes de chamar a API
- Validação cruzada da resposta do LLM com NCM e preço
- Uso do **Batch API** da OpenAI (50% mais barato, assíncrono)

### 2. Pipeline LangGraph de orquestração
O plano previa um arquivo `.py` unificando tudo em um grafo de estados:
- Nó de limpeza textual
- Nó de consulta ao dicionário GTIN
- Nó de clustering
- Nó LLM (para difíceis)
- Nó de validação final e consolidação
- Condições de transição com thresholds calibrados nos notebooks

### 3. Validação e correção de NCM
- Identificar registros onde o NCM declarado é inconsistente com a descrição
- Gerar mapa de inconsistências NCM → útil diretamente para a SEFAZ-BA
- Flag `ncm_consistente` na base de saída

### 4. Dicionário de abreviações por NCM
- Vocabulário `{ "FARIN": "FARINHA", "MAND": "MANDIOCA", ... }` segmentado por NCM
- Reutilizável para novos lotes de dados futuros

### 5. Relatórios de qualidade por emissor e município
- Taxa de erros / inconsistências por CNPJ emissor
- Municípios com pior qualidade de dados
- Insumo para ações regulatórias da SEFAZ

### 6. Análise de cesta básica
- Filtro dos produtos pertencentes à cesta básica
- Série temporal de preços por município e período
- Índice de variação de preços (inflação local)

---

## Ideias novas — o que poderia ser implementado além do plano

### A. NER customizado treinado com dados do projeto
**O que é:** Usar o LLM para anotar uma amostra (~500–1000 descrições) e treinar um modelo leve de NER (spaCy ou BERTimbau) que roda localmente em escala.
**Por que vale:** Depois do treino, extração é instantânea e gratuita — sem depender de API.
**Entidades:** `PRODUTO`, `MARCA`, `PESO`, `VARIANTE`, `UNIDADE`

### B. Dashboard interativo de monitoramento de preços
**O que é:** Interface Streamlit ou Gradio conectada à base padronizada.
**Funcionalidades:**
- Consultar preço médio de um produto por município e período
- Comparar preço entre municípios (mapa)
- Alertas de variação anômala (produto X subiu 40% no último mês)
**Audiência:** Analistas da SEI, jornalistas, consumidores

### C. Detecção de anomalias de preço
**O que é:** Modelo estatístico ou de ML para sinalizar preços fora do padrão.
- Outliers de preço dentro do mesmo cluster de produto
- Variação temporal suspeita (possível fraude fiscal ou erro de cadastro)
- Insumo direto para auditoria da SEFAZ

### D. Matching de produtos entre municípios (análise geoespacial)
**O que é:** Identificar se o mesmo produto (mesma descrição padronizada) tem preços sistematicamente diferentes entre regiões.
- Mapa de calor de preços por município
- Ranking de municípios mais caros por categoria (carnes, laticínios, grãos)
- Detectar isolamento logístico nos preços

### E. Integração com bases externas de referência
- **Open Food Facts** (base global de produtos com GTIN) — validação cruzada do dicionário
- **Tabela TACO** (composição nutricional de alimentos) — enriquecimento de dados
- **IBGE** (POF, IPCA) — contextualizar os preços encontrados em relação a índices nacionais

### F. API de consulta do dicionário padronizado
**O que é:** Uma API REST leve (FastAPI) que expõe o dicionário gerado.
- Endpoint: `GET /produto?gtin=7891000100103` → retorna descrição canônica, NCM, marca, peso
- Permite que outros sistemas da SEI e SEFAZ consumam a padronização
- Pode virar um serviço permanente alimentado por novos lotes de NFC-e

### G. Pipeline incremental para novos lotes
**O que é:** O pipeline atual trata um snapshot. Dados de NFC-e chegam continuamente.
- Novo lote → verificar se GTIN/descrição já está no dicionário
- Só processar o que é novo (evitar reprocessar tudo)
- Retroalimentar o dicionário com novos GTINs confiáveis encontrados
- Monitorar drift (descrições novas que não se encaixam nos clusters existentes)

### H. Generalização para outros estados
**O que é:** O pipeline é agnóstico ao estado. Com pequenos ajustes pode ser aplicado em dados de NFC-e de SP, MG, RS, etc.
- Vocabulário de abreviações regionais diferentes
- Potencial de parceria com outros SEIs estaduais

---

## Priorização sugerida

| Prioridade | Item | Impacto | Esforço |
|-----------|------|---------|---------|
| Alta | Completar Notebook 03 (LLM) | Essencial para o pipeline fechar | Baixo |
| Alta | Pipeline LangGraph | Entrega final do projeto | Médio |
| Alta | Análise de cesta básica | Objetivo original da SEI | Baixo (após pipeline) |
| Média | Relatórios de qualidade por emissor | Valor direto para SEFAZ | Baixo |
| Média | Mapa de inconsistências NCM | Valor regulatório | Baixo |
| Média | Dashboard de preços (Streamlit) | Democratiza o acesso aos dados | Médio |
| Média | Detecção de anomalias de preço | Auditoria fiscal | Médio |
| Baixa | NER customizado treinado | Escalabilidade de longo prazo | Alto |
| Baixa | API REST do dicionário | Integração institucional | Médio |
| Baixa | Pipeline incremental | Produção contínua | Alto |
| Exploratória | Matching geoespacial de preços | Pesquisa econômica | Alto |
| Exploratória | Integração Open Food Facts / IBGE | Enriquecimento de dados | Médio |
