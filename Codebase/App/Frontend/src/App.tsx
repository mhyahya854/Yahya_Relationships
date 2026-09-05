import { useEffect, useState } from "react";
import { api } from "./api";
import { Avatar } from "./components/ui";
import { PerspectiveProvider, usePerspective } from "./state";
import type { Person } from "./types";
import { BackupsView } from "./views/BackupsView";
import { FamilyView } from "./views/FamilyView";
import { HermesView } from "./views/HermesView";
import { PeopleView } from "./views/PeopleView";
import { RelationshipsView } from "./views/RelationshipsView";
import { SearchView } from "./views/SearchView";
import { RootUnavailableView } from "./features/dataRoot/components/RootUnavailableView";
import { StartupFailureView } from "./features/startupFailure/StartupFailureView";

type Screen = "people" | "relationships" | "family" | "search" | "hermes" | "backups";

const NAV: Array<{ id: Screen; label: string; icon: string }> = [
  { id: "people", label: "People", icon: "◉" },
  { id: "relationships", label: "Relationships", icon: "⌁" },
  { id: "family", label: "Family", icon: "❖" },
  { id: "search", label: "Search", icon: "⌕" },
  { id: "hermes", label: "Hermes", icon: "◇" },
  { id: "backups", label: "Backups", icon: "▤" },
];

function PerspectiveSelector() {
  const { perspectiveId, perspectivePerson, defaultId, setPerspective, returnToDefault } =
    usePerspective();
  const [people, setPeople] = useState<Person[]>([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    api.people.list().then((result) => setPeople(result.people)).catch(() => undefined);
  }, []);

  if (!perspectivePerson || !perspectiveId) {
    return <div className="perspective-selector">Loading perspective…</div>;
  }
  const isDefault = perspectiveId === defaultId;
  return (
    <div className="perspective-selector">
      <span className="perspective-label">Viewing relationships from:</span>
      <div className="perspective-current-wrap">
        <button
          type="button"
          className="perspective-current"
          onClick={() => setOpen((value) => !value)}
        >
          <Avatar person={perspectivePerson} size={24} />
          <strong>{perspectivePerson.name}</strong>
          <span className="chevron">▾</span>
        </button>
        {open && (
          <div className="perspective-dropdown">
            <div className="perspective-dropdown-scroll">
              {people.map((person) => (
                <button
                  type="button"
                  key={person.id}
                  className={person.id === perspectiveId ? "selected" : ""}
                  onClick={() => {
                    void setPerspective(person.id);
                    setOpen(false);
                  }}
                >
                  <Avatar person={person} size={22} />
                  <span>{person.name}</span>
                  {person.id === perspectiveId && <span className="check">✓</span>}
                </button>
              ))}
            </div>
            <button
              type="button"
              className="perspective-return"
              disabled={isDefault}
              onClick={() => void returnToDefault()}
            >
              Return to My Perspective
            </button>
          </div>
        )}
      </div>
      {!isDefault && (
        <button type="button" className="btn btn-ghost" onClick={() => void returnToDefault()}>
          Return to My Perspective
        </button>
      )}
    </div>
  );
}

function Shell() {
  const [screen, setScreen] = useState<Screen>("relationships");
  const { perspectivePerson } = usePerspective();

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">PR</div>
          <div>
            <div className="brand-title">People</div>
            <div className="brand-sub">Relationships</div>
          </div>
        </div>
        <nav className="nav">
          {NAV.map((item) => (
            <button
              type="button"
              key={item.id}
              className={screen === item.id ? "nav-item active" : "nav-item"}
              onClick={() => setScreen(item.id)}
            >
              <span className="nav-icon">{item.icon}</span>
              <span>{item.label}</span>
            </button>
          ))}
        </nav>
        <div className="sidebar-foot">
          <div className="muted small">
            Owner: {perspectivePerson?.name ?? "…"}
          </div>
          <div className="muted tiny">Local-first · SQLite · Markdown</div>
        </div>
      </aside>
      <main className="main">
        <header className="topbar">
          <PerspectiveSelector />
        </header>
        <div className="content">
          {screen === "people" && <PeopleView />}
          {screen === "relationships" && <RelationshipsView />}
          {screen === "family" && <FamilyView />}
          {screen === "search" && <SearchView />}
          {screen === "hermes" && <HermesView />}
          {screen === "backups" && <BackupsView />}
        </div>
      </main>
    </div>
  );
}

export function App() {
  const [rootUnavailable, setRootUnavailable] = useState(false);
  const [isFirstRun, setIsFirstRun] = useState(false);
  const [lastLocation, setLastLocation] = useState<string | undefined>(undefined);
  const [backendFailure, setBackendFailure] = useState<{ port?: number; errorMessage?: string } | null>(null);
  const [checking, setChecking] = useState(true);

  const checkRoot = async () => {
    setChecking(true);
    setBackendFailure(null);
    try {
      if (typeof window !== "undefined" && "__TAURI_INTERNALS__" in window) {
        try {
          const { invoke } = await import("@tauri-apps/api/core");
          const backendStatus = await invoke<{ port: number; healthy: boolean; error?: string }>("get_backend_status");
          if (!backendStatus.healthy) {
            setBackendFailure({
              port: backendStatus.port,
              errorMessage: backendStatus.error || "The local data service did not respond to health checks.",
            });
            setChecking(false);
            return;
          }
        } catch {
          // Fallback to direct HTTP check if command is unavailable
        }
      }

      const status = await api.dataRoot.status();
      setBackendFailure(null);
      if (status.first_run || status.configured === false) {
        setIsFirstRun(true);
        setRootUnavailable(true);
        setLastLocation(status.active_root);
      } else if (!status.health.ok && status.health.issues.some((i) => i.code === "DATA_ROOT_MISSING" || i.code === "DATABASE_MISSING")) {
        setIsFirstRun(false);
        setRootUnavailable(true);
        setLastLocation(status.active_root);
      } else {
        setIsFirstRun(false);
        setRootUnavailable(false);
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      let port: number | undefined = undefined;
      if (typeof window !== "undefined" && "__TAURI_INTERNALS__" in window) {
        try {
          const { invoke } = await import("@tauri-apps/api/core");
          port = await invoke<number>("get_backend_port");
        } catch {}
      }
      setBackendFailure({ port, errorMessage: message });
    } finally {
      setChecking(false);
    }
  };

  useEffect(() => {
    void checkRoot();
  }, []);

  if (!checking && backendFailure) {
    return (
      <StartupFailureView
        port={backendFailure.port}
        errorMessage={backendFailure.errorMessage}
        onRetry={checkRoot}
      />
    );
  }

  if (!checking && rootUnavailable) {
    return (
      <RootUnavailableView
        firstRun={isFirstRun}
        lastLocation={lastLocation}
        onRecovered={() => {
          setRootUnavailable(false);
          setIsFirstRun(false);
          void checkRoot();
        }}
      />
    );
  }

  return (
    <PerspectiveProvider>
      <Shell />
    </PerspectiveProvider>
  );
}
