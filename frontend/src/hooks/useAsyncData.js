import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Run an async loader and keep its result, discarding any response that arrives
 * after a newer run has started.
 *
 * The problem this exists for is a race that is easy to trigger and hard to
 * notice. Every data page in this app hand-rolled the same shape —
 * `useState` + `setLoading` + a `fetchX()` called from an effect — and none of them
 * cancelled or versioned the request. So switching engagements twice in quick
 * succession, or clicking a sortable column while a page is still loading, can let
 * a slow *earlier* response land last and overwrite the newer one. The screen then
 * shows data for a filter the user has already left, with no error to hint at it.
 *
 * Three things make that impossible here:
 *
 *   - each run takes a ticket (`runId`); a response whose ticket is stale is dropped
 *   - a run that resolves after unmount writes nothing
 *   - `loading` is cleared only by the run that is still current, so a superseded
 *     request cannot flick the spinner off while its replacement is in flight
 *
 * Deliberately not modelled on `useOrgUnits`, which caches a module-level promise
 * because the org tree is fetched once and shared. This is the general case: a
 * request per dependency change, no caching, no sharing.
 *
 * @param {() => Promise<any>} loader  The request. Re-read on every render, so it
 *   may close over fresh state without being a dependency.
 * @param {any[]} deps  Re-run when these change — anything the loader reads.
 *   **Keep the length stable across renders**: it is spread into a dependency
 *   array, and React requires a fixed count. A literal is the intended use.
 * @param {object} [options]
 * @param {boolean} [options.enabled=true]  Skip running while false. Assumed to
 *   go false → true (e.g. "wait until a record is selected"), not to toggle off
 *   again; a caller that disables it mid-flight keeps the last `loading` value.
 * @param {(error: any) => void} [options.onError]  Called for the current run's
 *   failure only, for a toast. `error` is also returned for inline rendering.
 * @returns {{data: any, loading: boolean, error: any, reload: () => Promise<any>, setData: Function}}
 *   `setData` is exposed so a page can apply an optimistic edit — a locally created
 *   row, a status change it just made — without re-fetching the whole list.
 */
export function useAsyncData(loader, deps = [], options = {}) {
  const { enabled = true, onError } = options;

  const [data, setData] = useState(null);
  // Seeded from `enabled`, not `true`: a disabled hook must not render a spinner
  // for a request it is never going to make.
  const [loading, setLoading] = useState(Boolean(enabled));
  const [error, setError] = useState(null);

  const runIdRef = useRef(0);
  const aliveRef = useRef(true);

  // Latest loader/callback without making them dependencies: a loader defined
  // inline is a new function every render, and depending on it would re-fetch in a
  // loop. `deps` is how a caller says what should actually trigger a re-run.
  //
  // Kept current in an effect rather than by assigning during render. Writing a ref
  // mid-render is what the lint rule forbids, and the reason is real: a render can
  // be discarded or replayed, and a ref mutated on the way through would carry that
  // into the committed tree. This effect is declared *before* the run effect below,
  // so on mount it has already caught up by the time that one fires.
  const loaderRef = useRef(loader);
  const onErrorRef = useRef(onError);

  useEffect(() => {
    loaderRef.current = loader;
    onErrorRef.current = onError;
  });

  const reload = useCallback(async () => {
    const runId = ++runIdRef.current;

    setLoading(true);
    setError(null);

    try {
      const result = await loaderRef.current();
      if (runId !== runIdRef.current || !aliveRef.current) return result;
      setData(result);
      return result;
    } catch (err) {
      if (runId !== runIdRef.current || !aliveRef.current) return undefined;
      setError(err);
      onErrorRef.current?.(err);
      return undefined;
    } finally {
      // Guarded too: letting a superseded request clear the spinner would hide the
      // fact that the current one is still running.
      if (runId === runIdRef.current && aliveRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    aliveRef.current = true;
    return () => {
      aliveRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (!enabled) return;
    // `reload` flips `loading` synchronously. That is the intended behaviour here —
    // the spinner should appear on the render after the dependency changed, not a
    // tick later — and the rule is silenced once, in this one hook, rather than in
    // each of the pages it replaces.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    reload();
    // `deps` is spread on purpose; see the JSDoc note about keeping its length fixed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, ...deps]);

  return { data, loading, error, reload, setData };
}

export default useAsyncData;
