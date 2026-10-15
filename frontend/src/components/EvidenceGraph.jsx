import { useEffect, useMemo, useRef, useState } from 'react';
import cytoscape from 'cytoscape';
import dagre from 'cytoscape-dagre';
import { toElements } from '../graph/toElements.js';

cytoscape.use(dagre);

const graphStyle = [
  {
    selector: 'node',
    style: {
      label: 'data(label)',
      shape: 'round-rectangle',
      width: 138,
      height: 52,
      padding: '6px',
      'background-color': '#f3f7f8',
      'border-color': '#b7c9ce',
      'border-width': 1,
      color: '#294552',
      'font-size': 10,
      'font-weight': 600,
      'text-wrap': 'wrap',
      'text-max-width': 120,
      'text-valign': 'center',
      'text-halign': 'center',
    },
  },
  {
    selector: 'node.cluster',
    style: {
      label: 'data(label)',
      shape: 'round-rectangle',
      'background-color': '#e8f0f1',
      'background-opacity': 0.36,
      'border-color': '#90a7ad',
      'border-style': 'dashed',
      'border-width': 1,
      color: '#71868c',
      'font-size': 8,
      'font-weight': 500,
      padding: '18px',
      'text-valign': 'top',
      'text-margin-y': 6,
      'z-compound-depth': 'bottom',
    },
  },
  {
    selector: 'node.designated',
    style: {
      'background-color': '#853b42',
      'border-color': '#762e36',
      color: '#fff8f6',
    },
  },
  {
    selector: 'node.target',
    style: {
      'border-color': '#176f70',
      'border-width': 3,
    },
  },
  {
    selector: 'edge',
    style: {
      label: 'data(label)',
      width: 2,
      'line-color': '#85a1a9',
      'target-arrow-color': '#85a1a9',
      'target-arrow-shape': 'triangle',
      'arrow-scale': 0.8,
      'curve-style': 'bezier',
      'control-point-step-size': 30,
      'font-size': 8,
      color: '#526e77',
      'text-rotation': 'autorotate',
      'text-background-color': '#fff',
      'text-background-opacity': 0.92,
      'text-background-padding': 2,
      'text-margin-y': -5,
    },
  },
  {
    selector: 'edge.proof',
    style: {
      width: 4,
      'line-color': '#bc4148',
      'target-arrow-color': '#bc4148',
      color: '#9d3039',
      'font-weight': 700,
      'z-index': 5,
    },
  },
  {
    selector: 'edge.decisive',
    style: {
      'line-outline-color': '#d39b42',
      'line-outline-width': 2,
    },
  },
  {
    selector: 'edge.expired',
    style: {
      'line-style': 'dashed',
      'line-color': '#929da2',
      'target-arrow-color': '#929da2',
      opacity: 0.5,
    },
  },
  {
    selector: 'edge.unknown',
    style: {
      label: '?',
      'line-style': 'dotted',
    },
  },
  {
    selector: 'edge.flagged',
    style: {
      'line-color': '#bd842b',
      'target-arrow-color': '#bd842b',
      color: '#986916',
    },
  },
  {
    selector: 'edge.lit',
    style: {
      width: 5,
      'line-color': '#d34b4e',
      'target-arrow-color': '#d34b4e',
    },
  },
];

const compareProofOrder = (left, right) => (
  (left.data.hop ?? Number.MAX_SAFE_INTEGER) - (right.data.hop ?? Number.MAX_SAFE_INTEGER)
  || left.data.id.localeCompare(right.data.id)
);

