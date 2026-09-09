import { useCallback, useEffect, useRef, useState } from "react";
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

type Screen = "people" | "relationships" | "family" | "search" | "hermes" | "backups";

type ReturnContext = {
  screen: Screen;
  label: string;
};

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
              aria-current={screen === item.id ? "page" : undefined}
              onClick={() => handlePrimaryNavigate(item.id)}
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
        {rootStatus.state === "READ_ONLY" && (
          <div role="status" className="info-note" style={{ margin: "12px 18px 0" }}>
            <strong>Read-only Data Root.</strong> Viewing and searching are available, but changes cannot be saved until this folder is writable or another Data Root is selected.
          </div>
        )}
        {rootStatus.state === "REPAIRABLE" && (
          <div role="status" className="info-note" style={{ margin: "12px 18px 0" }}>
            <strong>Data Root has repairable alignment issues.</strong> Reads remain available; review Data Root health before editing.
          </div>
        )}
        {rootStatus.state === "MAINTENANCE" && (
          <div role="status" className="info-note" style={{ margin: "12px 18px 0" }}>
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

export function App() {
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
    return <main style={{ minHeight: "100vh", display: "grid", placeItems: "center" }} role="status">Checking local data service and Data Root…</main>;
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
