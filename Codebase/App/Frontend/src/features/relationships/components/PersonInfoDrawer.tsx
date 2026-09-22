import { useEffect, useMemo, useState } from "react";
import { api } from "../../../api";
import { Avatar, Button, ErrorNote, Icon } from "../../../components/ui";
import type { Person, PersonProfileData } from "../../../types";
import { relationshipsApi } from "../api";
import type { RelationshipPath } from "../types";

type InfoTab =
  | "overview"
  | "relationships"
  | "paths"
  | "memories"
  | "events"
  | "media"
  | "conversations"
  | "documents"
  | "places"
  | "groups"
  | "journal";

export interface ConnectionsSyntheticDrawerDemo {
  memories?: string[];
  events?: string[];
  media?: string[];
  conversations?: string[];
  documents?: string[];
  places?: string[];
}

declare global {
  interface Window {
    __connectionsSyntheticDrawerDemo?: Record<string, ConnectionsSyntheticDrawerDemo>;
  }
}

const tabs: Array<{ id: InfoTab; label: string }> = [
  { id: "overview", label: "Overview" },
  { id: "relationships", label: "Relationships" },
  { id: "paths", label: "Relationship Paths" },
  { id: "memories", label: "Memories" },
  { id: "events", label: "Events" },
  { id: "media", label: "Photos & Videos" },
  { id: "conversations", label: "Conversations" },
  { id: "documents", label: "Documents" },
  { id: "places", label: "Places / Travel" },
  { id: "groups", label: "Groups" },
  { id: "journal", label: "Journal / Notes" },
];

function List({ title, values }: { title: string; values: Array<{ id: string; name: string; detail?: string | null }> }) {
  if (!values.length) return null;
  return (
    <section className="drawer-list-section">
      <h4>{title}</h4>
      <ul>
        {values.map((value) => (
          <li key={value.id}><strong>{value.name}</strong>{value.detail && <span>{value.detail}</span>}</li>
        ))}
      </ul>
    </section>
  );
}

function FutureBoundary({ tab, values }: { tab: string; values?: string[] }) {
  if (values?.length) {
    return (
      <section className="drawer-synthetic-boundary">
        <span>Synthetic fixture preview — not production data</span>
        <ul>{values.map((value) => <li key={value}>{value}</li>)}</ul>
      </section>
    );
  }
  return (
    <section className="drawer-empty-boundary">
      <strong>{tab} · Not implemented yet</strong>
      <p>This approved information boundary is ready for a future canonical source. No production data is connected yet.</p>
    </section>
  );
}

