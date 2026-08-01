/* hooks.jsx — shared React hooks.
 *
 * The prototype styles inline, so CSS media queries only reach elements that
 * happen to carry a className. Components that need to restructure (not just
 * restyle) below 768px use this instead of another !important override.
 */
function useIsMobile(query) {
  const q = query || '(max-width: 767px)';
  const [match, setMatch] = React.useState(
    () => typeof window !== 'undefined' && window.matchMedia
      ? window.matchMedia(q).matches : false);
  React.useEffect(() => {
    if (!window.matchMedia) return;
    const mql = window.matchMedia(q);
    const on = e => setMatch(e.matches);
    setMatch(mql.matches);
    if (mql.addEventListener) mql.addEventListener('change', on);
    else mql.addListener(on);                      // Safari < 14
    return () => {
      if (mql.removeEventListener) mql.removeEventListener('change', on);
      else mql.removeListener(on);
    };
  }, [q]);
  return match;
}

/* Reactive viewport width. analytics.jsx read window.innerWidth once at render
 * with no resize listener, so its chart kept portrait width after a rotate
 * (audit item #9). Task 12 consumes this. */
function useViewportWidth() {
  const [w, setW] = React.useState(
    () => (typeof window !== 'undefined' ? window.innerWidth : 1280));
  React.useEffect(() => {
    const on = () => setW(window.innerWidth);
    window.addEventListener('resize', on);
    on();
    return () => window.removeEventListener('resize', on);
  }, []);
  return w;
}

window.useIsMobile = useIsMobile;
window.useViewportWidth = useViewportWidth;
