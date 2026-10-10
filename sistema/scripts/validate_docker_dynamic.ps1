# Roda o orquestrador dinamico em containers para alguns cenarios e guarda
# cada resultado em sistema/results/docker_orquestrador_dinamico/<cenario>.
# Depois compare com a simulacao: python -m sistema.scripts.compare_docker_dynamic
#
# Uso (na raiz do repositorio, com as imagens tcc-node, tcc-orch e tcc-dev):
#   powershell -File sistema/scripts/validate_docker_dynamic.ps1

$ErrorActionPreference = "Continue"
$scenarios = @(
    @{ id = "n4_star_m25_forge";        nodes = 4;  mal = 0.25; topology = "star";     degree = 3; attack = "forge";  defense = "all" },
    @{ id = "n4_kregular_m25_forge";    nodes = 4;  mal = 0.25; topology = "kregular"; degree = 2; attack = "forge";  defense = "all" },
    @{ id = "n10_kregular_m25_censor";  nodes = 10; mal = 0.25; topology = "kregular"; degree = 4; attack = "censor"; defense = "all" },
    @{ id = "n20_kregular_m65_forge";   nodes = 20; mal = 0.65; topology = "kregular"; degree = 4; attack = "forge";  defense = "all" },
    @{ id = "n20_kregular_m65_forge_none"; nodes = 20; mal = 0.65; topology = "kregular"; degree = 4; attack = "forge"; defense = "none" }
)

foreach ($s in $scenarios) {
    $out = "sistema/results/docker_orquestrador_dinamico/$($s.id)"
    docker run --rm -v "${PWD}:/app" tcc-dev python -m sistema.scripts.gen_compose `
        --nodes $s.nodes --malicious $s.mal --seed 7 --collusion-value 999 --rounds 30 `
        --orchestration dynamic --topology $s.topology --degree $s.degree --defense $s.defense `
        --leader-attack $s.attack --mechanism beta --node-image tcc-node --orchestrator-image tcc-orch `
        --mount-code --max-sleep-ms 200 --timeout-s 120 --experiment-id "docker_$($s.id)" `
        --output-dir $out --compose-out docker-compose.dyn.generated.yml --config-out sistema/config/experiment.dyn.generated.yaml
    cmd /c "docker compose -f docker-compose.dyn.generated.yml -p tccdyn up --abort-on-container-exit --exit-code-from orchestrator > `"$env:TEMP\tccdyn_$($s.id).log`" 2>&1"
    $code = $LASTEXITCODE
    cmd /c "docker compose -f docker-compose.dyn.generated.yml -p tccdyn down > nul 2>&1"
    Write-Host "$($s.id): exit $code"
}
