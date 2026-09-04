import { useEffect, useState } from "react";
import { api } from "../api";
import { JournalModal } from "../components/PersonDetail";
import { Avatar, Button, ErrorNote, Modal } from "../components/ui";
import { usePerspective } from "../state";
import type { Person, SearchResult } from "../types";

export function SearchView() {
  const { perspectiveId, setPerspective } = usePerspective();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [people, setPeople] = useState<Person[]>([]);
  const [error, setError] = useState<unknown>(null);
  const [searched, setSearched] = useState(false);
  const [openPerson, setOpenPerson] = useState<Person | null>(null);
  const [journalFor, setJournalFor] = useState<Person | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.people
      .list()
      .then((result) => setPeople(result.people))
      .catch(setError);
  }, []);

  async function runSearch(term: string) {
    if (!term.trim()) return;
    setQuery(term);
    setLoading(true);
    try {
      const result = await api.search(term);
      setResults(result.results);
      setSearched(true);
      setError(null);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }

  const categoryLabel: Record<SearchResult["category"], string> = {
    PERSON: "Person",
    RELATIONSHIP: "Relationship",
    GROUP: "Group",
    JOURNAL: "Journal",
  };

  return (
    <div className="view">
      <div className="view-head">
        <div>
          <h1>Search</h1>
          <p className="muted">
            Deterministic search over people, aliases, groups, relationships
            and journal prose — no AI involved.
          </p>
        </div>
      </div>
      <ErrorNote error={error} />
      <form
        className="search-bar"
        onSubmit={(event) => {
          event.preventDefault();
          void runSearch(query);
        }}
      >
        <input
          className="text-input grow"
          placeholder="People, aliases, ماموں, maternal uncle, colleague, journal text…"
          value={query}
          autoFocus
          onChange={(event) => setQuery(event.target.value)}
        />
        <Button kind="primary" type="submit" disabled={loading}>
          Search
        </Button>
      </form>
      <div className="search-suggestions">
        {["Dad", "Ahmed", "ماموں", "maternal uncle", "close friend", "cousin", "journal"].map(
          (suggestion) => (
            <button
              type="button"
              key={suggestion}
              className="chip chip-button"
              onClick={() => void runSearch(suggestion)}
            >
              {suggestion}
            </button>
          ),
        )}
      </div>
      {loading && <div className="state-box">Searching…</div>}
      {!loading && searched && results.length === 0 && (
        <div className="empty-state">
          No results for “{query}”. Journal search reads the Markdown files
          directly.
        </div>
      )}
      <div className="search-results-list">
        {!loading &&
          results.map((result, index) => {
            const person = people.find((entry) => entry.id === result.person_id);
            return (
              <div className="search-result" key={`${result.category}-${index}`}>
                <span className={`tag tag-${result.category.toLowerCase()}`}>
                  {categoryLabel[result.category]}
                </span>
                <div className="search-result-main">
                  <strong>{result.title}</strong>
                  <div className="muted small">{result.match}</div>
                </div>
                {result.category === "PERSON" && person && (
                  <div className="row-actions">
                    <Button
                      kind="primary"
                      onClick={() => void setPerspective(person.id)}
                    >
                      View from this person
                    </Button>
                    <Button onClick={() => setOpenPerson(person)}>Details</Button>
                  </div>
                )}
                {result.category === "JOURNAL" && person && (
                  <div className="row-actions">
                    <Button onClick={() => setJournalFor(person)}>Open journal</Button>
                  </div>
                )}
              </div>
            );
          })}
      </div>
      {openPerson && (
        <Modal title={openPerson.name} onClose={() => setOpenPerson(null)}>
          <div className="side-profile-row">
            <Avatar person={openPerson} size={48} />
            <div>
              <strong>{openPerson.name}</strong>
              <div className="muted small">
                {openPerson.aliases.length
                  ? `Alias: ${openPerson.aliases.join(", ")}`
                  : "No aliases"}
              </div>
            </div>
          </div>
          <div className="row-actions modal-actions">
            <Button kind="primary" onClick={() => void setPerspective(openPerson.id)}>
              View from this person
            </Button>
            <Button onClick={() => setJournalFor(openPerson)}>Journal</Button>
          </div>
          {perspectiveId && (
            <p className="muted small">
              Open the Relationships screen to see how {openPerson.name} is
              connected from the current perspective.
            </p>
          )}
        </Modal>
      )}
      {journalFor && (
        <JournalModal person={journalFor} onClose={() => setJournalFor(null)} />
      )}
    </div>
  );
}
