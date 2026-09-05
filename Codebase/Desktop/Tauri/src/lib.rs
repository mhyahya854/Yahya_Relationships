use std::net::TcpListener;
use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::{Manager, RunEvent};

struct BackendState {
    port: u16,
    child: Mutex<Option<Child>>,
}

fn find_available_port() -> u16 {
    if let Ok(p_str) = std::env::var("PR_BACKEND_PORT") {
        if let Ok(p) = p_str.parse::<u16>() {
            return p;
        }
    }
    // Prefer default port 8765 if free
    if let Ok(listener) = TcpListener::bind("127.0.0.1:8765") {
        drop(listener);
        return 8765;
    }
    // Bind ephemeral port to find a free one
    if let Ok(listener) = TcpListener::bind("127.0.0.1:0") {
        if let Ok(addr) = listener.local_addr() {
            drop(listener);
            return addr.port();
        }
    }
    8765
}

fn find_packaged_sidecar() -> Option<PathBuf> {
    if let Ok(exe) = std::env::var("PR_BACKEND_EXE") {
        if !exe.trim().is_empty() {
            let p = PathBuf::from(exe);
            if p.exists() {
                return Some(p);
            }
        }
    }

    let binary_name = if cfg!(target_os = "windows") {
        "people-relationships-backend.exe"
    } else {
        "people-relationships-backend"
    };

    if let Ok(current) = std::env::current_exe() {
        if let Some(parent) = current.parent() {
            // 1. Same directory as current_exe
            let cand1 = parent.join(binary_name);
            if cand1.exists() {
                return Some(cand1);
            }
            // 2. binaries subfolder
            let cand2 = parent.join("binaries").join(binary_name);
            if cand2.exists() {
                return Some(cand2);
            }
            // 3. macOS bundle Contents/MacOS/
            #[cfg(target_os = "macos")]
            {
                let cand_mac = parent.join(binary_name);
                if cand_mac.exists() {
                    return Some(cand_mac);
                }
            }
        }
    }

    // 4. Check Desktop/Tauri/binaries for target-triple naming during development/staging
    if let Ok(cwd) = std::env::current_dir() {
        for candidate in cwd.ancestors() {
            let bin_dir = candidate.join("Codebase").join("Desktop").join("Tauri").join("binaries");
            if bin_dir.exists() {
                if let Ok(entries) = std::fs::read_dir(&bin_dir) {
                    for entry in entries.flatten() {
                        let path = entry.path();
                        if let Some(name) = path.file_name().and_then(|n| n.to_str()) {
                            if name.starts_with("people-relationships-backend") && path.is_file() {
                                return Some(path);
                            }
                        }
                    }
                }
            }
        }
    }

    None
}

fn spawn_backend(port: u16) -> Option<Child> {
    // Try packaged sidecar first
    if let Some(sidecar) = find_packaged_sidecar() {
        eprintln!("Launching packaged backend sidecar: {:?}", sidecar);
        if let Some(dir) = sidecar.parent() {
            let mut cmd = Command::new(&sidecar);
            cmd.arg("--port")
                .arg(port.to_string())
                .arg("--host")
                .arg("127.0.0.1")
                .env("PR_BACKEND_PORT", port.to_string())
                .env("PR_PARENT_PID", std::process::id().to_string())
                .current_dir(dir);

            #[cfg(target_os = "windows")]
            {
                use std::os::windows::process::CommandExt;
                const CREATE_NO_WINDOW: u32 = 0x08000000;
                cmd.creation_flags(CREATE_NO_WINDOW);
            }

            match cmd.spawn() {
                Ok(child) => return Some(child),
                Err(err) => eprintln!("Failed to spawn packaged sidecar: {err}"),
            }
        }
    }

    // Fallback to development mode (Python from .venv or PATH)
    let mut root: Option<PathBuf> = None;
    if let Ok(cwd) = std::env::current_dir() {
        for candidate in cwd.ancestors() {
            if candidate
                .join("Codebase")
                .join("App")
                .join("app")
                .join("backend")
                .join("main.py")
                .exists()
            {
                root = Some(candidate.to_path_buf());
                break;
            }
        }
    }
    let root = root?;

    let venv_python = if cfg!(target_os = "windows") {
        root.join("Codebase").join(".venv").join("Scripts").join("python.exe")
    } else {
        root.join("Codebase").join(".venv").join("bin").join("python")
    };
    let package_root = root.join("Codebase").join("App");

    let pythons: Vec<PathBuf> = if venv_python.exists() {
        vec![venv_python]
    } else if cfg!(target_os = "windows") {
        vec![PathBuf::from("python"), PathBuf::from("python3")]
    } else {
        vec![PathBuf::from("python3"), PathBuf::from("python")]
    };

    for py in pythons {
        let mut cmd = Command::new(&py);
        cmd.args(["-m", "app.backend.main", "--port", &port.to_string()])
            .current_dir(&package_root)
            .env("PYTHONPATH", &package_root)
            .env("PR_BACKEND_PORT", port.to_string())
            .env("PR_PARENT_PID", std::process::id().to_string());

        #[cfg(target_os = "windows")]
        {
            use std::os::windows::process::CommandExt;
            const CREATE_NO_WINDOW: u32 = 0x08000000;
            cmd.creation_flags(CREATE_NO_WINDOW);
        }

        if let Ok(child) = cmd.spawn() {
            return Some(child);
        }
    }

    None
}

fn wait_for_backend_readiness(port: u16, max_duration: Duration) -> bool {
    let start = Instant::now();
    let client = std::net::TcpStream::connect;
    let target = format!("127.0.0.1:{port}");

    while start.elapsed() < max_duration {
        if client(&target).is_ok() {
            return true;
        }
        std::thread::sleep(Duration::from_millis(150));
    }
    false
}

#[tauri::command]
async fn pick_folder(app: tauri::AppHandle) -> Result<Option<String>, String> {
    use tauri_plugin_dialog::DialogExt;
    let folder = app.dialog().file().blocking_pick_folder();
    Ok(folder.map(|p| p.to_string()))
}

#[tauri::command]
fn get_backend_url(state: tauri::State<BackendState>) -> String {
    format!("http://127.0.0.1:{}", state.port)
}

#[tauri::command]
fn get_backend_port(state: tauri::State<BackendState>) -> u16 {
    state.port
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
    let port = find_available_port();

    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.unminimize();
                let _ = window.set_focus();
            }
        }))
        .plugin(tauri_plugin_dialog::init())
        .setup(move |app| {
            let child = spawn_backend(port);
            app.manage(BackendState {
                port,
                child: Mutex::new(child),
            });

            // Wait for backend readiness before displaying window
            let _ = wait_for_backend_readiness(port, Duration::from_secs(12));

            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_backend_url,
            get_backend_port,
            open_path,
            pick_folder,
        ])
        .build(tauri::generate_context!())
        .expect("error while building People Relationships");

    app.run(|app_handle, event| match event {
        RunEvent::Exit | RunEvent::ExitRequested { .. } => {
            if let Some(state) = app_handle.try_state::<BackendState>() {
                if let Some(mut child) = state.child.lock().unwrap().take() {
                    let _ = child.kill();
                }
            }
        }
        _ => {}
    });
}
