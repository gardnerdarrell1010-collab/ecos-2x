import test from 'node:test';
import assert from 'node:assert/strict';
import {boundRequest, authorizedClaims, databaseLoginAllowed} from './online_transport_core.mjs';
const identity = {principal:'p',instance:'i',subject:'s',client:'c'};
const request = {schema_version:'1.0.0',context:{principal_id:'p',executor_instance_id:'i'},arguments:{}};
test('retains exact governed request and fence without mutating caller',()=>{
  const value = {...request,arguments:{fence:{claim_id:'claim',claim_version:7}}};
  assert.deepEqual(boundRequest('work.complete',value,identity),value);
  assert.notEqual(boundRequest('work.complete',value,identity),value);
});
test('rejects SQL and operations beyond transport ceiling',()=>{
  for(const op of ['execute_sql','select 1','principal.grant','authority.transfer'])
    assert.throws(()=>boundRequest(op,request,identity),/operation_not_allowed/);
});
test('rejects another principal or executor before database invocation',()=>{
  for(const context of [{principal_id:'other',executor_instance_id:'i'},{principal_id:'p',executor_instance_id:'other'}])
    assert.throws(()=>boundRequest('work.next',{...request,context},identity),/identity_mismatch/);
});
test('requires both immutable OAuth subject and registered client',()=>{
  const claims={sub:'s',client_id:'c',role:'authenticated',exp:1};
  assert.equal(authorizedClaims(claims,identity),true);
  for(const patch of [{sub:'other'},{client_id:'other'},{role:'service_role'}])
    assert.equal(authorizedClaims({...claims,...patch},identity),false);
});
test('refuses administrator database credentials',()=>{
  assert.equal(databaseLoginAllowed('postgresql://postgres@invalid/db'),false);
  assert.equal(databaseLoginAllowed('postgresql://online2x_synthetic@invalid/db'),true);
});
