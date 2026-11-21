import "./vendor/d3-7.9.0.min.js";

const d3 = globalThis.d3;
const marks = {
    Paper: d3.symbol().type(d3.symbolCircle).size(265)(),
    Dataset: d3.symbol().type(d3.symbolSquare).size(245)(),
    Label: d3.symbol().type(d3.symbolDiamond).size(125)(),
};

function caption(title) {
    const lines = [""];
    for (const word of title.split(/\s+/)) {
        const last = lines.length - 1;
        const line = [lines[last], word].filter(Boolean).join(" ");
        if (line.length <= 24) {
            lines[last] = line;
        } else if (lines[last] && last === 0) {
            lines.push(word);
        } else {
            lines[last] = line.slice(0, 23).trimEnd() + "…";
            break;
        }
    }
    return lines.map(line => line.length > 24 ? line.slice(0, 23).trimEnd() + "…" : line);
}

function edgePath({source, target, bend}) {
    const {x, y} = source;
    if (source === target) {
        const r = 30 + Math.abs(bend);
        return `M${x-6},${y-8}c${-r},${-r*1.6} ${r+12},${-r*1.6} 12,0`;
    }
    const dx = target.x - x;
    const dy = target.y - y;
    const length = Math.hypot(dx, dy) || 1;
    const nx = dx / length, ny = dy / length;
    const cx = (x + target.x) / 2 - ny * bend;
    const cy = (y + target.y) / 2 + nx * bend;
    return `M${x+nx*11},${y+ny*11}Q${cx},${cy} ${target.x-nx*12},${target.y-ny*12}`;
}

export default function ({parentElement, data}) {
    const svg = d3.select(parentElement.querySelector(".canvas"));
    svg.selectAll("*").remove();
    const defs = svg.append("defs");
    defs.append("marker").attr("id", "network-arrow").attr("viewBox", "0 0 8 8")
        .attr("refX", 7).attr("refY", 4).attr("markerWidth", 6).attr("markerHeight", 6)
        .attr("orient", "auto").append("path").attr("d", "M0,0 L8,4 L0,8 Z").attr("fill", "#858b87");
    const layer = svg.append("g").attr("class", "viewport");

    // D3 mutates coordinates and link endpoints. Keep Streamlit's input intact.
    const nodes = data.nodes.map(node => ({...node, lines: caption(node.label)}));
    const edges = data.edges.map(edge => ({...edge}));
    const pairs = d3.group(edges, e => JSON.stringify([e.source, e.target].sort()));
    for (const group of pairs.values()) {
        group.forEach((edge, i) => {
            edge.bend = (i - (group.length - 1) / 2) * (edge.source <= edge.target ? 35 : -35);
        });
    }
    const simulation = d3.forceSimulation(nodes)
        .force("link", d3.forceLink(edges).id(node => node.id).distance(145))
        .force("charge", d3.forceManyBody().strength(-360))
        .force("x", d3.forceX(0).strength(0.055))
        .force("y", d3.forceY(0).strength(0.055))
        .force("collide", d3.forceCollide(node => 15 + Math.max(...node.lines.map(line => line.length)) * 2.8))
        .stop();
    simulation.tick(160);

    const links = layer.append("g").selectAll("path").data(edges).join("path")
        .attr("class", edge => edge.predicate === "Labelled" ? "edge tag" : "edge")
        .attr("marker-end", edge => edge.predicate === "Labelled" ? null : "url(#network-arrow)")
        .attr("d", edgePath);
    links.append("title").text(edge => edge.predicate);
    const points = layer.append("g").selectAll("a").data(nodes).join("a")
        .attr("class", node => `node ${node.kind.toLowerCase()}${node.focused ? " focused" : ""}`)
        .attr("href", node => node.id)
        .attr("aria-label", node => `${node.kind} · ${node.label}`)
        .attr("transform", node => `translate(${node.x},${node.y})`);
    points.append("title").text(node => node.label);
    points.append("circle").attr("class", "halo").attr("r", 15);
    points.append("path").attr("class", "mark").attr("d", node => marks[node.kind]);
    points.append("text").attr("y", 27).selectAll("tspan").data(node => node.lines).join("tspan")
        .attr("x", 0).attr("dy", (_, i) => i ? "1.1em" : 0).text(line => line);

    const canvas = svg.node();
    let fitted = true;
    let bounds;
    const zoom = d3.zoom().scaleExtent([0.001, 12])
        .extent(() => [[0, 0], [canvas.clientWidth, canvas.clientHeight]])
        .on("start", event => svg.classed("panning", event.sourceEvent?.type === "mousedown"))
        .on("zoom", event => {
            if (event.sourceEvent) fitted = false;
            layer.attr("transform", event.transform);
        })
        .on("end", () => svg.classed("panning", false));
    svg.call(zoom).on("dblclick.zoom", null);

    points.call(d3.drag().container(layer.node()).clickDistance(4)
        .on("drag", function (event, node) {
            fitted = false;
            bounds = undefined;
            svg.classed("dragging", true);
            node.x = event.x;
            node.y = event.y;
            d3.select(this).attr("transform", `translate(${node.x},${node.y})`);
            links.filter(link => link.source === node || link.target === node).attr("d", edgePath);
        })
        .on("end", () => svg.classed("dragging", false)));

    function fit() {
        const w = canvas.clientWidth, h = canvas.clientHeight;
        if (!w || !h) return;
        bounds ??= layer.node().getBBox();
        const {x, y, width, height} = bounds;
        const k = Math.max(0.001, Math.min(1.35, (w - 48) / (width || 1), (h - 64) / (height || 1)));
        svg.call(zoom.transform, d3.zoomIdentity.translate(w / 2, h / 2)
            .scale(k).translate(-x - width / 2, -y - height / 2));
        fitted = true;
    }
    const controls = d3.select(parentElement.querySelector(".controls"));
    controls.selectAll("button").on("click", function () {
        const action = this.dataset.action;
        if (action === "fit") return fit();
        fitted = false;
        svg.call(zoom.scaleBy, action === "in" ? 1.4 : 1 / 1.4);
    });
    const resize = new ResizeObserver(() => { if (fitted) fit(); });
    resize.observe(canvas);
    fit();
    return () => {
        resize.disconnect();
        svg.on(".zoom", null);
        controls.selectAll("button").on("click", null);
    };
}
