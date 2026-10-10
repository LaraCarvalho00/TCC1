# Containers × simulação (orquestrador dinâmico, 30 rodadas)

Docker = uma execução em containers (repetição 7). Sim r7 = simulação na mesma repetição. Sim média = média das repetições 7 a 11.

Acurácia, liderança, anulações, forjas e massa maliciosa são medidas na cópia da cadeia seguida pela maioria dos honestos. A reputação final de cada nó é a da cópia que ele mesmo segue: depois de uma divisão, o conluio se dá nota alta na própria cadeia. Saltos nos containers seguem a ordem de chegada das mensagens, por isso podem passar um pouco da menor distância usada na simulação.

## n4_star_m25_forge

Cadeias válidas em todos os nós: sim.

| métrica | Docker | Sim r7 | Sim média |
|---|---|---|---|
| consensus_accuracy_weighted | 0.967 | 0.967 | 0.947 |
| consensus_accuracy_weighted_on_tests | 1.000 | 1.000 | 1.000 |
| rep_honest | 0.942 | 0.861 | 0.863 |
| rep_malicious | 0.041 | 0.041 | 0.041 |
| leader_malicious_rounds | 1 | 1 | 1.000 |
| accepted_rounds | 29 | 29 | 29.000 |
| voided_rounds | 1 | 1 | 1.000 |
| forged_accepted | 0 | 0 | 0.000 |
| censored_accepted | 0 | 0 | 0.000 |
| chain_split_rounds | 0 | 0 | 0.000 |
| n_chains_final | 1 | 1 | 1.000 |
| malicious_power_mass_final | 0.021 | 0.022 | 0.023 |
| mean_hops | 1.000 | 1.000 | 1.000 |
| max_consecutive_same_leader | 1 | 1 | 1.000 |

## n4_kregular_m25_forge

Cadeias válidas em todos os nós: sim.

| métrica | Docker | Sim r7 | Sim média |
|---|---|---|---|
| consensus_accuracy_weighted | 0.967 | 0.967 | 0.947 |
| consensus_accuracy_weighted_on_tests | 1.000 | 1.000 | 1.000 |
| rep_honest | 0.942 | 0.861 | 0.863 |
| rep_malicious | 0.041 | 0.041 | 0.041 |
| leader_malicious_rounds | 1 | 1 | 1.000 |
| accepted_rounds | 29 | 29 | 29.000 |
| voided_rounds | 1 | 1 | 1.000 |
| forged_accepted | 0 | 0 | 0.000 |
| censored_accepted | 0 | 0 | 0.000 |
| chain_split_rounds | 0 | 0 | 0.000 |
| n_chains_final | 1 | 1 | 1.000 |
| malicious_power_mass_final | 0.021 | 0.022 | 0.023 |
| mean_hops | 2.000 | 2.000 | 2.000 |
| max_consecutive_same_leader | 1 | 1 | 1.000 |

## n10_kregular_m25_censor

Cadeias válidas em todos os nós: sim.

| métrica | Docker | Sim r7 | Sim média |
|---|---|---|---|
| consensus_accuracy_weighted | 0.967 | 0.967 | 0.967 |
| consensus_accuracy_weighted_on_tests | 1.000 | 1.000 | 1.000 |
| rep_honest | 0.899 | 0.873 | 0.868 |
| rep_malicious | 0.042 | 0.042 | 0.042 |
| leader_malicious_rounds | 1 | 1 | 1.000 |
| accepted_rounds | 29 | 29 | 29.000 |
| voided_rounds | 1 | 1 | 1.000 |
| forged_accepted | 0 | 0 | 0.000 |
| censored_accepted | 0 | 0 | 0.000 |
| chain_split_rounds | 0 | 0 | 0.000 |
| n_chains_final | 1 | 1 | 1.000 |
| malicious_power_mass_final | 0.018 | 0.017 | 0.018 |
| mean_hops | 2.533 | 2.067 | 2.153 |
| max_consecutive_same_leader | 1 | 1 | 1.000 |

## n20_kregular_m65_forge

Cadeias válidas em todos os nós: sim.

| métrica | Docker | Sim r7 | Sim média |
|---|---|---|---|
| consensus_accuracy_weighted | 0.967 | 0.967 | 0.967 |
| consensus_accuracy_weighted_on_tests | 1.000 | 1.000 | 1.000 |
| rep_honest | 0.864 | 0.883 | 0.858 |
| rep_malicious | 0.973 | 0.973 | 0.973 |
| leader_malicious_rounds | 1 | 1 | 1.000 |
| accepted_rounds | 30 | 30 | 30.000 |
| voided_rounds | 0 | 0 | 0.000 |
| forged_accepted | 1 | 1 | 1.000 |
| censored_accepted | 0 | 0 | 0.000 |
| chain_split_rounds | 1 | 1 | 1.000 |
| n_chains_final | 2 | 2 | 2.000 |
| malicious_power_mass_final | 0.000 | 0.000 | 0.000 |
| mean_hops | 3.186 | 3.153 | 3.190 |
| max_consecutive_same_leader | 1 | 1 | 1.000 |

## n20_kregular_m65_forge_none

Cadeias válidas em todos os nós: sim.

| métrica | Docker | Sim r7 | Sim média |
|---|---|---|---|
| consensus_accuracy_weighted | 0.000 | 0.000 | 0.000 |
| consensus_accuracy_weighted_on_tests | 0.000 | 0.000 | 0.000 |
| rep_honest | 0.002 | 0.002 | 0.002 |
| rep_malicious | 0.998 | 0.998 | 0.998 |
| leader_malicious_rounds | 30 | 30 | 30.000 |
| accepted_rounds | 30 | 30 | 30.000 |
| voided_rounds | 0 | 0 | 0.000 |
| forged_accepted | 30 | 30 | 30.000 |
| censored_accepted | 0 | 0 | 0.000 |
| chain_split_rounds | 0 | 0 | 0.000 |
| n_chains_final | 1 | 1 | 1.000 |
| malicious_power_mass_final | 0.999 | 0.999 | 0.999 |
| mean_hops | 3.267 | 3.000 | 3.200 |
| max_consecutive_same_leader | 1 | 1 | 1.000 |

