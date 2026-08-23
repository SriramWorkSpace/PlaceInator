//! Sidecar supervision: spawn the Python sidecar, read its one-line
//! handshake, inject `window.__PLACEINATOR__` before the frontend's own
//! scripts run, and guarantee it dies with this process -- cleanly or not.
//!
//! The protocol is fully specified in `placeinator/main.py` and
//! `docs/decisions.md` (ADR 0001) -- this only implements the Rust side of
//! it. Two spawn paths, chosen by build mode: a debug build runs
//! `.venv/Scripts/python.exe -m placeinator.main` directly out of the repo
//! (unchanged from before packaging existed); a release build runs the
//! PyInstaller-frozen backend shipped as a bundle resource (see
//! `spawn_packaged_sidecar` below and `packaging/placeinator_backend.spec`,
//! proven standalone by the M6 packaging spike). `PLACEINATOR_DATA_DIR` is
//! deliberately left unset on both paths -- `platformdirs.user_data_dir`
//! resolves the same per-user AppData location regardless of dev vs.
//! packaged (see `placeinator/settings.py`'s own comment on that field), so
//! there is nothing for either path to override.
//!
//! Two cleanup mechanisms, deliberately both kept (see `create_kill_on_close_job`):
//! the `RunEvent::ExitRequested` handler's `child.kill()` for a fast, explicit
//! kill on a clean window close, and a Windows Job Object as the crash-safety
//! net for every other way this process can end -- the ExitRequested handler
//! never runs on a crash or a forceful kill, so it alone always left the
//! sidecar orphaned in exactly those cases (the documented gap this file used
//! to carry, reconfirmed against the packaged M6 build: `WM_CLOSE` killed the
//! sidecar, `Stop-Process -Force` on the parent did not).

use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::{mpsc, Mutex};
use std::time::Duration;

#[cfg(windows)]
use std::os::windows::process::CommandExt;
#[cfg(windows)]
use std::os::windows::io::AsRawHandle;

#[cfg(windows)]
use windows::Win32::Foundation::HANDLE;
#[cfg(windows)]
use windows::Win32::System::JobObjects::{
    AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation,
    SetInformationJobObject, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
};

use serde::Deserialize;
use tauri::{Manager, RunEvent, WebviewUrl, WebviewWindowBuilder};

/// Windows process-creation flag: suppress the console window Windows would
/// otherwise auto-allocate for a console-subsystem child (the frozen
/// backend, built `console=True` -- see the spec's own comment on why that
/// wasn't changed) when its parent -- this release Tauri binary, built
/// `windows_subsystem = "windows"` in main.rs -- has no console of its own
/// to attach it to. Piping stdout alone does not suppress this; only the
/// creation flag does.
#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

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

