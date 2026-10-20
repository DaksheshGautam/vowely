"""Opt-in local Qwen style check; no microphone, typing, downloads or live profile.

Uses synthetic cases from tests/fixtures. The report contains only case IDs,
timings and checks; --show-output explicitly prints the generated sample text.
This checks cleanup behavior, not acoustic recognition or universal accuracy.
"""
import argparse
import json
from pathlib import Path
import re
import threading
import time

from localflow.config import Config
from localflow.engines import cleanup_insertion_ready
from localflow.formatting import PreservedCleanupNotice,has_layout_cues
from localflow.natural_layout import Passage,literal_pattern
from localflow.resident import ResidentModels
from localflow.version import RELEASE_VERSION


def run(root,gpu=False,show_output=False,case_ids=()):
    project=Path(__file__).resolve().parents[1]
    cases=json.loads((project/'tests/fixtures/dictation_style.json').read_text(encoding='utf-8'))
    if case_ids:
        unknown=set(case_ids)-{case['id'] for case in cases}
        if unknown:raise ValueError('Unknown case: '+', '.join(sorted(unknown)))
        cases=[case for case in cases if case['id'] in case_ids]
    config=Config(cleanup_enabled=True,mode='Natural',threads=4,cleanup_gpu=gpu)
    runtime=ResidentModels(config,root)
    report={'version':RELEASE_VERSION,'model':Path(config.cleanup_model).name,
            'microphone_opened':False,'keys_injected':False,'downloads':False,'cases':[]}
    try:
        start=time.monotonic();runtime._start_one('qwen',gpu)
        report['load_seconds']=round(time.monotonic()-start,2)
        report['gpu_confirmed']=runtime.qwen.gpu_confirmed
        for case in cases:
            start=time.monotonic()
            text,warning=runtime.clean(Passage(case['raw']),config,threading.Event())
            checks={
                'bullet_count':len(re.findall(r'(?m)^\s*[-*•] ',text))==case['bullets'],
                'numbered_count':len(re.findall(r'(?m)^\s*\d+[.)] ',text))==case['numbered'],
                'retained_details':all(re.search(literal_pattern(p),text,re.I) for p in case['must_keep']),
                'removed_commands':not has_layout_cues(text),
                'validated_for_insertion':cleanup_insertion_ready(case['raw'],text,warning,config),
            }
            if phrase:=case.get('deduplicate'):
                checks['removed_duplicate']=len(re.findall(literal_pattern(phrase),text,re.I))==1
                checks['resolved_explicit_restart']='no, i mean' not in text.casefold()
            row={'id':case['id'],'seconds':round(time.monotonic()-start,2),
                 'source_fallback':isinstance(warning,PreservedCleanupNotice),
                 'checks':checks,'passed':all(checks.values())}
            report['cases'].append(row)
            # Console pipes on Windows may use cp1252; JSON escapes stay valid
            # for currencies and non-Latin source text on every console locale.
            print(json.dumps({**row,**({'text':text} if show_output else {})}),flush=True)
    finally:
        runtime.close()
        report['workers_stopped']=not runtime.qwen or not runtime.qwen.proc or runtime.qwen.proc.poll() is not None
    report['passed']=all(row['passed'] for row in report['cases']) and len(report['cases'])==len(cases) and report['workers_stopped']
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=Path.cwd(),help='Existing local models/engines directory')
    parser.add_argument('--gpu',action='store_true')
    parser.add_argument('--show-output',action='store_true')
    parser.add_argument('--case',action='append',default=[],help='Run only this fixture ID; may be repeated')
    parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    report=run(args.root.resolve(),args.gpu,args.show_output,args.case)
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:value for key,value in report.items() if key!='cases'}),flush=True)
    raise SystemExit(0 if report['passed'] else 1)
