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
    document.addEventListener("change", (event) => {
        if (event.target.matches(".study .graph-filter select")) event.target.form.requestSubmit();
    }, options);
    document.addEventListener("click", (event) => {
        const button = event.target.closest(".study [data-graph-zoom]");
        if (!button) return;
        const svg = document.querySelector(".st-key-graph_canvas .stGraphVizChart > svg");
        if (!svg) return;
        const action = button.dataset.graphZoom;
        if (action === "fit") {
            delete svg.dataset.zoom;
            svg.style.removeProperty("width");
            return;
        }
        const previous = Number(svg.dataset.zoom || 1);
        const fittedWidth = svg.getBoundingClientRect().width / previous;
        // Even a graph fitted to a small viewport can reach its natural size.
        const maximum = Math.max(4, 3 * svg.viewBox.baseVal.width / fittedWidth);
        const zoom = Math.min(maximum, Math.max(0.5, previous * (action === "in" ? 1.5 : 1 / 1.5)));
        svg.dataset.zoom = String(zoom);
        svg.style.width = fittedWidth * zoom + "px";
    }, options);
    document.addEventListener("submit", (event) => {
        const form = event.target;
        if (event.defaultPrevented || !form.matches(".study form[method=get]")) return;
        event.preventDefault();
        window.location.hash = new URLSearchParams(new FormData(form)).toString();
    }, options);

    readRoute();
    return () => listeners.abort();
}
