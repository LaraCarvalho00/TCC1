"""Gráficos de cenários concluídos com inferência por nó.

Lê uma grade registrada em ``manifesto_grade.json`` e os CSVs por rodada.
Cenários interrompidos não entram nas métricas; espaços ausentes não são
interpolados. A saída deve ser uma pasta nova.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import sys


def _safe_component(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError(f"Identificador de cenário ou tentativa inválido: {value!r}")
    return value


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ler_grade(directory: Path):
    """Retorna configuração, métricas de cenários concluídos e arquivos fonte."""
    directory = directory.resolve(strict=True)
    manifest_path = directory / "manifesto_grade.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    config = manifest["configuracao"]
    n_nodes, n_rounds = int(config["nos"]), int(config["rodadas"])
    seeds = config["sementes"]
    if n_nodes <= 0 or n_rounds <= 0 or len(seeds) != 1:
        raise ValueError("A figura requer quantidade positiva de nós e rodadas e uma única semente.")
    scenarios = manifest["cenarios"]
    if not isinstance(scenarios, list) or not scenarios:
        raise ValueError("A grade precisa conter cenários planejados.")
    found = []
    sources = [manifest_path]
    seen = set()
    for entry in scenarios:
        identifier = _safe_component(entry["id"])
        frac, prob, score, seed = (float(entry["fracao_maliciosos"]), float(entry["audit_p"]),
                                   entry["nota"], int(entry["semente"]))
        key = (frac, prob, score, seed)
        if not 0 <= frac <= 1 or prob not in (0.1, 0.2) or score not in ("graded", "exact") or seed != int(seeds[0]):
            raise ValueError(f"Parâmetros inconsistentes no cenário {identifier}.")
        if abs(round(frac * n_nodes) - frac * n_nodes) > 1e-9:
            raise ValueError(f"A fração de {identifier} não corresponde a uma quantidade inteira de nós.")
        if key in seen:
            raise ValueError(f"Cenário duplicado: {key}.")
        seen.add(key)
        if entry.get("status") != "concluido":
            continue
        attempts = entry["tentativas"]
        if not attempts or attempts[-1].get("status") != "concluido":
            raise ValueError(f"Tentativa final de {identifier} não está concluída.")
        attempt_id = _safe_component(attempts[-1]["id"])
        result_dir = directory / "cenarios" / identifier / attempt_id
        summary_path, rows_path = result_dir / "summary.json", result_dir / "rounds.csv"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        with rows_path.open(encoding="utf-8-sig", newline="") as file:
            rows = list(csv.DictReader(file))
        if len(rows) != n_rounds or sorted(int(row["round_index"]) for row in rows) != list(range(n_rounds)):
            raise ValueError(f"Número ou índices de rodadas inconsistentes em {identifier}.")
        for row in rows:
            if int(row["num_nodes"]) != n_nodes:
                raise ValueError(f"Quantidade de nós inconsistente em {identifier}.")
            if any(row[field] not in ("0", "1") for field in ("audited", "calibration", "consensus_correct")):
                raise ValueError(f"Indicadores de rodada inválidos em {identifier}.")
        if int(summary["summary"]["rounds"]) != n_rounds:
            raise ValueError(f"Resumo inconsistente em {identifier}.")
        eligible = [row for row in rows if row["audited"] == "0" and row["calibration"] == "0"]
        correct = sum(int(row["consensus_correct"]) for row in eligible)
        audited = sum(int(row["audited"]) for row in rows)
        run_config = summary.get("config", {})
        strategy = run_config.get("malicious_strategy", "knows_schedule")
        if strategy not in ("knows_schedule", "on_off"):
            raise ValueError(f"Estratégia maliciosa não suportada na figura de ataque: {strategy!r}.")
        if strategy == "knows_schedule" and run_config.get("audit_mode", "random") != "random":
            raise ValueError("Figura de ataque exige conferência aleatória para a estratégia knows_schedule.")
        warmup = int(run_config.get("honest_rounds", config.get("rodadas_iniciais_honestas", 5)))
        if "rodadas_iniciais_honestas" in config and warmup != int(config["rodadas_iniciais_honestas"]):
            raise ValueError(f"Rodadas iniciais inconsistentes no cenário {identifier}.")
        if warmup < 0:
            raise ValueError("Número de rodadas iniciais inválido.")
        attacking = [row for row in eligible if int(row["round_index"]) >= warmup]
        attack_correct = sum(int(row["consensus_correct"]) for row in attacking)
        found.append({"id": identifier, "fracao_maliciosos": frac, "nos_maliciosos": round(frac * n_nodes),
                      "audit_p": prob, "nota": score, "semente": seed, "acertos": correct,
                      "rodadas_avaliadas": len(eligible), "rodadas_auditadas": audited,
                      "acuracia": correct / len(eligible) if eligible else None,
                      "rodadas_iniciais_honestas": warmup, "acertos_com_ataque": attack_correct,
                      "rodadas_com_ataque_avaliadas": len(attacking),
                      "acuracia_com_ataque": attack_correct / len(attacking) if attacking else None})
        sources.extend((summary_path, rows_path))
    if not found:
        raise ValueError("Ainda não há cenário concluído para representar.")
    return config, scenarios, found, sources


def gerar(grade: Path, output: Path):
    config, scenarios, rows, sources = ler_grade(grade)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output.mkdir(parents=True, exist_ok=False)
    fields = ("id", "fracao_maliciosos", "nos_maliciosos", "audit_p", "nota", "semente",
              "acertos", "rodadas_avaliadas", "rodadas_auditadas", "acuracia",
              "rodadas_iniciais_honestas", "acertos_com_ataque", "rodadas_com_ataque_avaliadas", "acuracia_com_ataque")
    with (output / "dados_grafico.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
    fig, axes = plt.subplots(1, 2, figsize=(12, 6.7), sharey=True)
    partial = len(rows) < len(scenarios)
    title = "Acurácia do consenso por proporção de nós maliciosos"
    if partial:
        title += " — resultados parciais"
    fig.suptitle(title, fontsize=16, fontweight="bold", x=0.08, y=0.98, ha="left")
    fig.text(0.08, 0.91, f"{config['nos']} nós · {config['rodadas']} rodadas · uma semente · "
             f"{len(rows)}/{len(scenarios)} cenários concluídos", color="#666b73", fontsize=10)
    fractions = sorted({float(entry["fracao_maliciosos"]) for entry in scenarios})
    for ax, score, title_score in zip(axes, ("exact", "graded"), ("Nota exata", "Nota graduada")):
        for probability, color, marker in ((0.1, "#24629f", "o"), (0.2, "#187952", "s")):
            values = []
            for frac in fractions:
                value = next((row["acuracia"] for row in rows if row["fracao_maliciosos"] == frac
                              and row["audit_p"] == probability and row["nota"] == score), None)
                values.append(value * 100 if value is not None else float("nan"))
            ax.plot([f * 100 for f in fractions], values, color=color, marker=marker, linewidth=2,
                    markersize=6, label=f"Conferência p = {str(probability).replace('.', ',')}")
        ax.set_title(title_score, loc="left", fontweight="bold")
        # A small margin keeps markers at 0% and 100% fully visible.
        ax.set_ylim(-3, 103)
        ax.set_yticks(range(0, 101, 20))
        ax.set_xticks([f * 100 for f in fractions])
        ax.set_xlim(min(fractions) * 100 - 3, max(fractions) * 100 + 3)
        ax.set_xlabel("Nós maliciosos (%)")
        ax.grid(axis="y", alpha=0.22)
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("Acurácia do consenso (%)")
    fig.legend(*axes[0].get_legend_handles_labels(), loc="lower center", ncol=2, frameon=False,
               bbox_to_anchor=(0.5, 0.09))
    fig.text(0.08, 0.03, "Apenas rodadas sem conferência nem calibração; sem barras de erro.",
             color="#666b73", fontsize=9)
    fig.subplots_adjust(left=0.08, right=0.98, top=0.82, bottom=0.23, wspace=0.13)
    for ext in ("png", "pdf"):
        fig.savefig(output / f"acuracia_cenarios.{ext}", dpi=220, facecolor="white")
    plt.close(fig)

    fig, axes = plt.subplots(1, 2, figsize=(12, 6.7), sharey=True)
    title = "Acurácia do consenso nas rodadas com ataque"
    if partial:
        title += " — resultados parciais"
    fig.suptitle(title, fontsize=16, fontweight="bold", x=0.08, y=0.98, ha="left")
    fig.text(0.08, 0.91, f"{config['nos']} nós · {config['rodadas']} rodadas · uma semente · "
             f"{len(rows)}/{len(scenarios)} cenários concluídos", color="#666b73", fontsize=10)
    for ax, score, title_score in zip(axes, ("exact", "graded"), ("Nota exata", "Nota graduada")):
        for probability, color, marker in ((0.1, "#24629f", "o"), (0.2, "#187952", "s")):
            values = []
            for frac in fractions:
                row = next((row for row in rows if row["fracao_maliciosos"] == frac
                            and row["audit_p"] == probability and row["nota"] == score), None)
                value = row["acuracia_com_ataque"] if row else None
                values.append(value * 100 if value is not None else float("nan"))
            ax.plot([f * 100 for f in fractions], values, color=color, marker=marker, linewidth=2,
                    markersize=6, label=f"Conferência p = {str(probability).replace('.', ',')}")
        ax.set_title(title_score, loc="left", fontweight="bold")
        ax.set_ylim(-3, 103)
        ax.set_yticks(range(0, 101, 20))
        ax.set_xticks([f * 100 for f in fractions])
        ax.set_xlim(min(fractions) * 100 - 3, max(fractions) * 100 + 3)
        ax.set_xlabel("Nós maliciosos (%)")
        ax.grid(axis="y", alpha=0.22)
        ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("Acurácia do consenso (%)")
    fig.legend(*axes[0].get_legend_handles_labels(), loc="lower center", ncol=2, frameon=False,
               bbox_to_anchor=(0.5, 0.09))
    fig.text(0.08, 0.03, "Após imitação inicial; sem conferência nem calibração. Amostras pequenas.",
             color="#666b73", fontsize=9)
    fig.subplots_adjust(left=0.08, right=0.98, top=0.82, bottom=0.23, wspace=0.13)
    for ext in ("png", "pdf"):
        fig.savefig(output / f"acuracia_com_ataque.{ext}", dpi=220, facecolor="white")
    plt.close(fig)

    warmups = sorted({row["rodadas_iniciais_honestas"] for row in rows})
    if len(warmups) == 1:
        warmup_caption = f"{warmups[0]} rodada(s) inicial(is) em que os maliciosos imitam honestos"
    else:
        warmup_caption = "quantidades distintas de rodadas iniciais por cenário (ver CSV)"
    attack_counts = []
    for probability in sorted({row["audit_p"] for row in rows}):
        denominators = sorted({row["rodadas_com_ataque_avaliadas"] for row in rows if row["audit_p"] == probability})
        count_text = ", ".join(str(value) for value in denominators)
        attack_counts.append(f"p={str(probability).replace('.', ',')}: {count_text} rodada(s) elegível(is)")
    attack_counts_caption = "; ".join(attack_counts)

    caption = f"""# Comparação dos cenários de inferência

