const express=require('./deps/node_modules/express');
const Database=require('./deps/node_modules/better-sqlite3');
const crypto=require('node:crypto');
const db=new Database(process.env.BENCH_SQLITE,{readonly:true,fileMustExist:true});
const digest=Buffer.from(process.env.BENCH_AUTH_SHA,'hex');
const app=express();app.disable('x-powered-by');
app.use(express.json({limit:'16kb',strict:true}));
const queries={
 'products':['SELECT id,title,category,price FROM Products ORDER BY id',[],['id','title','category','price'],'rows'],
 'category':['SELECT id,title,price FROM Products WHERE category=? ORDER BY id',['category'],['id','title','price'],'rows'],
 'paid-summary':['SELECT COUNT(*) AS count_paid,SUM(amount) AS revenue FROM Orders WHERE paid=1',[],['count_paid','revenue'],'aggregate_rows']
};
app.post('/:route',(req,res)=>{
 const auth=req.get('authorization')||'';
 if(!auth.startsWith('Bearer ')||!crypto.timingSafeEqual(crypto.createHash('sha256').update(auth.slice(7)).digest(),digest))return res.status(401).json({error:'unauthorized'});
 if(!Object.hasOwn(queries,req.params.route))return res.status(404).json({error:'route'});
 const [sql,names,cols,kind]=queries[req.params.route];
 const data=req.body;
 if(!data||typeof data!=='object'||Array.isArray(data)||Object.keys(data).length!==names.length||names.some(n=>typeof data[n]!=='string'))return res.status(422).json({error:'invalid'});
 const rows=db.prepare(sql).raw().all(...names.map(n=>data[n]));
 res.json({kind,columns:cols,rows});
});
const server=app.listen(0,'127.0.0.1',()=>console.log('LISTENING http://127.0.0.1:'+server.address().port));
