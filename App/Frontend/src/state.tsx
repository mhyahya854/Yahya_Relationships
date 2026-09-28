import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { api } from "./api";
import type { Person } from "./types";

interface PerspectiveContextValue {
  perspectiveId: string | null;
  defaultId: string | null;
  perspectivePerson: Person | null;
  loading: boolean;
  setPerspective: (personId: string) => Promise<void>;
  returnToDefault: () => Promise<void>;
  refresh: () => Promise<void>;
}

const PerspectiveContext = createContext<PerspectiveContextValue | null>(null);

export function PerspectiveProvider({ children }: { children: ReactNode }) {
  const [perspectiveId, setPerspectiveId] = useState<string | null>(null);
  const [defaultId, setDefaultId] = useState<string | null>(null);
  const [perspectivePerson, setPerspectivePerson] = useState<Person | null>(null);
  const [loading, setLoading] = useState(true);

  const loadPerson = useCallback(async (personId: string) => {
    const result = await api.people.get(personId);
    setPerspectivePerson(result.person);
  }, []);

  const refresh = useCallback(async () => {
    const state = await api.state.get();
    setPerspectiveId(state.perspective_person_id);
    setDefaultId(state.default_perspective_person_id);
    await loadPerson(state.perspective_person_id);
  }, [loadPerson]);

  useEffect(() => {
    let cancelled = false;
    let attempts = 0;
    async function boot() {
      while (!cancelled) {
        try {
          await refresh();
          return;
        } catch {
          attempts += 1;
          if (attempts >= 12) return;
          await new Promise((resolve) => setTimeout(resolve, 1500));
        } finally {
          if (!cancelled) setLoading(false);
        }
      }
    }
    void boot();
    return () => {
      cancelled = true;
    };
  }, [refresh]);

  const setPerspective = useCallback(
    async (personId: string) => {
      const state = await api.state.set(personId);
      setPerspectiveId(state.perspective_person_id);
      setDefaultId(state.default_perspective_person_id);
      await loadPerson(state.perspective_person_id);
    },
    [loadPerson],
  );

  const returnToDefault = useCallback(async () => {
    const state = await api.state.reset();
    setPerspectiveId(state.perspective_person_id);
    setDefaultId(state.default_perspective_person_id);
    await loadPerson(state.perspective_person_id);
  }, [loadPerson]);

  const value = useMemo(
    () => ({
      perspectiveId,
      defaultId,
      perspectivePerson,
      loading,
      setPerspective,
      returnToDefault,
      refresh,
    }),
    [
      perspectiveId,
      defaultId,
      perspectivePerson,
      loading,
      setPerspective,
      returnToDefault,
      refresh,
    ],
  );

  return (
    <PerspectiveContext.Provider value={value}>
      {children}
    </PerspectiveContext.Provider>
  );
}

export function usePerspective(): PerspectiveContextValue {
  const context = useContext(PerspectiveContext);
  if (!context) {
    throw new Error("usePerspective must be used inside PerspectiveProvider");
  }
  return context;
}
