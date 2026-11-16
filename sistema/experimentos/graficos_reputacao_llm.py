"""Evolução da reputação por perfil nas grades de inferência real."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from pathlib import Path

from sistema.experimentos.graficos_cenarios_llm import ler_grade


def coletar(grade: Path):
    config, scenarios, completed, sources = ler_grade(grade)
    root = grade.resolve()
    entries = {entry['id']: entry for entry in scenarios}
    rows = []
    for item in completed:
        entry = entries[item['id']]
        folder = root / 'cenarios' / item['id'] / entry['tentativas'][-1]['id']
        history_path = folder / 'reputation_history.csv'
        rounds_path = folder / 'rounds.csv'
        with history_path.open(encoding='utf-8-sig', newline='') as stream:
            history = list(csv.DictReader(stream))
        with rounds_path.open(encoding='utf-8-sig', newline='') as stream:
            audited = {int(row['round_index']) + 1 for row in csv.DictReader(stream) if row['audited'] == '1'}
        grouped = {}
        observed = set()
        for row in history:
            checkpoint = int(row['checkpoint'])
            profile = row['profile']
            value = float(row['reputation'])
            identity = (checkpoint, row['node_id'])
            if identity in observed or profile not in ('honest', 'malicious') or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f'Histórico de reputação inválido: {history_path}')
            observed.add(identity)
            grouped.setdefault((checkpoint, profile), []).append(value)
        for checkpoint in range(int(config['rodadas']) + 1):
            for profile, quantity in (('honest', int(config['nos']) - item['nos_maliciosos']), ('malicious', item['nos_maliciosos'])):
                values = grouped.get((checkpoint, profile), [])
                if len(values) != quantity or not values:
                    raise ValueError(f'Histórico incompleto: {item["id"]}, checkpoint {checkpoint}, perfil {profile}')
                rows.append({'cenario': item['id'], 'fracao_maliciosos': item['fracao_maliciosos'],
                             'p': item['audit_p'], 'nota': item['nota'], 'semente': item['semente'],
                             'checkpoint': checkpoint, 'perfil': profile, 'quantidade_nos': quantity,
                             'reputacao_media': statistics.mean(values), 'conferencia_na_rodada': int(checkpoint in audited)})
        if len(observed) != (int(config['rodadas']) + 1) * int(config['nos']):
            raise ValueError(f'Quantidade de checkpoints inconsistente: {item["id"]}')
        sources.append(history_path)
    return config, scenarios, rows, sources


def gerar(grade: Path, output: Path):
    config, scenarios, rows, sources = coletar(grade)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    output.mkdir(parents=True, exist_ok=False)
    with (output / 'reputacao_por_rodada.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    for fraction in sorted({float(entry['fracao_maliciosos']) for entry in scenarios}):
        subset = [row for row in rows if row['fracao_maliciosos'] == fraction]
        if not subset:
            continue
        fig, axes = plt.subplots(2, 2, figsize=(12, 8), sharex=True, sharey=True)
        fig.suptitle(f'Reputação por rodada — {fraction:.0%} de nós maliciosos', x=.08, y=.98, ha='left', fontsize=16, fontweight='bold')
        fig.text(.08, .93, f"{config['nos']} nós · {config['rodadas']} rodadas · uma semente · médias por perfil", color='#666b73')
        for ax, (prob, note) in zip(axes.flat, ((.1, 'exact'), (.2, 'exact'), (.1, 'graded'), (.2, 'graded'))):
            selected = [row for row in subset if row['p'] == prob and row['nota'] == note]
            ax.set_title(f"p = {str(prob).replace('.', ',')} · nota {'exata' if note == 'exact' else 'graduada'}", loc='left', fontweight='bold')
            if not selected:
                ax.text(.5, .5, 'Cenário não concluído', ha='center', va='center', transform=ax.transAxes)
            else:
                for profile, color, label in (('honest', '#24629f', 'Honestos'), ('malicious', '#bd4a3d', 'Maliciosos')):
                    series = sorted((r for r in selected if r['perfil'] == profile), key=lambda r: r['checkpoint'])
                    ax.plot([r['checkpoint'] for r in series], [r['reputacao_media'] for r in series],
                            color=color, marker='o', markersize=3.5, linewidth=1.8, label=label)
                for checkpoint in sorted({r['checkpoint'] for r in selected if r['conferencia_na_rodada']}):
                    ax.axvline(checkpoint, color='#777777', linestyle=':', alpha=.7, linewidth=1)
            ax.set_ylim(-.03, 1.03)
            ax.set_xlim(-.2, int(config['rodadas']) + .2)
            rounds = int(config['rodadas'])
            step = max(1, math.ceil(rounds / 10))
            ticks = list(range(0, rounds + 1, step))
            if ticks[-1] != rounds:
                ticks.append(rounds)
            ax.set_xticks(ticks)
            ax.grid(axis='y', alpha=.2)
            ax.spines[['top', 'right']].set_visible(False)
        for ax in axes[:, 0]:
            ax.set_ylabel('Reputação média (0 a 1)')
        for ax in axes[-1, :]:
            ax.set_xlabel('Rodada (0 = reputação inicial)')
        legend = [Line2D([0], [0], color='#24629f', marker='o', label='Honestos'),
                  Line2D([0], [0], color='#bd4a3d', marker='o', label='Maliciosos'),
                  Line2D([0], [0], color='#777777', linestyle=':', label='Rodada com conferência')]
        fig.legend(handles=legend, loc='lower center', bbox_to_anchor=(.5, .035), ncol=3, frameon=False)
        fig.subplots_adjust(left=.08, right=.97, top=.86, bottom=.13, hspace=.35, wspace=.15)
        for ext in ('png', 'pdf'):
            fig.savefig(output / f'reputacao_{round(fraction * 100):02d}pct.{ext}', dpi=220, facecolor='white')
        plt.close(fig)
    warmup = config.get('rodadas_iniciais_honestas', 5)
    (output / 'LEGENDA_E_METODOLOGIA.md').write_text(
        '# Evolução da reputação\n\n'
        f'Cada figura representa uma proporção de nós maliciosos, {config["nos"]} nós, {config["rodadas"]} rodadas e uma semente. '
        f'Os maliciosos imitam honestos nas {warmup} primeiras rodadas.\n\n'
        f'Semente: {config["sementes"][0]}; critério de escolha: {config.get("criterio_semente", "não registrado")}.\n\n'
        'As linhas mostram médias aritméticas das reputações individuais de consenso por perfil. '
        'O ponto zero é o estado inicial; cada ponto posterior é o estado após a rodada e sua eventual conferência. '
        'Linhas verticais pontilhadas indicam rodadas conferidas. Cenários não concluídos não são estimados. '
        'As médias não são acurácia; uma única semente e poucas rodadas não permitem inferência estatística.\n', encoding='utf-8')
    unique_sources = {str(p.resolve()): p for p in sources}
    manifest = {'configuracao': config, 'cenarios_concluidos': len({r['cenario'] for r in rows}),
                'fontes': [{'caminho': name, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for name, p in sorted(unique_sources.items())]}
    (output / 'manifesto.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description='Gráficos da reputação por rodada e perfil')
    parser.add_argument('--grade', type=Path, required=True)
    parser.add_argument('--saida', type=Path, required=True)
    args = parser.parse_args()
    gerar(args.grade, args.saida)
    print(f'Gráficos e dados: {args.saida.resolve()}')


if __name__ == '__main__':
    main()
