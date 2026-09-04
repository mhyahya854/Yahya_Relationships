use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;

use tauri::{Manager, RunEvent};

struct BackendProcess(Mutex<Option<Child>>);

fn spawn_backend() -> Option<Child> {
    if let Ok(exe) = std::env::var("PR_BACKEND_EXE") {
        if !exe.trim().is_empty() {
            let path = PathBuf::from(exe);
            if let Some(dir) = path.parent() {
                return Command::new(&path)
                    .current_dir(dir)
                    .spawn()
                    .map_err(|error| eprintln!("backend spawn failed: {error}"))
                    .ok();
            }
        }
    }

    let mut root: Option<PathBuf> = None;
    if let Ok(cwd) = std::env::current_dir() {
        for candidate in cwd.ancestors() {
            if candidate.join("Codebase").join("App").join("Backend").join("main.py").exists()
                || candidate.join("app").join("backend").join("main.py").exists()
            {
                root = Some(candidate.to_path_buf());
                break;
            }
        }
    }
    let root = root?;

    let python_commands: &[&[&str]] = &[
        &["Codebase/.venv/Scripts/python.exe", "-m", "app.backend.main"],
        &[".venv/Scripts/python.exe", "-m", "app.backend.main"],
        &["python", "-m", "app.backend.main"],
    ];
    for command in python_commands {
        if command[0].contains('/') || command[0].contains('\\') {
            let full = root.join(command[0]);
            if !full.exists() {
                continue;
            }
        }
        if let Ok(child) = Command::new(command[0])
            .args(&command[1..])
            .current_dir(&root)
            .spawn()
        {
            return Some(child);
        }
    }
    None
}

#[tauri::command]
fn open_path(path: String) -> Result<(), String> {
    #[cfg(target_os = "windows")]
    {
        Command::new("explorer")
            .arg(&path)
            .spawn()
            .map_err(|error| format!("could not open folder: {error}"))?;
        return Ok(());
    }
    #[cfg(not(target_os = "windows"))]
    {
        let opener = if cfg!(target_os = "macos") { "open" } else { "xdg-open" };
        Command::new(opener)
            .arg(&path)
            .spawn()
            .map_err(|error| format!("could not open folder: {error}"))?;
        Ok(())
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .setup(|app| {
            if let Some(child) = spawn_backend() {
                app.manage(BackendProcess(Mutex::new(Some(child))));
            }
            let window = app.get_webview_window("main").unwrap();
            let _ = window.show();
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![open_path])
        .build(tauri::generate_context!())
        .expect("error while building People Relationships");
    app.run(|app_handle, event| {
        if let RunEvent::Exit = event {
            if let Some(state) = app_handle.try_state::<BackendProcess>() {
                if let Some(mut child) = state.0.lock().unwrap().take() {
                    let _ = child.kill();
                }
            }
        }
    });
}
