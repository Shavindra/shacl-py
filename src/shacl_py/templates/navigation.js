export default function ({ parentElement, setStateValue }) {
    // Streamlit can render the same component again before it unmounts.
    parentElement.routeListeners?.abort();
    const listeners = new AbortController();
    parentElement.routeListeners = listeners;
    const options = { signal: listeners.signal };
    const live = parentElement.liveFilter ??= { edit: null, timer: null };
    const selector = '.study form[data-live-filter] input[type="search"]';

    function readRoute() {
        setStateValue("route", window.location.hash.slice(1));
    }

    function editFor(input) {
        if (live.edit?.input !== input || live.edit.hash !== location.hash) {
            live.edit = { input, hash: location.hash, started: false, focused: true };
        }
        return live.edit;
    }

    function applyFilter(edit) {
        if (live.edit !== edit || location.hash !== edit.hash) return;
        const input = edit.input;
        const params = new URLSearchParams(new FormData(input.form));
        if (!input.value) params.delete(input.name);
        const next = new URL(location.href);
        next.hash = params.toString();
        if (next.hash === location.hash) return;
        // Back returns to the view before typing, even after several pauses.
        if (edit.started) history.replaceState(history.state, "", next);
        else history.pushState(history.state, "", next);
        edit.hash = next.hash;
        edit.started = true;
        readRoute();
    }

    function schedule(event) {
        const input = event.target;
        if (!input.matches(selector)) return;
        clearTimeout(live.timer);
        if (event.isComposing) return;
        const edit = editFor(input);
        edit.focused = true;
        live.timer = setTimeout(() => applyFilter(edit), 200);
    }

    // A server render replaces the search box. Keep any text entered since the
    // request and return the caret to the new input unless focus has moved on.
    function restoreInput() {
        const edit = live.edit;
        if (!edit || edit.input.isConnected || edit.hash !== location.hash) return;
        const old = edit.input;
        const input = document.querySelector(`${selector}[name="${CSS.escape(old.name)}"]`);
        if (!input) return;
        input.value = old.value;
        edit.input = input;
        if (edit.focused && document.activeElement === document.body) {
            input.focus({ preventScroll: true });
            input.setSelectionRange(old.selectionStart, old.selectionEnd, old.selectionDirection);
        }
    }

    // Keep an expanded concept's notes visible when a record tab replaces the HTML.
    const notesSelector = ".study details[data-concept-notes]";
    document.addEventListener("toggle", ({ target }) => {
        if (target.isConnected && target.matches?.(notesSelector)) {
            parentElement.openNotes = target.open ? target.dataset.conceptNotes : null;
        }
    }, { ...options, capture: true });

    function restoreControls() {
        restoreInput();
        const panel = document.querySelector(notesSelector);
        if (panel && !panel.open && panel.dataset.conceptNotes === parentElement.openNotes) {
            panel.open = true;
        }
    }

    const observer = new MutationObserver(restoreControls);
    observer.observe(document.querySelector(".st-key-shacl_viewer") ?? document.body,
        { childList: true, subtree: true });
    listeners.signal.addEventListener("abort", () => observer.disconnect());
    restoreControls();

    function focusMoved(event) {
        if (live.edit && event.target !== live.edit.input) live.edit.focused = false;
    }
    document.addEventListener("focusin", focusMoved, options);
    document.addEventListener("pointerdown", focusMoved, options);
    window.addEventListener("hashchange", () => {
        clearTimeout(live.timer);
        live.edit = null;
        readRoute();
    }, options);
    document.addEventListener("input", schedule, options);
    document.addEventListener("compositionend", schedule, options);
    function currentTermRoute() {
        const values = new URLSearchParams(window.location.hash.slice(1));
        if (values.get("section") === "terms" && values.get("term")?.startsWith("keyword/")) {
            if (!values.has("keyword")) values.set("keyword", values.get("term"));
            values.delete("term");
        }
        return values;
    }

    document.addEventListener("change", (event) => {
        const control = event.target;
        if (control.matches(".study .term-filters select")) {
            const values = currentTermRoute();
            values.set("section", "terms");
            if (control.value) values.set(control.name, control.value);
            else values.delete(control.name);
            window.location.hash = values.toString();
        } else if (control.matches(".study .graph-filter select, .study .method-filters select")) {
            control.form.requestSubmit();
        }
    }, options);
    document.addEventListener("submit", (event) => {
        const form = event.target;
        if (event.defaultPrevented || !form.matches(".study form[method=get]")) return;
        event.preventDefault();
        if (form.hasAttribute("data-live-filter")) {
            clearTimeout(live.timer);
            applyFilter(editFor(form.querySelector('input[type="search"]')));
        } else {
            const values = new URLSearchParams(new FormData(form));
            if (values.get("section") === "terms") {
                // A new route can arrive before Streamlit replaces the previous form.
                // Keep the other controls from the active bookmark.
                const current = currentTermRoute();
                if (current.get("section") === "terms") {
                    for (const key of form.matches(".term-filters") ? ["q"] : ["subject", "term", "keyword"]) {
                        if (current.has(key)) values.set(key, current.get(key));
                        else values.delete(key);
                    }
                }
                for (const key of ["q", "subject", "term", "keyword"]) if (!values.get(key)) values.delete(key);
            }
            if (form.matches(".method-filters")) {
                for (const key of ["technique", "compartment"]) if (!values.get(key)) values.delete(key);
            }
            window.location.hash = values.toString();
        }
    }, options);

    readRoute();
    return () => listeners.abort();
}
