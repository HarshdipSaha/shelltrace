import { useEffect, useMemo, useRef, useState } from 'react';
import cytoscape from 'cytoscape';
import dagre from 'cytoscape-dagre';
import { toElements } from '../graph/toElements.js';

cytoscape.use(dagre);

const graphStyle = (isDark = document.documentElement.dataset.theme === 'dark') => {
  const palette = isDark
    ? {
      node: '#1b2936', nodeBorder: '#486174', nodeText: '#e2edf3', cluster: '#304454',
      clusterBorder: '#668293', clusterText: '#b5c9d4', designated: '#9a4a54',
      designatedBorder: '#e58089', edge: '#93adbb', edgeText: '#c5d5de', edgeLabel: '#151f2a',
      proof: '#ff7d88', proofText: '#ffb4bc', decisive: '#ffd18b', expired: '#71828d',
      flagged: '#ffd18b', flaggedText: '#ffe0aa', lit: '#ff7d88', target: '#7bd9c7',
    }
    : {
      node: '#f3f7f8', nodeBorder: '#b7c9ce', nodeText: '#294552', cluster: '#e8f0f1',
      clusterBorder: '#90a7ad', clusterText: '#71868c', designated: '#853b42',
      designatedBorder: '#762e36', edge: '#85a1a9', edgeText: '#526e77', edgeLabel: '#fff',
      proof: '#bc4148', proofText: '#9d3039', decisive: '#d39b42', expired: '#929da2',
      flagged: '#bd842b', flaggedText: '#986916', lit: '#d34b4e', target: '#176f70',
    };

  return [
  {
    selector: 'node',
    style: {
      label: 'data(label)',
      shape: 'round-rectangle',
      width: 138,
      height: 52,
      padding: '6px',
      'background-color': palette.node,
      'border-color': palette.nodeBorder,
      'border-width': 1,
      color: palette.nodeText,
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
      'background-color': palette.cluster,
      'background-opacity': 0.36,
      'border-color': palette.clusterBorder,
      'border-style': 'dashed',
      'border-width': 1,
      color: palette.clusterText,
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
      'background-color': palette.designated,
      'border-color': palette.designatedBorder,
      color: '#fff8f6',
    },
  },
  {
    selector: 'node.target',
    style: {
      'border-color': palette.target,
      'border-width': 3,
    },
  },
  {
    selector: 'edge',
    style: {
      label: 'data(label)',
      width: 2,
      'line-color': palette.edge,
      'target-arrow-color': palette.edge,
      'target-arrow-shape': 'triangle',
      'arrow-scale': 0.8,
      'curve-style': 'bezier',
      'control-point-step-size': 30,
      'font-size': 8,
      color: palette.edgeText,
      'text-rotation': 'autorotate',
      'text-background-color': palette.edgeLabel,
      'text-background-opacity': 0.92,
      'text-background-padding': 2,
      'text-margin-y': -5,
    },
  },
  {
    selector: 'edge.proof',
    style: {
      width: 4,
      'line-color': palette.proof,
      'target-arrow-color': palette.proof,
      color: palette.proofText,
      'font-weight': 700,
      'z-index': 5,
    },
  },
  {
    selector: 'edge.decisive',
    style: {
      'line-outline-color': palette.decisive,
      'line-outline-width': 2,
    },
  },
  {
    selector: 'edge.expired',
    style: {
      'line-style': 'dashed',
      'line-color': palette.expired,
      'target-arrow-color': palette.expired,
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
      'line-color': palette.flagged,
      'target-arrow-color': palette.flagged,
      color: palette.flaggedText,
    },
  },
  {
    selector: 'edge.lit',
    style: {
      width: 5,
      'line-color': palette.lit,
      'target-arrow-color': palette.lit,
    },
  },
  ];
};

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
      style: graphStyle(),
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
    const themeObserver = new MutationObserver(() => cy.style(graphStyle()));
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

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
      themeObserver.disconnect();
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
