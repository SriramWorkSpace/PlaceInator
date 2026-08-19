"""Sidecar entry point.

Startup handshake: this process binds an ephemeral loopback port itself, then
prints exactly one machine-readable line to stdout before serving:

    PLACEINATOR_READY {"port": 51234, "token": "..."}

The Rust shell reads that line, stops reading stdout, and injects both values
into the WebView. Binding the socket here rather than letting uvicorn do it is
what makes the port knowable before the server starts accepting.
"""

from __future__ import annotations

import copy
import json
import logging
import socket
import sys

import uvicorn
from uvicorn.config import LOGGING_CONFIG

from placeinator.app import create_app
from placeinator.security import generate_token
from placeinator.settings import get_settings

HANDSHAKE_PREFIX = "PLACEINATOR_READY"


def _stderr_only_log_config() -> dict:
    """uvicorn ships its access-log handler pointed at stdout.

    stdout is the handshake channel, so anything uvicorn writes there can
    interleave with -- or be mistaken for -- the ready line. Move every handler
    to stderr and leave stdout carrying exactly one line for its whole life.
    """
    config = copy.deepcopy(LOGGING_CONFIG)
    for handler in config.get("handlers", {}).values():
        if "stream" in handler:
            handler["stream"] = "ext://sys.stderr"
    return config


def _bind_socket(host: str, port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.listen(128)
    sock.set_inheritable(True)
    return sock


def _emit_handshake(port: int, token: str) -> None:
    payload = json.dumps({"port": port, "token": token})
    sys.stdout.write(f"{HANDSHAKE_PREFIX} {payload}\n")
    sys.stdout.flush()


def main() -> int:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,  # stdout is reserved for the handshake line
    )

    sock = _bind_socket(settings.host, settings.port)
    bound_port = sock.getsockname()[1]
    token = generate_token()

    app = create_app()
    config = uvicorn.Config(
        app,
        log_level=settings.log_level,
        access_log=settings.dev_mode,
        log_config=_stderr_only_log_config(),
        lifespan="on",
    )
    server = uvicorn.Server(config)

    _emit_handshake(bound_port, token)

    try:
        server.run(sockets=[sock])
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
