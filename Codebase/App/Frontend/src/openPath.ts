import { invoke } from "@tauri-apps/api/core";

export function isTauri(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

export async function openFolder(path: string): Promise<string> {
  if (!isTauri()) {
    return "Not running inside the desktop shell — open the folder manually:\n" + path;
  }
  try {
    await invoke("open_path", { path });
    return "Opened: " + path;
  } catch (error) {
    return "Could not open folder: " + String(error);
  }
}
