"""Functional smoke test for the PyInstaller onedir spike.

Not part of the test suite (tests/) -- this drives the *frozen* exe as a
black box over real HTTP, the same way the Rust shell would, to prove the
packaging spike's success criteria: starts, handshakes, serves /health,
initializes ONNX Runtime, loads the embedding model, embeds, ranks, and
touches SQLite -- all inside one process that isn't the dev venv.

Usage: <python> packaging/test_functional.py <path-to-PlaceInatorBackend.exe> [data-dir]
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import httpx

SDE_RESUME_TEX = r"""
\documentclass{article}
\begin{document}
Jane Doe
\section{Skills}
Python, FastAPI, PostgreSQL, Docker, Kubernetes
\section{Experience}
\begin{itemize}
\item Built a backend service in Python and FastAPI handling 10k requests/sec
\item Deployed services to Kubernetes and ran CI/CD pipelines
\end{itemize}
\end{document}
"""


def main() -> int:
    exe_path = Path(sys.argv[1]).resolve()
    data_dir = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else None

    env = {"PLACEINATOR_LOG_LEVEL": "info"}
    if data_dir is not None:
        env["PLACEINATOR_DATA_DIR"] = str(data_dir)

    print(f"[1/9] starting {exe_path}")
    proc = subprocess.Popen(
        [str(exe_path)],
        cwd=str(exe_path.parent),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    try:
        deadline = time.monotonic() + 60.0
        line = ""
        while time.monotonic() < deadline:
            line = proc.stdout.readline()
            if line:
                break
            if proc.poll() is not None:
                stderr = proc.stderr.read()
                print("[FAIL] process exited before printing a handshake line")
                print("---- stderr ----")
                print(stderr)
                return 1

        if not line.startswith("PLACEINATOR_READY"):
            print(f"[FAIL] unexpected first stdout line: {line!r}")
            return 1
        payload = json.loads(line[len("PLACEINATOR_READY") :].strip())
        port, token = payload["port"], payload["token"]
        base = f"http://127.0.0.1:{port}"
        headers = {"Authorization": f"Bearer {token}"}
        print(f"[2/9] handshake OK -- port {port}")

        with httpx.Client(base_url=base, headers=headers, timeout=60.0) as client:
            r = client.get("/health", headers={})
            assert r.status_code == 200 and r.json()["status"] == "ok", r.text
            print("[3/9] /health OK")

            r = client.get("/api/status")
            assert r.status_code == 200, r.text
            status = r.json()
            assert status["database_ok"] is True, status
            print(f"[4/9] SQLite OK -- {status['table_count']} tables, data_dir={status['data_dir']}")

            deadline = time.monotonic() + 120.0
            while time.monotonic() < deadline:
                r = client.get("/api/matching/model-status")
                model_status = r.json()
                if model_status["ready"]:
                    break
                time.sleep(2)
            assert model_status["ready"], f"model never became ready: {model_status}"
            print("[5/9] ONNX Runtime + embedding model ready")

            r = client.put(
                "/api/profile",
                json={"full_name": "Spike Tester", "email": "spike@example.com"},
            )
            assert r.status_code == 200, r.text
            print("[6/9] profile created")

            r = client.post(
                "/api/resumes",
                data={"label": "SDE", "source_format": "tex", "is_primary": "true"},
                files={"file": ("resume.tex", SDE_RESUME_TEX.encode(), "text/plain")},
            )
            assert r.status_code == 201, r.text
            resume = r.json()
            assert resume["chunk_count"] > 0, "resume produced no chunks -- embedding likely failed"
            print(f"[7/9] resume embedded -- {resume['chunk_count']} chunks (real ONNX inference)")

            r = client.post(
                "/api/jobs/manual",
                json={
                    "company": "Acme",
                    "designation": "Backend Engineer",
                    "description": "Python, FastAPI, Kubernetes",
                    "location": None,
                    "url": None,
                    "deadline": None,
                },
            )
            assert r.status_code == 201, r.text
            job_id = r.json()["id"]

            r = client.post(f"/api/matching/jobs/{job_id}/rank-resumes")
            assert r.status_code == 200, r.text
            matches = r.json()
            assert matches and matches[0]["resume_id"] == resume["id"], matches
            print(
                f"[8/9] real match computed -- semantic_score={matches[0]['semantic_score']:.3f}"
            )

        print("[9/9] shutting down")
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            print("[WARN] had to hard-kill -- terminate() alone didn't stop it in 10s")

        print("\nALL CHECKS PASSED")
        return 0

    except Exception:
        import traceback

        traceback.print_exc()
        return 1
    finally:
        if proc.poll() is None:
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
