import subprocess,json,threading,queue,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
ENTRY=str(ROOT/'node_modules/@modelcontextprotocol/server-memory/dist/index.js')
class MCP:
 def __init__(self,label,path,raw=False):
  self.p=subprocess.Popen((['node',ENTRY] if raw else [sys.executable,str(ROOT/'memory_gateway.py')]),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env={**os.environ,'MEMORY_FILE_PATH':str(path)})
  self.q=queue.Queue(); self.seq=0; self.label=label
  threading.Thread(target=self.read,daemon=True).start()
  hello=self.rpc('initialize',{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':label,'version':'1.0'}})
  self.p.stdin.write(json.dumps({'jsonrpc':'2.0','method':'notifications/initialized'})+'\n');self.p.stdin.flush()
  self.hello=hello
 def read(self):
  for l in self.p.stdout:
   try:self.q.put(json.loads(l))
   except Exception:pass
 def rpc(self,method,params):
  self.seq+=1; n=self.seq
  self.p.stdin.write(json.dumps({'jsonrpc':'2.0','id':n,'method':method,'params':params})+'\n'); self.p.stdin.flush()
  while True:
   r=self.q.get(timeout=95)
   if r.get('id')==n:
    if 'error' in r: raise RuntimeError(r['error'])
    if r.get('result',{}).get('isError'):raise RuntimeError(r['result'])
    return r['result']
 def call(self,name,args):return self.rpc('tools/call',{'name':name,'arguments':args})
 def close(self):
  self.p.stdin.close()
  try:self.p.wait(timeout=5)
  except subprocess.TimeoutExpired:self.p.terminate();self.p.wait(timeout=5)
def parse(r):
 if 'structuredContent' in r:return r['structuredContent']
 return json.loads(r['content'][0]['text'])
