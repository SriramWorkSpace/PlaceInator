//! Sidecar supervision: spawn the Python sidecar, read its one-line
//! handshake, inject `window.__PLACEINATOR__` before the frontend's own
//! scripts run, and kill the sidecar on exit.
//!
//! The protocol is fully specified in `placeinator/main.py` and
//! `docs/decisions.md` (ADR 0001) -- this only implements the Rust side of
//! it. Dev-mode only: spawns `.venv/Scripts/python.exe -m placeinator.main`
//! directly rather than a bundled binary. `PLACEINATOR_DATA_DIR` is
//! deliberately left unset here -- only a packaged build should override it
//! (see `placeinator/settings.py`'s own comment on that field).

use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::{mpsc, Mutex};
use std::time::Duration;

use serde::Deserialize;
use tauri::{Manager, RunEvent, WebviewUrl, WebviewWindowBuilder};

const HANDSHAKE_PREFIX: &str = "PLACEINATOR_READY";
const HANDSHAKE_TIMEOUT: Duration = Duration::from_secs(30);

#[derive(Deserialize)]
struct Handshake {
    port: u16,
    token: String,
}

/// Holds the sidecar's `Child` for the app's lifetime, so the exit handler
/// can kill it. `None` once taken (killed, or never successfully spawned).
struct SidecarProcess(Mutex<Option<Child>>);

fn repo_root() -> PathBuf {
    // src-tauri/ is always a direct child of the repo root -- true in dev
    // and, once PyInstaller wiring lands, still true for a packaged build's
    // own resolution (that phase is deferred; this fn only serves dev mode).
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .expect("src-tauri has a parent directory")
        .to_path_buf()
}

fn spawn_sidecar() -> std::io::Result<Child> {
    let root = repo_root();
    let python = root.join(".venv").join("Scripts").join("python.exe");
    Command::new(python)
        .args(["-m", "placeinator.main"])
        .current_dir(&root)
        .stdout(Stdio::piped())
        // Sidecar logging goes to stderr by design (main.py repoints every
        // uvicorn handler there) -- inherit it so it lands in the same
        // console the Tauri process itself logs to.
        .stderr(Stdio::inherit())
        .spawn()
}

/// Blocks until the sidecar prints its handshake line, or `timeout` elapses,
/// or the sidecar exits without ever printing one. The blocking read runs on
/// a background thread so a sidecar that never writes *anything* still times
/// out -- `BufRead::read_line` has no built-in deadline, so a plain
/// elapsed-time check inside the read loop would never fire if the process
/// hangs silently.
fn read_handshake(child: &mut Child, timeout: Duration) -> Result<Handshake, String> {
    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| "sidecar stdout was not piped".to_string())?;
    let (tx, rx) = mpsc::channel();

    std::thread::spawn(move || {
        let mut reader = BufReader::new(stdout);
        let mut line = String::new();
        loop {
            line.clear();
            match reader.read_line(&mut line) {
                Ok(0) => {
                    let _ = tx.send(Err(
                        "sidecar exited before printing a handshake line".to_string()
                    ));
                    return;
                }
                Ok(_) => {
                    if let Some(payload) = line.trim_end().strip_prefix(HANDSHAKE_PREFIX) {
                        let result = serde_json::from_str::<Handshake>(payload.trim())
                            .map_err(|e| format!("could not parse handshake line: {e}"));
                        let _ = tx.send(result);
                        return;
                    }
                    // Not the handshake line. stdout should carry nothing
                    // else by contract, but keep reading rather than assume.
                }
                Err(e) => {
                    let _ = tx.send(Err(e.to_string()));
                    return;
                }
            }
        }
    });

    rx.recv_timeout(timeout).unwrap_or_else(|_| {
        Err(format!(
            "sidecar did not print a handshake line within {timeout:?}"
        ))
    })
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }

            let mut child = spawn_sidecar()
                .map_err(|e| format!("failed to spawn the Python sidecar: {e}"))?;

            let handshake = match read_handshake(&mut child, HANDSHAKE_TIMEOUT) {
                Ok(h) => h,
                Err(e) => {
                    log::error!("sidecar handshake failed: {e}");
                    // Best-effort: it may already have exited (that's one
                    // of the error paths in read_handshake).
                    let _ = child.kill();
                    return Err(format!("sidecar failed to start: {e}").into());
                }
            };

            // Injected before the frontend's own scripts run on every
            // navigation (Tauri's initialization_script guarantee), which
            // is what src/lib/api.ts's connection() depends on --  it reads
            // this synchronously on the very first API call.
            let init_script = format!(
                "window.__PLACEINATOR__ = {{ port: {}, token: {} }};",
                handshake.port,
                serde_json::to_string(&handshake.token).expect("a String always serializes"),
            );

            WebviewWindowBuilder::new(app, "main", WebviewUrl::default())
                .title("PlaceInator")
                .inner_size(1280.0, 800.0)
                .initialization_script(&init_script)
                .build()?;

            app.manage(SidecarProcess(Mutex::new(Some(child))));

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building the Tauri application")
        .run(|app_handle, event| {
            // Windows doesn't auto-reap a child when this process exits --
            // without this the sidecar outlives a closed window. A
            // Job-Object-based guarantee (survives a crash, not just a
            // clean exit) is a real gap, deliberately deferred rather than
            // bundled into this first pass.
            if let RunEvent::ExitRequested { .. } = event {
                if let Some(state) = app_handle.try_state::<SidecarProcess>() {
                    if let Ok(mut guard) = state.0.lock() {
                        if let Some(mut child) = guard.take() {
                            let _ = child.kill();
                        }
                    }
                }
            }
        });
}
