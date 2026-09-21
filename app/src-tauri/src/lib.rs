mod engine;

use engine::{Endpoint, EngineState};
use tauri::{Emitter, Manager, RunEvent};

/// The webview asks for this once on boot; every request it makes carries the
/// token. Passing it through a command rather than injecting it into the page
/// keeps it out of the DOM and out of any page source the user might save.
#[tauri::command]
fn engine_endpoint(state: tauri::State<'_, EngineState>) -> Result<Endpoint, String> {
    state
        .endpoint
        .lock()
        .unwrap()
        .clone()
        .ok_or_else(|| "engine is not running".to_string())
}

#[tauri::command]
fn restart_engine(app: tauri::AppHandle) -> Result<Endpoint, String> {
    engine::shutdown(&app);
    *app.state::<EngineState>().shutting_down.lock().unwrap() = false;
    engine::spawn(&app)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .manage(EngineState::default())
        .invoke_handler(tauri::generate_handler![engine_endpoint, restart_engine])
        .setup(|app| {
            let handle = app.handle().clone();
            // Spawn off the main thread: the handshake blocks, and blocking
            // setup() delays the window appearing.
            std::thread::spawn(move || match engine::spawn(&handle) {
                Ok(endpoint) => {
                    let _ = handle.emit("engine://ready", endpoint);
                }
                Err(err) => {
                    eprintln!("engine failed to start: {err}");
                    let _ = handle.emit("engine://failed", err);
                }
            });
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building Not3")
        .run(|app, event| {
            if let RunEvent::ExitRequested { .. } | RunEvent::Exit = event {
                engine::shutdown(app);
            }
        });
}
