#!/usr/bin/env python3
"""Small-output Chat bridge to the shared Memory MCP. Full data remains stored."""
import argparse,json,sys,os
from pathlib import Path
from datetime import datetime,timezone
from protocol_client import MCP,ROOT,parse

def main():
 p=argparse.ArgumentParser(description=__doc__)
 sub=p.add_subparsers(dest='op',required=True)
 s=sub.add_parser('search');s.add_argument('query');s.add_argument('--limit',type=int,default=3);s.add_argument('--offset',type=int,default=0)
 g=sub.add_parser('open');g.add_argument('names',nargs='+');g.add_argument('--history',action='store_true');g.add_argument('--relations',action='store_true')
 sub.add_parser('status')
 r=sub.add_parser('remember');r.add_argument('--name',required=True);r.add_argument('--kind',choices=['preference','fact','decision','task'],required=True);r.add_argument('--text',required=True);r.add_argument('--client',default='ChatGPT Chat');r.add_argument('--source',default='user statement');r.add_argument('--supersedes')
 a=p.parse_args();m=MCP(a.client if a.op=='remember' else 'shared-memory-chat-bridge',Path(os.environ.get('MEMORY_FILE_PATH',str(ROOT/'data/memory.jsonl'))))
 try:
  if a.op=='search':
   response=m.call('search_nodes',{'query':a.query,'limit':max(1,min(a.limit,20)),'offset':max(0,a.offset)})
   result=parse(response)
   result['retrieval_notes']=[x['text'] for x in response.get('content',[])[1:] if x.get('type')=='text']
  elif a.op=='open':
   response=m.call('open_nodes',{'names':a.names,'include_history':a.history,'include_relations':a.relations});result=parse(response)
   result['retrieval_notes']=[x['text'] for x in response.get('content',[])[1:] if x.get('type')=='text']
  elif a.op=='status':result={'server':m.hello['serverInfo'],'mode':'compact','tools':[t['name'] for t in m.rpc('tools/list',{})['tools']]}
  else:
   if len(a.text)>16000:raise ValueError('Use concise memory text, at most 16000 characters; split larger supporting material.')
   existing=parse(m.call('open_nodes',{'names':[a.name]}))['entities']
   unchanged=False
   for e in existing:
    for obs in e.get('observations',[]):
     try:old=json.loads(obs)
     except ValueError:continue
     if old.get('text','').strip()==a.text.strip() and old.get('supersedes')==a.supersedes:unchanged=True
   if unchanged:result={'saved':False,'unchanged':True,'name':a.name}
   else:
    observation={'timestamp':datetime.now(timezone.utc).isoformat(),'client':a.client,'text':a.text,'source':a.source}
    if a.supersedes:observation['supersedes']=a.supersedes
    text=json.dumps(observation,ensure_ascii=False,separators=(',',':'))
    if not existing:m.call('create_entities',{'entities':[{'name':a.name,'entityType':a.kind,'observations':[]}]})
    m.call('add_observations',{'observations':[{'entityName':a.name,'contents':[text]}]})
    saved=parse(m.call('open_nodes',{'names':[a.name]}))
    if not any(text in x['observations'] for x in saved['entities']):raise RuntimeError('Write could not be verified')
    result={'saved':True,'name':a.name}
  print(json.dumps(result,ensure_ascii=False,separators=(',',':')))
 finally:m.close()
if __name__=='__main__':
 try:main()
 except Exception as exc:print(json.dumps({'error':str(exc)},ensure_ascii=False),file=sys.stderr);sys.exit(1)