export function PersonInfoDrawer({
  person,
  perspectiveId,
  perspectiveName,
  onClose,
  onOpenJournal,
  onNavigateToProfile,
  onNavigateToFamily,
}: {
  person: Person;
  perspectiveId: string | null;
  perspectiveName: string;
  onClose: () => void;
  onOpenJournal: (person: Person) => void;
  onNavigateToProfile?: (personId: string) => void;
  onNavigateToFamily?: (personId: string) => void;
}) {
  const [tab, setTab] = useState<InfoTab>("overview");
  const [profile, setProfile] = useState<PersonProfileData | null>(null);
  const [paths, setPaths] = useState<RelationshipPath[]>([]);
  const [loading, setLoading] = useState(true);
  const [pathsLoading, setPathsLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const demo = window.__connectionsSyntheticDrawerDemo?.[person.id];

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    api.people.profile(person.id, perspectiveId ?? undefined)
      .then((response) => {
        if (!cancelled) setProfile(response.profile);
      })
      .catch((nextError) => {
        if (!cancelled) setError(nextError);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [person.id, perspectiveId]);

  useEffect(() => {
    if (tab !== "paths" || !perspectiveId || perspectiveId === person.id || paths.length) return;
    let cancelled = false;
    setPathsLoading(true);
    relationshipsApi.paths(perspectiveId, person.id, 30, 50)
      .then((response) => {
        if (!cancelled) setPaths(response.paths);
      })
      .catch((nextError) => {
        if (!cancelled) setError(nextError);
      })
      .finally(() => {
        if (!cancelled) setPathsLoading(false);
      });
    return () => { cancelled = true; };
  }, [paths.length, person.id, perspectiveId, tab]);

  const overview = useMemo(() => [
    person.birth_year ? `Born ${person.birth_year}` : "Birth year unknown",
    person.gender ? `Gender: ${person.gender}` : "Gender not recorded",
    person.branch ? `Branch: ${person.branch}` : null,
  ].filter(Boolean), [person.birth_year, person.branch, person.gender]);

  const tabContent = () => {
    if (loading && !profile) return <p className="muted small">Loading available person data…</p>;
    switch (tab) {
      case "overview":
        return (
          <div className="drawer-overview">
            <ul>{overview.map((item) => <li key={item}>{item}</li>)}</ul>
            {person.aliases.length > 0 && <p><strong>Aliases</strong><br />{person.aliases.join(" · ")}</p>}
            {person.note_en && <p><strong>Notes</strong><br />{person.note_en}</p>}
            {person.note_ur && <p dir="rtl" lang="ur">{person.note_ur}</p>}
          </div>
        );
      case "relationships":
        return (
          <div>
            <List title="Parents" values={(profile?.family.parents ?? []).map((item) => ({ id: item.id, name: item.name, detail: `${item.role}${item.kind ? ` · ${item.kind}` : ""}` }))} />
            <List title="Spouses / partners" values={(profile?.family.spouses ?? []).map((item) => ({ id: item.id, name: item.name, detail: item.status }))} />
            <List title="Children" values={(profile?.family.children ?? []).map((item) => ({ id: item.id, name: item.name, detail: `${item.role}${item.kind ? ` · ${item.kind}` : ""}` }))} />
            <List title="Siblings" values={(profile?.family.siblings ?? []).map((item) => ({ id: item.id, name: item.name, detail: item.type }))} />
            <List title="Recorded general relationships" values={(profile?.general ?? []).map((item) => ({ id: String(item.id), name: item.other_person.name, detail: item.label }))} />
            {!profile?.family.parents.length && !profile?.family.spouses.length && !profile?.family.children.length && !profile?.family.siblings.length && !profile?.general.length && <p className="empty-inline">No relationship facts are currently available.</p>}
          </div>
        );
      case "paths":
        if (!perspectiveId || perspectiveId === person.id) return <p className="empty-inline">Choose a different FROM person to inspect paths.</p>;
        return (
          <div className="drawer-path-list">
            <p>Canonical paths from <strong>{perspectiveName}</strong> to <strong>{person.name}</strong>.</p>
            {pathsLoading && <p className="muted small">Loading canonical paths…</p>}
            {paths.map((path, index) => <div key={path.id}><strong>{index + 1}. {path.label_en}</strong><span>{path.distance} steps{path.side ? ` · ${path.side}` : ""}</span></div>)}
            {!pathsLoading && !paths.length && <p className="empty-inline">No supported route was returned.</p>}
          </div>
        );
      case "groups":
        return person.groups.length ? (
          <ul className="drawer-group-list">{person.groups.map((group) => <li key={group.id}>{group.name}{group.is_primary && <span>Primary</span>}</li>)}</ul>
        ) : <p className="empty-inline">No groups are recorded.</p>;
      case "journal":
        return (
          <div className="drawer-journal">
            {profile?.journal.exists ? <p>{profile.journal.content.slice(0, 900)}{profile.journal.content.length > 900 ? "…" : ""}</p> : <p className="empty-inline">No journal has been created for this person.</p>}
            <Button kind="ghost" onClick={() => onOpenJournal(person)}><Icon name="journal" /> Open journal</Button>
          </div>
        );
      case "memories": return <FutureBoundary tab="Memories" values={demo?.memories} />;
      case "events": return <FutureBoundary tab="Events" values={demo?.events} />;
      case "media": return <FutureBoundary tab="Photos & Videos" values={demo?.media} />;
      case "conversations": return <FutureBoundary tab="Conversations" values={demo?.conversations} />;
      case "documents": return <FutureBoundary tab="Documents" values={demo?.documents} />;
      case "places": return <FutureBoundary tab="Places / Travel" values={demo?.places} />;
      default: return null;
    }
  };

  return (
    <aside className="relationships-panel person-info-drawer glass-panel" role="dialog" aria-label={`Information for ${person.name}`}>
      <header className="person-info-drawer-head">
        <Avatar person={person} size={42} />
        <div><strong>{person.name}</strong><span>Person information</span></div>
        <Button kind="ghost" className="icon-button" onClick={onClose} ariaLabel="Close person information" title="Close person information"><Icon name="close" /></Button>
      </header>
      <ErrorNote error={error} />
      <div className="person-info-tabs" role="tablist" aria-label="Person information sections">
        {tabs.map((item) => <button key={item.id} type="button" role="tab" aria-selected={tab === item.id} onClick={() => setTab(item.id)}>{item.label}</button>)}
      </div>
      <div className="person-info-drawer-body" role="tabpanel">{tabContent()}</div>
      {(onNavigateToProfile || onNavigateToFamily) && (
        <footer className="person-info-drawer-actions">
          {onNavigateToProfile && (
            <Button kind="ghost" onClick={() => onNavigateToProfile(person.id)}>
              <Icon name="profile" /> View Profile
            </Button>
          )}
          {onNavigateToFamily && (
            <Button kind="ghost" onClick={() => onNavigateToFamily(person.id)}>
              <Icon name="family" /> View Family
            </Button>
          )}
        </footer>
      )}
    </aside>
  );
}