/// Holds the Job Object handle for the app's lifetime -- purely to keep it
/// open (see `create_kill_on_close_job`'s doc comment for why that's the
/// entire mechanism). Never read back out; `app.manage()` needs somewhere
/// to keep it alive, nothing more.
///
/// `HANDLE` wraps a raw pointer, so it isn't `Send`/`Sync` by default; this
/// value is opaque OS-assigned data with no thread affinity, only ever
/// created once on the setup thread and never mutated afterward, which is
/// exactly the case these two impls exist for.
#[cfg(windows)]
struct SidecarJob(#[allow(dead_code)] HANDLE);
#[cfg(windows)]
unsafe impl Send for SidecarJob {}
#[cfg(windows)]
unsafe impl Sync for SidecarJob {}

/// Creates a Windows Job Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`
/// set. Windows closes every handle a process owns when that process ends,
/// for *any* reason including a crash or an external `TerminateProcess` --
/// with this limit set, the moment the job object's last handle closes (i.e.
/// this app's process ending, however it ends), every process still
/// assigned to the job is killed by the OS itself. No cooperative shutdown
/// code in this process has to run for that to happen, which is exactly the
/// property `RunEvent::ExitRequested`'s handler cannot offer on its own.
#[cfg(windows)]
fn create_kill_on_close_job() -> windows::core::Result<HANDLE> {
    let job = unsafe { CreateJobObjectW(None, windows::core::PCWSTR::null())? };

    let mut info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION::default();
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;

    unsafe {
        SetInformationJobObject(
            job,
            JobObjectExtendedLimitInformation,
            &info as *const _ as *const std::ffi::c_void,
            std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
        )?;
    }

    Ok(job)
}

fn repo_root() -> PathBuf {
    // src-tauri/ is always a direct child of the repo root at compile time --
    // true in dev, but CARGO_MANIFEST_DIR is baked in at build time, so this
    // would resolve to the *build machine's* checkout on an installed copy.
    // Only the debug spawn path (spawn_sidecar) ever calls this; the release
    // path resolves everything through app.path().resource_dir() instead
    // (spawn_packaged_sidecar), which is install-location-aware.
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .expect("src-tauri has a parent directory")
        .to_path_buf()
}

fn spawn_sidecar(app: &tauri::App) -> std::io::Result<Child> {
    if cfg!(debug_assertions) {
        let root = repo_root();
        let python = root.join(".venv").join("Scripts").join("python.exe");
        Command::new(python)
            .args(["-m", "placeinator.main"])
            .current_dir(&root)
            .stdout(Stdio::piped())
            // Sidecar logging goes to stderr by design (main.py repoints
            // every uvicorn handler there) -- inherit it so it lands in the
            // same console the Tauri process itself logs to.
            .stderr(Stdio::inherit())
            .spawn()
    } else {
        spawn_packaged_sidecar(app)
    }
}

/// Release-mode only: the debug branch above spawns the repo's own venv
/// Python directly, which does not exist in an installed application.
/// `tauri.conf.json`'s `bundle.resources` (not `externalBin`) ships the
/// whole PyInstaller onedir output under the app's resource directory --
/// `externalBin`'s sidecar convention is built for a single portable file,
/// but onedir's `_internal/` directory must sit next to the exe for
/// PyInstaller's own loader to find it (verified during the packaging
/// spike), so the whole folder travels as one resource tree instead of
/// being squeezed into that convention.
#[cfg(windows)]
fn spawn_packaged_sidecar(app: &tauri::App) -> std::io::Result<Child> {
    let resource_dir = app
        .path()
        .resource_dir()
        .map_err(|e| std::io::Error::other(format!("could not resolve resource_dir: {e}")))?;
    let backend_dir = resource_dir.join("backend");
    let exe = backend_dir.join("PlaceInatorBackend.exe");

    Command::new(&exe)
        .current_dir(&backend_dir)
        .stdout(Stdio::piped())
        // Stdio::null() rather than inherit(): this release binary is a
        // windowed-subsystem process (main.rs), so it normally has no
        // console and thus no valid stderr handle to hand down -- null()
        // guarantees the child gets a real (if discarding) handle instead
        // of possibly inheriting an invalid one.
        .stderr(Stdio::null())
        .creation_flags(CREATE_NO_WINDOW)
        .spawn()
}

#[cfg(not(windows))]
fn spawn_packaged_sidecar(_app: &tauri::App) -> std::io::Result<Child> {
    Err(std::io::Error::new(
        std::io::ErrorKind::Unsupported,
        "packaged sidecar spawning is only implemented for Windows (spec: PlaceInatorBackend.exe)",
    ))
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

            let mut child = spawn_sidecar(app)
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

            // Best-effort: a failure here (unexpected on any normal Windows
            // install) just means this run doesn't get the crash-safety net
            // below -- not worth failing the whole app over, the same
            // "degrade, don't crash" judgment call the Python side makes for
            // ModelDownloadError/OcrUnavailableError.
            #[cfg(windows)]
            match create_kill_on_close_job() {
                Ok(job) => {
                    let handle = HANDLE(child.as_raw_handle() as *mut _);
                    if let Err(e) = unsafe { AssignProcessToJobObject(job, handle) } {
                        log::warn!("could not assign the sidecar to its Job Object: {e}");
                    }
                    app.manage(SidecarJob(job));
                }
                Err(e) => log::warn!("could not create a Job Object for the sidecar: {e}"),
            }

            app.manage(SidecarProcess(Mutex::new(Some(child))));

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building the Tauri application")
        .run(|app_handle, event| {
            // The fast, explicit path for a clean window close -- the Job
            // Object created in setup() (create_kill_on_close_job) is what
            // covers every other way this process can end, including a
            // crash, where this handler never runs at all.
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
