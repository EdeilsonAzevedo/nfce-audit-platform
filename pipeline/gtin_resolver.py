"""
gtin_resolver.py

1. Transforma o CSV de amostra num JSON {gtin: [{des_item_norm, ncm, ...}]}
2. Para cada GTIN, resolve:
   - Descrição limpa/padronizada
   - Marca
   - Volume/peso
   - NCM correto

Estratégia para minimizar tokens GPT:
  - Agrupa e deduplica descrições localmente (envia só top-5 mais frequentes)
  - Usa TF-IDF local contra as 15k NCMs para pré-selecionar 3 candidatos
  - GPT recebe apenas os candidatos pré-filtrados, não toda a base NCM
"""

import json
import os
import argparse
from collections import Counter
from pathlib import Path

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from openai import OpenAI

# Carrega secrets.env se existir (não sobrescreve variáveis já definidas no ambiente)
_env_file = Path(__file__).parent.parent / "secrets.env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        if _line.strip() and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())


# ---------------------------------------------------------------------------
# 1. Construção do JSON de GTINs
# ---------------------------------------------------------------------------

def build_gtin_json(csv_path: str) -> dict:
    """Agrupa registros do CSV por GTIN, mantendo campos descritivos e financeiros."""
    df = pd.read_csv(csv_path)
    df = df[df["gtin"].astype(str).str.strip() != "SEM GTIN"]
    for col in ["valor_unit_liq", "qtd_geral_item", "qtd_reg_consolid"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    result = {}
    cols = ["des_item_norm", "ncm", "valor_unit_liq", "qtd_geral_item", "qtd_reg_consolid"]
    cols = [c for c in cols if c in df.columns]
    for gtin, group in df.groupby("gtin"):
        records = group[cols].dropna(subset=["des_item_norm"]).to_dict("records")
        result[str(gtin)] = records
    return result


def save_gtin_json(gtin_json: dict, output_path: str) -> None:
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(gtin_json, f, ensure_ascii=False, indent=2)
    print(f"[✓] JSON salvo em: {output_path}  ({len(gtin_json)} GTINs)")


# ---------------------------------------------------------------------------
# 2. Carregamento e indexação da tabela NCM
# ---------------------------------------------------------------------------

def load_ncm_table(xlsx_path: str) -> pd.DataFrame:
    """Carrega a tabela NCM e mantém apenas códigos de 8 dígitos (folhas)."""
    df = pd.read_excel(xlsx_path, header=3)
    df.columns = ["codigo", "descricao", "data_inicio", "data_fim",
                  "ato_legal", "numero", "ano"]
    df = df.iloc[1:].copy()  # remove a linha de cabeçalho duplicada
    df["codigo_str"] = df["codigo"].astype(str).str.replace(".", "", regex=False)
    # Apenas NCMs folha (8 dígitos)
    df = df[df["codigo_str"].str.len() == 8].dropna(subset=["descricao"])
    df = df.reset_index(drop=True)
    return df[["codigo_str", "descricao"]].rename(columns={"codigo_str": "codigo"})


def build_tfidf_index(ncm_df: pd.DataFrame):
    """Constrói índice TF-IDF sobre as descrições NCM."""
    vectorizer = TfidfVectorizer(
        analyzer="char_wb",   # n-gramas de caracteres → robusto a abreviações
        ngram_range=(3, 5),
        min_df=1,
        sublinear_tf=True,
    )
    tfidf_matrix = vectorizer.fit_transform(ncm_df["descricao"].str.lower())
    return vectorizer, tfidf_matrix


def find_ncm_candidates(
    query: str,
    ncm_df: pd.DataFrame,
    vectorizer: TfidfVectorizer,
    tfidf_matrix,
    top_k: int = 3,
) -> list[dict]:
    """Retorna os top_k NCMs mais similares à query por TF-IDF."""
    q_vec = vectorizer.transform([query.lower()])
    scores = cosine_similarity(q_vec, tfidf_matrix).flatten()
    top_idx = scores.argsort()[-top_k:][::-1]
    return ncm_df.iloc[top_idx].to_dict("records")


# ---------------------------------------------------------------------------
# 3. Normalização NCM (CSV usa inteiro sem zeros à esquerda)
# ---------------------------------------------------------------------------

def normalize_ncm(ncm_raw) -> str | None:
    """Converte 1019000 → '01019000'."""
    try:
        s = str(int(ncm_raw)).zfill(8)
        return s if len(s) == 8 else None
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# 4. Resolução por GTIN via GPT (token-eficiente)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "Você é um especialista em classificação fiscal de produtos de consumo "
    "no Brasil. Retorne APENAS JSON válido, sem markdown ou explicações."
)

USER_TEMPLATE = """Produto com GTIN {gtin}.

Descrições observadas (ordenadas por frequência):
{desc_block}

Candidatos NCM por similaridade textual:
{ncm_block}

Retorne EXATAMENTE este JSON:
{{
  "descricao": "<descrição limpa, padronizada, legível>",
  "marca": "<marca ou null>",
  "volume": "<ex: 200ml, 1kg, 500g ou null>",
  "ncm": "<código 8 dígitos sem pontos>",
  "confianca": <número de 0 a 1>,
  "motivo_confianca": "<justificativa curta: ex: descrições consistentes, NCM ambíguo, marca não identificada>"
}}"""


