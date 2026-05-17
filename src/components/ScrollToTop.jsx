import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'

/**
 * Reset the window scroll to the top whenever the route pathname changes.
 *
 * React Router does NOT scroll to top on navigation by default — when a user
 * clicks a link on a long page (e.g. the bottom of the compare hub), the
 * destination page renders scrolled mid-way down. This component restores
 * the conventional "new page = top of page" behaviour.
 *
 * The hash-anchor case is preserved: if the URL has a `#fragment`, the
 * browser's native anchor scroll is left in place by skipping the reset.
 *
 * Mount this as a child of `<BrowserRouter>` once (in App.jsx, near the
 * top of the routes tree).
 */
export default function ScrollToTop() {
  const { pathname, hash } = useLocation()
  useEffect(() => {
    if (hash) return
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' })
  }, [pathname, hash])
  return null
}
