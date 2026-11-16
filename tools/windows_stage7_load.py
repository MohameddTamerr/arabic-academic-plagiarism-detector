# -*- coding: utf-8 -*-
"""Bounded, opt-in six-user staging smoke/load harness. Never starts a server."""
import argparse, concurrent.futures, json, statistics, time
from pathlib import Path
import requests


def percentile(values, p):
    if not values: return None
    values=sorted(values); return values[min(len(values)-1, int((len(values)-1)*p))]


def user_flow(base_url, credential, report_id, iterations):
    session=requests.Session(); timings=[]; failures=[]
    login=session.post(base_url+'/api/auth/login', json=credential, timeout=20)
    if login.status_code != 200: return {'failures':[f'login:{login.status_code}'], 'timings':[]}
    for _ in range(iterations):
        start=time.perf_counter(); response=session.get(f'{base_url}/api/reports/{report_id}/summary', timeout=30)
        timings.append((time.perf_counter()-start)*1000)
        if response.status_code != 200: failures.append(f'report:{response.status_code}')
    return {'timings':timings,'failures':failures}


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--base-url', required=True); parser.add_argument('--report-id', required=True)
    parser.add_argument('--credentials', required=True, type=Path, help='JSON list of exactly six staging accounts')
    parser.add_argument('--iterations',type=int,default=5); parser.add_argument('--output',type=Path,default=Path('stage7b_load_results.json'))
    args=parser.parse_args(); creds=json.loads(args.credentials.read_text(encoding='utf-8'))
    if len(creds)!=6: raise SystemExit('Exactly six isolated staging credentials are required.')
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        results=list(pool.map(lambda c:user_flow(args.base_url.rstrip('/'),c,args.report_id,args.iterations),creds))
    timings=[v for r in results for v in r['timings']]; failures=[v for r in results for v in r['failures']]
    args.output.write_text(json.dumps({'users':6,'requests':len(timings),'failures':failures,'p50_ms':percentile(timings,.5),'p95_ms':percentile(timings,.95),'mean_ms':statistics.mean(timings) if timings else None},indent=2),encoding='utf-8')


if __name__=='__main__': main()
