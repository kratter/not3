//! Supervises the Python engine process.
//!
//! Deliberately uses `std::process::Command` rather than `tauri-plugin-shell`:
//! the plugin does not expose creation flags (needed to suppress a console
//! window on Windows) or the raw process handle (needed for the Job Object).
//! Since we spawn from Rust and never from JS, the shell plugin's ACL would
//! buy us nothing anyway.
//!
//! Three layers keep the engine from outliving the app:
//!   1. A Windows Job Object with KILL_ON_JOB_CLOSE — the kernel reaps the
//!      child whatever happens to us, including a Task Manager kill.
//!   2. An explicit kill on ExitRequested, for the ordinary path.
//!   3. `--parent-pid` and `--watch-stdin` in the engine itself, which is what
//!      covers macOS and Linux where there is no Job Object.

use std::io::{BufRead, BufReader};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;

use rand::Rng;
use serde::Serialize;
use tauri::{AppHandle, Emitter, Manager};

#[cfg(windows)]
use std::os::windows::process::CommandExt;

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

/// What the webview needs in order to talk to the engine.
#[derive(Clone, Debug, Serialize)]
pub struct Endpoint {
    pub base_url: String,
    pub token: String,
    pub pid: u32,
}

#[derive(Default)]
pub struct EngineState {
    pub endpoint: Mutex<Option<Endpoint>>,
    pub child: Mutex<Option<Child>>,
    pub shutting_down: Mutex<bool>,
}

fn random_token() -> String {
    let bytes: [u8; 32] = rand::thread_rng().gen();
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

/// Locate the bundled engine, or fall back to a dev checkout.
fn engine_command(app: &AppHandle) -> Result<Command, String> {
    // Bundled: PyInstaller onedir copied in through `bundle.resources`.
    let exe_name = if cfg!(windows) { "not3-engine.exe" } else { "not3-engine" };
    if let Ok(path) = app
        .path()
        .resolve(format!("engine/{exe_name}"), tauri::path::BaseDirectory::Resource)
    {
        if path.is_file() {
            return Ok(Command::new(path));
        }
    }

    // Explicit override, for running against an engine started by hand.
    if let Ok(custom) = std::env::var("NOT3_ENGINE_EXE") {
        return Ok(Command::new(custom));
    }

    // Dev checkout: drive the uv environment directly so there is no build
    // step between editing Python and seeing it in the app.
    if cfg!(debug_assertions) {
        let engine_dir = dev_engine_dir();
        if engine_dir.join("pyproject.toml").is_file() {
            let mut cmd = Command::new("uv");
            cmd.arg("run")
                .arg("--project")
                .arg(&engine_dir)
                .arg("not3-engine");
            return Ok(cmd);
        }
        return Err(format!(
            "No engine found. Looked for a bundled binary and for a dev checkout at {}",
            engine_dir.display()
        ));
    }

    Err("No engine binary found in app resources.".into())
}

fn dev_engine_dir() -> PathBuf {
    // CARGO_MANIFEST_DIR is app/src-tauri, so the engine is two levels up.
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(|p| p.parent())
        .map(|p| p.join("engine"))
        .unwrap_or_else(|| PathBuf::from("../../engine"))
}

pub fn spawn(app: &AppHandle) -> Result<Endpoint, String> {
    let token = random_token();
    let mut cmd = engine_command(app)?;

    cmd.arg("--port")
        .arg("0")
        .arg("--parent-pid")
        .arg(std::process::id().to_string())
        .arg("--watch-stdin")
        .env("NOT3_TOKEN", &token)
        .stdin(Stdio::piped()) // a real pipe, so stdin EOF is a usable signal
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    #[cfg(windows)]
    cmd.creation_flags(CREATE_NO_WINDOW);

    let mut child = cmd
        .spawn()
        .map_err(|e| format!("Could not start the engine: {e}"))?;

    #[cfg(windows)]
    attach_to_job(&child);

    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| "engine produced no stdout".to_string())?;

    // The engine prints one JSON handshake line and then goes quiet. Read it
    // on this thread: the app is not usable until we know the port anyway.
    let mut reader = BufReader::new(stdout);
    let mut line = String::new();
    let mut endpoint: Option<Endpoint> = None;
    for _ in 0..40 {
        line.clear();
        match reader.read_line(&mut line) {
            Ok(0) => break,
            Ok(_) => {
                if let Ok(value) = serde_json::from_str::<serde_json::Value>(line.trim()) {
                    if value.get("event").and_then(|v| v.as_str()) == Some("ready") {
                        let port = value.get("port").and_then(|v| v.as_u64()).unwrap_or(0);
                        let pid = value.get("pid").and_then(|v| v.as_u64()).unwrap_or(0);
                        endpoint = Some(Endpoint {
                            base_url: format!("http://127.0.0.1:{port}"),
                            token: token.clone(),
                            pid: pid as u32,
                        });
                        break;
                    }
                }
            }
            Err(e) => return Err(format!("engine handshake failed: {e}")),
        }
    }

    let endpoint = endpoint.ok_or_else(|| {
        let _ = child.kill();
        "engine started but never reported a port".to_string()
    })?;

    // Drain stderr so a chatty engine cannot fill the pipe buffer and block.
    if let Some(stderr) = child.stderr.take() {
        let handle = app.clone();
        std::thread::spawn(move || {
            for line in BufReader::new(stderr).lines().map_while(Result::ok) {
                eprintln!("[engine] {line}");
                let _ = handle.emit("engine://log", line);
            }
        });
    }

    let state = app.state::<EngineState>();
    *state.endpoint.lock().unwrap() = Some(endpoint.clone());
    *state.child.lock().unwrap() = Some(child);

    supervise(app.clone());
    Ok(endpoint)
}

