const values = (record) => Object.values(record || {});

export function toElements(result) {
  const evidence = result?.evidence || {};
  const evidenceEntries = Object.entries(evidence);
  const records = evidenceEntries.map(([, edge]) => edge);
  const proof = new Set(values(result?.packs).flatMap((pack) => pack?.proof || []));
  const decisive = new Set(values(result?.packs).flatMap((pack) => pack?.decisive || []));
  const flagged = new Set((result?.red_flags || []).flatMap((flag) => flag?.evidence_keys || []));
  const aliases = records.filter((edge) => edge.type === 'SAME_AS' && edge.from_id && edge.to_id);
  const parents = new Map();

  const find = (id) => {
    if (!parents.has(id)) parents.set(id, id);
    const parent = parents.get(id);
    if (parent === id) return id;
    const root = find(parent);
    parents.set(id, root);
    return root;
  };
  const unite = (left, right) => {
    const leftRoot = find(left);
    const rightRoot = find(right);
    if (leftRoot === rightRoot) return;
    const [first, second] = [leftRoot, rightRoot].sort();
    parents.set(second, first);
  };

  aliases.forEach((edge) => unite(edge.from_id, edge.to_id));
  const aliasOf = new Map([...parents.keys()].map((id) => [id, find(id)]));
  const nodes = new Map();
  const edges = [];
  const traceNodes = new Map((result?.trace?.nodes || []).map((node) => [node.id, node]));
  const traceEdgeOrder = new Map((result?.trace?.edges || []).map((edge, index) => [edge.k, index]));
  const designated = new Set(records
    .filter((edge) => edge.type === 'DESIGNATED')
    .map((edge) => edge.from_id));

  const addNode = (id, name, kind) => {
    if (!id) return;
    const canonical = aliasOf.get(id);
    if (canonical) {
      const clusterId = `cluster:${canonical}`;
      if (!nodes.has(clusterId)) {
        nodes.set(clusterId, {
          data: { id: clusterId, label: 'alias cluster' },
          classes: 'cluster',
        });
      }
    }

    const traceNode = traceNodes.get(id);
    const data = {
      ...(nodes.get(id)?.data || {}),
      id,
      label: nodes.get(id)?.data?.label || traceNode?.name || name || id,
      kind: traceNode?.kind || kind,
    };
    if (canonical) data.parent = `cluster:${canonical}`;
    nodes.set(id, {
      data,
      classes: [
        data.kind?.toLowerCase(),
        id === result?.entity?.id ? 'target' : '',
        designated.has(id) ? 'designated' : '',
      ].filter(Boolean).join(' '),
    });
  };

  for (const [evidenceKey, edge] of evidenceEntries) {
    if (edge.type === 'DESIGNATED') {
      addNode(edge.from_id, edge.from_name, 'Person');
      continue;
    }
    if (edge.type === 'SAME_AS') continue;

    addNode(edge.from_id, edge.from_name, edge.type === 'OFFICER_OF' ? 'Person' : 'Entity');
    addNode(edge.to_id, edge.to_name, 'Entity');
    const key = edge.k || evidenceKey;
    const expired = Boolean(edge.valid_to && result?.as_of && edge.valid_to < result.as_of);
    const unknown = edge.type === 'OWNS' && edge.pct == null;
    const label = edge.type === 'OWNS'
      ? (unknown ? '?' : `${edge.pct}%`)
      : (edge.type || '').toLowerCase();
    const classes = [
      edge.type?.toLowerCase(),
      proof.has(key) ? 'proof' : '',
      decisive.has(key) ? 'decisive' : '',
      flagged.has(key) ? 'flagged' : '',
      expired ? 'expired' : '',
      unknown ? 'unknown' : '',
    ].filter(Boolean).join(' ');
    const data = {
      id: key,
      source: edge.from_id,
      target: edge.to_id,
      label,
      validity: `${edge.valid_from || 'open'} → ${edge.valid_to || 'open'}`,
    };
    const traceOrder = traceEdgeOrder.get(key);
    if (traceOrder !== undefined) data.hop = traceOrder + 1;
    edges.push({ data, classes });
  }

  if (result?.entity?.id) {
    addNode(result.entity.id, result.entity.name, result.entity.kind);
  }

  return { nodes: [...nodes.values()], edges };
}
