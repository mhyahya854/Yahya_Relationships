import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { api } from "./api";
import { Avatar, Button } from "./components/ui";
import { PerspectiveProvider, usePerspective } from "./state";
import type { Person } from "./types";
import { BackupsView } from "./views/BackupsView";
import { FamilyView } from "./views/FamilyView";
import { HermesView } from "./views/HermesView";
import { PeopleView } from "./views/PeopleView";
import { RelationshipsView } from "./views/RelationshipsView";
import { SearchView } from "./views/SearchView";
import { RootUnavailableView } from "./features/dataRoot/components/RootUnavailableView";
import type { DataRootState, DataRootStatus } from "./features/dataRoot/types";
import { StartupFailureView } from "./features/startupFailure/StartupFailureView";
import { ThemeProvider, ThemeToggle } from "./theme";

type Screen = "people" | "relationships" | "family" | "search" | "hermes" | "backups";

type ReturnContext = {
  screen: Screen;
  label: string;
};

const NAV: Array<{ id: Screen; label: string }> = [
  { id: "people", label: "People" },
  { id: "relationships", label: "Connections" },
  { id: "family", label: "Family Tree" },
  { id: "search", label: "Search" },
  { id: "hermes", label: "Hermes" },
  { id: "backups", label: "Backups" },
];

