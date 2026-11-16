"""Executa as séries de experimentos descritas no artigo."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import traceback
import uuid

RAIZ = Path(__file__).resolve().parents[2]
BANCO_PADRAO = RAIZ / "sistema" / "dados" / "banco_smol.json"
SAIDA_PADRAO = RAIZ / "resultados" / "artigo"

SERIES = {
    "ruido": 2560,
    "centros": 960,
    "sensibilidade": 120,
    "instabilidade": 30,
    "contraste": 10,
}
PRINCIPAIS = ("ruido", "centros", "sensibilidade", "instabilidade")


def _etapas(serie: str) -> tuple[str, ...]:
    return PRINCIPAIS if serie == "todas" else (serie,)


def _comando(serie: str, destino: Path, banco: Path, workers: int, guardar_brutos: bool) -> list[str]:
    if serie in ("ruido", "centros"):
        cmd = [sys.executable, "-m", f"sistema.experimentos.{serie}",
               "--saida", str(destino), "--banco", str(banco), "--workers", str(workers)]
        if guardar_brutos:
            cmd.append("--guardar-brutos")
        return cmd
    return [sys.executable, "-m", "sistema.experimentos.complementares", serie,
            "--saida", str(destino / serie), "--banco", str(banco), "--workers", str(workers)]


def _gravar(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def executar(serie: str, destino: str | Path, banco: str | Path, workers: int = 1,
             guardar_brutos: bool = False) -> tuple[Path, bool]:
    if serie not in (*SERIES, "todas"):
        raise ValueError(f"Série desconhecida: {serie}")
    if workers < 1:
        raise ValueError("workers deve ser pelo menos 1")
    if guardar_brutos and serie not in ("ruido", "centros", "todas"):
        raise ValueError("--guardar-brutos está disponível para ruído e centros")
    bank = Path(banco).resolve(strict=True)
    if not bank.is_file():
        raise ValueError("O banco deve ser um arquivo")
    root = Path(destino).resolve()
    root.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc)
    path = root / (started.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8])
    path.mkdir()
    path_manifest = path / "manifesto_execucao.json"
    steps = _etapas(serie)
    manifest = {
        "serie": serie, "inicio_utc": started.isoformat(), "status": "em_andamento",
        "banco": str(bank), "workers": workers, "guardar_brutos": guardar_brutos,
        "total_previsto": sum(SERIES[name] for name in steps),
        "etapas": [{"serie": name, "previstas": SERIES[name], "status": "pendente"} for name in steps],
        "observacao": "As respostas são selecionadas do banco pré-gerado; contraste é separado das séries principais.",
    }
    _gravar(path_manifest, manifest)
    ok = True
    try:
        for info in manifest["etapas"]:
            name = info["serie"]
            info["status"] = "em_andamento"
            cmd = _comando(name, path, bank, workers, guardar_brutos)
            info["comando"] = cmd
            _gravar(path_manifest, manifest)
            print(f"Série {name}: {info['previstas']} execuções", flush=True)
            result = subprocess.run(cmd, cwd=RAIZ, check=False)
            info["codigo_saida"] = result.returncode
            info["status"] = "concluido" if result.returncode == 0 else "falhou"
            if result.returncode:
                ok = False
                break
        manifest["status"] = "concluido" if ok else "falhou"
    except BaseException:
        manifest["status"] = "falhou"
        manifest["erro"] = traceback.format_exc()
        raise
    finally:
        manifest["fim_utc"] = datetime.now(timezone.utc).isoformat()
        _gravar(path_manifest, manifest)
    return path, ok


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Séries de simulação com respostas pré-geradas")
    parser.add_argument("serie", choices=(*SERIES, "todas"))
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--banco", default=str(BANCO_PADRAO))
    parser.add_argument("--saida", default=str(SAIDA_PADRAO), help="Diretório-base para novas execuções")
    parser.add_argument("--guardar-brutos", action="store_true", help="Preserva dados brutos das séries de ruído e centros")
    parser.add_argument("--planejar", action="store_true", help="Mostra as séries e quantidades sem executá-las")
    args = parser.parse_args(argv)
    if args.workers < 1:
        parser.error("--workers deve ser pelo menos 1")
    if args.guardar_brutos and args.serie not in ("ruido", "centros", "todas"):
        parser.error("--guardar-brutos está disponível para ruído e centros")
    if args.planejar:
        for name in _etapas(args.serie):
            print(f"{name}: {SERIES[name]}")
        print(f"Total: {sum(SERIES[name] for name in _etapas(args.serie))}")
        return 0
    try:
        path, ok = executar(args.serie, args.saida, args.banco, args.workers, args.guardar_brutos)
    except (OSError, ValueError) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    print(f"Resultados: {path}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
