import dataclasses
import json
import unittest
from client_policy import OfflineCandidate, PROFILE, DIGEST, Rejected
from routing_candidate import Home, Manifest, Refused, SYNTHETIC

V3=(1.,0.,0.)
V768=(1.,)+(0.,)*767

class FakeExchange:
    """No network and no model. Records only fabricated fixtures."""
    def __init__(self):
        self.calls=[]
        self.fail_at=None
        self.hook=None
    def __call__(self, body, remaining):
        data=json.loads(body);self.calls.append(data)
        if self.hook: self.hook()
        if self.fail_at==len(self.calls): return 503,b'{}'
        return 200,json.dumps({'profile':PROFILE,'model_digest':DIGEST,
            'dimension':768,'operation':data['operation'],
            'input_tokens':[4]*len(data['texts']),
            'embeddings':[V768]*len(data['texts'])}).encode()

class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.h=Home();self.a=self.h.bind('fabricated-A');self.b=self.h.bind('fabricated-B')
        self.s=Manifest('synthetic3',SYNTHETIC,'synthetic',3,'exact-fixture-index3-v1')
        self.m=Manifest('semantic768',PROFILE,DIGEST,768,'exact-fixture-index768-v1')
        for r in (self.a,self.b): self.h.initialize(r,self.s)
        self.fake=FakeExchange();self.client=OfflineCandidate(self.fake,max_calls=32,total_seconds=30)
    def tearDown(self): self.h.close()
    def seed(self, repo=None, chunks=None):
        repo=repo or self.a;chunks=chunks or ['Fabricated cedar library opens nine.']
        repo.write(repo.route(),'dummy-document',chunks,[V3]*len(chunks))
    def ready(self):
        self.seed();self.a.freeze(self.a.route());self.a.stage(self.m)
        self.a.populate(self.m.namespace,self.client)
    def count(self,table,namespace):
        return self.h.db.execute('SELECT count(*) FROM '+table+' WHERE tenant=? AND '+('namespace' if table!='namespaces' else 'name')+'=?',(self.a.tenant,namespace)).fetchone()[0]
    def boom(self, at):
        def fail(step):
            if step==at: raise RuntimeError('injected fixture failure')
        return fail
    def test_home_authoritative_tuple(self):
        r=self.a.route()
        self.assertEqual(r.manifest,self.s);self.assertEqual(r.epoch,1)
        self.assertEqual(self.h.db.execute('SELECT count(*) FROM routes').fetchone()[0],2)
    def test_frozen_bound_scope(self):
        with self.assertRaises(dataclasses.FrozenInstanceError): self.a.tenant=self.b.tenant
        with self.assertRaises(dataclasses.FrozenInstanceError): self.a.route().manifest.dimension=768
    def test_foreign_route_read_write_freeze_refused(self):
        foreign=self.b.route()
        for call in [lambda:self.a.search(foreign,V3),lambda:self.a.write(foreign,'x',['dummy'],[V3]),lambda:self.a.freeze(foreign)]:
            with self.assertRaises(Refused): call()
    def test_same_bytes_two_tenants_separate(self):
        self.seed(self.a);self.seed(self.b)
        self.a.write(self.a.route(),'only-A',['Fabricated A only'],[V3])
        self.assertEqual(len(self.a.search(self.a.route(),V3)['hits']),2)
        self.assertEqual(len(self.b.search(self.b.route(),V3)['hits']),1)
    def test_write_document_chunk_atomic_failure(self):
        for step in ('document','chunk_vector'):
            with self.assertRaises(RuntimeError):
                self.a.write(self.a.route(),'failed',['fabricated one','fabricated two'],[V3,V3],self.boom(step))
            self.assertEqual(self.count('documents','synthetic3'),0)
            self.assertEqual(self.count('chunks','synthetic3'),0)
    def test_invalid_vector_before_visible_document(self):
        for v in ([0.]*3,[True,0.,0.],[float('nan'),0.,0.],V768):
            with self.assertRaises(Refused): self.a.write(self.a.route(),'bad',['dummy'],[v])
        self.assertEqual(self.count('documents','synthetic3'),0)
    def test_stage_requires_freeze(self):
        with self.assertRaises(Refused):self.a.stage(self.m)
    def test_frozen_write_refused(self):
        self.a.freeze(self.a.route())
        with self.assertRaises(Refused):self.seed()
    def test_manifest_profile_and_dimension_refuse(self):
        self.a.freeze(self.a.route())
        for m in (dataclasses.replace(self.m,dimension=3),dataclasses.replace(self.m,model_digest='wrong'),dataclasses.replace(self.m,metric='unreviewed'),dataclasses.replace(self.m,index_generation='')):
            with self.assertRaises(Refused):self.a.stage(m)
    def test_unready_target_switch_refused(self):
        self.seed();self.a.freeze(self.a.route());self.a.stage(self.m)
        with self.assertRaises(Refused):self.a.switch(self.a.route(),'semantic768')
    def test_populate_fake_raw_contract_no_identity(self):
        self.ready()
        self.assertTrue(self.fake.calls)
        self.assertEqual(set(self.fake.calls[0]),{'profile','operation','texts'})
        self.assertNotIn(self.a.tenant,json.dumps(self.fake.calls))
        self.assertEqual(self.fake.calls[0]['texts'],['Fabricated cedar library opens nine.'])
    def test_later_fake_batch_failure_no_semantic_store(self):
        self.seed(chunks=['Fabricated chunk '+str(i) for i in range(5)])
        self.a.freeze(self.a.route());self.a.stage(self.m);self.fake.fail_at=2
        with self.assertRaises(Rejected):self.a.populate('semantic768',self.client)
        self.assertEqual(len(self.fake.calls),2);self.assertEqual(self.count('documents','semantic768'),0)
        self.assertEqual(self.count('chunks','semantic768'),0)
    def test_populate_atomic_failure_and_retry_local_fixture(self):
        self.seed();self.a.freeze(self.a.route());self.a.stage(self.m)
        for step in ('document','chunk_vector','before_ready'):
            with self.assertRaises(RuntimeError):self.a.populate('semantic768',self.client,self.boom(step))
            self.assertEqual(self.count('documents','semantic768'),0)
            self.assertEqual(self.h.db.execute('SELECT state FROM namespaces WHERE tenant=? AND name=?',(self.a.tenant,'semantic768')).fetchone()[0],'BUILDING')
        # Explicit local fixture retry, not a production transport retry policy.
        self.a.populate('semantic768',self.client)
    def test_source_changed_during_fake_exchange_refused(self):
        self.seed();self.a.freeze(self.a.route());self.a.stage(self.m)
        def mutate():
            self.a.freeze(self.a.route(),False)
            self.a.write(self.a.route(),'new',['Fabricated late source'],[V3])
            self.a.freeze(self.a.route())
        self.fake.hook=mutate
        with self.assertRaisesRegex(Refused,'source_changed'):self.a.populate('semantic768',self.client)
        self.assertEqual(self.count('documents','semantic768'),0)
    def test_cutover_and_truthful_readpaths(self):
        self.ready();old=self.a.route();new=self.a.switch(old,'semantic768')
        self.assertEqual(new.epoch,old.epoch+1);self.assertEqual(new.manifest.dimension,768)
        result=self.a.search(new,V768)
        self.assertEqual(result['route'].manifest.profile,PROFILE);self.assertEqual(len(result['hits']),1)
        with self.assertRaises(Refused):self.a.search(new,V3)
        with self.assertRaises(Refused):self.a.search(old,V3)
        self.assertEqual(self.count('documents','synthetic3'),1)
    def test_cutover_atomic_failure_keeps_old_tuple(self):
        self.ready();old=self.a.route()
        for step in ('old_inactive','route_updated'):
            with self.assertRaises(RuntimeError):self.a.switch(old,'semantic768',self.boom(step))
            self.assertEqual(self.a.route(),old)
            self.assertEqual(self.h.db.execute("SELECT count(*) FROM namespaces WHERE tenant=? AND state='ACTIVE'",(self.a.tenant,)).fetchone()[0],1)
    def test_unfrozen_switch_refused(self):
        self.ready();self.a.freeze(self.a.route(),False)
        with self.assertRaises(Refused):self.a.switch(self.a.route(),'semantic768')
    def test_rollback_tuple_epoch_and_old_readpath(self):
        self.ready();old=self.a.route();new=self.a.switch(old,'semantic768')
        back=self.a.switch(new,'synthetic3')
        self.assertEqual(back.manifest,self.s);self.assertEqual(back.epoch,3)
        self.assertEqual(len(self.a.search(back,V3)['hits']),1)
        with self.assertRaises(Refused):self.a.search(new,V768)
    def test_rollback_blocks_semantic_only_write(self):
        self.ready();new=self.a.switch(self.a.route(),'semantic768')
        self.a.freeze(new,False);self.a.write(new,'semantic-only',['Fabricated new source'],[V768])
        self.a.freeze(new)
        with self.assertRaisesRegex(Refused,'corpus_mismatch'):self.a.switch(new,'synthetic3')
        self.assertEqual(self.a.route(),new)
        self.assertEqual(self.count('documents','synthetic3'),1)
        self.assertEqual(self.count('documents','semantic768'),2)
    def test_foreign_namespace_cannot_cutover_or_populate(self):
        self.ready();self.b.freeze(self.b.route())
        with self.assertRaises(Refused):self.b.switch(self.b.route(),'semantic768')
        with self.assertRaises(Refused):self.b.populate('semantic768',self.client)
    def test_index_manifest_change_stales_expected_route(self):
        old=self.a.route()
        raw=dataclasses.replace(self.s,index_generation='unexpected-index')
        self.h.db.execute('UPDATE namespaces SET manifest=? WHERE tenant=? AND name=?',(json.dumps(raw.__dict__),self.a.tenant,'synthetic3'))
        with self.assertRaises(Refused):self.a.search(old,V3)
    def test_fake_staging_preserves_protected_namespace_and_other_tenant(self):
        self.seed(self.b);before=list(self.h.db.iterdump())
        b_rows=self.b.search(self.b.route(),V3)
        self.ready();self.a.switch(self.a.route(),'semantic768')
        self.assertEqual(b_rows,self.b.search(self.b.route(),V3))
        self.assertEqual(self.count('documents','synthetic3'),1)
    def test_home_building_or_ready_rejected_before_read(self):
        self.seed()
        for state in ('BUILDING','READY'):
            self.h.db.execute('UPDATE namespaces SET state=? WHERE tenant=? AND name=?',(state,self.a.tenant,'synthetic3'))
            with self.assertRaisesRegex(Refused,'invalid_home_namespace_state'):self.a.route()
        self.h.db.execute("UPDATE namespaces SET state='ACTIVE' WHERE tenant=? AND name=?",(self.a.tenant,'synthetic3'))
    def test_home_manifest_namespace_mismatch_rejected(self):
        old=self.a.route()
        bad=dataclasses.replace(self.s,namespace='absent')
        self.h.db.execute('UPDATE namespaces SET manifest=? WHERE tenant=? AND name=?',(json.dumps(bad.__dict__),self.a.tenant,'synthetic3'))
        with self.assertRaisesRegex(Refused,'invalid_home_manifest_namespace'):self.a.route()
        # A constructed expected tuple must not turn absent namespace into [] hits.
        forged=dataclasses.replace(old,manifest=bad)
        with self.assertRaisesRegex(Refused,'invalid_home_manifest_namespace'):self.a.search(forged,V3)
    def test_home_epoch_strict_positive_integer_rejected(self):
        for epoch in (0,-1,1.5,'not-an-integer'):
            self.h.db.execute('UPDATE routes SET epoch=? WHERE tenant=?',(epoch,self.a.tenant))
            with self.assertRaisesRegex(Refused,'invalid_home_epoch'):self.a.route()
        self.h.db.execute('UPDATE routes SET epoch=1 WHERE tenant=?',(self.a.tenant,))
    def test_home_missing_namespace_row_rejected(self):
        # Corrupt an own disposable fixture only, explicitly bypass its FK.
        self.h.db.execute('PRAGMA foreign_keys=OFF')
        self.h.db.execute('UPDATE routes SET name=? WHERE tenant=?',('absent',self.a.tenant))
        self.h.db.execute('PRAGMA foreign_keys=ON')
        with self.assertRaisesRegex(Refused,'invalid_home_namespace_state'):self.a.route()
    def test_routing_home_survives_local_reconnect(self):
        self.ready();active=self.a.switch(self.a.route(),'semantic768')
        self.h.reopen_local_fixture()
        self.assertEqual(self.a.route(),active)
        self.assertEqual(len(self.a.search(active,V768)['hits']),1)
        self.assertEqual(self.h.db.execute('SELECT frozen FROM routes WHERE tenant=?',(self.a.tenant,)).fetchone()[0],1)
        back=self.a.switch(active,'synthetic3')
        self.h.reopen_local_fixture()
        self.assertEqual(self.a.route(),back)
        self.assertEqual(len(self.a.search(back,V3)['hits']),1)
    def test_corrupt_profile_fails_on_home_read(self):
        bad=dataclasses.replace(self.s,dimension=768)
        self.h.db.execute('UPDATE namespaces SET manifest=? WHERE tenant=? AND name=?',(json.dumps(bad.__dict__),self.a.tenant,'synthetic3'))
        with self.assertRaises(Refused):self.a.route()
    def test_empty_snapshot_refused_without_call(self):
        self.a.freeze(self.a.route());self.a.stage(self.m)
        with self.assertRaises(Refused):self.a.populate('semantic768',self.client)
        self.assertEqual(self.fake.calls,[])

if __name__=='__main__':unittest.main(verbosity=2)
