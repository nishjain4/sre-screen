"""Run repository checks without deployment credentials or production access."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def run_check(name: str, command: list[str], cwd: Path, output: Path,
              timeout: int = 600) -> dict:
    started = time.monotonic()
    log = output / f"{name}.log"
    try:
        with log.open("wb") as stream:
            result = subprocess.run(command, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT,
                                    timeout=timeout, check=False)
        code = result.returncode
    except (OSError, subprocess.TimeoutExpired) as exc:
        with log.open("a", encoding="utf-8") as stream:
            stream.write(f"\n{type(exc).__name__}: {exc}\n")
        code = 124
    return {"name": name, "status": "passed" if code == 0 else "failed",
            "exit_code": code, "seconds": round(time.monotonic() - started, 2),
            "log": log.name}


def write_report(checks: list[dict], output: Path) -> dict:
    report = {"version": 1, "timestamp": datetime.now(timezone.utc).isoformat(),
              "status": "failed" if any(check["status"] == "failed" for check in checks) else "passed",
              "checks": checks}
    (output / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = ["# Repository Validation", "", f"Result: **{report['status']}**", "",
             "| Check | Status | Log |", "| --- | --- | --- |"]
    lines.extend(f"| {check['name']} | {check['status']} | {check['log']} |" for check in checks)
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("validation-results"))
    parser.add_argument("--include-tests", action="store_true",
                        help="Also run local test suites (not shipped in this repository)")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    os.environ.update(LLM_PROVIDER="offline", AWS_EC2_METADATA_DISABLED="true",
                      MCP_CONFIG_PATH=str(root / "automation" / "offline-mcp.yaml"),
                      DATABASE_PATH=str(output / "smoke.db"), API_KEY="", GITEA_TOKEN="")
    npm = shutil.which("npm")
    if npm is None:
        parser.error("npm is required; install Node.js 22 or newer")
    checks = [
        ("python-static", [sys.executable, "-m", "ruff", "check", "backend/app", "automation", "gitea_mcp",
                           "--select", "E9,F63,F7,F82", "--output-format", "concise"], root),
        ("backend-build", [sys.executable, "-m", "build", "backend", "--outdir", str(output / "dist")], root),
        ("frontend-build", [npm, "run", "build"], root / "frontend"),
        ("startup-health", [sys.executable, "automation/smoke.py"], root),
    ]
    if args.include_tests:
        test_dirs = [path for path in ("backend/tests", "automation/tests") if (root / path).is_dir()]
        if not test_dirs:
            parser.error("--include-tests requires local test folders, which are not shipped")
        checks.insert(0, (
            "unit-integration",
            [sys.executable, "-m", "pytest", "-c", "backend/pyproject.toml", *test_dirs,
             "--ignore=backend/tests/test_bedrock.py", "-q"],
            root,
        ))
    results = [run_check(name, command, cwd, output) for name, command, cwd in checks]
    custom = root / "automation" / "custom-checks.json"
    if custom.exists():
        for index, command in enumerate(json.loads(custom.read_text(encoding="utf-8"))):
            if not isinstance(command, list) or not command or not all(isinstance(part, str) for part in command):
                raise ValueError("Custom checks must be nonempty argv arrays, never shell strings")
            results.append(run_check(f"custom-{index}", command, root, output))
    report = write_report(results, output)
    print((output / "report.md").read_text(encoding="utf-8"))
    return int(report["status"] != "passed")


if __name__ == "__main__":
    raise SystemExit(main())