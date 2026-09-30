"""Figuras da rede de 50 nós: estilos estáveis e eventos sem interpolação."""
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import PercentFormatter

STYLES = {
    'on': ('#0072B2', 'o', '-', 'Com validação'),
    'off': ('#E69F00', 's', '--', 'Sem validação'),
    'majority': ('#444444', '^', '-.', 'Maioria simples'),
    'honest_on': ('#0072B2', 'o', '-', 'Honestos · com validação'),
    'honest_off': ('#009E73', 's', '--', 'Honestos · sem validação'),
    'mal_on': ('#D55E00', '^', '-', 'Maliciosos · com validação'),
    'mal_off': ('#CC79A7', 'D', '-.', 'Maliciosos · sem validação'),
}
PCTS = [0, 20, 40, 60, 80]
NAMES = {'ema': 'EMA', 'ema_asymmetric': 'EMA assimétrica', 'beta': 'Beta'}


def calendar(group):
    calendars = {tuple(sorted({t for t, _ in r['before']})) for r in group}
    if len(calendars) != 1:
        raise ValueError('Calendários diferentes entre as sementes')
    return list(next(iter(calendars)))


def event_series(run, kind, profile=None):
    """Insere pré e pós no mesmo x; não antecipa a intervenção."""
    x, values = [], []
    mask = (~run['mal'] if profile == 'honest' else run['mal'])
    def measure(scores):
        if kind == 'score':
            return scores[mask].mean()
        total = scores.sum()
        return scores[run['mal']].sum() / total if total else 0.
    events = {t for t, _ in run['before']}
    for t, scores in enumerate(run['scores']):
        if t in events:
            pre = np.array([run['before'][t, n] for n in range(len(scores))])
            x.append(t)
            values.append(measure(pre))
        x.append(t)
        values.append(measure(scores))
    return np.array(x), np.array(values)


def draw(ax, x, values, style, phase=0, band=True):
    color, marker, dash, label = STYLES[style]
    a = np.array(values)
    mean = a.mean(axis=0)
    # Different marker positions expose coincident curves without jittering data.
    positions = [i for i, t in enumerate(x) if t % 5 == phase % 5
                 and (i == len(x)-1 or x[i+1] != t)]
    ax.plot(x, mean, color=color, marker=marker, linestyle=dash,
            markevery=positions, markersize=4.8, markeredgewidth=1.1,
            markerfacecolor='white', linewidth=1.7, label=label, zorder=3)
    if band:
        error = 1.96 * a.std(axis=0, ddof=1) / np.sqrt(len(a))
        ax.fill_between(x, np.maximum(0, mean-error), np.minimum(1, mean+error),
                        color=color, alpha=.055, linewidth=0, zorder=1)


def decorate(ax, events, percent=False, delta=False):
    ax.set(xlim=(-1, 52), ylim=(-1.03, 1.03) if delta else (-.035, 1.035),
           xlabel='Rodada', xticks=[0, 10, 20, 30, 40, 50])
    ax.grid(axis='y', color='#dddddd', linewidth=.55)
    ax.tick_params(labelsize=10)
    if percent:
        ax.yaxis.set_major_formatter(PercentFormatter(1))
    for i, t in enumerate(events, 1):
        ax.axvline(t, color='#8a8a8a', linestyle=(0, (2, 4)), linewidth=.8, zorder=0)
        ax.text(t, 1.025, f'T{i}', transform=ax.get_xaxis_transform(), ha='center',
                fontsize=8, color='#555555', clip_on=False)


def handles(keys):
    return [Line2D([], [], color=STYLES[k][0], marker=STYLES[k][1],
                   linestyle=STYLES[k][2], markerfacecolor='white',
                   label=STYLES[k][3], linewidth=1.7) for k in keys]


def sheet(title, subtitle, keys, event_note=True):
    fig, axes = plt.subplots(3, 2, figsize=(12, 10), layout='constrained')
    fig.suptitle(title + '\n' + subtitle, fontsize=14, fontweight='medium')
    legend = axes.flat[5]
    legend.axis('off')
    h = handles(keys)
    if event_note:
        h.append(Line2D([], [], color='#888888', ls=':', label='T1–T5: validação após a tarefa'))
    legend.legend(handles=h, loc='upper left', frameon=False, fontsize=10,
                  handlelength=3.5, labelspacing=.6)
    note = '50 nós · 10 sementes · 50 rodadas\nFaixas: média ± 1,96 erro-padrão.'
    if 'honest_off' in keys:
        note += '\nNo teste: vazio = antes; preenchido = depois.\nO segmento vertical representa a correção.'
    elif 'Mudança' in title:
        note = 'Δ medido entre antes da primeira e depois da\nsegunda pergunta. Barras: média ± 1,96 EP.'
    elif 'Ganho' in title:
        note = 'Diferença pareada: com − sem validação.\nBarras: média ± 1,96 EP entre sementes.\nNão há tarefa após T5 nesta execução.'
    legend.text(.02, .015, note, va='bottom',
                transform=legend.transAxes, fontsize=9, color='#555555', linespacing=1.35)
    return fig, list(axes.flat)[:5]


