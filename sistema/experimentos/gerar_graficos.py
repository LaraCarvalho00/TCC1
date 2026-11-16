"""Gera gráficos das séries experimentais a partir de resultados concluídos.

Exemplo: python -m sistema.experimentos.gerar_graficos --ruido DIR --centros DIR
  --sensibilidade DIR --instabilidade DIR --saida NOVO_DIR
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from sistema.core.answer import normalize


FRACTIONS = (0, 0.05, 0.20, 0.25, 0.35, 0.50, 0.65, 0.80)
EFFECTIVE = tuple(round(50 * f) * 2 for f in FRACTIONS)
BLUE = "#24629f"
ORANGE = "#d26a22"
GREEN = "#187952"
GRAY = "#666b73"
BLACK = "#202632"


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def _completed(directory: Path, expected: int, name: str) -> dict:
    manifest = json.loads((directory / "manifesto.json").read_text(encoding="utf-8"))
    if (manifest.get("status") != "concluido" or manifest.get("concluidas") != expected
            or (manifest.get("experimento") or manifest.get("serie")) != name):
        raise ValueError(f"O lote {directory} não registra {expected} execuções concluídas de {name}")
    return manifest


def _find(rows: list[dict], **filters) -> dict:
    def match(row):
        return all(abs(float(row[key]) - value) < 1e-9 if isinstance(value, float)
                   else str(row[key]) == str(value) for key, value in filters.items())
    found = [row for row in rows if match(row)]
    if len(found) != 1:
        raise ValueError(f"Esperava um registro para {filters}; encontrados {len(found)}")
    return found[0]


def _result(rows, config, collusion, fraction, noise="sutil_0.2", grade="exact", **extra):
    return _find(rows, config=config, conluio=str(collusion), fracao=float(fraction),
                 ruido=noise, nota_gabarito=grade, **extra)


def _rate(row, key="com_reputacao_sem_gabarito_media"):
    value = row[key]
    if value == "":
        raise ValueError(f"Métrica ausente: {key}")
    return float(value) * 100


def _figure(title: str, subtitle: str, ncols: int = 1, figsize=(11.2, 6.4), sharey=False):
    fig, axes = plt.subplots(1, ncols, figsize=figsize, sharey=sharey, squeeze=False)
    fig.suptitle(title, fontsize=17, weight="bold", x=0.08, y=0.98, ha="left")
    fig.text(0.08, 0.925, subtitle, fontsize=10, color=GRAY, ha="left")
    return fig, axes[0]


def _axis(ax, x_label=True):
    ax.grid(axis="y", alpha=0.22, linewidth=0.7)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
    if x_label:
        ax.set_xlabel("Nós maliciosos na rede (%)")
    ax.set_xticks(EFFECTIVE)
    ax.set_ylim(0, 100)


def _save(fig, directory: Path, name: str):
    for ext in ("png", "pdf"):
        fig.savefig(directory / f"{name}.{ext}", dpi=220, facecolor="white")
    plt.close(fig)


def _validate_manifests(r: Path, c: Path, banco: Path, *, complementares: Path | None = None,
                        sensibilidade: Path | None = None, instabilidade: Path | None = None) -> list[Path]:
    if complementares is not None:
        if sensibilidade is not None or instabilidade is not None:
            raise ValueError("Use o lote complementar único ou as duas séries separadas, sem misturá-los")
        extras = [complementares]
        manifests = [_completed(complementares, 160, "todas")]
    else:
        if sensibilidade is None or instabilidade is None:
            raise ValueError("Informe --complementares ou ambas --sensibilidade e --instabilidade")
        extras = [sensibilidade, instabilidade]
        manifests = [_completed(sensibilidade, 120, "sensibilidade"),
                     _completed(instabilidade, 30, "instabilidade")]
    manifests += [_completed(r, 2560, "ruido"), _completed(c, 960, "centros")]
    bank_hash = hashlib.sha256(banco.read_bytes()).hexdigest()
    if any(manifest.get("banco_sha256") != bank_hash for manifest in manifests):
        raise ValueError("O banco informado não corresponde ao banco usado em todos os lotes")
    return [directory / "resumo.csv" for directory in extras]


def gerar(ruido: Path, centros: Path, banco: Path, output: Path, *,
          complementares: Path | None = None, sensibilidade: Path | None = None,
          instabilidade: Path | None = None):
    epaths = _validate_manifests(ruido, centros, banco, complementares=complementares,
                                 sensibilidade=sensibilidade, instabilidade=instabilidade)
    rpath, ppath = ruido / "resumo.csv", ruido / "reputacao_por_rodada.csv"
    cpath = centros / "resumo.csv"
    rows, reputation, center = map(_rows, (rpath, ppath, cpath))
    extra = [row for path in epaths for row in _rows(path)]
    data = json.loads(banco.read_text(encoding="utf-8"))
    tasks = data["tarefas"]
    model_name = data.get("parametros", {}).get("modelo")
    if not isinstance(model_name, str) or not model_name.strip():
        raise ValueError("O banco deve informar o modelo em parametros.modelo")
    if len(tasks) != 50 or any(len(task["amostras"]) != 20 for task in tasks):
        raise ValueError("O banco deve conter 50 questões com 20 respostas cada")
    correct_counts = [sum(normalize(sample.get("resposta")) is not None and
                          normalize(sample.get("resposta")) == normalize(task["answer"])
                          for sample in task["amostras"]) for task in tasks]
    output.mkdir(parents=True, exist_ok=False)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.labelcolor": BLACK, "xtick.color": BLACK, "ytick.color": BLACK})

    # Figura 2: mesmo conjunto de respostas para o medoide sem peso e consenso.
    fig, axes = _figure("Conferência e conluio", "Acurácia nas rodadas sem conferência nem calibração · distância 0,2 · nota exata", 2, (12, 7), True)
    strategies = (("sem_genese", "Sem conferência", GRAY, "o"),
                  ("com_genese", "Calibração e calendário", ORANGE, "s"),
                  ("auditoria_p10", "Sorteio: p = 0,1", BLUE, "^"),
                  ("auditoria_p20", "Sorteio: p = 0,2", GREEN, "D"))
    for ax, collusion, title in zip(axes, (0, 1), ("Sem conluio", "Com conluio")):
        for config, label, color, marker in strategies:
            values = [_rate(_result(rows, config, collusion, f)) for f in FRACTIONS]
            ax.plot(EFFECTIVE, values, color=color, marker=marker, linewidth=2, markersize=5, label=label)
        values = [_rate(_result(rows, "sem_genese", collusion, f), "sem_reputacao_sem_gabarito_media") for f in FRACTIONS]
        ax.plot(EFFECTIVE, values, color=BLACK, marker="x", linestyle="--", linewidth=1.7, label="Medoide sem pesos¹")
        _axis(ax)
        ax.set_title(title, loc="left", fontsize=12, weight="bold")
    axes[0].set_ylabel("Acurácia média (%)")
    fig.legend(*axes[0].get_legend_handles_labels(), loc="lower center", ncol=3, frameon=False, bbox_to_anchor=(0.5, 0.055), fontsize=9)
    fig.text(0.08, 0.018, "¹ Mesmo conjunto de respostas da condição sem conferência. Médias de cinco sementes.", fontsize=9, color=GRAY)
    fig.subplots_adjust(left=0.08, right=0.98, top=0.84, bottom=0.27, wspace=0.12)
    _save(fig, output, "01_conferencia_conluio")

    # Figura 3: nota e ruído, auditados com p=0,2, conluio.
    fig, axes = _figure("Nota e intensidade da perturbação", "Acurácia nas rodadas sem conferência nem calibração · conluio · sorteio p = 0,2", 2, (12, 6.6), True)
    attacks = (("alto", "Corrupção alta", BLACK, "o"), ("sutil_0.5", "Distância 0,5", "#ac7924", "s"),
               ("sutil_0.2", "Distância 0,2", BLUE, "^"), ("sutil_0.05", "Distância 0,05", GREEN, "D"))
    for ax, grade, title in zip(axes, ("graded", "exact"), ("Nota graduada", "Nota exata")):
        for noise, label, color, marker in attacks:
            ax.plot(EFFECTIVE, [_rate(_result(rows, "auditoria_p20", 1, f, noise, grade)) for f in FRACTIONS],
                    color=color, marker=marker, linewidth=2, markersize=5, label=label)
        _axis(ax)
        ax.set_title(title, loc="left", fontsize=12, weight="bold")
    axes[0].set_ylabel("Acurácia média (%)")
    fig.legend(*axes[0].get_legend_handles_labels(), loc="lower center", ncol=4, frameon=False, bbox_to_anchor=(0.5, 0.06), fontsize=9)
    fig.text(0.08, 0.02, "Cada ponto é a média de cinco sementes.", fontsize=9, color=GRAY)
    fig.subplots_adjust(left=0.08, right=0.98, top=0.83, bottom=0.25, wspace=0.12)
    _save(fig, output, "02_nota_perturbacao")

    # Figura 4: curvas da média de reputação.
    fig, axes = _figure("Evolução da reputação", "Reputação média de consenso · conluio · distância 0,2 · sorteio p = 0,2", 2, (12, 6.5), True)
    for ax, frac, title in zip(axes, (0.5, 0.8), ("50% de nós maliciosos", "80% de nós maliciosos")):
        for grade, style, grade_label in (("exact", "-", "exata"), ("graded", "--", "graduada")):
            for column, color, group in (("reputacao_media_honestos", BLUE, "Honestos"), ("reputacao_media_maliciosos", ORANGE, "Maliciosos")):
                selected = [row for row in reputation if row["config"] == "auditoria_p20" and row["conluio"] == "1"
                            and row["ruido"] == "sutil_0.2" and row["nota_gabarito"] == grade
                            and abs(float(row["fracao"]) - frac) < 1e-9 and row[column] != ""]
                series = sorted((int(row["rodada"]), float(row[column])) for row in selected)
                if len(series) != 51 or [p[0] for p in series] != list(range(51)):
                    raise ValueError(f"Série de reputação incompleta: {frac}, {grade}, {group}")
                ax.plot([p[0] for p in series], [p[1] for p in series], color=color, linestyle=style, linewidth=2, label=f"{group} · nota {grade_label}")
        ax.set_title(title, loc="left", fontsize=12, weight="bold")
        ax.set_xlabel("Rodadas concluídas")
        ax.set_ylim(0, 1)
        ax.set_xlim(0, 50)
        ax.grid(axis="y", alpha=0.22)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("Reputação média de consenso")
    fig.legend(*axes[0].get_legend_handles_labels(), loc="lower center", ncol=4, frameon=False, bbox_to_anchor=(0.5, 0.065), fontsize=9)
    fig.text(0.08, 0.02, "O ponto zero é a reputação inicial. Cada curva é a média de cinco sementes.", fontsize=9, color=GRAY)
    fig.subplots_adjust(left=0.08, right=0.98, top=0.83, bottom=0.25, wspace=0.12)
    _save(fig, output, "03_reputacao_por_rodada")

    # Comparação dos centros; o mesmo conjunto de condições do texto.
    fig, (ax,) = _figure("Centro da agregação", "Acurácia nas rodadas sem conferência · conluio · distância 0,2 · nota exata · sorteio p = 0,2")
    for value, label, color, marker in (("medoid", "Medoide", BLUE, "o"), ("median", "Mediana", GREEN, "s"), ("mean", "Média", ORANGE, "^")):
        ys = [_rate(_result(center, "auditoria_p20", 1, f, centro=value)) for f in FRACTIONS]
        ax.plot(EFFECTIVE, ys, marker=marker, linewidth=2.2, color=color, label=label)
    _axis(ax)
    ax.set_ylabel("Acurácia média (%)")
    fig.legend(*ax.get_legend_handles_labels(), loc="lower center", frameon=False, ncol=3, bbox_to_anchor=(0.5, 0.08))
    fig.text(0.08, 0.035, "Médias de cinco sementes; acurácia exige igualdade exata com o gabarito.", fontsize=9, color=GRAY)
    fig.subplots_adjust(left=0.08, right=0.97, top=0.82, bottom=0.23)
    _save(fig, output, "04_centros_consenso")

    # Instabilidade: baseline obtida do lote de ruído, séries adicionais do lote complementar.
    fig, (ax,) = _figure("Efeito de nós instáveis", "Acurácia nas rodadas sem conferência · conluio · distância 0,2 · nota exata · sorteio p = 0,2")
    positions = np.arange(3)
    for offset, share, color, label in ((-0.25, 0, BLUE, "0% instáveis"), (0, 0.1, ORANGE, "10% instáveis"), (0.25, 0.2, GREEN, "20% instáveis")):
        means, errors = [], []
        for frac in (0.5, 0.65, 0.8):
            if share == 0:
                point = _result(rows, "auditoria_p20", 1, frac)
                means.append(_rate(point)); errors.append(float(point["com_reputacao_sem_gabarito_dp"]) * 100)
            else:
                point = _find(extra, serie="instabilidade", fracao=float(frac), instaveis=float(share))
                means.append(float(point["acuracia_media"]) * 100); errors.append(float(point["acuracia_dp"]) * 100)
        ax.bar(positions + offset, means, width=0.24, color=color, label=label, yerr=errors, capsize=3, error_kw={"elinewidth": 1})
    ax.set_xticks(positions, ["50", "64", "80"])
    ax.set_xlabel("Nós maliciosos na rede (%)")
    ax.set_ylabel("Acurácia média (%)")
    ax.set_ylim(0, 100)
    ax.grid(axis="y", alpha=0.22); ax.set_axisbelow(True); ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, ncol=3, loc="upper right")
    fig.text(0.08, 0.035, "Barras de erro: desvio-padrão amostral de cinco sementes, em pontos percentuais.", fontsize=9, color=GRAY)
    fig.subplots_adjust(left=0.08, right=0.97, top=0.82, bottom=0.17)
    _save(fig, output, "05_instabilidade")

    # Tabela visual das nove configurações da tabela de sensibilidade.
    fig, (ax,) = _figure("Sensibilidade da reputação", "Acurácia nas rodadas sem conferência · conluio · distância 0,2 · nota exata · sorteio p = 0,2", figsize=(11.2, 7.4))
    specs = [("ema", c, g, f"EMA simétrica · αc={str(c).replace('.', ',')} · αg={str(g).replace('.', ',')}")
             for c in (0.05, 0.3) for g in (0.5, 0.8, 0.95)]
    specs += [("ema_slow_up", 0.05, 0.8, "Subida lenta · αc=0,05 · αg=0,8"),
              ("ema_asymmetric", 0.05, 0.8, "EMA assimétrica · αc=0,05 · αg=0,8"),
              ("beta", 0.05, 0.8, "Beta · αc=0,05 · αg=0,8")]
    values = []
    for mechanism, consensus, oracle, _ in specs:
        row = []
        for frac in (0.5, 0.65, 0.8):
            if mechanism == "ema_slow_up":
                row.append(_rate(_result(rows, "auditoria_p20", 1, frac)))
            else:
                entry = _find(extra, serie="sensibilidade", mecanismo=mechanism, alpha_consenso=float(consensus),
                              alpha_gabarito=float(oracle), fracao=float(frac))
                row.append(float(entry["acuracia_media"]) * 100)
        values.append(row)
    matrix = np.array(values)
    heat = ax.imshow(matrix, cmap="Blues", vmin=0, vmax=100, aspect="auto")
    ax.set_xticks(range(3), ["50%", "64%", "80%"])
    ax.set_xlabel("Nós maliciosos na rede")
    ax.set_yticks(range(len(specs)), [item[3] for item in specs], fontsize=9)
    ax.tick_params(length=0)
    for i in range(len(specs)):
        for j in range(3):
            ax.text(j, i, f"{matrix[i, j]:.1f}%".replace(".", ","), ha="center", va="center", color="white" if matrix[i, j] > 58 else BLACK, fontsize=10)
    bar = fig.colorbar(heat, ax=ax, pad=0.03)
    bar.set_label("Acurácia média (%)")
    fig.text(0.08, 0.058, "αc: taxa de consenso; αg: taxa pelo gabarito (na subida lenta, taxa de descida).", fontsize=9, color=GRAY)
    fig.text(0.08, 0.025, "Cada célula: média de cinco sementes. Desvios-padrão no CSV de resultados.", fontsize=9, color=GRAY)
    fig.subplots_adjust(left=0.36, right=0.95, top=0.82, bottom=0.15)
    _save(fig, output, "06_sensibilidade")

    # O banco foi gerado anteriormente; não confundir com uma nova inferência.
    total_correct = sum(correct_counts)
    overall = 100 * total_correct / 1000
    fig, (ax,) = _figure("Respostas do modelo por questão", f"Banco pré-gerado · {model_name} · 50 questões · 20 respostas por questão", figsize=(12, 6.7))
    indices = list(range(1, 51))
    ax.bar(indices, [count * 5 for count in correct_counts], color=BLUE, width=0.8, label="Acerto por questão")
    ax.axhline(overall, color=ORANGE, linestyle="--", linewidth=2,
               label=f"Banco completo: {total_correct}/1000 = {overall:.1f}%".replace(".", ","))
    ax.set_xlim(0, 51)
    ax.set_ylim(0, 105)
    ax.set_xticks([1, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50])
    ax.set_xlabel("Questão no banco")
    ax.set_ylabel("Respostas corretas por questão (%)")
    ax.set_axisbelow(True); ax.grid(axis="y", alpha=0.22); ax.spines[["top", "right"]].set_visible(False)
    ax.legend(loc="lower center", frameon=False, ncol=2, bbox_to_anchor=(0.5, -0.27))
    fig.text(0.08, 0.025, "Acerto por igualdade exata após extração da resposta; respostas ausentes contam como erro.", fontsize=9, color=GRAY)
    fig.subplots_adjust(left=0.08, right=0.97, top=0.82, bottom=0.25)
    _save(fig, output, "07_banco_modelo")

    captions = """# Gráficos dos experimentos de inferência distribuída

