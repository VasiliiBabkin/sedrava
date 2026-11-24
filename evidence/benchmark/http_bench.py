import os,sys,json,sqlite3,subprocess,time,statistics,hashlib,secrets,selectors,concurrent.futures,random,http.client,urllib.parse
from pathlib import Path
H=Path(__file__).resolve().parent;R=Path.home()/'.sedrava-dev/sedrava'
NATIVE=Path(sys.argv[1]);DB=Path(sys.argv[2])
BASE=H/'http-fixtures';BASE.mkdir(mode=0o700,exist_ok=True)
cpus=sorted(os.sched_getaffinity(0))
server_cpu=cpus[0];client_cpu=cpus[-1]
os.sched_setaffinity(0,{client_cpu})
auth_token=secrets.token_hex(32);digest=hashlib.sha256(auth_token.encode()).hexdigest()
auth=BASE/'auth.json';auth.write_text(json.dumps([{"id":"bench","sha256":digest,"role":"write"}]));auth.chmod(0o600)
def run(*a):return json.loads(subprocess.check_output([str(x) for x in a],text=True,stderr=subprocess.PIPE,timeout=20))
def init_native(p,seed=True):
    run(DB,"init",p)
    for i,q in enumerate((R/'examples/sales_demo/schema.sql').read_text().splitlines()):run(DB,'sql',p,q,f"benchmark-schema-{i:04}")
    if seed:
      for i in range(64):
        q=f"INSERT INTO Products (id,title,category,price) VALUES ('p{i:03}','Product {i}','c{i%8}',{i+1})"
        run(DB,'sql',p,q,f"benchmark-prod-{i:04}")
        q=f"INSERT INTO Orders (id,product_id,amount,paid) VALUES ('o{i:03}','p{i:03}',{i+1},{'true' if i%2==0 else 'false'})"
        run(DB,'sql',p,q,f"benchmark-order-{i:04}")
def fixture_sqlite(p):
    with sqlite3.connect(p) as c:
        c.executescript("CREATE TABLE Products(id TEXT PRIMARY KEY,title TEXT,category TEXT,price INT);CREATE TABLE Orders(id TEXT PRIMARY KEY,product_id TEXT REFERENCES Products(id),amount INT,paid BOOL);CREATE INDEX products_category ON Products(category);CREATE INDEX orders_paid ON Orders(paid);")
        c.executemany("INSERT INTO Products VALUES (?,?,?,?)",[(f'p{i:03}',f'Product {i}',f'c{i%8}',i+1) for i in range(64)])
        c.executemany("INSERT INTO Orders VALUES (?,?,?,?)",[(f'o{i:03}',f'p{i:03}',i+1,int(i%2==0)) for i in range(64)])
def start(kind,p,n):
    env={**os.environ,'BENCH_SQLITE':str(p),'BENCH_AUTH_SHA':digest}
    if kind=='sedrava':
        a=[NATIVE,'database-api','run',R/'examples/sales_demo/sales_api.sdr','--database',p,'--trusted','--allow-write','--auth-file',auth,'--max-requests',str(n),'--idle-ms','15000']
    elif kind=='fastapi':a=[H/'venv/bin/python',H/'fastapi_server.py']
    else:a=['node',H/'express_server.js']
    log=(BASE/f'{kind}.log').open('a')
    proc=subprocess.Popen(['taskset','-c',str(server_cpu),*map(str,a)],stdout=subprocess.PIPE,stderr=log,text=True,env=env,cwd=H)
    log.close()
    try:
      with selectors.DefaultSelector() as sel:
        sel.register(proc.stdout,selectors.EVENT_READ);assert sel.select(15),(kind,'startup timeout')
        line=proc.stdout.readline().strip()
      assert line.startswith("LISTENING http://127.0.0.1:"),(kind,line,proc.poll())
      return proc,int(line.rsplit(':',1)[1])
    except:
      proc.kill();proc.wait();raise
def finish(proc,kind):
    if kind=='sedrava':
      assert proc.wait(timeout=20)==0
    else:
      proc.terminate();proc.wait(timeout=10)
    proc.stdout.close()
def req(port,path,body,key=None):
    data=json.dumps(body,separators=(',',':')).encode()
    headers={'Content-Type':'application/json','Authorization':'Bearer '+auth_token,'Connection':'close'}
    if key:headers['Idempotency-Key']=key
    c=http.client.HTTPConnection('127.0.0.1',port,timeout=10)
    t=time.perf_counter_ns()
    try:
      c.request('POST',path,body=data,headers=headers)
      r=c.getresponse();v=json.loads(r.read());elapsed=(time.perf_counter_ns()-t)/1e6
      return r.status,v,elapsed
    finally:c.close()
