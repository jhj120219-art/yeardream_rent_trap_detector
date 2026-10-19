"""기존 collect_rent.py로 수집한 전체 원본 CSV를 정제·검증 후 원자적으로 교체한다.
실행: python -m backend.scripts.import_data --raw data/rent_raw.csv
증분 병합 대신 전체 스냅샷 교체: 정정 반영/재실행 중복 방지. 의심 중복은 기존 clean() 정책대로 보존.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import pandas as pd
import compare_rent
from backend.app.analysis_service import load_pool
from backend.app.config import Settings


def import_raw(raw, target):
    frame=pd.read_csv(raw,dtype=str)
    cleaned,report=compare_rent.clean(frame)
    target.parent.mkdir(parents=True,exist_ok=True)
    tmp=None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',suffix='.csv',dir=target.parent,delete=False) as out:
            tmp=Path(out.name)
            cleaned.to_csv(out,index=False)
        load_pool(tmp)  # 검증 실패 시 기존 정상 스냅샷을 교체하지 않는다.
        sha=hashlib.sha256(tmp.read_bytes()).hexdigest()
        os.replace(tmp,target)
    finally:
        if tmp is not None:
            tmp.unlink(missing_ok=True)
    return {'rows':len(cleaned),'sha256':sha,'cleaning_report':report}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw',type=Path,required=True)
    parser.add_argument('--out',type=Path,default=Settings().clean_csv)
    args=parser.parse_args()
    print(json.dumps(import_raw(args.raw,args.out),ensure_ascii=False,indent=2))