function NavIcon({ screen }: { screen: Screen }) {
  const paths: Record<Screen, ReactNode> = {
    people: <><circle cx="8" cy="7" r="3" /><path d="M2.8 17c.5-3 2.2-4.5 5.2-4.5s4.7 1.5 5.2 4.5" /><circle cx="16" cy="8" r="2.3" /><path d="M14 13c2.7-.5 4.4.8 5 3" /></>,
    relationships: <><circle cx="5" cy="12" r="2.5" /><circle cx="17" cy="6" r="2.5" /><circle cx="17" cy="18" r="2.5" /><path d="M7.3 10.8 14.6 7M7.3 13.2l7.3 3.8" /></>,
    family: <><circle cx="12" cy="5" r="2.5" /><circle cx="5" cy="18" r="2.5" /><circle cx="19" cy="18" r="2.5" /><path d="M12 7.5v4M5 15.5v-4h14v4" /></>,
    search: <><circle cx="10.5" cy="10.5" r="6" /><path d="m15 15 4 4" /></>,
    hermes: <><path d="M12 3.2 20 8l-8 4.8L4 8 12 3.2Z" /><path d="m4 12 8 4.8 8-4.8M4 16l8 4.8 8-4.8" /></>,
    backups: <><path d="M4 7h16v13H4zM6 4h12v3" /><path d="M8 11h8M8 15h5" /></>,
  };
  return <svg className="nav-icon" viewBox="0 0 24 24" aria-hidden="true">{paths[screen]}</svg>;
}

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
      <span className="perspective-label">Perspective of:</span>
      <div className="perspective-current-wrap">
        <button
          type="button"
          className="perspective-current"
          onClick={() => setOpen((value) => !value)}
          aria-haspopup="listbox"
          aria-expanded={open}
        >
          <Avatar person={perspectivePerson} size={24} />
          <strong>{perspectivePerson.name}</strong>
          <span className="chevron">▾</span>
        </button>
        {open && (
          <div className="perspective-dropdown">
            <div className="perspective-dropdown-scroll" role="listbox" aria-label="Choose perspective">
              {people.map((person) => (
                <button
                  type="button"
                  key={person.id}
                  className={person.id === perspectiveId ? "selected" : ""}
                  role="option"
                  aria-selected={person.id === perspectiveId}
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

function Shell({ rootStatus }: { rootStatus: DataRootStatus }) {
  const [screen, setScreen] = useState<Screen>("relationships");
  const [returnContext, setReturnContext] = useState<ReturnContext | null>(null);
  const [searchMounted, setSearchMounted] = useState(false);
  const [peopleTargetId, setPeopleTargetId] = useState<string | null>(null);
  const [peopleGroupId, setPeopleGroupId] = useState<string | null>(null);
  const [relationshipTargetId, setRelationshipTargetId] = useState<string | null>(null);
  const { perspectivePerson, defaultId, setPerspective } = usePerspective();
  const navigationRequest = useRef(0);
  const relationshipHandoff = useRef<Promise<void>>(Promise.resolve());

  // Family Session State (persists across tab navigation during app session)
  const [familyFocusId, setFamilyFocusId] = useState<string | null>(null);
  const [familySelectedId, setFamilySelectedId] = useState<string | null>(null);
  const clearPeopleTarget = useCallback(() => setPeopleTargetId(null), []);
  const clearRelationshipTarget = useCallback(() => setRelationshipTargetId(null), []);

  // Initialize Family focus to defaultId once available (independent of global perspective)
  useEffect(() => {
    if (!familyFocusId && defaultId) {
      setFamilyFocusId(defaultId);
    }
  }, [defaultId, familyFocusId]);

  const screenLabel = (target: Screen) => NAV.find((item) => item.id === target)?.label ?? target;

  const openScreen = (target: Screen) => {
    if (target === "search") setSearchMounted(true);
    setScreen(target);
  };

  const rememberReturn = (destination: Screen, origin = screen) => {
    setReturnContext(origin === destination ? null : { screen: origin, label: screenLabel(origin) });
  };

  const handlePrimaryNavigate = (target: Screen) => {
    navigationRequest.current += 1;
    setReturnContext(null);
    if (target === "people") {
      setPeopleTargetId(null);
      setPeopleGroupId(null);
    }
    openScreen(target);
  };

  const handleReturn = () => {
    if (!returnContext) return;
    navigationRequest.current += 1;
    const target = returnContext.screen;
    setReturnContext(null);
    openScreen(target);
  };

  const handleNavigateToRelationships = (personId: string, fromPerspectiveId?: string) => {
    const origin = screen;
    const request = ++navigationRequest.current;
    const run = async () => {
      if (request !== navigationRequest.current) return;
      try {
        if (fromPerspectiveId && fromPerspectiveId !== perspectivePerson?.id) {
          await setPerspective(fromPerspectiveId);
        }
        if (request !== navigationRequest.current) return;
        if (origin === "people") setPeopleTargetId(personId);
        setRelationshipTargetId(personId);
        rememberReturn("relationships", origin);
        openScreen("relationships");
      } catch (err) {
        console.error("Failed to set perspective for Relationships handoff:", err);
      }
    };
    const queued = relationshipHandoff.current.then(run, run);
    relationshipHandoff.current = queued.then(() => undefined, () => undefined);
    return queued;
  };

  const handleNavigateToProfile = (personId: string) => {
    navigationRequest.current += 1;
    if (screen === "relationships") setRelationshipTargetId(personId);
    setPeopleTargetId(personId);
    setPeopleGroupId(null);
    rememberReturn("people");
    openScreen("people");
  };

  const handleNavigateToGroup = (groupId: string) => {
    navigationRequest.current += 1;
    setPeopleTargetId(null);
    setPeopleGroupId(groupId);
    rememberReturn("people");
    openScreen("people");
  };

  const handleNavigateToFamily = (personId: string) => {
    navigationRequest.current += 1;
    setFamilySelectedId(personId);
    rememberReturn("family");
    openScreen("family");
  };

  const isCanvasScreen = screen === "relationships" || screen === "family";

  return (
    <div className={`shell ${isCanvasScreen ? "canvas-mode" : ""}`}>
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 32 32">
              <circle cx="9" cy="10" r="4" />
              <circle cx="23" cy="10" r="4" />
              <circle cx="16" cy="23" r="4" />
              <path d="M12.5 12.4 14.8 19M19.5 12.4 17.2 19M13 10h6" />
            </svg>
          </div>
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
              aria-current={screen === item.id ? "page" : undefined}
              onClick={() => handlePrimaryNavigate(item.id)}
            >
              <NavIcon screen={item.id} />
              <span>
                {item.label}
                {item.id === "relationships" && <span className="sr-only"> Relationships</span>}
              </span>
            </button>
          ))}
        </nav>
        <div className="sidebar-foot">
          <div className="muted small">
            Owner: {perspectivePerson?.name ?? "…"}
          </div>
          <div className="muted tiny">Private · Local-first</div>
        </div>
      </aside>
      <main className="main">
        {rootStatus.state === "READ_ONLY" && (
          <div role="status" className="status-banner info-note">
            <strong>Read-only Data Root.</strong> Viewing and searching are available, but changes cannot be saved until this folder is writable or another Data Root is selected.
          </div>
        )}
        {rootStatus.state === "REPAIRABLE" && (
          <div role="status" className="status-banner info-note">
            <strong>Data Root has repairable alignment issues.</strong> Reads remain available; review Data Root health before editing.
          </div>
        )}
        {rootStatus.state === "MAINTENANCE" && (
          <div role="status" className="status-banner info-note">
            <strong>Data maintenance is in progress.</strong> {rootStatus.maintenance_operation ?? "Root-changing actions are temporarily disabled."}
          </div>
        )}
        <header className="topbar">
          <PerspectiveSelector />
        </header>
        <div className="content">
          {returnContext && screen !== "people" && (
            <div className="navigation-return" role="status">
              <Button kind="ghost" onClick={handleReturn}>
                ← Return to {returnContext.label}
                {returnContext.label === "Connections" && <span className="sr-only">Return to Relationships</span>}
              </Button>
              <span className="muted small">Your {returnContext.label} context is unchanged.</span>
            </div>
          )}
          {screen === "people" && (
            <PeopleView
              initialPersonId={peopleTargetId}
              initialGroupId={peopleGroupId}
              onNavigateToRelationships={handleNavigateToRelationships}
              onNavigateToFamily={handleNavigateToFamily}
              onTargetUnavailable={clearPeopleTarget}
              returnLabel={returnContext?.label}
              onReturn={returnContext ? handleReturn : undefined}
            />
          )}
          {screen === "relationships" && (
            <RelationshipsView
              initialTargetId={relationshipTargetId}
              onTargetChange={setRelationshipTargetId}
              onTargetUnavailable={clearRelationshipTarget}
              onNavigateToProfile={handleNavigateToProfile}
              onNavigateToFamily={handleNavigateToFamily}
            />
          )}
          {screen === "family" && defaultId && (
            <FamilyView
              focusPersonId={familyFocusId ?? defaultId}
              onFocusPersonChange={(newId) => setFamilyFocusId(newId)}
              selectedPersonId={familySelectedId}
              onSelectedPersonChange={(personId) => setFamilySelectedId(personId)}
              onNavigateToProfile={handleNavigateToProfile}
              onNavigateToRelationships={handleNavigateToRelationships}
            />
          )}
          {searchMounted && (
            <div hidden={screen !== "search"}>
              <SearchView
                onNavigateToProfile={handleNavigateToProfile}
                onNavigateToRelationships={handleNavigateToRelationships}
                onNavigateToFamily={handleNavigateToFamily}
                onNavigateToGroup={handleNavigateToGroup}
              />
            </div>
          )}
          {screen === "hermes" && <HermesView />}
          {screen === "backups" && <BackupsView />}
        </div>
      </main>
    </div>
  );
}

function AppContent() {
  const [rootUnavailable, setRootUnavailable] = useState<DataRootState | null>(null);
  const [rootStatus, setRootStatus] = useState<DataRootStatus | null>(null);
  const [lastLocation, setLastLocation] = useState<string | null>(null);
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
      setRootStatus(status);
      setBackendFailure(null);
      if (["UNCONFIGURED", "MISSING", "INVALID"].includes(status.state)) {
        setRootUnavailable(status.state);
        setLastLocation(status.last_configured_root);
      } else {
        setRootUnavailable(null);
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

  if (checking || !rootStatus) {
    return <main className="startup-check" role="status">Checking local data service and Data Root…</main>;
  }

  if (!checking && rootUnavailable) {
    return (
      <RootUnavailableView
        state={rootUnavailable}
        lastLocation={lastLocation}
        issues={rootStatus.health.issues}
        onRecovered={() => {
          setRootUnavailable(null);
          void checkRoot();
        }}
      />
    );
  }

  return (
    <PerspectiveProvider key={rootStatus.root_id ?? rootStatus.active_root ?? rootStatus.state}>
      <Shell rootStatus={rootStatus} />
    </PerspectiveProvider>
  );
}

export function App() {
  return (
    <ThemeProvider>
      <AppContent />
      <ThemeToggle />
    </ThemeProvider>
  );
}
