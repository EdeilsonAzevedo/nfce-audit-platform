"""
build_price_series.py

Lê o CSV de amostra e gera output/price_series.json com o formato:
  { "<gtin>": { "<YYYY-MM-DD>": <preco_medio_ponderado> } }

Execute uma vez (ou sempre que o CSV mudar):
  python pipeline/build_price_series.py
"""

import json
import pandas as pd
from pathlib import Path

BASE = Path(__file__).parent.parent
CSV = BASE / "data" / "raw" / "WorkshopSampleSEI_utf8.csv"
OUTPUT = BASE / "output" / "price_series.json"


def build():
    print(f"Lendo {CSV} ...")
    df = pd.read_csv(CSV, sep=" ", quotechar='"', on_bad_lines="skip", low_memory=False)

    df = df[df["gtin"].astype(str).str.strip() != "SEM GTIN"]
    df["valor_unit_liq"] = pd.to_numeric(df["valor_unit_liq"], errors="coerce")
    df["qtd_geral_item"] = pd.to_numeric(df["qtd_geral_item"], errors="coerce").fillna(1)
    df = df.dropna(subset=["data", "gtin", "valor_unit_liq"])
    df = df[df["valor_unit_liq"] > 0]

    df["val_pond"] = df["valor_unit_liq"] * df["qtd_geral_item"]

    agg = (
        df.groupby(["gtin", "data"])
        .agg(val_sum=("val_pond", "sum"), qty_sum=("qtd_geral_item", "sum"))
        .reset_index()
    )
    agg["preco"] = (agg["val_sum"] / agg["qty_sum"]).round(4)

    result: dict = {}
    for gtin, grp in agg.groupby("gtin"):
        result[str(gtin)] = dict(zip(grp["data"], grp["preco"].tolist()))

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)

    print(f"[✓] {OUTPUT.name} gerado — {len(result)} GTINs com dados de preço")


if __name__ == "__main__":
    build()
