import json
import io
import csv
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, jsonify, make_response, abort, send_file, request

app = Flask(__name__)

BASE = Path(__file__).parent
OUTPUT = BASE.parent / "output"

# ---------------------------------------------------------------------------
# Carrega dados na inicialização
# ---------------------------------------------------------------------------

with open(OUTPUT / "gtin_resolved.json", encoding="utf-8") as f:
    RESOLVED: list[dict] = json.load(f)

with open(OUTPUT / "gtin_index.json", encoding="utf-8") as f:
    INDEX: dict[str, list[dict]] = json.load(f)

with open(OUTPUT / "price_series.json", encoding="utf-8") as f:
    PRICE_SERIES: dict[str, dict[str, float]] = json.load(f)

DATA_RAW = BASE.parent / "data" / "raw"
with open(DATA_RAW / "aliquotas_icms_ba.json", encoding="utf-8") as f:
    ALIQUOTAS: dict[str, dict] = json.load(f)

RESOLVED_MAP: dict[str, dict] = {r["gtin"]: r for r in RESOLVED}

CAPITULOS_NCM = {
    "01": "Animais vivos",
    "02": "Carnes e miudezas comestíveis",
    "03": "Peixes e crustáceos",
    "04": "Leite, laticínios, ovos e mel",
    "05": "Outros produtos de origem animal",
    "07": "Legumes e hortaliças",
    "08": "Frutas e cascas cítricas",
    "09": "Café, chá, mate e especiarias",
    "10": "Cereais",
    "11": "Produtos da moagem; amido e féculas",
    "12": "Sementes e frutos oleaginosos",
    "15": "Gorduras e óleos animais ou vegetais",
    "16": "Preparações de carnes ou peixes",
    "17": "Açúcares e produtos de confeitaria",
    "18": "Cacau e suas preparações",
    "19": "Preparações à base de cereais (pão, biscoito, macarrão)",
    "20": "Preparações de legumes e frutas",
    "21": "Preparações alimentícias diversas",
    "22": "Bebidas, líquidos alcoólicos e vinagres",
    "24": "Fumo (tabaco) e sucedâneos",
    "30": "Produtos farmacêuticos",
    "33": "Cosméticos e perfumaria",
    "34": "Sabões e produtos de limpeza",
    "39": "Plásticos e suas obras",
    "48": "Papel e cartão",
    "61": "Vestuário de malha",
    "62": "Vestuário exceto de malha",
    "64": "Calçados",
    "84": "Máquinas e equipamentos",
    "85": "Eletroeletrônicos",
    "94": "Móveis",
    "95": "Brinquedos e artigos esportivos",
    "96": "Obras diversas",
}

def pad_ncm(raw) -> str | None:
    try:
        return str(int(raw)).zfill(8)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Páginas
# ---------------------------------------------------------------------------

@app.route("/")
def home():
    return render_template("home.html")


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html", active_page="dashboard")


@app.route("/auditoria")
def auditoria():
    return render_template("auditoria.html", active_page="auditoria")


@app.route("/inconsistencias")
def inconsistencias():
    return render_template("inconsistencias.html", active_page="inconsistencias")


@app.route("/explorador")
def explorador():
    return render_template("explorador.html", active_page="explorador")


@app.route("/perspectivas")
def perspectivas():
    return render_template("perspectivas.html", active_page="perspectivas")


@app.route("/metodologia")
def metodologia():
    return render_template("metodologia.html", active_page="metodologia")


@app.route("/autor")
def autor():
    return render_template("autor.html", active_page="autor")


@app.route("/cesta")
def cesta():
    return render_template("cesta.html", active_page="cesta")


@app.route("/relatorio-fraude")
def relatorio_fraude():
    return render_template("relatorio_fraude.html", active_page="relatorio_fraude")


@app.route("/fluxograma")
def fluxograma():
    return send_file(BASE / "fluxograma_metodologia.html")


@app.route("/api/gtin/<gtin>/update", methods=["POST"])
def api_update_gtin(gtin):
    resolved = RESOLVED_MAP.get(gtin)
    if not resolved:
        abort(404)
    data = request.get_json()
    allowed = {"descricao", "marca", "volume", "ncm"}
    for key in allowed:
        if key in data:
            resolved[key] = data[key] if data[key] else None
    with open(OUTPUT / "gtin_resolved.json", "w", encoding="utf-8") as f:
        json.dump(RESOLVED, f, ensure_ascii=False, indent=2)
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# APIs
# ---------------------------------------------------------------------------

