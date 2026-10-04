"""Repeat a real YouTube goal. Caches may be used; these are not forced cold/uncached runs."""
import argparse
import json
import time
import uuid
from pathlib import Path
import httpx

root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--warm',type=int,default=5);p.add_argument('--output',default='docs/youtube-performance-runs.json');args=p.parse_args()
client=httpx.Client(base_url='http://127.0.0.1:8000',timeout=30,trust_env=False)
health=client.get('/api/health').json()
if not health.get('ready'):raise SystemExit(health)
rows=[]
for i in range(args.warm+2):
    kind='first_run' if i==0 else 'repeat'
    body={'goal':'Explain database indexes: compare an index lookup with a table scan, then give a SQL lookup example.','prior_knowledge':'I know basic SQL.','time_budget_seconds':300,'request_id':str(uuid.uuid4())}
    accepted_start=time.monotonic();response=client.post('/api/lessons',json=body);response.raise_for_status();lesson=response.json();accepted=time.monotonic()-accepted_start
    print(f'{kind} {i}: accepted {lesson["id"]} in {accepted:.3f}s',flush=True)
    lid=lesson['id'];seen=set();deadline=time.monotonic()+900
    while time.monotonic()<deadline:
        lesson=client.get(f'/api/lessons/{lid}').json()
        for short in lesson['shorts']:
            if short['status']=='ready' and short['id'] not in seen:
                seen.add(short['id']);print(f'  short {len(seen)} ready: {short["timings"]}',flush=True)
        if lesson['job']['status'] in {'complete','failed','cancelled','interrupted'}:break
        time.sleep(.25)
    else:
        client.post(f'/api/lessons/{lid}/cancel',json={});raise SystemExit('Benchmark timed out.')
    row={'kind':kind,'lesson_id':lid,'sources':[{'video_id':s['video_id'],'url':s['url'],'source_type':s['source_type']} for s in lesson['sources']],'accepted_seconds':accepted,'terminal_seconds':lesson['job']['updated_at']-lesson['job']['created_at'],'status':lesson['job']['status'],'metrics':lesson['metrics'],'stage_timings':lesson['job']['stage_timings'],'settings':lesson['provider_settings'],'shorts':[{'template':s['scenes'][0]['template'] if s['scenes'] else None,'status':s['status'],'duration_ms':s['measured_duration_ms'],'cache_hit':s['cache_hit'],'timings':s['timings']} for s in lesson['shorts']],'error':lesson['job']['error'],'planned_duration_ms':lesson['planned_duration_ms']}
    rows.append(row)
    output=root/args.output;output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps({'health':health,'runs':rows},indent=2)+'\n')
    (root/'.data'/f'youtube-benchmark-{i}.json').write_text(json.dumps(lesson,indent=2))
    print(f'  {row["status"]}: {row["metrics"]} {row["error"]}',flush=True)
print('Measurements saved:',output)
