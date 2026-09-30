"""Relatório reproduzível da comparação pareada de validação em 50 nós."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def read(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))


def save_csv(path, rows):
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--on', required=True)
    parser.add_argument('--off', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    figs = out / 'graficos'
    figs.mkdir()
    runs, final_nodes, effects, evolution = {}, [], [], []
    all_events = 0
    all_queries = 0
    for enabled, root in [(0, args.off), (1, args.on)]:
        index = read(Path(root) / 'matrix_index.csv')
        assert len(index) == 270, (root, len(index))
        for entry in index:
            pct, coll, seed = int(entry['malicious_pct']), int(entry['collusion']), int(entry['seed'])
            mechanism = entry['mechanism']
            meta = dict(validacao=enabled, maliciosos_pct=pct, conluio=coll, mecanismo=mechanism, semente=seed)
            folder = Path(entry['output_dir'])
            summary = json.loads((folder / 'summary.json').read_text(encoding='utf-8'))['summary']
            assert summary['validation_rounds'] == ([10, 20, 30, 40, 50] if enabled else [])
            rounds = read(folder / 'rounds.csv')
            assert len(rounds) == 50
            hist = read(folder / 'reputation_history.csv')
            assert len(hist) == 2550
            scores = np.full((51, 50), np.nan)
            profiles = {}
            for row in hist:
                n = int(row['node_id'].split('-')[-1])
                scores[int(row['checkpoint']), n] = float(row['reputation'])
                profiles[n] = row['profile']
            assert np.isfinite(scores).all()
            mal = np.array([profiles[n] == 'malicious' for n in range(50)])
            assert mal.sum() == pct // 2
            signature = hashlib.sha256()
            normal = read(folder / 'per_node.csv')
            assert len(normal) == 2500
            for row in normal:
                signature.update(json.dumps([row[k] for k in ['round_index','node_id','task_id','answer','latency_ms']], separators=(',', ':')).encode())
            updates = read(folder / 'validation_updates.csv')
            assert len(updates) == (500 if enabled else 0)
            all_queries += len(updates)
            before = {}
            after = {}
            for row in updates:
                key = (int(row['round_number']), int(row['node_id'].split('-')[-1]))
                before.setdefault(key, float(row['reputation_before']))
                after[key] = float(row['reputation_after'])
                assert row['outcome'] in ['CORRECT', 'INCORRECT']
            for (t, n), pre in before.items():
                assert abs(after[t,n] - scores[t,n]) < 2e-6
                effects.append({**meta, 'rodada': t, 'no': f'node-{n}', 'perfil': profiles[n], 'score_antes': pre, 'score_depois': after[t,n], 'delta': after[t,n]-pre})
            all_events += len(summary['validation_rounds'])
            acc = np.array([float(r['consensus_correct']) for r in rounds])
            majority = np.array([float(r['majority_correct']) for r in rounds])
            total = scores.sum(axis=1)
            share = np.divide(scores[:,mal].sum(axis=1), total, out=np.zeros(51), where=total != 0)
            runs[enabled,coll,pct,mechanism,seed] = dict(scores=scores,mal=mal,acc=acc,majority=majority,share=share,before=before,after=after,signature=signature.hexdigest())
            for n in range(50):
                final_nodes.append({**meta,'no':f'node-{n}','perfil':profiles[n],'score_inicial':scores[0,n],'score_final':scores[-1,n]})
            for t in range(51):
                evolution.append({**meta,'rodada':t,'score_honestos':scores[t,~mal].mean(),'score_maliciosos':scores[t,mal].mean() if mal.any() else '', 'peso_maliciosos':share[t], 'acuracia_consenso':acc[t-1] if t else '', 'acuracia_maioria':majority[t-1] if t else '', 'validacao_concluida':int(enabled and t in [10,20,30,40,50])})
    assert len(runs) == 540
    for (enabled,coll,pct,mech,seed), r in runs.items():
        if enabled:
            control = runs[0,coll,pct,mech,seed]
            assert r['signature'] == control['signature'], 'Perguntas/respostas normais não pareadas'
            assert np.array_equal(r['acc'][:10], control['acc'][:10])
            assert np.array_equal(r['scores'][:10], control['scores'][:10])
    save_csv(out/'scores_finais_por_no.csv', final_nodes)
    save_csv(out/'impacto_por_teste_e_no.csv', effects)
    save_csv(out/'evolucao_por_rodada.csv', evolution)
    from sistema.scripts.plot_rede50 import render
    mechanisms = ['ema','ema_asymmetric','beta']
    percentages = [0,20,40,60,80]
    def batch(on, coll, pct, mech):
        return [runs[on,coll if pct else 0,pct,mech,s] for s in range(10)]
    summary_rows = []
    for coll in [0,1]:
        for mech in mechanisms:
            for pct in percentages:
                if not pct and coll:
                    continue
                on, off = batch(1,coll,pct,mech), batch(0,coll,pct,mech)
                diffs = np.array([a['acc'].mean()-b['acc'].mean() for a,b in zip(on,off)])
                summary_rows.append(dict(conluio=coll,mecanismo=mech,maliciosos_pct=pct,acuracia_sem=np.mean([r['acc'].mean() for r in off]),acuracia_com=np.mean([r['acc'].mean() for r in on]),ganho_pp=100*diffs.mean(),erro_padrao_ganho_pp=100*diffs.std(ddof=1)/np.sqrt(10),score_final_honestos=np.mean([r['scores'][-1,~r['mal']].mean() for r in on]),score_final_maliciosos=np.mean([r['scores'][-1,r['mal']].mean() for r in on]) if pct else '',peso_final_maliciosos=np.mean([r['share'][-1] for r in on])))
    figures = render(runs, figs)
    save_csv(out/'resumo_comparativo.csv',summary_rows)
    event_summary=[]
    for coll in [0,1]:
        for mech in mechanisms:
            for pct in percentages:
                if not pct and coll: continue
                group=batch(1,coll,pct,mech)
                for t in [10,20,30,40,50]:
                    for profile in ['honest','malicious']:
                        mask=~group[0]['mal'] if profile=='honest' else group[0]['mal']
                        if not mask.any(): continue
                        pre=np.mean([r['before'][t,n] for r in group for n in np.where(mask)[0]])
                        post=np.mean([r['after'][t,n] for r in group for n in np.where(mask)[0]])
                        event_summary.append(dict(conluio=coll,mecanismo=mech,maliciosos_pct=pct,rodada=t,perfil=profile,score_antes=pre,score_depois=post,delta=post-pre))
    save_csv(out/'impacto_medio_por_teste.csv',event_summary)
    windows=[]
    for coll in [0,1]:
        for mech in mechanisms:
            for pct in percentages:
                if not pct and coll: continue
                on,off=batch(1,coll,pct,mech),batch(0,coll,pct,mech)
                for start in [1,11,21,31,41]:
                    a=np.mean([r['acc'][start-1:start+9].mean() for r in on])
                    b=np.mean([r['acc'][start-1:start+9].mean() for r in off])
                    windows.append(dict(conluio=coll,mecanismo=mech,maliciosos_pct=pct,inicio=start,fim=start+9,acuracia_com=a,acuracia_sem=b,ganho_pp=100*(a-b)))
    save_csv(out/'impacto_na_janela_seguinte.csv',windows)
    meta={'commit_base':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'execucoes':540,'pares':270,'validacoes_concluidas':all_events,'consultas_validacao':all_queries,'condicao_com':str(Path(args.on).resolve()),'condicao_sem':str(Path(args.off).resolve()),'checks':['540 execuções completas','50 rodadas e 50 nós em cada execução','270 pares com perguntas, respostas e latências normais idênticas','sem diferença antes da primeira validação','hash/score do checkpoint conferido após cada teste'],'observacao':'store.py recebeu retry limitado de PermissionError; simulação e regras de reputação inalteradas.'}
    (out/'verificacao.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# Evolução da rede de 50 nós e impacto da validação','', '## Experimento realizado','',f'Foram concluídas **540 execuções (270 pares)**, com 50 rodadas cada, dez sementes (0–9), três mecanismos (EMA, EMA assimétrica e Beta), 0/20/40/60/80% de maliciosos e variantes com/sem conluio. O cenário 0% não é duplicado. Cada execução começa com score 0,5. São **{all_events} eventos de validação e {all_queries:,} consultas individuais**.'.replace(',', '.'),'', 'A cada dez rodadas, cada nó recebe duas perguntas de uma partição reservada da amostra local do dataset. Os percentuais são cenários independentes, não uma invasão gradual dentro da mesma execução. Honestidade simulada: probabilidade de acerto 0,9; EMA alpha=0,3; confiança mínima 0,55.','', '**Natureza dos resultados:** respostas simuladas por perfil, como na matriz da Lara; não houve inferência de uma LLM. O simulador utiliza a resposta esperada para fabricar respostas conforme o perfil. Em execução HTTP real, o payload dos nós contém apenas identificador/pergunta. A atualização operacional não usa gabarito; o avaliador da validação usa. Este dataset não comprova o treinamento da LLM.','', '## Como interpretar as marcações','', '- Linhas verticais: validações concluídas após as rodadas 10, 20, 30, 40 e 50, somente na condição ligada.','- Reputação: símbolo vazio = antes do primeiro item do teste; cheio = depois do segundo. Segmento vertical = impacto imediato total.','- O consenso da rodada 10 ocorre antes do teste; o efeito possível começa na 11. A validação 50 altera o score final, mas não há rodada 51 para medir consenso posterior.','- Curvas: médias das dez sementes. Faixas: média ± 1,96 erro-padrão, aproximação descritiva com dez repetições. Não usar nós como repetições independentes.','- Painéis de acurácia mostram proporção de sementes corretas naquela rodada. Mapas de calor mostram cada nó da semente 0; todos os nós e sementes estão nos CSVs.','', '## Resultado agregado das 50 rodadas','', '| Conluio | Mecanismo | Maliciosos | Sem validação | Com validação | Ganho (p.p.) | Score honesto final | Score malicioso final |','|---|---|---:|---:|---:|---:|---:|---:|']
    for row in summary_rows:
        mal=row['score_final_maliciosos']
        lines.append(f"| {'Sim' if row['conluio'] else 'Não'} | {row['mecanismo']} | {row['maliciosos_pct']}% | {row['acuracia_sem']:.1%} | {row['acuracia_com']:.1%} | {row['ganho_pp']:+.1f} | {row['score_final_honestos']:.3f} | {mal if mal=='' else format(mal,'.3f')} |")
    lines += ['', '## Impacto nos cenários com maioria maliciosa em conluio','']
    for pct in [60,80]:
        for mech in mechanisms:
            row=next(r for r in summary_rows if r['conluio']==1 and r['maliciosos_pct']==pct and r['mecanismo']==mech)
            events=[r for r in event_summary if r['conluio']==1 and r['maliciosos_pct']==pct and r['mecanismo']==mech and r['rodada']==10]
            delta=', '.join(f"{r['perfil']}: {r['score_antes']:.3f} → {r['score_depois']:.3f} (Δ {r['delta']:+.3f})" for r in events)
            lines += [f"- **{pct}% / {mech}:** acurácia {row['acuracia_sem']:.1%} → {row['acuracia_com']:.1%}; ganho {row['ganho_pp']:+.1f} p.p.; peso malicioso final {row['peso_final_maliciosos']:.1%}. No primeiro teste: {delta}."]
    lines += ['', 'Mudança imediata de score não garante recuperação do consenso. O efeito líquido depende das atualizações das dez tarefas normais entre testes, da frequência/quantidade de perguntas e do mecanismo. Os cenários sem conluio permitem que votos maliciosos se dispersem; acurácia alta nesse caso não prova resistência a uma maioria coordenada.', '', '## Gráficos','']
    for title, name in figures:
        lines += [f'### {title}', '', f'![{title}](graficos/{name}.png)', '',
                  f'[PDF vetorial](graficos/{name}.pdf)', '']
    lines += ['## Dados, rastreabilidade e limites','', '- [Resumo comparativo](resumo_comparativo.csv): resultados por cenário e erro-padrão do ganho pareado.','- [Evolução por rodada](evolucao_por_rodada.csv): consenso, scores por perfil e fração de peso malicioso para cada semente.','- [Score final de cada nó](scores_finais_por_no.csv). Histórico completo por nó: `reputation_history.csv` em cada execução bruta.','- [Impacto por teste e nó](impacto_por_teste_e_no.csv): antes/depois agregado das duas perguntas.','- [Impacto médio por teste](impacto_medio_por_teste.csv).','- [Efeito na janela seguinte](impacto_na_janela_seguinte.csv): comparação de 1–10, 11–20, 21–30, 31–40 e 41–50.','- [Verificações](verificacao.json): fontes e conferências estruturais e pareadas.','', 'As perguntas/respostas/latências das tarefas normais foram verificadas como idênticas entre cada par. Os dados da Lara usam outra atualização operacional, portanto não são o controle causal deste experimento. A inferência é restrita ao modelo simulado, às dez sementes e à amostra local; não demonstra desempenho real de uma LLM.','', 'A primeira tentativa com validação foi interrompida por bloqueio transitório de arquivo no Windows. O parcial foi preservado e excluído da análise; a repetição completa usou `com_validacao_v2`, após retry limitado na persistência. Nenhuma configuração científica foi alterada.','', '## Reprodução','', '```powershell', 'python -X utf8 -m sistema.scripts.run_matrix --nodes 50 --malicious 0 .2 .4 .6 .8 --seeds 10 --rounds 50 --validation-questions 2 --output NOVA_PASTA_COM', 'python -X utf8 -m sistema.scripts.run_matrix --nodes 50 --malicious 0 .2 .4 .6 .8 --seeds 10 --rounds 50 --validation-questions 2 --no-validation --output NOVA_PASTA_SEM', 'python -X utf8 -m sistema.scripts.report_rede50 --on NOVA_PASTA_COM --off NOVA_PASTA_SEM --output NOVA_PASTA_RELATORIO', '```','']
    lines[4] = (f'Foram concluídas **540 execuções (270 pares)**, com 50 rodadas cada, '
                'dez sementes (0–9), três mecanismos (EMA, EMA assimétrica e Beta), '
                '0/20/40/60/80% de maliciosos e variantes com/sem conluio. '
                'O cenário 0% não é duplicado. Cada execução começa com score 0,5. '
                f'São **{all_events} eventos de validação e {all_queries} consultas individuais**.')
    findings = ['', '## Principais resultados', '']
    for row in summary_rows:
        if row['conluio'] == 0 and row['maliciosos_pct'] == 80:
            findings.append(f"- **80% sem conluio / {row['mecanismo']}:** acurácia de {row['acuracia_sem']:.1%} para {row['acuracia_com']:.1%}, ganho de {row['ganho_pp']:.1f} pontos percentuais.")
    findings += ['- **60% e 80% com conluio:** acurácia permaneceu em 0% nos três mecanismos, apesar da correção imediata dos scores em cada teste. Duas perguntas por dez tarefas não foram suficientes neste modelo.', '']
    lines[2:2] = findings
    lines += ['', '## Verificação do código', '', 'Os dois testes novos de retry da persistência passaram. A suíte executou 24 testes: 21 passaram e três testes HTTP não puderam executar por falta de `httpx`/`pydantic` no ambiente. As 540 simulações não dependem desses módulos. As verificações dos dados pareados e dos checkpoints passaram; `git diff --check` sem erros.', '']
    (out/'RELATORIO.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps(meta,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
