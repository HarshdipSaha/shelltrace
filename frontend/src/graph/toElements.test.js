import test from 'node:test';
import assert from 'node:assert/strict';
import hero from './fixtures/hero_case.json' with { type: 'json' };
import { toElements } from './toElements.js';

test('proof edges are marked and aliases are compound children', () => {
  const { nodes, edges } = toElements(hero);
  const proof = edges.filter((edge) => edge.classes.includes('proof')).map((edge) => edge.data.id);

  assert.deepStrictEqual(new Set(proof), new Set(['syn:G1-1', 'syn:G1-2', 'syn:G1-3']));
  assert.ok(nodes.find((node) => node.data.id === 'cluster:c_bluelagoon'));
  assert.strictEqual(
    nodes.find((node) => node.data.id === 'c_bluelagoon_alias').data.parent,
    'cluster:c_bluelagoon',
  );
  assert.ok(nodes.find((node) => node.data.id === hero.entity.id).classes.includes('target'));
  assert.ok(edges.every((edge) => edge.data.label !== undefined));
  assert.ok(edges.every((edge) => edge.data.validity !== undefined));
});

test('unknown expired stakes retain proof, decisive, and red-flag markers', () => {
  const result = {
    entity: { id: 'target', name: 'Target Co', kind: 'Company' },
    as_of: '2024-01-01',
    packs: { OFAC: { proof: ['edge-1'], decisive: ['edge-1'] } },
    red_flags: [{ evidence_keys: ['edge-1'] }],
    evidence: {
      'edge-1': {
        k: 'edge-1',
        type: 'OWNS',
        from_id: 'owner',
        from_name: 'Unknown Owner',
        to_id: 'target',
        to_name: 'Target Co',
        pct: null,
        valid_from: null,
        valid_to: '2022-01-01',
      },
    },
  };

  const edge = toElements(result).edges[0];

  for (const marker of ['proof', 'decisive', 'flagged', 'expired', 'unknown']) {
    assert.ok(edge.classes.includes(marker), `expected ${marker} marker`);
  }
  assert.equal(edge.data.label, '?');
  assert.equal(edge.data.validity, 'open → 2022-01-01');
});