@app.route("/api/stats")
def api_stats():
    high = sum(1 for r in RESOLVED if r.get("confianca", 0) >= 0.8)
    med  = sum(1 for r in RESOLVED if 0.6 <= r.get("confianca", 0) < 0.8)
    low  = sum(1 for r in RESOLVED if r.get("confianca", 0) < 0.6)

    brand_counter = Counter(
        r["marca"] for r in RESOLVED if r.get("marca")
    )
    top_brands = [{"marca": m, "count": c} for m, c in brand_counter.most_common(10)]

    ncm_counter = Counter(r.get("ncm") for r in RESOLVED if r.get("ncm"))
    top_ncms = [{"ncm": n, "count": c} for n, c in ncm_counter.most_common(10)]

    buckets = {"0.0–0.4": 0, "0.4–0.6": 0, "0.6–0.8": 0, "0.8–1.0": 0}
    for r in RESOLVED:
        v = r.get("confianca", 0)
        if v < 0.4:
            buckets["0.0–0.4"] += 1
        elif v < 0.6:
            buckets["0.4–0.6"] += 1
        elif v < 0.8:
            buckets["0.6–0.8"] += 1
        else:
            buckets["0.8–1.0"] += 1

    conf_distribution = [{"label": k, "count": v} for k, v in buckets.items()]

    return jsonify({
        "total": len(RESOLVED),
        "high_conf": high,
        "med_conf": med,
        "low_conf": low,
        "top_brands": top_brands,
        "top_ncms": top_ncms,
        "conf_distribution": conf_distribution,
    })


@app.route("/api/gtins")
def api_gtins():
    return jsonify(RESOLVED)


@app.route("/api/auditoria")
def api_auditoria():
    items = [r for r in RESOLVED if r.get("confianca", 0) < 0.75]
    items.sort(key=lambda r: r.get("confianca", 0))
    return jsonify(items)


@app.route("/api/inconsistencias")
def api_inconsistencias():
    result = []
    for gtin, records in INDEX.items():
        resolved = RESOLVED_MAP.get(gtin)
        if not resolved:
            continue

        ncm_counter = Counter(
            pad_ncm(r["ncm"]) for r in records if r.get("ncm") and pad_ncm(r["ncm"])
        )
        if not ncm_counter:
            continue

        ncm_original = ncm_counter.most_common(1)[0][0]
        ncm_resolvido = resolved.get("ncm")

        if ncm_original and ncm_resolvido and ncm_original != ncm_resolvido:
            result.append({
                "gtin": gtin,
                "descricao": resolved.get("descricao"),
                "ncm_original": ncm_original,
                "ncm_resolvido": ncm_resolvido,
                "confianca": resolved.get("confianca"),
                "motivo": resolved.get("motivo_confianca"),
            })

    result.sort(key=lambda x: x.get("confianca", 0))
    return jsonify(result)


@app.route("/api/gtin/<gtin>")
def api_gtin(gtin):
    resolved = RESOLVED_MAP.get(gtin)
    if not resolved:
        abort(404)

    raw_records = INDEX.get(gtin, [])
    desc_counter = Counter(
        r["des_item_norm"].strip().upper()
        for r in raw_records
        if r.get("des_item_norm")
    )
    desc_freq = [{"desc": d, "count": c} for d, c in desc_counter.most_common()]

    return jsonify({
        "resolved": resolved,
        "raw_records": raw_records,
        "desc_freq": desc_freq,
    })


@app.route("/api/serie-precos/<gtin>")
def api_serie_precos_gtin(gtin):
    """Série de preços de um único GTIN, agregada por período."""
    periodo = request.args.get("periodo", "mensal")
    daily = PRICE_SERIES.get(gtin)
    if not daily:
        return jsonify({"gtin": gtin, "periodos": [], "valores": [], "sem_dados": True})

    def to_periodo(date_str: str) -> str:
        if periodo == "semanal":
            d = datetime.strptime(date_str, "%Y-%m-%d")
            return d.strftime("%Y-W%V")
        return date_str[:7]

    buckets: dict[str, list] = defaultdict(list)
    for date_str, price in daily.items():
        buckets[to_periodo(date_str)].append(price)

    periodos = sorted(buckets)
    valores = [round(sum(buckets[p]) / len(buckets[p]), 4) for p in periodos]

    resolved = RESOLVED_MAP.get(gtin, {})
    label = resolved.get("descricao") or resolved.get("marca") or gtin

    return jsonify({"gtin": gtin, "label": label, "periodos": periodos, "valores": valores, "sem_dados": False})


@app.route("/api/serie-precos/fit/<gtin>")
def api_serie_precos_fit(gtin):
    """Ajusta curva polinomial à série de preço de um GTIN."""
    import numpy as np

    grau = min(int(request.args.get("grau", 2)), 5)
    base = api_serie_precos_gtin(gtin).get_json()
    if base["sem_dados"] or len(base["valores"]) <= grau:
        return jsonify({**base, "fitted": [], "coef": [], "grau": grau, "r2": None})

    valores = base["valores"]
    n = len(valores)
    xs = list(range(n))

    coef_arr = np.polyfit(xs, valores, grau)
    p_fn = np.poly1d(coef_arr)
    fitted = [round(float(p_fn(i)), 4) for i in xs]

    mean_y = sum(valores) / n
    ss_res = sum((y - p_fn(x)) ** 2 for x, y in zip(xs, valores))
    ss_tot = sum((y - mean_y) ** 2 for y in valores)
    r2 = round(1 - ss_res / ss_tot, 4) if ss_tot else None

    return jsonify({**base, "fitted": fitted, "coef": coef_arr.tolist(), "grau": grau, "r2": r2})


