# Dados — NFC-e Bahia

Os dados utilizados neste projeto são amostras de Notas Fiscais Eletrônicas
ao Consumidor (NFC-e) do Estado da Bahia, fornecidas pela **SEI-BA**
(Superintendência de Estudos Econômicos e Sociais da Bahia) para o
**Workshop CeMEAI 2026**.

---

## Estrutura esperada

```
data/
├── WorkshopSampleSEI_utf8.csv   # Base principal de NFC-e (pré-agregada)
├── Tabela_NCM_Vigente.xlsx      # Tabela NCM oficial (Receita Federal)
├── amostra_gtin_789.csv         # Amostra de GTINs iniciados com 789 (EAN-13 BR)
└── gtin_789_validacao.csv       # Resultado da validação de GTINs da amostra
```

## Esquema da base principal (`WorkshopSampleSEI_utf8.csv`)

| Coluna             | Tipo    | Descrição                                              |
|--------------------|---------|--------------------------------------------------------|
| `data`             | date    | Data de emissão da NFC-e (YYYY-MM-DD)                  |
| `des_item`         | string  | Descrição livre do produto (campo problemático)         |
| `ncm`              | string  | Código NCM de 8 dígitos declarado pelo emissor          |
| `gtin`             | string  | Código de barras EAN/GTIN (pode estar ausente ou errado)|
| `unidade`          | string  | Unidade de medida (UN, KG, LT, CX…)                    |
| `valor_unit_liq`   | float   | Valor unitário líquido em R$                            |
| `qtd_geral_item`   | float   | Quantidade total vendida (consolidada)                  |
| `qtd_reg_consolid` | int     | Número de registros/notas consolidados nessa linha      |

> A base já vem **pré-agregada**: cada linha representa uma combinação única
> de (data, descrição, NCM, GTIN, unidade, valor), não um registro por nota.

---

## Contato

**SEI-BA:** www.sei.ba.gov.br
