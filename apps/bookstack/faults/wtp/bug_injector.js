/**
 * Introduction:
 * -------------
 * This script monitors the page for two types of events:
 *   1. Initial page load (DOMContentLoaded or already-loaded document)
 *   2. DOM mutations (subtree changes, attributes, or child list changes)
 * 
 * When either event occurs, it evaluates a user-defined condition via the 
 * `isConditionMet` function. If the condition returns true, the `onConditionMet`
 * function is executed exactly once. After triggering, the sentinel cleans up 
 * its internal MutationObserver.
 * 
 * Usage:
 * ------
 * - Inject this template via Playwright.
 * - Replace {{IS_CONDITION_MET}} -> Body of the condition-checking function.
 * - Replace {{ON_CONDITION_MET}} -> Body of the callback to execute when condition is met.
 * - Use window.__BUG_INJECTOR_API__.transition(key, { active, after }) for
 *   visit/transition-counted bugs.
 */

(() => {
  // Only activate after init.py sets this flag post-setup; prevents modal
  // overlays from blocking Playwright click actionability during login.
  if (!sessionStorage.getItem('__flash_ui_active__')) return;

  // Keep trigger state under an explicit injector kind so reloads and
  // transition-counted bugs use the same namespace.
  const INJECTOR_KIND = "{{INJECTOR_KIND}}";
  const NAMESPACE = "__BUG_INJECTOR__:" + INJECTOR_KIND;
  const API_NAMESPACE = "__BUG_INJECTOR_API__";
  const STORAGE_KEY = "__BUG_INJECTOR_TRIGGERED__:" + INJECTOR_KIND;
  const TRIGGERED_URL_KEY = "__BUG_INJECTOR_TRIGGERED_URL__:" + INJECTOR_KIND;
  const FORCE_NEXT_TRANSITION_KEY = "__BUG_INJECTOR_FORCE_NEXT_TRANSITION__";
  const TRANSITION_PREV_PREFIX = "__BUG_INJECTOR_TRANSITION_PREV__:";
  const TRANSITION_COUNT_PREFIX = "__BUG_INJECTOR_TRANSITION_COUNT__:";

  // Prevent duplicate observers if the script is injected multiple times on the same page.
  // The sessionStorage.getItem(STORAGE_KEY) guard has been moved to after isConditionMet
  // and onConditionMet are defined, so the re-apply block can call onConditionMet() safely.
  if (window[NAMESPACE]) return;

  function transition(key, { active, after = 1 }) {
    const normalizedKey = String(key);
    const prevKey = `${TRANSITION_PREV_PREFIX}${normalizedKey}`;
    const countKey = `${TRANSITION_COUNT_PREFIX}${normalizedKey}`;
    const isActive = Boolean(active);
    const prevActive = sessionStorage.getItem(prevKey) === "true";
    const forceRequested = sessionStorage.getItem(FORCE_NEXT_TRANSITION_KEY) === "true";

    sessionStorage.setItem(prevKey, String(isActive));

    if (!isActive) return false;

    const isTransition = forceRequested || !prevActive;
    if (!isTransition) return false;

    if (forceRequested) {
      sessionStorage.removeItem(FORCE_NEXT_TRANSITION_KEY);
    }

    const threshold = Number(after) || 1;
    const count = Number(sessionStorage.getItem(countKey) || 0) + 1;
    sessionStorage.setItem(countKey, String(count));

    return count >= threshold;
  }

  window[API_NAMESPACE] = {
    forceNextTransitionKey: FORCE_NEXT_TRANSITION_KEY,
    transition,
  };

  // Evaluates whether the desired condition has been satisfied.
  // Replace with your custom code
  const isConditionMet = () => {};

  // Called exactly once when the condition is satisfied.
  // Replace with your custom code
  const onConditionMet = () => {};

  // If the bug was already triggered in a prior page load, re-apply the effect on
  // every subsequent visit to the same page.  Uses the URL recorded at trigger time
  // (pathname + search) rather than calling isConditionMet() again: transition-based
  // conditions have sessionStorage side effects (counter increments, prevActive updates)
  // that corrupt state when called repeatedly outside the normal first-trigger flow.
  //
  // Deferred via DOMContentLoaded: add_init_script runs before the DOM is parsed, so
  // document.querySelector() returns null at IIFE execution time for DOM-based bugs.
  if (sessionStorage.getItem(STORAGE_KEY)) {
    const triggeredUrl = sessionStorage.getItem(TRIGGERED_URL_KEY);
    if (triggeredUrl && (window.location.pathname + window.location.search) === triggeredUrl) {
      if (document.readyState === "complete" || document.readyState === "interactive") {
        onConditionMet();
      } else {
        document.addEventListener("DOMContentLoaded", () => onConditionMet(), { once: true });
      }
    }
    return;
  }

  // Internal State
  // -----------------------------------------------------------------------------
  // Tracks whether the initial page load event has been handled
  let pageLoaded = false;

  // Tracks whether the condition has been satisfied and action has been executed
  let conditionMet = false;

  // Prevents concurrent condition checks when a series of DOM mutation events happen
  let checkScheduled = false;

  // MutationObserver for DOM mutation events
  let mutationObserver = null;

  // Handles detection events by checking condition and triggering onConditionMet() once
  function handleDetection() {
    if (conditionMet) return;

    if (isConditionMet()) {
      conditionMet = true;
      onConditionMet();
      cleanup();
    }

    if (mutationObserver) {
      mutationObserver.takeRecords();
    }
  }

  // Cleanup after triggering onConditionMet()
  function cleanup() {
    sessionStorage.setItem(STORAGE_KEY, "true");
    sessionStorage.setItem(TRIGGERED_URL_KEY, window.location.pathname + window.location.search);

    if (mutationObserver) {
      mutationObserver.disconnect();
      mutationObserver = null;
    }
  }

  // Detector #1: Page Load
  // -----------------------------------------------------------------------------
  function handlePageLoad() {
    if (pageLoaded) return;
    pageLoaded = true;
    handleDetection();
  }

  if (document.readyState === "complete" || document.readyState === "interactive") {
    handlePageLoad();
  } else {
    document.addEventListener("DOMContentLoaded", handlePageLoad, { once: true });
  }

  // Detector #2: Coalesced DOM Mutations
  // -----------------------------------------------------------------------------
  function handleObserver() {
    mutationObserver = new MutationObserver(() => {
      if (conditionMet) {
        cleanup();
        return;
      }

      // Coalesce multiple mutations into one check per animation frame
      if (checkScheduled) return;

      checkScheduled = true;
      handleDetection();

      // Allow next burst of mutations to trigger check
      requestAnimationFrame(() => {
        checkScheduled = false;
      });
    });

    mutationObserver.observe(document.documentElement, {
      subtree: true,
      childList: true,
      attributes: true,
      attributeFilter: ["class", "style", "hidden", "aria-expanded", "aria-hidden"]
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", handleObserver, { once: true });
  } else {
    handleObserver();
  }

  window[NAMESPACE] = { mutationObserver, conditionMet };
})();