/// Notice if the engine dies on its own, so the UI can say so rather than
/// silently failing every request.
fn supervise(app: AppHandle) {
    std::thread::spawn(move || loop {
        std::thread::sleep(std::time::Duration::from_millis(400));

        // `State` borrows the AppHandle, so each probe gets its own scope and
        // yields a plain value; holding it across the emit below would keep a
        // MutexGuard alive longer than the borrow checker allows.
        let outcome: Option<Option<i32>> = {
            let state = app.state::<EngineState>();
            let mut guard = state.child.lock().unwrap();
            match guard.as_mut() {
                None => None,
                Some(child) => match child.try_wait() {
                    Ok(Some(status)) => Some(Some(status.code().unwrap_or(-1))),
                    Ok(None) => Some(None),
                    Err(_) => Some(Some(-1)),
                },
            }
        };

        let code = match outcome {
            None => return, // nothing to supervise
            Some(None) => continue, // still running
            Some(Some(code)) => code,
        };

        let intentional = {
            let state = app.state::<EngineState>();
            let intentional = *state.shutting_down.lock().unwrap();
            *state.child.lock().unwrap() = None;
            intentional
        };
        if !intentional {
            let _ = app.emit("engine://exited", code);
        }
        return;
    });
}

pub fn shutdown(app: &AppHandle) {
    let state = app.state::<EngineState>();
    *state.shutting_down.lock().unwrap() = true;
    // Bind before the `if let`: an `if let` scrutinee's temporaries live to the
    // end of the block, so the MutexGuard would outlive `state` itself.
    let child = state.child.lock().unwrap().take();
    if let Some(mut child) = child {
        // Dropping stdin closes the pipe, which the engine treats as a
        // shutdown signal; kill is the backstop if it does not take.
        drop(child.stdin.take());
        std::thread::sleep(std::time::Duration::from_millis(150));
        let _ = child.kill();
        let _ = child.wait();
    }
}

/// Put the child in a job that dies with us.
///
/// Without this, force-quitting the app leaves an orphaned Python process
/// holding the GPU and a lock on the database. Tauri does not reap sidecars
/// reliably (tauri#5611), so this is the only guarantee available on Windows.
#[cfg(windows)]
fn attach_to_job(child: &Child) {
    use std::os::windows::io::AsRawHandle;
    use windows_sys::Win32::Foundation::HANDLE;
    use windows_sys::Win32::System::JobObjects::{
        AssignProcessToJobObject, CreateJobObjectW, SetInformationJobObject,
        JobObjectExtendedLimitInformation, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    };

    // Leaked on purpose: the job must outlive this function and stay open for
    // the life of the process. Closing the handle is precisely what triggers
    // the kill, so it is released only when we exit — which is the point.
    static JOB: std::sync::OnceLock<usize> = std::sync::OnceLock::new();

    let job = *JOB.get_or_init(|| unsafe {
        let handle = CreateJobObjectW(std::ptr::null(), std::ptr::null());
        if handle.is_null() {
            return 0;
        }
        let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
        SetInformationJobObject(
            handle,
            JobObjectExtendedLimitInformation,
            &info as *const _ as *const std::ffi::c_void,
            std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
        );
        handle as usize
    });

    if job != 0 {
        unsafe {
            AssignProcessToJobObject(job as HANDLE, child.as_raw_handle() as HANDLE);
        }
    }
}
