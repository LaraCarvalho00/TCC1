# Campanha Qwen concluída

40 cenários; 20 nós; 50 rodadas; 40000 gerações verificadas. Uma cópia MLX 4-bit, lote de até 20 gerações independentes. Maliciosos 20/40/60/80%, p=0,2; notas exata/graduada; sementes 0–4.

Reputação: média por perfil dentro da semente e depois média entre cinco sementes. Faixa de um desvio padrão, não intervalo de confiança. Acurácia do consenso na fase de ataque exclui as cinco rodadas iniciais, rodadas auditadas e de calibração. Acurácia bruta usa respostas da LLM antes da corrupção, comparadas ao gabarito; falhas de extração contam como erros.

As condições usam as mesmas sementes e tarefas. A LLM responde antes da corrupção e sem receber a nota ou o perfil do nó; por isso as curvas de acurácia bruta se sobrepõem. Cada cenário gerou suas próprias respostas, sem reutilizar cache de outro cenário.

Os cenários foram executados em ordem fixa. As diferenças de tempo não isolam um efeito causal da porcentagem de maliciosos: carga da máquina e condições térmicas também podem variar.

Tempo de inferência exclui comunicação, consenso, carregamento e exportação. Latência por nó registrada no backend representa tempo até a conclusão do lote. MLX 4-bit não equivale a NF4. Os resultados descrevem este banco de tarefas e parâmetros; não são um benchmark geral de acurácia do Qwen.

| Maliciosos | Nota | Consenso no ataque | LLM bruta |
|---|---|---:|---:|
| 20% | exact | 40.9% | 32.1% |
| 20% | graded | 41.5% | 32.1% |
| 40% | exact | 30.0% | 32.1% |
| 40% | graded | 22.2% | 32.1% |
| 60% | exact | 9.3% | 32.1% |
| 60% | graded | 3.5% | 32.1% |
| 80% | exact | 2.3% | 32.1% |
| 80% | graded | 0.0% | 32.1% |
