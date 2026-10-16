import csv,json
from pathlib import Path
import pytest
from shelltrace.loaders.common import NodeRow,EdgeRow,PctError,normalise_pct,load_rows
from shelltrace.loaders.opensanctions import AUTH_MAP,parse_opensanctions
from shelltrace.loaders.gleif import parse_gleif_rr,select_component
from shelltrace.loaders.gem import parse_gem

FIX=Path(__file__).parent/'fixtures'

def test_pct_normalisation():
    assert normalise_pct('51','percent') == 51
    assert normalise_pct(.51,'fraction') == 51
    assert normalise_pct(None,'percent') is None
    assert normalise_pct('','percent') is None
    assert normalise_pct(1,'percent') == 1
    for bad in ['-1','100.5','abc',float('nan'),float('inf'),True]:
        with pytest.raises(PctError):normalise_pct(bad,'percent')
    with pytest.raises(PctError):normalise_pct(1.1,'fraction')
    with pytest.raises(PctError):normalise_pct(1,'guess')

def test_authentic_os_and_synthetic_person_rejection(tmp_path):
    # Authentic corpus is corporate only; rejection marker below is explicitly synthetic.
    path=tmp_path/'os.jsonl'
    path.write_text((FIX/'os_sample.ftm.jsonl').read_text(encoding='utf8')+'\n'+json.dumps({'id':'synthetic-person-marker','schema':'Person','caption':'SYNTHETIC PERSON TEST MARKER','properties':{}}),encoding='utf8')
    nodes,des,dropped=parse_opensanctions(path,AUTH_MAP)
    assert dropped==1 and all(n.label in {'Company','Vessel'} for n in nodes)
    assert {'OFAC','EU','UK'}=={e.properties['authority'] for e in des}
    assert any(n.label=='Vessel' and n.properties['imo'].isdigit() for n in nodes)
    assert any(e.properties['listed_on_basis']=='first_seen' for e in des)
    assert any(e.properties['listed_on_basis']=='source' for e in des)
    assert all(e.source in {n.id for n in nodes} for e in des)
    assert all(e.properties['src'].startswith('opensanctions:') for e in des)

def test_gleif_exact_headers_direction_period_and_units(tmp_path):
    rows=list(csv.DictReader((FIX/'gleif_rr_sample.csv').open(encoding='utf8')))
    row=rows[0].copy()
    row.update({'Relationship.StartNode.NodeID':'CHILD','Relationship.EndNode.NodeID':'PARENT',
                'Relationship.RelationshipType':'IS_DIRECTLY_CONSOLIDATED_BY','Relationship.RelationshipStatus':'ACTIVE',
                'Relationship.Period.1.periodType':'ACCOUNTING_PERIOD','Relationship.Period.1.startDate':'2000-01-01',
                'Relationship.Period.2.periodType':'RELATIONSHIP_PERIOD','Relationship.Period.2.startDate':'2020-01-02T00:00:00.000Z'})
    for i in range(1,6):
        for k in ['MeasurementMethod','QuantifierAmount','QuantifierUnits']:row[f'Relationship.Quantifiers.{i}.{k}']=''
    row.update({'Relationship.Quantifiers.2.MeasurementMethod':'ACCOUNTING_CONSOLIDATION','Relationship.Quantifiers.2.QuantifierAmount':'75','Relationship.Quantifiers.2.QuantifierUnits':'PERCENTAGE'})
    variants=[row,{**row,'Relationship.StartNode.NodeID':'BLANKUNIT','Relationship.Quantifiers.2.QuantifierUnits':''},
              {**row,'Relationship.StartNode.NodeID':'ULTIMATE','Relationship.RelationshipType':'IS_ULTIMATELY_CONSOLIDATED_BY'},
              {**row,'Relationship.StartNode.NodeID':'INACTIVE','Relationship.RelationshipStatus':'INACTIVE'}]
    path=tmp_path/'rr.csv'
    with path.open('w',newline='',encoding='utf8') as f:
        w=csv.DictWriter(f,fieldnames=list(row));w.writeheader();w.writerows(variants)
    edges=parse_gleif_rr(path,{'PARENT','CHILD','BLANKUNIT','ULTIMATE','INACTIVE'})
    assert len(edges)==2
    own=next(e for e in edges if e.label=='OWNS');ctrl=next(e for e in edges if e.label=='CONTROLS')
    assert (own.source,own.target)==('lei:PARENT','lei:CHILD')
    assert own.properties['pct']==75 and own.properties['pct_basis']=='accounting_consolidation'
    assert own.properties['valid_from']=='2020-01-02'
    assert ctrl.properties.get('pct') is None and ctrl.properties['data_error']=='missing_quantifier_units'

def test_component_down_three_up_one():
    es=[EdgeRow('lei:'+a,'lei:'+b,'CONTROLS',a+b) for a,b in [('P','S'),('S','A'),('A','B'),('B','C'),('C','D'),('GP','P'),('OTHER','A')]]
    keep=select_component(es,{'S'})
    assert keep=={'S','P','A','B','C','OTHER'}

def test_gem_imputed_and_people_cannot_be_definite_ownership(tmp_path):
    # Synthetic schema examples only: authentic GEM export is unavailable (404).
    rows=[{'id':i,'caption':i,'schema':'Company','properties':{}} for i in ['synthetic-A','synthetic-B']]
    rows += [{'id':'synthetic-person','schema':'Person','properties':{}},
             {'id':'synthetic-own','schema':'Ownership','properties':{'owner':['synthetic-A'],'asset':['synthetic-B'],'percentage':['80'],'share_imputed':['true']}},
             {'id':'synthetic-person-own','schema':'Ownership','properties':{'owner':['synthetic-person'],'asset':['synthetic-B'],'percentage':['90']}}]
    path=tmp_path/'gem.jsonl';path.write_text('\n'.join(json.dumps(x) for x in rows),encoding='utf8')
    nodes,edges,dropped=parse_gem(path)
    assert len(nodes)==2 and dropped==1 and len(edges)==1
    assert edges[0].properties.get('pct') is None and edges[0].properties['data_error']=='imputed_or_unverified_share'

def test_load_rows_attributed_idempotent(store):
    import uuid
    from shelltrace.db import ro
    g=store._db.select_graph('task21_test_'+uuid.uuid4().hex[:8])
    ns=[NodeRow('a','Company','Alpha'),NodeRow('b','Vessel','Beta'),NodeRow('real_ofac','Program','OFAC',properties={'authority':'OFAC'})]
    es=[EdgeRow('a','b','OWNS','ab',{'pct':51,'pct_basis':'shareholding'}),EdgeRow('a','real_ofac','DESIGNATED','d',{'listed_on':'2020-01-01','listed_on_basis':'source'})]
    try:
        load_rows(g,ns,es,'test-snapshot','test licence',batch_size=1);load_rows(g,ns,es,'test-snapshot','test licence',batch_size=1)
        assert ro(g,'MATCH (n) RETURN count(n) AS n')[0]['n']==3
        assert ro(g,'MATCH ()-[r]->() RETURN count(r) AS n')[0]['n']==2
        assert ro(g,'MATCH (n) WHERE n.src IS NULL OR n.snapshot IS NULL OR n.licence IS NULL RETURN count(n) AS n')[0]['n']==0
        assert ro(g,'MATCH ()-[r]->() WHERE r.src IS NULL OR r.snapshot IS NULL OR r.licence IS NULL RETURN count(r) AS n')[0]['n']==0
        with pytest.raises(ValueError):load_rows(g,[NodeRow('p','Person','forbidden')],[],'s','l')
    finally:g.delete()
