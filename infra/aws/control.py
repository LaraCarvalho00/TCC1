"""Launch and reconcile temporary validation hosts; AWS access is lazy for local tests."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from sistema.aplicacao.capacidade_nuvem import DEFAULT_INSTANCE, plan_capacity
TERMINAL = {"completed", "failed", "timed_out"}


def utcnow():
    return datetime.now(timezone.utc)


def integer(value, name, minimum, maximum):
    if isinstance(value, bool) or not re.fullmatch(r"\d+", str(value)):
        raise ValueError(f"{name} must be an integer")
    result = int(value)
    if not minimum <= result <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return result


def payload(inputs, *, run_id, bucket, region, now=None):
    """Validate dispatch inputs before creating any billable resource."""
    if not re.fullmatch(r"gh-\d+-\d+", run_id):
        raise ValueError("Invalid run ID")
    mode = inputs.get("mode", "matrix")
    if mode not in {"matrix", "custom"}:
        raise ValueError("mode must be matrix or custom")
    honest = integer(inputs.get("honest_nodes", 40), "honest_nodes", 0, 100)
    malicious = integer(inputs.get("malicious_nodes", 10), "malicious_nodes", 0, 100)
    nodes = 50 if mode == "matrix" else honest + malicious
    if mode == "custom" and min(honest, malicious) < 1:
        raise ValueError("Custom mode requires at least one honest and one malicious node")
    if not 6 <= nodes <= 100:
        raise ValueError("The total number of nodes must be between 6 and 100")
    rounds = integer(inputs.get("rounds", 50), "rounds", 2, 50)
    hours = integer(inputs.get("max_hours", 72), "max_hours", 1, 168)
    seed = integer(inputs.get("seed", 0), "seed", 0, 2**31 - 1)
    # Matches the previous 50-round design; shorter smoke runs still attack.
    honest_rounds = min(5, rounds - 1)
    now = now or utcnow()
    deadline = now + timedelta(hours=hours)
    capacity = plan_capacity(nodes, inputs.get("instance_type", DEFAULT_INSTANCE))
    return {
        **capacity,
        "run_id": run_id, "mode": mode, "nodes": nodes,
        "honest_nodes": honest, "malicious_nodes": malicious,
        "rounds": rounds, "honest_rounds": honest_rounds, "seed": seed,
        "model": "HuggingFaceTB/SmolLM3-3B",
        "max_hours": hours, "deadline_epoch": int(deadline.timestamp()),
        "results_bucket": bucket, "results_prefix": f"runs/{run_id}", "aws_region": region,
        "created_at": now.isoformat(),
        "planned_scenarios": 16 if mode == "matrix" else 4,
        "planned_generations": nodes * rounds * (16 if mode == "matrix" else 4),
    }


def put_json(s3, bucket, key, data):
    s3.put_object(Bucket=bucket, Key=key, Body=json.dumps(data, indent=2).encode(),
                  ContentType="application/json", ServerSideEncryption="AES256")


def get_json(s3, bucket, key):
    try:
        return json.loads(s3.get_object(Bucket=bucket, Key=key)["Body"].read())
    except Exception as exc:
        if getattr(exc, "response", {}).get("Error", {}).get("Code") in {"NoSuchKey", "404"}:
            return None
        raise


def terraform(directory, *args, capture=False):
    return subprocess.run(["terraform", f"-chdir={directory}", *args], check=True,
                          text=True, capture_output=capture)


def init(directory, record):
    terraform(directory, "init", "-input=false", "-reconfigure",
              f"-backend-config=bucket={record['state_bucket']}",
              f"-backend-config=key=runs/{record['run_id']}/terraform.tfstate",
              f"-backend-config=region={record['aws_region']}",
              "-backend-config=encrypt=true", "-backend-config=use_lockfile=true")


def launch(session, inputs, settings, run_id, working):
    data = payload(inputs, run_id=run_id, bucket=settings["results_bucket"], region=settings["aws_region"])
    directory = ROOT / "infra" / "aws" / "run"
    variables = {
        "aws_region": settings["aws_region"], "project_name": settings["project_name"],
        "run_id": run_id, "results_bucket": settings["results_bucket"],
        "instance_type": data["instance_type"], "node_count": data["nodes"],
        "ami_id": settings.get("ami_id", ""),
        "runtime_permissions_boundary_arn": settings["runtime_permissions_boundary_arn"],
        "expires_at": datetime.fromtimestamp(data["deadline_epoch"], timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
    }
    working.mkdir(parents=True, exist_ok=True)
    archive = working / "source.tar.gz"
    subprocess.run(["git", "archive", "--format=tar.gz", f"--output={archive}", "HEAD"], cwd=ROOT, check=True)
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                            capture_output=True, text=True).stdout.strip()
    record = {**data, "state_bucket": settings["state_bucket"], "project_name": settings["project_name"],
              "terraform_variables": variables, "commit": commit,
              "source_sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}
    s3 = session.client("s3")
    prefix = data["results_prefix"]
    # Persist recovery data BEFORE apply, including partial provisioning failures.
    put_json(s3, data["results_bucket"], f"{prefix}/control/run.json", record)
    s3.upload_file(str(archive), data["results_bucket"], f"{prefix}/input/source.tar.gz",
                   ExtraArgs={"ServerSideEncryption": "AES256", "Tagging": "purpose=run-input"})
    put_json(s3, data["results_bucket"], f"{prefix}/input/run.json", data)
    varfile = working / "terraform.tfvars.json"
    varfile.write_text(json.dumps(variables), encoding="utf-8")
    (working / "run.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    init(directory, record)
    terraform(directory, "plan", "-input=false", "-lock-timeout=120s", f"-var-file={varfile}",
              f"-out={working / 'run.tfplan'}")
    terraform(directory, "apply", "-input=false", "-lock-timeout=120s", str(working / "run.tfplan"))
    outputs = json.loads(terraform(directory, "output", "-json", capture=True).stdout)
    record["outputs"] = {key: item["value"] for key, item in outputs.items()}
    put_json(s3, data["results_bucket"], f"{prefix}/control/run.json", record)
    (working / "run.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def should_cleanup(record, status, instance_states, *, now=None, force=False):
    if force:
        return True
    now = now or utcnow()
    if now.timestamp() >= record["deadline_epoch"]:
        return True
    if status and status.get("state") in TERMINAL and status.get("upload_complete") is True:
        return True
    # A host can terminate before publishing status (boot failure / watchdog).
    # Give launch at least one hour before treating no instance as a failed run.
    old_enough = (now - datetime.fromisoformat(record["created_at"])).total_seconds() >= 3600
    return old_enough and all(state == "terminated" for state in instance_states)


def extract_source(archive, destination):
    with tarfile.open(archive) as stream:
        for member in stream.getmembers():
            target = (destination / member.name).resolve()
            if not target.is_relative_to(destination.resolve()) or member.issym() or member.islnk() or member.isdev():
                raise ValueError("Unsafe source archive")
        stream.extractall(destination, filter="data")


def cleanup_one(session, record, *, force=False):
    s3 = session.client("s3")
    bucket, prefix = record["results_bucket"], record["results_prefix"]
    if get_json(s3, bucket, f"{prefix}/control/cleaned.json"):
        return "already_cleaned"
    status = get_json(s3, bucket, f"{prefix}/status.json")
    ec2 = session.client("ec2")
    reservations = ec2.describe_instances(Filters=[
        {"Name": "tag:Project", "Values": [record["project_name"]]},
        {"Name": "tag:RunId", "Values": [record["run_id"]]},
    ])["Reservations"]
    states = [instance["State"]["Name"] for group in reservations for instance in group["Instances"]]
    if not should_cleanup(record, status, states, force=force):
        return "running"
    # Also catches RunInstances succeeding immediately before Terraform loses
    # its runner/state write. Do not depend on downloading the archive or init
    # succeeding to stop the billable host; failures remain retryable below.
    live_ids = [instance["InstanceId"] for group in reservations for instance in group["Instances"]
                if instance["State"]["Name"] not in {"terminated", "shutting-down"}]
    if live_ids:
        ec2.terminate_instances(InstanceIds=live_ids)
    with tempfile.TemporaryDirectory(prefix="validation-cleanup-") as temp:
        work = Path(temp)
        archive = work / "source.tar.gz"
        s3.download_file(bucket, f"{prefix}/input/source.tar.gz", str(archive))
        if hashlib.sha256(archive.read_bytes()).hexdigest() != record["source_sha256"]:
            raise ValueError("Source archive hash mismatch")
        source = work / "source"
        source.mkdir()
        extract_source(archive, source)
        directory = source / "infra" / "aws" / "run"
        variables = work / "terraform.tfvars.json"
        variables.write_text(json.dumps(record["terraform_variables"]), encoding="utf-8")
        init(directory, record)
        terraform(directory, "destroy", "-auto-approve", "-input=false", "-lock-timeout=120s", f"-var-file={variables}")
    # Do not publish cleaned until EC2 confirms termination as well as destroy.
    if live_ids:
        ec2.get_waiter("instance_terminated").wait(InstanceIds=live_ids,
                                                  WaiterConfig={"Delay": 10, "MaxAttempts": 60})
    put_json(s3, bucket, f"{prefix}/control/cleaned.json", {"run_id": record["run_id"], "cleaned_at": utcnow().isoformat(),
             "forced": force, "worker_state": status.get("state") if status else "missing"})
    return "destroyed"


def records(s3, bucket, run_id=None):
    if run_id:
        if not re.fullmatch(r"gh-\d+-\d+", run_id):
            raise ValueError("Invalid run ID")
        record = get_json(s3, bucket, f"runs/{run_id}/control/run.json")
        return [record] if record else []
    result = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=bucket, Prefix="runs/", Delimiter="/"):
        for entry in page.get("CommonPrefixes", []):
            prefix = entry["Prefix"]
            if not get_json(s3, bucket, prefix + "control/cleaned.json"):
                record = get_json(s3, bucket, prefix + "control/run.json")
                if record:
                    result.append(record)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("launch", "cleanup"))
    parser.add_argument("--run-id")
    parser.add_argument("--force", action="store_true", help="Terminate the selected run immediately")
    args = parser.parse_args()
    if args.force and not args.run_id:
        parser.error("--force requires an explicit --run-id")
    import boto3
    region = os.environ["AWS_REGION"]
    bucket = os.environ["RESULTS_BUCKET"]
    session = boto3.Session(region_name=region)
    if args.command == "launch":
        if not args.run_id:
            parser.error("launch requires --run-id")
        settings = {"aws_region": region, "results_bucket": bucket, "state_bucket": os.environ["STATE_BUCKET"],
                    "project_name": os.environ.get("PROJECT_NAME") or "distributed-ai",
                    "runtime_permissions_boundary_arn": os.environ["RUNTIME_BOUNDARY_ARN"],
                    "ami_id": os.environ.get("GPU_AMI_ID", "")}
        if not settings["runtime_permissions_boundary_arn"] or not settings["state_bucket"] or not bucket:
            parser.error("Configure the bootstrap outputs in GitHub repository variables first")
        record = launch(session, json.loads(os.environ["DISPATCH_INPUTS"]), settings, args.run_id,
                        (ROOT / ".cloud" / args.run_id).resolve())
        message = (f"Run `{args.run_id}` launched asynchronously.\n\n"
                   f"{record['planned_scenarios']} scenarios; {record['planned_generations']:,} new generations.\n\n"
                   f"{record['model_instances']} independent resident NF4 models across {record['gpu_count']} GPUs.\n\n"
                   f"Results: `s3://{bucket}/{record['results_prefix']}/`\n\n"
                   f"Hard deadline (UTC): `{record['terraform_variables']['expires_at']}`.\n\n"
                   "The green launch job confirms provisioning; consult status.json for experiment completion.\n")
        print(message)
        if os.environ.get("GITHUB_STEP_SUMMARY"):
            with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as out:
                out.write(message)
    else:
        failed = []
        for record in records(session.client("s3"), bucket, args.run_id):
            try:
                print(record["run_id"], cleanup_one(session, record, force=args.force))
            except Exception as exc:
                failed.append(record["run_id"])
                print(f"Cleanup failed for {record['run_id']}: {exc}")
        if failed:
            raise RuntimeError(f"Cleanup failed for: {', '.join(failed)}")


if __name__ == "__main__":
    main()
