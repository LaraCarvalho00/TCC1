"""Exporta CSVs novos e reutiliza as figuras da main sem conclusões antigas."""
from __future__ import annotations

import csv
import json
from pathlib import Path
import re
import sys

from .exportar_cenarios import export as export_scenarios
from .result_data import validation_rounds


def export(matrix_dir: str, out_dir: str) -> None:
    root = Path(matrix_dir)
    out = Path(out_dir)
    with (root / "matrix_index.csv").open(encoding="utf-8", newline="") as handle:
        index = list(csv.DictReader(handle))
    if not index or "validation_enabled" not in index[0]:
        raise ValueError("Use uma matriz com os metadados de validação.")
    fields = ("validation_enabled", "validation_questions", "test_every", "rounds",
              "dataset", "dataset_limit", "min_confidence")
    if len({tuple(row.get(k) for k in fields) for row in index}) != 1:
        raise ValueError("Exporte configurações metodológicas diferentes em pastas separadas.")
    calendars = {tuple(validation_rounds(row["output_dir"]) or []) for row in index}
    if len(calendars) != 1:
        raise ValueError("Validações concluídas divergem entre execuções.")
    calendar = next(iter(calendars))
    if out.exists() and any(out.iterdir()):
        raise FileExistsError("Pasta de exportação não vazia; preserve os resultados anteriores.")
    export_scenarios(str(root), str(out))

    # Individual validation accuracy is deliberately separate from consensus.
    rows = []
    for run in index:
        payload = json.loads((Path(run["output_dir"]) / "summary.json").read_text(encoding="utf-8"))
        for event in payload["summary"]["validation_events"]:
            evaluated = event["correct_total"] + event["incorrect_total"]
            rows.append({
                "experiment_id": run["experiment_id"], "nodes": run["nodes"],
                "malicious_pct": run["malicious_pct"], "collusion": run["collusion"],
                "mechanism": run["mechanism"], "seed": run["seed"],
                "round": event["round_number"], "status": event["status"],
                "questions": event["total_questions"], "correct": event["correct_total"],
                "incorrect": event["incorrect_total"], "timeouts": event["timeout_total"],
                "errors": event["error_total"],
                "accuracy": event["correct_total"] / evaluated if evaluated else "",
                "coverage": evaluated / (event["total_questions"] * event["total_nodes"]),
            })
    with (out / "validacao_por_execucao.csv").open("w", encoding="utf-8", newline="") as handle:
        columns = list(rows[0]) if rows else ["experiment_id", "round", "accuracy", "coverage"]
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    template = Path(__file__).resolve().parents[1] / "resultados" / "teste_fixo"
    figures = out / "figuras"
    figures.mkdir()
    style = (template / "figuras" / "estilo_figuras.tex").read_text(encoding="utf-8")
    interval = int(index[0]["test_every"])
    rounds = int(index[0]["rounds"])
    style = style.replace("xmax=53", f"xmax={rounds + 3}")
    style = style.replace("xtick={0,10,20,30,40,50}", "xtick={" + ",".join(map(str, [0, *calendar])) + "}")
    style = style.replace("mark repeat=10", f"mark repeat={interval}")
    style = style.replace("mark phase=9", f"mark phase={interval - 1}")
    if calendar:
        style = style.replace(r"\pgfplotsinvokeforeach{10,20,30,40,50}",
                              r"\pgfplotsinvokeforeach{" + ",".join(map(str, calendar)) + "}")
    else:
        style = re.sub(r"\\newcommand\{\\linhasDeTeste\}.*", r"\\newcommand{\\linhasDeTeste}{}\n\\newcommand{\\legendaRodadaDeTeste}{}", style, flags=re.S)
    style = style.replace("Rodada de teste", "Rodada de validação")
    (figures / "estilo_figuras.tex").write_text(style, encoding="utf-8")
    included = []
    for file in sorted((template / "figuras").glob("fig_*.tex")):
        content = file.read_text(encoding="utf-8")
        references = re.findall(r"\{(por_rodada/[^}]+\.csv)\}", content)
        if not references or not all((out / ref).exists() for ref in references):
            continue
        (figures / file.name).write_text(content, encoding="utf-8")
        included.append(r"\input{figuras/" + file.name + "}")
    document = "\n".join([
        r"\documentclass[11pt]{article}", r"\usepackage[T1]{fontenc}",
        r"\usepackage[utf8]{inputenc}", r"\usepackage[margin=2cm]{geometry}",
        r"\usepackage{pgfplots}", r"\usepgfplotslibrary{groupplots}",
        r"\usetikzlibrary{calc}", r"\input{figuras/estilo_figuras.tex}",
        r"\begin{document}", r"\section*{Validação por dataset}",
        "Simulação com respostas fabricadas; não representa execução da LLM. "
        "Acurácia do consenso medida antes da validação; reputação medida depois. "
        "As linhas verticais indicam validações concluídas.",
        *included, r"\end{document}", "",
    ])
    (out / "main.tex").write_text(document, encoding="utf-8")
    (out / "LEIA-ME.md").write_text(
        "# Resultados da integração\n\n"
        f"Execuções: {len(index)}. Validações concluídas: {list(calendar)}.\n\n"
        "Simulação por perfis, sem inferência real da LLM. O dataset não comprova "
        "proveniência de treinamento. O consenso é medido antes da validação e "
        "as curvas de reputação usam o checkpoint após a validação.\n\n"
        "`validacao_por_execucao.csv` separa a acurácia individual e a cobertura "
        "(respostas avaliáveis/consultas). Timeout/erro não conta como resposta errada. "
        "Os CSVs em `analise/` descrevem o consenso nas tarefas normais.\n\n"
        f"Figuras incluídas: {len(included)}; somente as que possuem todos os cenários necessários. "
        "Compile `main.tex` a partir desta pasta. Cada figura lê diretamente os CSVs; "
        "o estilo compartilhado preserva cores, marcadores e transparência da main.\n",
        encoding="utf-8",
    )
    print(f"Validação: {out}; {len(included)} figuras disponíveis.")


if __name__ == "__main__":
    export(sys.argv[1], sys.argv[2])
