"""PyInstaller entry point for the sidecar spike (see decisions.md ADR 0001).

Not the dev entry point -- that's `python -m placeinator.main`, unchanged.
This wrapper exists only because PyInstaller's Analysis adds the *script's*
own directory to sys.path, not the repo root; running placeinator/main.py
directly as the frozen entry would break its `from placeinator.app import
...` absolute imports. Living outside the placeinator/ package and being
pointed at from placeinator_backend.spec's pathex=[repo_root] is what makes
`import placeinator` resolve correctly once frozen.
"""

from placeinator.main import main

if __name__ == "__main__":
    raise SystemExit(main())