As figuras 1 a 6 foram geradas a partir dos resultados consolidados de simulações com 50 nós, 50 rodadas e cinco sementes. As respostas honestas são sorteadas do banco pré-gerado de 50 questões e 1.000 respostas; não há nova execução da LLM durante as rodadas. Os percentuais do eixo horizontal representam a quantidade efetiva de nós maliciosos; por exemplo, 32 de 50 correspondem a 64%. A figura 7 descreve diretamente o banco de respostas, sem simular rede ou usar sementes de simulação.

1. **Conferência e conluio** — compara acurácia ponderada sem conferência, com calibração e calendário, e com sorteio p=0,1 ou p=0,2. O medoide sem pesos usa as respostas da configuração sem conferência. Distância 0,2 e nota exata; resultados médios nas rodadas sem gabarito nem calibração. As configurações diferem também em calibração, atualização e conjunto de rodadas avaliadas; não se pode atribuir a diferença somente ao sorteio.
2. **Nota e perturbação** — comparação das notas graduada e exata sob conluio e sorteio p=0,2, por intensidade da corrupção.
3. **Reputação por rodada** — médias de reputação de consenso dos perfis honesto e malicioso em 50% e 80% de maliciosos, com conluio, distância 0,2 e sorteio p=0,2. Linha contínua: nota exata; tracejada: graduada. Rodada zero é o estado inicial.
4. **Centros de consenso** — compara medoide, mediana e média sob conluio, distância 0,2, nota exata e sorteio p=0,2. A acurácia mede igualdade exata com o gabarito.
5. **Instabilidade** — compara 0%, 10% e 20% de nós instáveis, com conluio, distância 0,2, nota exata e conferência por sorteio p=0,2. O eixo vertical mostra a acurácia nas rodadas sem conferência nem calibração. As barras de erro são desvios-padrão amostrais das cinco sementes, em pontos percentuais. O caso sem instabilidade vem da série de ruído.
6. **Sensibilidade** — acurácia média para diferentes mecanismos e taxas de consenso e de gabarito, sob conluio, distância 0,2, nota exata e sorteio p=0,2. αc é a taxa de consenso; αg, a taxa de atualização pelo gabarito, que na subida lenta é a taxa de descida. A subida lenta de referência vem da série de ruído; os desvios estão no CSV complementar.
7. **Banco de respostas do modelo** — percentual de acerto das 20 respostas pré-geradas para cada uma das 50 questões. A linha horizontal mostra o percentual das 1.000 respostas do banco. A resposta extraída é comparada exatamente ao gabarito; respostas ausentes são erros. Essa figura descreve o banco histórico, e não uma nova execução de inferência.

