"""Offline example: read ANP by-well rows, build a field series and a fluid basis.

The two rows are excerpts of the public ANP file 2023_12_producao_Mar.csv
(Produção por Poço, December 2023). Run:  python examples/field_history.py
"""

from anp_well_production import (
    aggregate,
    fluid_basis,
    normalize,
    read_table_bytes,
    well_history,
)

HEADER = (
    "Estado;Bacia;Nome Poço ANP;Nome Poço Operador;Campo;Operador;Número do Contrato;Período;"
    "Óleo (bbl/dia);Condensado (bbl/dia);Petróleo (bbl/dia);Gás Natural (Mm³/dia) Assoc;"
    "Gás Natural (Mm³/dia) N Assoc;Gás Natural (Mm³/dia) Total;Volume Gás Royalties (m³/mês);"
    "Água (bbl/dia);Instalação Destino;Tipo Instalação;Tempo de Produção (hs por mês);Grau API;"
    "% em Volumes Metano;% em Volumes Etano;% em Volumes Propano;% em Volumes Iso-Butano;"
    "% em Volumes Butano;% em Volumes Iso-Pentano;% em Volumes n-Pentano;% em Volumes Hexanos;"
    "% em Volumes Heptanos;% em Volumes Octanos;% em Volumes Nonanos;% em Volumes Decanos;"
    "% em Volumes Undecanos;% em Volumes Oxigênio;% em Volumes Nitrogênio;% em Volumes Gás Carbônico"
)
ROW = (
    "Rio de Janeiro;Campos;7-PPT-50HP-RJS;7PPT50HPRJS;PAPA-TERRA;3R Petroleum;480000035569771;2023/12;"
    "4841,6358;0;4841,6358;31,0802;0;31,0802;961,627;1449,9353;PETROBRAS 61;UEP;729;;"
    "85,876;5,696;4,268;,878;1,287;,377;,353;,247;,148;,051;,006;0;0;0;,514;,299"
)


def main() -> None:
    headers, rows, meta = read_table_bytes((HEADER + "\n" + ROW + "\n").encode("cp1252"))
    records = normalize(headers, rows)
    field = aggregate(records, by=("field",))[0]
    print("field", field["field"], "liquid m3/d %.0f" % field["liquid_m3d"],
          "GOR sm3/sm3 %.1f" % field["gor_sm3_sm3"], "water cut %.2f" % field["water_cut"])
    history = well_history(records, "7-PPT-50HP-RJS")
    basis = fluid_basis(history[0])
    print("methane mole fraction %.3f" % basis["gas"]["mole_fraction"]["methane"])
    for warning in basis["warnings"][:2]:
        print("warning:", warning)


if __name__ == "__main__":
    main()
