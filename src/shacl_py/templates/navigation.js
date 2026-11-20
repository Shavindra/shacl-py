export default function ({ parentElement, setStateValue }) {
    // Streamlit can render the same component again before it unmounts.
    parentElement.routeListeners?.abort();
    const listeners = new AbortController();
    parentElement.routeListeners = listeners;
    const options = { signal: listeners.signal };

    function readRoute() {
        setStateValue("route", window.location.hash.slice(1));
    }

    window.addEventListener("hashchange", readRoute, options);
    document.addEventListener("submit", (event) => {
        const form = event.target;
        if (event.defaultPrevented || !form.matches(".study form[method=get]")) return;
        event.preventDefault();
        window.location.hash = new URLSearchParams(new FormData(form)).toString();
    }, options);

    readRoute();
    return () => listeners.abort();
}