A acurácia nas rodadas sem conferência exclui também as rodadas de calibração. Essas curvas mostram resultados experimentais, não uma implantação física distribuída nem uma nova medição do modelo.
"""
    (output / "LEGENDA_E_METODOLOGIA.md").write_text(captions, encoding="utf-8")
    sources = (rpath, ppath, cpath, *epaths, banco)
    manifest = {"fontes": [{"caminho": str(p.resolve()), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in sources],
                "graficos": [f"{i:02d}" for i in range(1, 8)], "criterio": "médias e séries dos CSVs consolidados e banco pré-gerado"}
    (output / "manifesto.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Gera gráficos dos experimentos concluídos")
    parser.add_argument("--ruido", type=Path, required=True)
    parser.add_argument("--centros", type=Path, required=True)
    parser.add_argument("--complementares", type=Path, help="Lote único com as 160 execuções complementares")
    parser.add_argument("--sensibilidade", type=Path, help="Lote concluído de 120 execuções de sensibilidade")
    parser.add_argument("--instabilidade", type=Path, help="Lote concluído de 30 execuções de instabilidade")
    parser.add_argument("--banco", type=Path, default=Path(__file__).resolve().parents[1] / "dados" / "banco_smol.json")
    parser.add_argument("--saida", type=Path, required=True, help="Nova pasta para as figuras")
    args = parser.parse_args(argv)
    try:
        gerar(args.ruido, args.centros, args.banco, args.saida, complementares=args.complementares,
              sensibilidade=args.sensibilidade, instabilidade=args.instabilidade)
    except (OSError, KeyError, ValueError, AssertionError) as exc:
        print(f"Não foi possível gerar as figuras: {exc}", file=sys.stderr)
        return 1
    print(f"Figuras e legendas: {args.saida.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
