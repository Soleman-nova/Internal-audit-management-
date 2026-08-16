import { useEffect, useState } from 'react';
import { usersApi } from '../api/usersApi';

/**
 * Loads the EEU organisational tree once and shares it across every picker.
 *
 * The corporate structure nests three deep — chief office → region → customer
 * service center — and is 600+ units in total, so it cannot be paginated
 * through per keystroke. `/auth/departments/tree/` returns the whole thing
 * compactly in one request; this hook caches the in-flight promise at module
 * level so the five forms that mount a picker share a single fetch instead of
 * each firing their own, without needing another context provider in main.jsx.
 */

// Module-level cache: the org tree changes only when an admin edits a unit, so
// one fetch per page load is enough. Call clearOrgUnitsCache() after a write.
let cachedPromise = null;

export function clearOrgUnitsCache() {
  cachedPromise = null;
}

function fetchOrgUnits() {
  if (!cachedPromise) {
    cachedPromise = usersApi.getDepartmentTree().then((units) => {
      if (!Array.isArray(units)) return [];
      return units;
    }).catch((err) => {
      // Don't cache a failure — the next mount should get a fresh attempt.
      cachedPromise = null;
      throw err;
    });
  }
  return cachedPromise;
}

/** Group units by parent id once, so each cascade step is an O(1) lookup. */
function indexUnits(units) {
  const byId = new Map();
  const byParent = new Map();
  units.forEach((unit) => {
    byId.set(String(unit.id), unit);
    const parentKey = unit.parent == null ? 'root' : String(unit.parent);
    if (!byParent.has(parentKey)) byParent.set(parentKey, []);
    byParent.get(parentKey).push(unit);
  });
  return { byId, byParent };
}

export function useOrgUnits() {
  const [state, setState] = useState({
    units: [],
    byId: new Map(),
    byParent: new Map(),
    loading: true,
    error: null,
  });

  useEffect(() => {
    let active = true;
    fetchOrgUnits()
      .then((units) => {
        if (!active) return;
        setState({ units, ...indexUnits(units), loading: false, error: null });
      })
      .catch((err) => {
        if (!active) return;
        // Name the cause in the console: the picker can only show a one-line
        // message, and a 404 here means the backend predates /departments/tree/.
        console.error('Failed to load the org unit tree:', err);
        setState({
          units: [],
          byId: new Map(),
          byParent: new Map(),
          loading: false,
          error: err?.message || 'Could not load the organisational structure.',
        });
      });
    return () => {
      active = false;
    };
  }, []);

  const { byId, byParent } = state;

  /** Direct children of a unit, optionally narrowed to one unit_type. */
  const childrenOf = (parentId, unitType) => {
    if (parentId === null || parentId === undefined || parentId === '') return [];
    const children = byParent.get(String(parentId)) || [];
    return unitType ? children.filter((u) => u.unit_type === unitType) : children;
  };

  /**
   * The chain from the root down to `unitId`, e.g.
   * [Region Coordination, Adama Region, Adama CSC No.1].
   * Returns [] when the id is unknown — a retired unit, say, which the tree
   * endpoint excludes.
   */
  const ancestorsOf = (unitId) => {
    const chain = [];
    const seen = new Set();
    let current = byId.get(String(unitId));
    while (current && !seen.has(String(current.id))) {
      seen.add(String(current.id));
      chain.unshift(current);
      current = current.parent == null ? null : byId.get(String(current.parent));
    }
    return chain;
  };

  return {
    units: state.units,
    byId,
    childrenOf,
    ancestorsOf,
    loading: state.loading,
    error: state.error,
  };
}

export default useOrgUnits;