Foram planejados {len(scenarios)} cenários; {len(rows)} estavam concluídos ao gerar esta figura.
Cada cenário tem {config['nos']} nós, {config['rodadas']} rodadas e uma única semente.
Semente: {config['sementes'][0]}; critério de escolha: {config.get('criterio_semente', 'não registrado')}.
Pontos ausentes correspondem a cenários não concluídos ou sem rodadas elegíveis; eles não são estimados.

A acurácia é a proporção de respostas do consenso ponderado que coincidem exatamente com o gabarito
entre as rodadas sem conferência e sem calibração. Rodadas de teste sem conferência também são incluídas.
Os numeradores e denominadores, o número de conferências e a semente de cada ponto estão em `dados_grafico.csv`.
Com uma única semente não se calculam intervalos de confiança ou significância estatística.

Os painéis distinguem a nota aplicada na conferência. As cores indicam a probabilidade de sorteio,
que não garante uma quantidade fixa de rodadas auditadas. As séries podem ter denominadores diferentes.
Com apenas {config['rodadas']} rodadas, cada rodada tem grande influência sobre a porcentagem.
O primeiro gráfico também inclui as rodadas iniciais em que os maliciosos imitam honestos.
O segundo gráfico considera somente as rodadas após essa imitação inicial, ainda excluindo
conferência e calibração; os respectivos acertos e denominadores constam no mesmo CSV.
Há {warmup_caption}. Para os cenários concluídos, a quantidade observada de rodadas com
ataque sem conferência nem calibração é: {attack_counts_caption}. Esses números são
obtidos dos próprios resultados e podem variar entre cenários. São amostras pequenas e com denominadores distintos;
as diferenças podem refletir a seleção das rodadas, não somente o valor de p.
"""
    (output / "LEGENDA_E_METODOLOGIA.md").write_text(caption, encoding="utf-8")
    manifest = {"cenarios_planejados": len(scenarios), "cenarios_concluidos": len(rows),
                "fontes": [{"caminho": str(p.resolve()), "sha256": _sha(p)} for p in sources],
                "criterio": "acertos do consenso nas rodadas sem conferência nem calibração"}
    (output / "manifesto.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Gera comparação de cenários com inferência real")
    parser.add_argument("--grade", type=Path, required=True)
    parser.add_argument("--saida", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        gerar(args.grade, args.saida)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"Não foi possível gerar os gráficos: {exc}", file=sys.stderr)
        return 1
    print(f"Gráfico e dados: {args.saida.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