def stat(a,elapsed):
    a=sorted(a);n=len(a);return {"requests":n,"median_ms":statistics.median(a),"p95_ms":a[(n*95+99)//100-1],"p99_ms":a[(n*99+99)//100-1],"rps":n/elapsed,"errors":0,"samples_ms":a}
def expected(i):
    if i%3==0:return '/products',{},{"kind":"rows","columns":["id","title","category","price"],"rows":[[f'p{j:03}',f'Product {j}',f'c{j%8}',j+1] for j in range(64)]}
    if i%3==1:
        k=i%8;return '/category',{'category':f'c{k}'},{"kind":"rows","columns":["id","title","price"],"rows":[[f'p{j:03}',f'Product {j}',j+1] for j in range(k,64,8)]}
    return '/paid-summary',{},{"kind":"aggregate_rows","columns":["count_paid","revenue"],"rows":[[32,1024]]}
if sys.argv[3]=='read':
    nfile=BASE/'read.log';sfile=BASE/'read.sqlite'
    init_native(nfile);fixture_sqlite(sfile)
    result=[];kinds=['sedrava','fastapi','express']
    for c in (1,4,8):
      for round in range(2):
        for kind in kinds[round:]+kinds[:round]:
          p,port=start(kind,nfile if kind=='sedrava' else sfile,210)
          try:
            def one(i):
              path,body,want=expected(i);status,out,dt=req(port,path,body)
              assert status==200 and out==want,(kind,path,status,out,want)
              return dt
            for i in range(10):one(i)
            t=time.perf_counter()
            with concurrent.futures.ThreadPoolExecutor(max_workers=c) as ex:lat=list(ex.map(one,range(200)))
            value=stat(lat,time.perf_counter()-t)
            result.append({"engine":kind,"concurrency":c,"round":round,**value})
            print(kind,c,round,{k:v for k,v in value.items() if k!='samples_ms'},flush=True)
            finish(p,kind)
          finally:
            if p.poll() is None:p.kill();p.wait()
    (H/'http.json').write_text(json.dumps({"results":result,"workload":"authenticated POST JSON read API, same SQL results, 64 products/orders; new TCP connection per call; 2 rounds, 200 measured requests each; 1 worker each; client/server pinned to different VDS CPUs; SQLite baselines do not match full native HTTP validation","server_cpu":server_cpu,"client_cpu":client_cpu},indent=2))
else:
    result=[]
    for concurrency in (1,4,8):
      db=BASE/f'full-{concurrency}.log';init_native(db,False)
      # Each independent user creates product/order, corrects, marks paid.
      users=40;total=users*3
      p,port=start('sedrava',db,total+3)
      try:
        def flow(i):
            ident=f'p{i:03}';order=f'o{i:03}';start_t=time.perf_counter_ns();lat=[]
            status,a,t=req(port,'/new-product-order',{'product_id':ident,'title':f'Product {i}','category':f'c{i%8}','price':i+1,'order_id':order,'amount':100},f'full-create-{i:06}')
            assert status==200 and a['affected']==2 and not a['replayed'],(i,status,a);lat.append(t)
            status,b,t=req(port,'/correct-order',{'id':order,'old_amount':100,'new_amount':150},f'full-correct-{i:06}')
            assert status==200 and [x['rows'] for x in b['reads']]==[[[100,False]],[[150,False]]],(i,status,b);lat.append(t)
            status,d,t=req(port,'/mark-paid',{'id':order},f'full-pay-{i:06}')
            assert status==200 and d['affected']==1,(i,status,d);lat.append(t)
            return lat,(time.perf_counter_ns()-start_t)/1e6
        t=time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as ex:flows=list(ex.map(flow,range(users)))
        elapsed=time.perf_counter()-t
        status,summary,_=req(port,'/paid-summary',{});assert status==200 and summary['rows']==[[users,users*150]],summary
        status,orders,_=req(port,'/orders',{});assert status==200 and len(orders['rows'])==users and all(row[2:]==[150,True] for row in orders['rows'])
        status,replay,_=req(port,'/mark-paid',{'id':'o000'},'full-pay-000000');assert status==200 and replay['replayed']
        finish(p,'sedrava');run(DB,'verify',db)
        v=stat([x for a,_ in flows for x in a],elapsed)
        result.append({"concurrency":concurrency,"users":users,"flows_per_second":users/elapsed,"flow_latency":stat([x for _,x in flows],elapsed),"http":v,"verified_final_revenue":users*150,"journal_bytes":db.stat().st_size})
        print('full',concurrency,{k:v for k,v in v.items() if k!='samples_ms'},'users/s',users/elapsed,flush=True)
      finally:
        if p.poll() is None:p.kill();p.wait()
    (H/'full.json').write_text(json.dumps({"results":result,"workload":"actual authenticated Sedrava HTTP + SedravaSQL journal: create product and order atomically, sequential correction and payment status, validate final aggregate and replay; synthetic Python client, no generated UI or external network"},indent=2))
