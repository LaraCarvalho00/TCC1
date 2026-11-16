"""Validação somente leitura do banco de tarefas e dos caches SQLite da grade Qwen."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..core.answer import extract_final_answer, normalize

EXPECTED_MODEL = "Qwen/Qwen3-0.6B"
EXPECTED_TASKS = 50
DEFAULT_GRADE = Path("sistema/results/grade-n50-r50-qwen3-20261116")


@dataclass
class ValidationIssue:
    level: str  # "error" | "warn"
    code: str
    message: str


@dataclass
class DatasetReport:
    ok: bool
    issues: list[ValidationIssue] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def add(self, level: str, code: str, message: str) -> None:
        self.issues.append(ValidationIssue(level, code, message))
        if level == "error":
            self.ok = False


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_task_bank(bank_path: Path) -> tuple[dict[str, dict], dict[str, str], str]:
    payload = json.loads(bank_path.read_text(encoding="utf-8-sig"))
    tasks = payload.get("tarefas")
    if not isinstance(tasks, list) or not tasks:
        raise ValueError("banco_smol: lista 'tarefas' ausente ou vazia")
    by_id = {}
    hashes = {}
    for item in tasks:
        tid = item["id"]
        if tid in by_id:
            raise ValueError(f"tarefa duplicada: {tid}")
        q = item["question"]
        if not q or item.get("answer") is None:
            raise ValueError(f"tarefa incompleta: {tid}")
        by_id[tid] = item
        hashes[tid] = hashlib.sha256(q.encode("utf-8")).hexdigest()
    digest = sha256_file(bank_path)
    return by_id, hashes, digest


def db_open_ro(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    return db


def parse_stored_answer(raw: str) -> Any:
    return json.loads(raw)


def stored_matches_parser(text: str, stored: Any) -> bool:
    reparsed = normalize(extract_final_answer(text or ""))
    stored_n = normalize(stored if not isinstance(stored, str) else json.loads(stored))
    if reparsed is None and stored_n is None:
        return True
    return reparsed == stored_n


def validate_task_bank(bank_path: Path) -> DatasetReport:
    report = DatasetReport(ok=True)
    try:
        by_id, _, digest = load_task_bank(bank_path)
    except ValueError as exc:
        report.add("error", "bank_invalid", str(exc))
        return report
    report.metrics["tasks"] = len(by_id)
    if len(by_id) != EXPECTED_TASKS:
        report.add("warn", "bank_task_count", f"esperadas {EXPECTED_TASKS} tarefas; encontradas {len(by_id)}")
    report.metrics["bank_sha256"] = digest
    return report


def validate_scenario_sqlite(
    sqlite_path: Path,
    *,
    by_id: dict[str, dict],
    hashes: dict[str, str],
    expected_requests: int | None = 2500,
    bank_sha256: str | None = None,
) -> DatasetReport:
    report = DatasetReport(ok=True, metrics={"scenario_sqlite": str(sqlite_path)})
    if not sqlite_path.is_file():
        report.add("error", "sqlite_missing", f"arquivo ausente: {sqlite_path}")
        return report

    db = db_open_ro(sqlite_path)
    try:
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for required in ("meta", "generations", "gateway_requests"):
            if required not in tables:
                report.add("error", "schema_table", f"tabela ausente: {required}")

        meta_row = db.execute("SELECT config FROM meta WHERE id=1").fetchone()
        if meta_row is None:
            report.add("error", "meta_missing", "meta.config ausente")
            config = {}
        else:
            config = json.loads(meta_row[0])
            report.metrics["model"] = config.get("model") or config.get("model_name")
            if report.metrics.get("model") and report.metrics["model"] != EXPECTED_MODEL:
                report.add("warn", "model_name", f"modelo {report.metrics['model']!r} != {EXPECTED_MODEL!r}")
            tasks_sha = config.get("tasks_sha256")
            if bank_sha256 and tasks_sha and tasks_sha != bank_sha256:
                report.add("error", "tasks_sha", "hash do banco na meta diverge do arquivo local")
            report.metrics["temperature"] = config.get("temperature")
            report.metrics["top_p"] = config.get("top_p")
            report.metrics["workers"] = config.get("workers")

        requests = db.execute("SELECT COUNT(*) FROM gateway_requests").fetchone()[0]
        generations = db.execute("SELECT COUNT(*) FROM generations").fetchone()[0]
        report.metrics["gateway_requests"] = requests
        report.metrics["generations"] = generations

        if expected_requests is not None and requests == expected_requests and generations != requests:
            report.add(
                "error",
                "join_count",
                f"gerações ({generations}) != pedidos ({requests}) em cenário aparentemente completo",
            )
        elif generations > requests:
            report.add("error", "orphan_generations", "há gerações a mais que pedidos no gateway")

        joined = db.execute(
            """
            SELECT COUNT(*) FROM gateway_requests r
            INNER JOIN generations g ON r.seed = g.seed AND r.question_hash = g.question_hash
            """
        ).fetchone()[0]
        report.metrics["joined"] = joined
        if joined != generations:
            report.add(
                "error",
                "join_gap",
                f"só {joined}/{generations} gerações combinam com gateway_requests (seed+question_hash)",
            )

        orphan_req = db.execute(
            """
            SELECT COUNT(*) FROM gateway_requests r
            LEFT JOIN generations g ON r.seed = g.seed AND r.question_hash = g.question_hash
            WHERE g.seed IS NULL
            """
        ).fetchone()[0]
        if orphan_req:
            report.add("warn", "pending_requests", f"{orphan_req} pedidos sem geração confirmada")

        null_text = 0
        null_answer = 0
        bad_hash = 0
        bad_task = 0
        parser_mismatch = 0
        no_hash = 0
        correct = 0

        rows = db.execute(
            """
            SELECT r.task_id, r.question_hash, g.answer, g.text
            FROM gateway_requests r
            JOIN generations g ON r.seed = g.seed AND r.question_hash = g.question_hash
            """
        )
        for row in rows:
            tid = row["task_id"]
            if tid not in by_id:
                bad_task += 1
                continue
            if row["question_hash"] != hashes[tid]:
                bad_hash += 1
                continue
            text = row["text"]
            if text is None or text == "":
                null_text += 1
            try:
                stored = parse_stored_answer(row["answer"])
            except json.JSONDecodeError:
                null_answer += 1
                continue
            if stored is None:
                null_answer += 1
            if not stored_matches_parser(text, stored):
                parser_mismatch += 1
            if "####" not in (text or ""):
                no_hash += 1
            expected = by_id[tid]["answer"]
            if normalize(stored) == normalize(expected):
                correct += 1

        report.metrics.update(
            {
                "null_text": null_text,
                "null_answer_json": null_answer,
                "task_id_unknown": bad_task,
                "question_hash_mismatch": bad_hash,
                "parser_mismatch": parser_mismatch,
                "without_hash_marker": no_hash,
                "raw_correct": correct,
                "raw_accuracy": correct / joined if joined else None,
            }
        )
        if bad_task:
            report.add("error", "unknown_task", f"{bad_task} linhas com task_id fora do banco")
        if bad_hash:
            report.add("error", "hash_mismatch", f"{bad_hash} linhas com question_hash != SHA256(pergunta)")
        if null_text:
            report.add("error", "empty_text", f"{null_text} textos vazios")
        if null_answer:
            report.add("error", "bad_answer_json", f"{null_answer} respostas JSON inválidas ou null")
        if parser_mismatch:
            report.add(
                "error",
                "parser_drift",
                f"{parser_mismatch} linhas: extract_final_answer(text) != valor armazenado",
            )
    finally:
        db.close()

    return report


def validate_grade_manifest(grade_dir: Path) -> DatasetReport:
    report = DatasetReport(ok=True, metrics={"grade_dir": str(grade_dir)})
    manifest = grade_dir / "manifesto_grade.json"
    if not manifest.is_file():
        report.add("error", "manifest_missing", f"ausente: {manifest}")
        return report
    data = json.loads(manifest.read_text(encoding="utf-8-sig"))
    cfg = data.get("configuracao", {})
    report.metrics["modelo_manifesto"] = cfg.get("modelo")
    report.metrics["tasks_sha256_manifesto"] = cfg.get("fingerprint", {}).get("tarefas_sha256")
    if cfg.get("modelo") != EXPECTED_MODEL:
        report.add("warn", "manifest_model", f"manifesto lista {cfg.get('modelo')!r}")
    scenarios = data.get("cenarios") or []
    report.metrics["scenario_count"] = len(scenarios)
    for sc in scenarios:
        report.metrics.setdefault("scenarios", []).append(
            {"id": sc["id"], "status": sc.get("status"), "tentativas": len(sc.get("tentativas") or [])}
        )
    return report


def validate_qwen_grade(
    root: Path,
    bank_path: Path | None = None,
) -> DatasetReport:
    """Valida manifesto, banco e cada cenário com inferencias.sqlite."""
    root = Path(root)
    if bank_path is None:
        bank_path = root.parent.parent / "dados" / "banco_smol.json"
    bank_path = Path(bank_path)
    if not bank_path.is_file():
        bank_path = Path(__file__).resolve().parents[1] / "dados" / "banco_smol.json"
    combined = DatasetReport(ok=True, metrics={"root": str(root)})
    bank_report = validate_task_bank(bank_path)
    combined.issues.extend(bank_report.issues)
    combined.metrics["bank"] = bank_report.metrics
    if not bank_report.ok:
        combined.ok = False
        return combined

    by_id, hashes, digest = load_task_bank(bank_path)
    manifest_report = validate_grade_manifest(root)
    combined.issues.extend(manifest_report.issues)
    combined.metrics["manifest"] = manifest_report.metrics
    if not manifest_report.ok:
        combined.ok = False

    cenarios = root / "cenarios"
    if not cenarios.is_dir():
        combined.add("error", "cenarios_dir", f"pasta ausente: {cenarios}")
        return combined

    scenario_reports = []
    for path in sorted(cenarios.glob("*/inferencias.sqlite")):
        scenario_id = path.parent.name
        manifest_sc = next(
            (s for s in (manifest_report.metrics.get("scenarios") or []) if s.get("id") == scenario_id),
            None,
        )
        status = (manifest_sc or {}).get("status")
        complete = status == "concluido"
        expected = 2500 if complete else None
        sc_report = validate_scenario_sqlite(
            path,
            by_id=by_id,
            hashes=hashes,
            expected_requests=expected,
            bank_sha256=digest,
        )
        sc_report.metrics["scenario_id"] = scenario_id
        sc_report.metrics["manifest_status"] = status
        scenario_reports.append(sc_report.metrics)
        for issue in sc_report.issues:
            tagged = ValidationIssue(issue.level, issue.code, f"{scenario_id}: {issue.message}")
            combined.issues.append(tagged)
            if issue.level == "error":
                combined.ok = False

    combined.metrics["scenarios_validated"] = scenario_reports
    return combined


def format_report_markdown(report: DatasetReport, title: str = "Validação do dataset Qwen") -> str:
    lines = [f"# {title}", "", f"**Resultado:** {'OK' if report.ok else 'FALHAS'}", ""]
    if report.metrics:
        lines.append("## Métricas")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(report.metrics, ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")
    if report.issues:
        lines.append("## Ocorrências")
        lines.append("")
        for item in report.issues:
            lines.append(f"- **{item.level}** `{item.code}`: {item.message}")
        lines.append("")
    return "\n".join(lines)