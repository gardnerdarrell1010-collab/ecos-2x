"""Portable governed-operation client: one connection, bounded reconnect, no secrets/logging.

The caller supplies an authenticated least-privilege connection factory and request
context. This does not perform interpretation, provider effects, or scheduling.
"""
import json,time
import psycopg
from psycopg.types.json import Jsonb

class GovernedClient:
    def __init__(self,connect,sleep=time.sleep,reconnect_delays=(0.25,1.0)):
        self.connect=connect;self.sleep=sleep;self.delays=reconnect_delays;self.db=None
        self.metrics={'calls':0,'connections_opened':0,'reconnects':0,'response_bytes':0,'query_ms':0.0}
    def close(self):
        if self.db is not None:self.db.close();self.db=None
    def operate(self,operation,request):
        # Reuse the SAME idempotency key after an ambiguous connection failure.
        assert request['context']['idempotency_key']
        for attempt in range(len(self.delays)+1):
            start=time.monotonic()
            try:
                if self.db is None:
                    self.db=self.connect();self.metrics['connections_opened']+=1
                with self.db.transaction():
                    result=self.db.execute('select ecos.operate(%s,%s)',(operation,Jsonb(request))).fetchone()[0]
                self.metrics['calls']+=1;self.metrics['response_bytes']+=len(json.dumps(result,default=str).encode())
                self.metrics['query_ms']+=(time.monotonic()-start)*1000
                return result
            except psycopg.OperationalError:
                self.close()
                if attempt==len(self.delays):raise
                self.metrics['reconnects']+=1;self.sleep(self.delays[attempt])
        raise AssertionError('unreachable')
