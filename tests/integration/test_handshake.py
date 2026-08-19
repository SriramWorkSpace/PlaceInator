"""M0 acceptance: the sidecar must start, announce itself, and gate the API.

This is the contract the Rust shell depends on, so it is tested against a real
subprocess rather than an in-process app -- an in-process test would not catch a
stray print corrupting the handshake line.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time

import httpx
import pytest

from placeinator.main import HANDSHAKE_PREFIX


@pytest.fixture(scope="module")
def sidecar(tmp_path_factory, repo_root):
    """Launch the sidecar exactly as the shell will, and parse its handshake."""
    data_dir = tmp_path_factory.mktemp("appdata")
    env = {
        **_clean_env(),
        "PLACEINATOR_DATA_DIR": str(data_dir),
        "PLACEINATOR_LOG_LEVEL": "warning",
    }

    proc = subprocess.Popen(
        [sys.executable, "-m", "placeinator.main"],
        cwd=repo_root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    try:
        line = _read_handshake(proc, timeout=30.0)
        assert line.startswith(HANDSHAKE_PREFIX), f"unexpected first stdout line: {line!r}"
        payload = json.loads(line[len(HANDSHAKE_PREFIX) :].strip())

        base_url = f"http://127.0.0.1:{payload['port']}"
        _wait_for_health(base_url, timeout=30.0)
        yield base_url, payload["token"]
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def _clean_env() -> dict[str, str]:
    import os

    return {k: v for k, v in os.environ.items() if not k.startswith("PLACEINATOR_")}


def _read_handshake(proc: subprocess.Popen, timeout: float) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        line = proc.stdout.readline()  # type: ignore[union-attr]
        if line:
            return line
        if proc.poll() is not None:
            stderr = proc.stderr.read()  # type: ignore[union-attr]
            raise RuntimeError(f"sidecar exited early (code {proc.returncode}):\n{stderr}")
    raise TimeoutError("no handshake line within timeout")


def _wait_for_health(base_url: str, timeout: float) -> None:
    deadline = time.monotonic() + timeout
    last: Exception | None = None
    while time.monotonic() < deadline:
        try:
            if httpx.get(f"{base_url}/health", timeout=2.0).status_code == 200:
                return
        except Exception as exc:  # server still binding
            last = exc
        time.sleep(0.1)
    raise TimeoutError(f"sidecar never became healthy: {last}")


def test_handshake_reports_a_reachable_port(sidecar):
    base_url, _ = sidecar
    response = httpx.get(f"{base_url}/health", timeout=5.0)
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_protected_route_rejects_missing_token(sidecar):
    base_url, _ = sidecar
    assert httpx.get(f"{base_url}/api/status", timeout=5.0).status_code == 401


def test_protected_route_rejects_wrong_token(sidecar):
    base_url, _ = sidecar
    response = httpx.get(
        f"{base_url}/api/status",
        headers={"Authorization": "Bearer not-the-real-token"},
        timeout=5.0,
    )
    assert response.status_code == 401


def test_protected_route_accepts_handshake_token_and_reaches_the_database(sidecar):
    base_url, token = sidecar
    response = httpx.get(
        f"{base_url}/api/status",
        headers={"Authorization": f"Bearer {token}"},
        timeout=5.0,
    )
    assert response.status_code == 200

    body = response.json()
    assert body["database_ok"] is True
    # Schema was created on startup, so the real tables must be present.
    assert body["table_count"] >= 8
