import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { JournalModal } from "../components/PersonDetail";
import { Button, ErrorNote } from "../components/ui";
import { usePerspective } from "../state";
import type { Person, SearchResult } from "../types";

type SearchFilter = "ALL" | SearchResult["category"];

const FILTERS: Array<{ id: SearchFilter; label: string }> = [
  { id: "ALL", label: "All" },
  { id: "PERSON", label: "People" },
  { id: "RELATIONSHIP", label: "Relationships" },
  { id: "GROUP", label: "Groups" },
  { id: "JOURNAL", label: "Journals" },
];

export function SearchView({
  onNavigateToProfile,
  onNavigateToRelationships,
  onNavigateToGroup,
}: {
  onNavigateToProfile: (personId: string) => void;
  onNavigateToRelationships: (personId: string, fromPerspectiveId?: string) => void;
  onNavigateToGroup: (groupId: string) => void;
}) {
  const { perspectiveId, perspectivePerson } = usePerspective();
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [people, setPeople] = useState<Person[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [searched, setSearched] = useState(false);
  const [journalFor, setJournalFor] = useState<Person | null>(null);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState<SearchFilter>("ALL");
  const requestNumber = useRef(0);
  const abortController = useRef<AbortController | null>(null);
  const searchedQuery = useRef<string | null>(null);
  const previousPerspective = useRef(perspectiveId);

  useEffect(() => {
    api.people.list().then((result) => setPeople(result.people)).catch(setError);
  }, []);

  const clearSearch = useCallback(() => {
    requestNumber.current += 1;
    abortController.current?.abort();
    abortController.current = null;
    searchedQuery.current = null;
    setQuery("");
    setSubmittedQuery("");
    setResults([]);
    setError(null);
    setSearched(false);
    setLoading(false);
    setFilter("ALL");
  }, []);

  const runSearch = useCallback(async (term: string) => {
    if (!term.trim()) {
      clearSearch();
      return;
    }
    const currentRequest = requestNumber.current + 1;
    requestNumber.current = currentRequest;
    abortController.current?.abort();
    const controller = new AbortController();
    abortController.current = controller;
    searchedQuery.current = term;
    setSubmittedQuery(term);
    setLoading(true);
    setError(null);
    try {
      const result = await api.search(term, perspectiveId || undefined, 100, controller.signal);
      if (requestNumber.current !== currentRequest) return;
      setResults(result.results);
      setSearched(true);
    } catch (err) {
      if (controller.signal.aborted || requestNumber.current !== currentRequest) return;
      setResults([]);
      setSearched(true);
      setError(err);
    } finally {
      if (requestNumber.current === currentRequest) setLoading(false);
    }
  }, [clearSearch, perspectiveId]);

  useEffect(() => {
    if (previousPerspective.current !== perspectiveId && searchedQuery.current) {
      void runSearch(searchedQuery.current);
    }
    previousPerspective.current = perspectiveId;
  }, [perspectiveId, runSearch]);

  useEffect(() => () => abortController.current?.abort(), []);

  const counts = useMemo(() => {
    const next: Record<SearchResult["category"], number> = {
      PERSON: 0,
      RELATIONSHIP: 0,
      GROUP: 0,
      JOURNAL: 0,
    };
    for (const result of results) next[result.category] += 1;
    return next;
  }, [results]);

  const visibleResults = filter === "ALL"
    ? results
    : results.filter((result) => result.category === filter);

  const personFor = (personId: string | null | undefined) =>
    people.find((person) => person.id === personId);

  return (
    <div className="view search-view">
      <div className="view-head">
        <div>
          <h1>Search</h1>
          <p className="muted">
            Deterministic local search from <strong>{perspectivePerson?.name ?? "the current perspective"}</strong>
            {" "}across people, aliases, relationships, groups, and Journal Markdown. No AI or network search.
          </p>
        </div>
      </div>

      <form
        className="search-bar"
        role="search"
        onSubmit={(event) => {
          event.preventDefault();
          void runSearch(query);
        }}
      >
        <input
          className="text-input grow"
          aria-label="Global search"
          placeholder="Name, alias, ماموں, relationship, group, or Journal text…"
          value={query}
          autoFocus
          onChange={(event) => {
            const value = event.target.value;
            setQuery(value);
            if (!value.trim()) clearSearch();
          }}
        />
        {query && <Button onClick={clearSearch}>Clear</Button>}
        <Button kind="primary" type="submit" disabled={loading || !query.trim()}>
          Search
        </Button>
      </form>

      <div className="search-suggestions" aria-label="Search suggestions">
        {["Yahya", "ماموں", "maternal uncle", "close friend", "cousin", "journal"].map(
          (suggestion) => (
            <button
              type="button"
              key={suggestion}
              className="chip chip-button"
              onClick={() => {
                setQuery(suggestion);
                void runSearch(suggestion);
              }}
            >
              {suggestion}
            </button>
          ),
        )}
      </div>

      {searched && (
        <div className="search-filters" aria-label="Search result categories">
          {FILTERS.map((item) => {
            const count = item.id === "ALL" ? results.length : counts[item.id];
            return (
              <button
                type="button"
                key={item.id}
                className={`tab ${filter === item.id ? "active" : ""}`}
                aria-pressed={filter === item.id}
                onClick={() => setFilter(item.id)}
              >
                {item.label} ({count})
              </button>
            );
          })}
        </div>
      )}

      <ErrorNote error={error} />
      {!searched && !loading && !error && (
        <div className="state-box search-initial">Enter a query to search canonical local data.</div>
      )}
      {loading && <div className="state-box" role="status">Searching…</div>}
      {!loading && searched && !error && visibleResults.length === 0 && (
        <div className="empty-state">
          No {filter === "ALL" ? "" : `${FILTERS.find((item) => item.id === filter)?.label.toLowerCase()} `}
          results for “{submittedQuery}”.
        </div>
      )}

      <div className="search-results-list" aria-live="polite" aria-busy={loading}>
        {!loading && !error && visibleResults.map((result) => {
          const person = personFor(result.person_id ?? result.target_person_id);
          const personA = personFor(result.person_a_id);
          const personB = personFor(result.person_b_id);
          const matchedForward = result.matched_fields?.includes("label_a_to_b") ?? false;
          const matchedReverse = result.matched_fields?.includes("label_b_to_a") ?? false;
          const preferReverse = result.directionality === "directional" &&
            ((matchedReverse && !matchedForward) ||
              (!matchedForward && !matchedReverse && result.direction_from === result.person_b_id));
          return (
            <article className="search-result" key={result.result_id} data-result-id={result.result_id}>
              <span className={`tag tag-${result.category.toLowerCase()}`}>
                {result.relationship_kind === "family"
                  ? "Family relationship"
                  : result.relationship_kind === "general"
                    ? "General relationship"
                    : FILTERS.find((item) => item.id === result.category)?.label.replace(/s$/, "")}
              </span>
              <div className="search-result-main">
                <strong>{result.title}</strong>
                <span className="muted tiny">{result.subtitle}</span>
                {result.relationship_kind === "general" ? (
                  <div className="search-relationship-orientation">
                    {result.directionality === "symmetric" ? (
                      <span>{result.person_a_name} ↔ {result.person_b_name}: <strong>{result.label_a_to_b}</strong></span>
                    ) : (
                      <>
                        <span>{result.person_a_name} → {result.person_b_name}: <strong>{result.label_a_to_b}</strong></span>
                        <span>{result.person_b_name} → {result.person_a_name}: <strong>{result.label_b_to_a}</strong></span>
                      </>
                    )}
                    {result.notes && <span className="muted">Notes: {result.notes}</span>}
                  </div>
                ) : (
                  <div className="search-match" dir="auto">{result.match}</div>
                )}
              </div>

              <div className="row-actions search-result-actions">
                {result.category === "PERSON" && person && (
                  <>
                    <Button kind="primary" onClick={() => onNavigateToProfile(person.id)}>Details</Button>
                    <Button onClick={() => onNavigateToRelationships(person.id)}>View in Relationships</Button>
                    <Button onClick={() => setJournalFor(person)}>Journal</Button>
                  </>
                )}
                {result.relationship_kind === "family" && person && result.perspective_id && (
                  <>
                    <Button kind="primary" onClick={() => onNavigateToRelationships(person.id, result.perspective_id)}>
                      View in Relationships
                    </Button>
                    <Button onClick={() => onNavigateToProfile(person.id)}>Details</Button>
                  </>
                )}
                {result.relationship_kind === "general" && personA && personB && (
                  <>
                    <Button
                      kind="primary"
                      onClick={() => onNavigateToRelationships(
                        preferReverse ? personA.id : personB.id,
                        preferReverse ? personB.id : personA.id,
                      )}
                    >
                      View {preferReverse ? personB.name : personA.name}{" "}
                      {result.directionality === "symmetric" ? "↔" : "→"}{" "}
                      {preferReverse ? personA.name : personB.name}
                    </Button>
                    {result.directionality === "directional" && (
                      <Button onClick={() => onNavigateToRelationships(
                        preferReverse ? personB.id : personA.id,
                        preferReverse ? personA.id : personB.id,
                      )}>
                        View {preferReverse ? personA.name : personB.name} → {preferReverse ? personB.name : personA.name}
                      </Button>
                    )}
                  </>
                )}
                {result.category === "GROUP" && result.group_id && (
                  <Button kind="primary" onClick={() => onNavigateToGroup(result.group_id!)}>View members</Button>
                )}
                {result.category === "JOURNAL" && person && (
                  <>
                    <Button kind="primary" onClick={() => setJournalFor(person)}>Open Journal</Button>
                    <Button onClick={() => onNavigateToProfile(person.id)}>Details</Button>
                  </>
                )}
              </div>
            </article>
          );
        })}
      </div>

      {journalFor && <JournalModal person={journalFor} onClose={() => setJournalFor(null)} />}
    </div>
  );
}
