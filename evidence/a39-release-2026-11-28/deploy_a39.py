"""Deploy the prepared language site and immutable versioned download directory."""
import hashlib,json,os,pwd,shutil,stat,tempfile,urllib.request
from pathlib import Path
HOME=Path("/var/www/popizdim_tf7_usr/data/.sedrava-dev")
SRC=HOME/"a39-site/dist"
PUB=HOME/"a39-dist/publish"
WEB=Path("/var/www/virtreal_ru_usr27/data/www/virtreal.ru/sedrava")
DEST=WEB/"downloads/0.12.0-alpha.4"
OWNER=pwd.getpwnam("virtreal_ru_usr27")
SHA="984350bb3fc55a34a4a6a874ea1842dc8c63f9e253002f11172c374f195016b5"
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def safe_dir(p):
 m=p.lstat();assert stat.S_ISDIR(m.st_mode) and m.st_uid==OWNER.pw_uid,p
def fetch(url):
 with urllib.request.urlopen(url,timeout=25) as f:
  assert f.status==200
  return hashlib.sha256(f.read()).hexdigest()
def snapshot(root):
 out={}
 for p in root.rglob("*"):
  assert not p.is_symlink(),p
  if p.is_file():out[str(p.relative_to(root))]=sha(p)
 return out
def main():
 assert os.geteuid()==0
 safe_dir(WEB);safe_dir(WEB/"downloads")
 assert not DEST.exists() and not DEST.is_symlink(),"new version already exists"
 old=snapshot(WEB/"downloads")
 assert old and "0.12.0-alpha.3/index.html" in old
 files=snapshot(PUB);assert len(files)==9
 archive=next(n for n in files if n.endswith(".tar.gz"));assert files[archive]==SHA
 for line in (PUB/"SHA256SUMS").read_text().splitlines():
  h,n=line.split("  ",1);assert files[n]==h
 source=snapshot(SRC)
 assert 20<len(source)<1000 and not any(n.startswith("downloads/") for n in source)
 assert all((SRC/n).stat().st_size<32*1024*1024 for n in source)
 # Backup only replaced site files; no unrelated sites or previous downloads.
 base=WEB.parent.parent.parent/".sedrava-a29-backups"
 assert base.is_dir() and not base.is_symlink() and base.stat().st_uid==0
 backup=Path(tempfile.mkdtemp(prefix="a39-",dir=base))
 records=[];installed=False
 def ensure_parent(dest):
  for d in reversed(dest.parents):
   if d==WEB or WEB in d.parents:
    if not d.exists():d.mkdir();os.chown(d,OWNER.pw_uid,OWNER.pw_gid);d.chmod(0o755)
    safe_dir(d)
 def install(source,dest):
  ensure_parent(dest)
  fd,tmp=tempfile.mkstemp(prefix=".a39-",dir=dest.parent)
  try:
   with os.fdopen(fd,"wb") as f:f.write(source.read_bytes());f.flush();os.fsync(f.fileno())
   os.chown(tmp,OWNER.pw_uid,OWNER.pw_gid);os.chmod(tmp,0o644)
   assert sha(Path(tmp))==sha(source)
   os.replace(tmp,dest)
  finally:
   if os.path.exists(tmp):os.unlink(tmp)
 try:
  stage=Path(tempfile.mkdtemp(prefix=".a39-download-",dir=DEST.parent))
  for name,h in files.items():
   dst=stage/name;shutil.copyfile(PUB/name,dst);os.chown(dst,OWNER.pw_uid,OWNER.pw_gid);dst.chmod(0o644);assert sha(dst)==h
  os.chown(stage,OWNER.pw_uid,OWNER.pw_gid);stage.chmod(0o755)
  assert not DEST.exists()
  stage.rename(DEST);installed=True
  for name in sorted(source,key=lambda n:(Path(n).suffix in (".html",".json",".xml"),n)):
   p=WEB/name
   if p.exists() or p.is_symlink():
    m=p.lstat();assert stat.S_ISREG(m.st_mode) and m.st_uid==OWNER.pw_uid,p
    b=backup/name;b.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,b);assert sha(p)==sha(b)
   else:b=None
   install(SRC/name,p);records.append((p,b))
  for n,h in old.items():assert sha(WEB/"downloads"/n)==h
  for n,h in files.items():
   assert fetch("https://sedrava.virtreal.ru/downloads/0.12.0-alpha.4/"+n)==h,n
  for route in ("","ru/","getting-started/","ru/getting-started/","platform/","ru/platform/","releases/","ru/releases/"):
   assert fetch("https://sedrava.virtreal.ru/"+route)==source[route+"index.html"],route
  print("PASS deploy",len(source),"site files;",len(files),"download files via HTTPS;",len(old),"old download files preserved; backup",backup)
 except BaseException:
  for dest,b in reversed(records):
   if b is None:dest.unlink()
   else:install(b,dest)
  # Only remove this just-created version directory if all original bytes are present.
  if installed and snapshot(DEST)==files:shutil.rmtree(DEST)
  raise
if __name__=="__main__":main()