def save(fig, folder, name):
    fig.savefig(folder / (name + '.png'), dpi=240, facecolor='white')
    fig.savefig(folder / (name + '.pdf'), facecolor='white')
    plt.close(fig)


def render(runs, folder, heatmap_only=False):
    plt.rcParams.update({'font.family':'DejaVu Sans', 'font.size':11,
        'axes.spines.top':False, 'axes.spines.right':False,
        'axes.labelcolor':'#333333', 'axes.edgecolor':'#aaaaaa',
        'pdf.fonttype':42, 'savefig.pad_inches':.15})
    def group(on, coll, pct, mech):
        return [runs[on, coll if pct else 0, pct, mech, s] for s in range(10)]
    outputs = []
    for coll in [0, 1]:
        for mech in NAMES:
            tag = f'{mech}_{"com" if coll else "sem"}_conluio'
            subtitle = f'{NAMES[mech]} · {"com" if coll else "sem"} conluio · média de 10 sementes'
            for metric, title, keys in ([] if heatmap_only else [
                ('acuracia','Acurácia do consenso',['on','off','majority']),
                ('scores','Evolução dos scores',['honest_on','honest_off','mal_on','mal_off']),
                ('influencia','Influência dos nós maliciosos',['on','off']),
                ('impacto','Mudança de score causada por cada teste',['honest_on','mal_on']),
                ('janelas','Ganho de acurácia após as validações',['on'])]):
                fig, axes = sheet(title, subtitle, keys, event_note=metric!='janelas')
                for ax, pct in zip(axes, PCTS):
                    on, off = group(1,coll,pct,mech), group(0,coll,pct,mech)
                    events = calendar(on)
                    ax.set_title(f'{pct}% maliciosos · {pct//2} de 50 nós', loc='left',
                                 fontsize=12, pad=23 if metric!='janelas' else 12)
                    if metric == 'acuracia':
                        for key, data, phase in [('off',off,2),('on',on,0),('majority',on,4)]:
                            draw(ax,np.arange(1,51),[r['majority' if key=='majority' else 'acc'] for r in data],key,phase)
                        ax.set_ylabel('Respostas corretas')
                    elif metric in ['scores','influencia']:
                        profiles = ['honest','mal'] if metric=='scores' else [None]
                        for profile in profiles:
                            if profile=='mal' and pct==0: continue
                            for enabled,data in [('off',off),('on',on)]:
                                key=f'{profile}_{enabled}' if profile else enabled
                                pairs=[event_series(r,'score' if profile else 'share',profile) for r in data]
                                draw(ax,pairs[0][0],[v for _,v in pairs],key,list(STYLES).index(key)%5)
                                if profile and enabled=='on':
                                    mask=~on[0]['mal'] if profile=='honest' else on[0]['mal']
                                    for t in events:
                                        pre=np.mean([r['before'][t,n] for r in on for n in np.where(mask)[0]])
                                        post=np.mean([r['after'][t,n] for r in on for n in np.where(mask)[0]])
                                        color,marker,_,_=STYLES[key]
                                        ax.scatter([t,t],[pre,post],marker=marker,s=32,
                                                   facecolors=['white',color],edgecolors=color,zorder=5)
                        ax.set_ylabel('Score (0–1)' if metric=='scores' else 'Participação no peso total')
                        if metric=='influencia':
                            ax.axhline(.5,color='#555555',ls='-.',lw=.8,zorder=0)
                            ax.text(1,.52,'Referência: 50% do peso',fontsize=8,color='#666666')
                    elif metric=='impacto':
                        for profile,key in [('honest','honest_on'),('mal','mal_on')]:
                            mask=~on[0]['mal'] if profile=='honest' else on[0]['mal']
                            if not mask.any(): continue
                            a=np.array([[np.mean([r['after'][t,n]-r['before'][t,n] for n in np.where(mask)[0]]) for t in events] for r in on])
                            color,marker,_,label=STYLES[key]
                            ax.errorbar(events,a.mean(axis=0),yerr=1.96*a.std(axis=0,ddof=1)/np.sqrt(10),
                                        color=color,marker=marker,ls='-',capsize=3,label=label)
                        ax.axhline(0,color='#333333',lw=.8)
                        ax.set_ylabel('Δ score: depois − antes')
                    else:
                        starts=[0,*events[:-1]]
                        ends=events
                        a=np.array([[r['acc'][s:e].mean()-c['acc'][s:e].mean() for s,e in zip(starts,ends)] for r,c in zip(on,off)])*100
                        ax.axhline(0,color='#999999',lw=.8)
                        ax.errorbar(range(len(starts)),a.mean(axis=0),yerr=1.96*a.std(axis=0,ddof=1)/np.sqrt(10),
                                    color=STYLES['on'][0],marker='o',capsize=4)
                        ax.set(xticks=range(len(starts)),xticklabels=[f'{s+1}–{e}' for s,e in zip(starts,ends)],
                               xlabel='Janela de rodadas (1–10: antes de T1)',ylabel='Com − sem validação (p.p.)',ylim=(-5,35))
                        ax.grid(axis='y',alpha=.15)
                    if metric!='janelas':
                        decorate(ax,events,percent=metric in ['acuracia','influencia'],delta=metric=='impacto')
                name=f'{metric}_{tag}'
                save(fig,folder,name)
                outputs.append((f'{title} — {subtitle}',name))
            fig,axes=plt.subplots(5,2,figsize=(12,15),layout='constrained')
            fig.suptitle(f'Score individual dos 50 nós\n{NAMES[mech]} · {"com" if coll else "sem"} conluio · semente 0',fontsize=14)
            for i,pct in enumerate(PCTS):
                for enabled in [0,1]:
                    ax=axes[i,enabled]
                    r=runs[enabled,coll if pct else 0,pct,mech,0]
                    im=ax.imshow(r['scores'].T,aspect='auto',origin='lower',vmin=0,vmax=1,
                                 cmap='viridis',interpolation='nearest',extent=[-.5,50.5,-.5,49.5])
                    ax.set_title(f'{pct}% maliciosos · {"com" if enabled else "sem"} validação',fontsize=11,pad=22)
                    ax.set(xlabel='Rodada',ylabel='Índice do nó',xticks=[0,10,20,30,40,50])
                    boundary=int(r['mal'].sum())
                    if boundary:
                        ax.axhline(boundary-.5,color='white',linewidth=1.1)
                        ax.text(1,boundary/2,'Maliciosos',color='white',fontsize=8,
                                bbox=dict(facecolor='#111111',alpha=.65,edgecolor='none'))
                    ax.text(1,(boundary+50)/2,'Honestos',color='white',fontsize=8,
                            bbox=dict(facecolor='#111111',alpha=.65,edgecolor='none'))
                    for j,t in enumerate(calendar([r]),1):
                        ax.axvline(t,color='white',ls=':',linewidth=.8)
                        ax.text(t,1.015,f'T{j}',transform=ax.get_xaxis_transform(),ha='center',fontsize=7)
            fig.colorbar(im,ax=axes.ravel().tolist(),label='Score (0–1)',shrink=.5,pad=.025)
            name=f'nos_{tag}'
            save(fig,folder,name)
            outputs.append((f'Scores individuais — {NAMES[mech]} · {"com" if coll else "sem"} conluio · semente 0',name))
            if coll and not heatmap_only:
                fig, axes = plt.subplots(1,2,figsize=(12,5.5))
                fig.subplots_adjust(top=.76,bottom=.27,wspace=.2)
                fig.suptitle(f'Detalhe: maioria maliciosa em conluio\n{NAMES[mech]} · correções de score e evolução entre testes',fontsize=14)
                for ax,pct in zip(axes,[60,80]):
                    for profile in ['honest','mal']:
                        for enabled in [0,1]:
                            data=group(enabled,coll,pct,mech)
                            pairs=[event_series(r,'score',profile) for r in data]
                            key=f'{profile}_{"on" if enabled else "off"}'
                            draw(ax,pairs[0][0],[v for _,v in pairs],key,list(STYLES).index(key)%5)
                    decorate(ax,calendar(group(1,coll,pct,mech)))
                    ax.set_title(f'{pct}% maliciosos',pad=24,loc='left')
                    ax.set_ylabel('Score médio')
                fig.legend(handles=handles(['honest_on','honest_off','mal_on','mal_off']),
                           loc='lower center',bbox_to_anchor=(.5,.01),ncol=2,frameon=False,fontsize=10)
                name=f'detalhe_{tag}'
                save(fig,folder,name)
                outputs.append((f'Detalhe dos cenários críticos — {subtitle}',name))
    return outputs