@app.route("/api/capitulos")
def api_capitulos():
    chapters: dict[str, dict] = {}
    for r in RESOLVED:
        gtin = r.get("gtin")
        ncm = r.get("ncm") or ""
        ncm_padded = pad_ncm(ncm) or ncm
        cap = ncm_padded[:2] if len(ncm_padded) >= 2 else "00"
        if cap not in chapters:
            chapters[cap] = {
                "capitulo": cap,
                "descricao": CAPITULOS_NCM.get(cap, f"Capítulo {cap}"),
                "gtins": [],
            }
        raw = INDEX.get(gtin, [])
        freq = sum(int(rec.get("qtd_reg_consolid") or 0) for rec in raw)
        chapters[cap]["gtins"].append({
            "gtin": gtin,
            "descricao": r.get("descricao") or r.get("marca") or gtin,
            "ncm": ncm_padded,
            "confianca": r.get("confianca"),
            "frequencia": freq,
        })

    for cap in chapters:
        chapters[cap]["gtins"].sort(key=lambda x: x["frequencia"], reverse=True)

    result = sorted(chapters.values(), key=lambda x: x["capitulo"])
    return jsonify(result)




@app.route("/api/relatorio-fraude")
def api_relatorio_fraude():
    CONF_MIN = 0.80
    result = []
    total_perda = 0.0

    for r in RESOLVED:
        gtin = r.get("gtin")
        confianca = r.get("confianca", 0)
        if confianca < CONF_MIN:
            continue

        ncm_resolvido = r.get("ncm")
        if not ncm_resolvido:
            continue

        raw_records = INDEX.get(gtin, [])
        if not raw_records:
            continue

        ncm_counter = Counter(
            pad_ncm(rec["ncm"]) for rec in raw_records if rec.get("ncm") and pad_ncm(rec["ncm"])
        )
        if not ncm_counter:
            continue

        ncm_declarado = ncm_counter.most_common(1)[0][0]
        if ncm_declarado == ncm_resolvido:
            continue

        ncm4_decl = ncm_declarado[:4] if ncm_declarado else None
        ncm4_corr = ncm_resolvido[:4] if ncm_resolvido else None

        aliq_decl = ALIQUOTAS.get(ncm4_decl, {}).get("aliquota_icms_pct", 0.0) if ncm4_decl else 0.0
        aliq_corr = ALIQUOTAS.get(ncm4_corr, {}).get("aliquota_icms_pct", 0.0) if ncm4_corr else 0.0
        delta_aliq = aliq_corr - aliq_decl

        if delta_aliq <= 0:
            continue

        # Agrega valores financeiros dos registros do gtin_index
        base_valor = 0.0
        freq_notas = 0
        for rec in raw_records:
            v = float(rec.get("valor_unit_liq") or 0)
            q = float(rec.get("qtd_geral_item") or 0)
            n = float(rec.get("qtd_reg_consolid") or 0)
            base_valor += v * q * n
            freq_notas += int(rec.get("qtd_reg_consolid") or 0)

        perda_icms = base_valor * (delta_aliq / 100)
        total_perda += perda_icms

        result.append({
            "gtin": gtin,
            "descricao": r.get("descricao"),
            "ncm_declarado": ncm_declarado,
            "ncm_correto": ncm_resolvido,
            "aliquota_declarada_pct": aliq_decl,
            "aliquota_correta_pct": aliq_corr,
            "delta_aliquota_pct": round(delta_aliq, 2),
            "base_valor_brl": round(base_valor, 2),
            "perda_icms_estimada_brl": round(perda_icms, 2),
            "frequencia_notas": freq_notas,
            "confianca": confianca,
            "motivo": r.get("motivo_confianca"),
        })

    result.sort(key=lambda x: x["perda_icms_estimada_brl"], reverse=True)

    return jsonify({
        "total_perda_brl": round(total_perda, 2),
        "total_gtins": len(result),
        "itens": result,
    })


@app.route("/api/export-relatorio-fraude")
def api_export_relatorio_fraude():
    dados = api_relatorio_fraude().get_json()
    itens = dados.get("itens", [])

    output = io.StringIO()
    fieldnames = [
        "gtin", "descricao", "ncm_declarado", "ncm_correto",
        "aliquota_declarada_pct", "aliquota_correta_pct", "delta_aliquota_pct",
        "base_valor_brl", "perda_icms_estimada_brl", "frequencia_notas", "confianca",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(itens)

    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = "attachment; filename=relatorio_fraude_icms.csv"
    return response


@app.route("/api/export-auditoria")
def api_export_auditoria():
    items = [r for r in RESOLVED if r.get("confianca", 0) < 0.75]
    items.sort(key=lambda r: r.get("confianca", 0))

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=["gtin", "descricao", "marca", "volume", "ncm", "confianca", "motivo_confianca"],
        extrasaction="ignore",
    )
    writer.writeheader()
    writer.writerows(items)

    response = make_response(output.getvalue())
    response.headers["Content-Type"] = "text/csv; charset=utf-8"
    response.headers["Content-Disposition"] = "attachment; filename=auditoria_gtin.csv"
    return response


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True, port=5000, threaded=True)
