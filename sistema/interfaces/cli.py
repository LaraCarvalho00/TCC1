"""Entrada principal para as séries de inferência distribuída."""
from __future__ import annotations

import argparse

from sistema.interfaces import artigo_cli


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sistema de inferência distribuída")
    commands = parser.add_subparsers(dest="grupo", required=True)
    commands.add_parser("experimentos", add_help=False, help="Séries do artigo")
    _args, remainder = parser.parse_known_args(argv)
    return artigo_cli.main(remainder)


if __name__ == "__main__":
    raise SystemExit(main())