def resolve_gtin(
    gtin: str,
    records: list[dict],
    ncm_df: pd.DataFrame,
    vectorizer,
    tfidf_matrix,
    client: OpenAI,
    model: str = "gpt-4o-mini",
    max_descs: int = 10,
    ncm_candidates: int = 3,
) -> dict:
    """Chama o GPT com contexto mínimo e retorna o resultado estruturado."""

    # Frequência de descrições — envia todas as únicas, limitado a max_descs
    desc_counter = Counter(
        r["des_item_norm"].strip().upper()
        for r in records
        if r.get("des_item_norm")
    )
    top_desc_list = [d for d, _ in desc_counter.most_common(max_descs)]

    # Frequência de NCMs (já normalizados)
    ncm_counter = Counter(
        normalize_ncm(r["ncm"])
        for r in records
        if r.get("ncm") and normalize_ncm(r["ncm"])
    )
    most_common_ncm = ncm_counter.most_common(1)[0][0] if ncm_counter else None

    # Candidatos NCM via TF-IDF (usa a descrição mais frequente como query)
    candidates = find_ncm_candidates(
        top_desc_list[0], ncm_df, vectorizer, tfidf_matrix, top_k=ncm_candidates
    )

    # Garante que o NCM mais votado está entre os candidatos
    candidate_codes = {c["codigo"] for c in candidates}
    if most_common_ncm and most_common_ncm not in candidate_codes:
        # Busca a descrição desse NCM na tabela
        match = ncm_df[ncm_df["codigo"] == most_common_ncm]
        if not match.empty:
            candidates.append(match.iloc[0].to_dict())

    desc_block = "\n".join(
        f"  {i+1}. {d} (freq: {desc_counter[d]})"
        for i, d in enumerate(top_desc_list)
    )
    ncm_block = "\n".join(
        f"  - {c['codigo']}: {c['descricao']}" for c in candidates
    )

    prompt = USER_TEMPLATE.format(
        gtin=gtin,
        desc_block=desc_block,
        ncm_block=ncm_block,
    )

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )

    raw = response.choices[0].message.content
    result = json.loads(raw)
    result["gtin"] = gtin
    result["tokens_used"] = response.usage.total_tokens
    return result


# ---------------------------------------------------------------------------
# 5. Pipeline principal
# ---------------------------------------------------------------------------

def run(
    csv_path: str,
    ncm_xlsx_path: str,
    gtin_json_output: str = "gtin_index.json",
    results_output: str = "gtin_resolved.json",
    api_key: str | None = None,
    model: str = "gpt-4o-mini",
    target_gtins: list[str] | None = None,
):
    print("[1/4] Carregando CSV e construindo índice de GTINs...")
    gtin_json = build_gtin_json(csv_path)
    save_gtin_json(gtin_json, gtin_json_output)

    print("[2/4] Carregando tabela NCM e construindo índice TF-IDF...")
    ncm_df = load_ncm_table(ncm_xlsx_path)
    vectorizer, tfidf_matrix = build_tfidf_index(ncm_df)
    print(f"      {len(ncm_df)} NCMs folha indexados.")

    print("[3/4] Resolvendo GTINs via GPT...")
    client = OpenAI(api_key=api_key)  # usa OPENAI_API_KEY do ambiente se None

    gtins_to_process = target_gtins if target_gtins else list(gtin_json.keys())

    # Carrega resultados já salvos para retomar de onde parou
    results_path = Path(results_output)
    if results_path.exists():
        with open(results_path, encoding="utf-8") as f:
            results = json.load(f)
        already_done = {r["gtin"] for r in results}
        print(f"      Retomando: {len(already_done)} GTINs já processados, pulando.")
    else:
        results = []
        already_done = set()

    total_tokens = 0

    for i, gtin in enumerate(gtins_to_process, 1):
        if gtin in already_done:
            print(f"  [{i}/{len(gtins_to_process)}] GTIN {gtin}: já processado, pulando.")
            continue

        records = gtin_json.get(gtin, [])
        if not records:
            print(f"  [{i}/{len(gtins_to_process)}] GTIN {gtin}: sem registros, pulando.")
            continue

        try:
            res = resolve_gtin(
                gtin, records, ncm_df, vectorizer, tfidf_matrix, client, model,
                max_descs=10,
            )
            total_tokens += res.pop("tokens_used", 0)
            results.append(res)
            # Salva incrementalmente a cada GTIN processado
            with open(results_path, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(
                f"  [{i}/{len(gtins_to_process)}] {gtin} → "
                f"{res.get('descricao')} | {res.get('marca')} | "
                f"{res.get('volume')} | NCM {res.get('ncm')} "
                f"(confiança: {res.get('confianca')})"
            )
        except Exception as e:
            print(f"  [{i}/{len(gtins_to_process)}] GTIN {gtin}: ERRO → {e}")

    print(f"\n[✓] Concluído. {len(results)} GTINs resolvidos → {results_output}")
    print(f"    Tokens GPT nesta sessão: {total_tokens:,}")
    print(f"    Média por GTIN: {total_tokens // max(total_tokens and 1, 1):,} tokens")


# ---------------------------------------------------------------------------
# 6. CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Resolve descrição, marca, volume e NCM para GTINs."
    )
    parser.add_argument("--csv", default="data/raw/amostra_gtin_789.csv")
    parser.add_argument("--ncm", default="data/raw/Tabela_NCM_Vigente.xlsx")
    parser.add_argument("--json-out", default="output/gtin_index.json")
    parser.add_argument("--results-out", default="output/gtin_resolved.json")
    parser.add_argument("--model", default="gpt-4o-mini")
    parser.add_argument(
        "--gtins", nargs="*", help="GTINs específicos (default: todos)"
    )
    parser.add_argument("--api-key", default=None)
    args = parser.parse_args()

    run(
        csv_path=args.csv,
        ncm_xlsx_path=args.ncm,
        gtin_json_output=args.json_out,
        results_output=args.results_out,
        model=args.model,
        target_gtins=args.gtins,
        api_key=args.api_key,
    )
