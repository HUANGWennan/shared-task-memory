#!/usr/bin/env python3
"""Compact MCP views over the unchanged official persistent memory server.
All writes pass through unchanged. Full history and relations are opt-in reads.
"""
import json,os,subprocess,sys,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parent
UPSTREAM=ROOT/'node_modules/@modelcontextprotocol/server-memory/dist/index.js'
VISIBLE={'search_nodes','open_nodes','create_entities','add_observations','delete_entities','delete_observations'}
DESCRIPTIONS={
 'search_nodes':'Find related memories. Returns up to 3 short previews; open selected names for full content. Use offset to see more matches.',
 'open_nodes':'Read named memories in full. Tasks return the newest checkpoint; include_history=true retrieves all prior checkpoints. Relations are opt-in.',
 'create_entities':'Create new named memories; existing names are skipped. Use add_observations to update.',
 'add_observations':'Append concise new facts or complete task checkpoints to existing memories; skip unchanged state.',
 'delete_entities':'Delete named memories only when the user requests forgetting them.',
 'delete_observations':'Delete specified observations only when the user requests forgetting/correcting them.'}

def bounded(value,default,maximum):
 try:return max(1,min(int(value),maximum))
 except (TypeError,ValueError):return default

def decoded(raw):
 try:return json.loads(raw)
 except (TypeError,ValueError):return {'text':raw}

def newest(observations):
 # ISO timestamps with offsets may differ; compare the actual times, not strings.
 from datetime import datetime,timezone
 def key(pair):
  i,text=pair;v=decoded(text);s=v.get('timestamp','')
  try:
   t=datetime.fromisoformat(s.replace('Z','+00:00'))
   if t.tzinfo is None:t=t.replace(tzinfo=timezone.utc)
   return (t.timestamp(),i)
  except (ValueError,TypeError,AttributeError):return (0,i)
 return max(enumerate(observations),key=key)[1] if observations else None

def preview(entity,query):
 obs=entity.get('observations',[])
 # Prefer an observation actually containing the query, then its newest match.
 matching=[s for s in obs if query.lower() in s.lower()] if query else obs
 raw=newest(matching or obs) or '{}';v=decoded(raw)
 text=v.get('text')
 if not isinstance(text,str):text=json.dumps(v,ensure_ascii=False,separators=(',',':'))
 pos=text.lower().find(query.lower()) if query else 0;start=max(0,pos-80)
 snippet=text[start:start+420]
 record={'preview':snippet,'open_for_full_content':True,'observation_count':len(obs)}
 for k in ['timestamp','source_updated_at','source']:
  if k in v:record[k]=v[k]
 return {'name':entity['name'],'entityType':entity.get('entityType','memory'),'observations':[json.dumps(record,ensure_ascii=False,separators=(',',':'))]}

def compact_result(result,context):
 if result.get('isError'):return result
 graph=result.get('structuredContent')
 if not isinstance(graph,dict):
  try:graph=json.loads(next(x['text'] for x in result.get('content',[]) if x.get('type')=='text'))
  except (ValueError,KeyError,StopIteration):return result
 if 'entities' not in graph or 'relations' not in graph:return result
 entities=graph['entities'];notes=[];args=context['args']
 if context['name']=='search_nodes' and not args.get('full_results'):
  query=str(args.get('query',''));total=len(entities)
  def rank(e):
   name=e['name'];lower=name.lower();q=query.lower()
   return (not (q and q in lower),not name.startswith(('preference:','fact:','decision:','task:')),name.startswith('memory-document:'),name)
  entities=sorted(entities,key=rank)
  limit=bounded(args.get('limit'),3,20)
  try:offset=max(0,int(args.get('offset',0)))
  except (TypeError,ValueError):offset=0
  entities=[preview(e,query) for e in entities[offset:offset+limit]]
  notes.append(f'{total} matches; showing {offset+1 if entities else 0}-{offset+len(entities)}. Open selected names for full text; use offset/limit for more.')
 elif context['name']=='open_nodes' and not args.get('include_history'):
  compact=[]
  for e in entities:
   obs=e.get('observations',[])
   if e.get('entityType')=='task' and len(obs)>1:
    compact.append({**e,'observations':[newest(obs)]})
    notes.append(f"{e['name']}: newest of {len(obs)} checkpoints; full history remains stored. Use include_history=true for earlier decisions, constraints, or audit.")
   else:compact.append(e)
  entities=compact
 graph={**graph,'entities':entities,'relations':graph['relations'] if args.get('include_relations') else []}
 # Keep the standard output shape and full entity text on explicit open calls.
 out={**result,'structuredContent':graph,'content':[{'type':'text','text':json.dumps(graph,ensure_ascii=False,separators=(',',':'))}]}
 if notes:out['content'].append({'type':'text','text':' '.join(notes)})
 return out

