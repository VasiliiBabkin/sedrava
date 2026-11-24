import hashlib,hmac,json,os,socket,sqlite3
from fastapi import FastAPI,Request
from fastapi.responses import JSONResponse
import uvicorn
db=sqlite3.connect(os.environ["BENCH_SQLITE"])
db.execute("PRAGMA query_only=ON")
digest=os.environ["BENCH_AUTH_SHA"]
app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
queries={
 "products":("SELECT id,title,category,price FROM Products ORDER BY id",[],["id","title","category","price"],"rows"),
 "category":("SELECT id,title,price FROM Products WHERE category=? ORDER BY id",["category"],["id","title","price"],"rows"),
 "paid-summary":("SELECT COUNT(*) AS count_paid,SUM(amount) AS revenue FROM Orders WHERE paid=1",[],["count_paid","revenue"],"aggregate_rows")
}
@app.post("/{route}")
async def route(route:str,request:Request):
    auth=request.headers.get("Authorization","")
    if not auth.startswith("Bearer ") or not hmac.compare_digest(hashlib.sha256(auth[7:].encode()).hexdigest(),digest):
        return JSONResponse({"error":"unauthorized"},401)
    if route not in queries:return JSONResponse({"error":"route"},404)
    sql,names,cols,kind=queries[route]
    try:
        data=await request.json()
        if type(data) is not dict or set(data)!=set(names) or any(type(data[n]) is not str for n in names):raise ValueError()
    except Exception:return JSONResponse({"error":"invalid"},422)
    rows=db.execute(sql,[data[n] for n in names]).fetchall()
    return {"kind":kind,"columns":cols,"rows":rows}
sock=socket.socket()
sock.bind(("127.0.0.1",0));sock.listen(128)
print("LISTENING http://127.0.0.1:"+str(sock.getsockname()[1]),flush=True)
uvicorn.Server(uvicorn.Config(app,host="127.0.0.1",port=0,access_log=False,log_level="error",timeout_keep_alive=1,loop="asyncio",http="h11")).run(sockets=[sock])