function EvidenceGraph({ result, onSelect }) {
  const containerRef = useRef(null);
  const [hovered, setHovered] = useState(null);
  const [selectedNode, setSelectedNode] = useState(null);
  const graph = useMemo(
    () => (result ? toElements(result) : { nodes: [], edges: [] }),
    [result],
  );
  const proofEdges = useMemo(() => graph.edges
    .filter((edge) => edge.classes.split(' ').includes('proof'))
    .sort(compareProofOrder), [graph.edges]);

  useEffect(() => {
    if (!result || !containerRef.current) return undefined;
    const cy = cytoscape({
      container: containerRef.current,
      elements: [...graph.nodes, ...graph.edges],
      style: graphStyle,
      layout: {
        name: 'dagre',
        rankDir: 'TB',
        nodeSep: 40,
        rankSep: 70,
        padding: 28,
      },
      minZoom: 0.35,
      maxZoom: 2.2,
      boxSelectionEnabled: false,
    });
    const timers = proofEdges.map((edge, index) => window.setTimeout(() => {
      cy.getElementById(edge.data.id).addClass('lit');
    }, index * 250));
    const resizeObserver = typeof ResizeObserver === 'undefined'
      ? null
      : new ResizeObserver(() => cy.resize());
    resizeObserver?.observe(containerRef.current);

    cy.on('tap', 'edge', (event) => {
      const edge = event.target;
      setSelectedNode(null);
      onSelect?.(edge.id());
    });
    cy.on('tap', 'node', (event) => {
      const node = event.target;
      setHovered(null);
      if (node.hasClass('cluster')) return;
      setSelectedNode({ name: node.data('label'), kind: node.data('kind') });
      onSelect?.(null);
    });
    cy.on('mouseover', 'edge', (event) => {
      const edge = event.target;
      setHovered({ key: edge.id(), validity: edge.data('validity') });
    });
    cy.on('mouseout', 'edge', () => setHovered(null));

    return () => {
      timers.forEach(window.clearTimeout);
      resizeObserver?.disconnect();
      cy.destroy();
    };
  }, [result, onSelect, graph.nodes, graph.edges, proofEdges]);

  return (
    <section className="evidence-graph-panel panel" aria-label="Evidence graph">
      <div className="graph-panel-heading">
        <div>
          <p className="eyebrow">OWNERSHIP PROOF / {result ? `${graph.nodes.length} ENTITIES` : 'READY'}</p>
          <h2>Evidence graph</h2>
        </div>
        {result && <span className="graph-scope">{result.max_hops} hop bound</span>}
      </div>
      {result ? (
        <>
          <div
            className="evidence-graph-canvas"
            ref={containerRef}
            role="img"
            aria-label="Interactive ownership evidence graph. Proof edges are red; select an edge to inspect its evidence."
            data-testid="evidence-graph-canvas"
          />
          {hovered && (
            <div className="graph-hover-record" role="status">
              <code>{hovered.key}</code><span>{hovered.validity}</span>
            </div>
          )}
          {selectedNode && (
            <div className="graph-node-record" role="status">
              <span>Selected entity</span><strong>{selectedNode.name}</strong><small>{selectedNode.kind}</small>
            </div>
          )}
          {proofEdges.length > 0 && (
            <div className="graph-proof-keys" role="group" aria-label="Proof evidence keys">
              <span>Proof records</span>
              {proofEdges.map((edge) => (
                <button
                  key={edge.data.id}
                  type="button"
                  aria-label={`Select evidence ${edge.data.id}`}
                  title={`Select ${edge.data.id}`}
                  onClick={() => { setSelectedNode(null); onSelect?.(edge.data.id); }}
                >
                  {edge.data.id}<small>{edge.data.label}</small>
                </button>
              ))}
            </div>
          )}
        </>
      ) : (
        <div className="graph-empty">
          <span className="graph-empty-mark" aria-hidden="true">◎</span>
          <strong>Evidence appears after an investigation</strong>
          <p>Run a dated case to see ownership paths, source records, and the edges that support each verdict.</p>
        </div>
      )}
      <div className="graph-legend" aria-label="Evidence graph legend">
        <span><i className="legend-proof" />Ownership proof</span>
        <span><i className="legend-decisive" />Decisive record</span>
        <span><i className="legend-expired" />Expired</span>
        <span><i className="legend-unknown" />Unknown stake</span>
        <span><i className="legend-flagged" />Red flag</span>
        <span><i className="legend-designated" />Designated</span>
      </div>
    </section>
  );
}

export default EvidenceGraph;
