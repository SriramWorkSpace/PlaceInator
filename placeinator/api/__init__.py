"""HTTP layer.

One router module per feature, each exporting a module-level ``router``.
``placeinator.app.create_app`` registers them behind the handshake-token
dependency; only ``health`` is exposed unauthenticated, because the shell polls
it to learn when the sidecar is up -- before it has anything to authenticate
with.

Routers stay thin: request validation and response shaping only. Business logic
belongs in the feature packages so it stays testable without HTTP.
"""