def schema_add(tool,name,spec):
 tool.setdefault('inputSchema',{}).setdefault('properties',{})[name]=spec

def rewrite_response(message,context):
 result=message.get('result')
 if not isinstance(result,dict):return message
 if context['method']=='initialize':
  result['instructions']='Shared memory: retrieve relevant context once per new/resumed task, reuse it within the conversation. Search returns previews; open selected nodes. Save only new important preferences/corrections and meaningful task milestones/end state, not every turn. Never load the full graph routinely. Full historical text is preserved; request include_history=true for older task constraints.'
 elif context['method']=='tools/list':
  result['tools']=[t for t in result.get('tools',[]) if t['name'] in VISIBLE]
  for t in result['tools']:
   n=t['name'];t['description']=DESCRIPTIONS[n]
   if n=='search_nodes':
    for k,s in {'limit':{'type':'integer','minimum':1,'maximum':20,'default':3},'offset':{'type':'integer','minimum':0,'default':0},'full_results':{'type':'boolean','default':False},'include_relations':{'type':'boolean','default':False}}.items():schema_add(t,k,s)
   if n=='open_nodes':
    for k in ['include_history','include_relations']:schema_add(t,k,{'type':'boolean','default':False})
 elif context['method']=='tools/call' and context.get('name') in ['search_nodes','open_nodes']:
  message['result']=compact_result(result,context)
 return message

def main():
 child=subprocess.Popen(['node',str(UPSTREAM)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=sys.stderr,text=True,bufsize=1,env=os.environ.copy())
 pending={};lock=threading.Lock();output_lock=threading.Lock()
 def pump():
  for line in child.stdout:
   try:
    message=json.loads(line);key=json.dumps(message.get('id'),sort_keys=True)
    with lock:context=pending.pop(key,None) if 'id' in message else None
    if context:message=rewrite_response(message,context)
    out=json.dumps(message,ensure_ascii=False,separators=(',',':'))+'\n'
   except Exception as exc:
    print('Memory gateway response passthrough:',type(exc).__name__,file=sys.stderr);out=line
   with output_lock:sys.stdout.write(out);sys.stdout.flush()
 thread=threading.Thread(target=pump,daemon=True);thread.start()
 try:
  for line in sys.stdin:
   try:
    request=json.loads(line);method=request.get('method');context={'method':method}
    if method=='tools/call':
     params=request.get('params',{});args=dict(params.get('arguments') or {})
     context.update(name=params.get('name'),args=args)
     extras={'search_nodes':['limit','offset','full_results','include_relations'],'open_nodes':['include_history','include_relations']}.get(params.get('name'),[])
     for k in extras:request['params']['arguments'].pop(k,None)
    if 'id' in request:
     with lock:pending[json.dumps(request['id'],sort_keys=True)]=context
    line=json.dumps(request,ensure_ascii=False,separators=(',',':'))+'\n'
   except Exception:pass
   child.stdin.write(line);child.stdin.flush()
 finally:
  try:child.stdin.close();child.wait(timeout=5)
  except (BrokenPipeError,subprocess.TimeoutExpired):child.terminate();child.wait(timeout=5)
  thread.join(timeout=2)
if __name__=='__main__':main()
