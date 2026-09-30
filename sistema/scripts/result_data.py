"""Leitura compatível dos checkpoints finais e validações executadas."""
import csv
import json
import os


def final_reputation_rows(folder):
    history = os.path.join(folder, "reputation_history.csv")
    if os.path.isfile(history):
        with open(history, encoding="utf-8", newline="") as handle:
            return [{"round_index": int(r["checkpoint"]) - 1,
                     "reputation_after": r["reputation"], "profile": r["profile"]}
                    for r in csv.DictReader(handle) if int(r["checkpoint"]) > 0]
    with open(os.path.join(folder, "per_node.csv"), encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def validation_rounds(folder):
    """None identifica resultado legado; [] significa nenhuma validação."""
    with open(os.path.join(folder, "summary.json"), encoding="utf-8") as handle:
        summary = json.load(handle)["summary"]
    return summary.get("validation_rounds")
