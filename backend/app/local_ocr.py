"""Local two-engine OCR bridge. Images are temporary; all values require review."""
import asyncio
import contextlib
import importlib.util
import importlib
import inspect
from io import BytesIO
import json
import subprocess
import sys
import tempfile
import warnings
import threading
from pathlib import Path
from PIL import Image, UnidentifiedImageError
from fastapi import HTTPException
from .card_consensus import extraction_result, CardConsensusRequest, run as combine_cards

ROOT = Path(__file__).resolve().parents[2]
_lock = threading.BoundedSemaphore(1)

def selectable(card):
    return card.get('status') == 'extracted' and card.get('fields', {}).get('contract_type', {}).get('value') == '월세'

def choose_card(result, index):
    cards = result.get('ocr_cards', [])
    if index < 0 or index >= len(cards) or not selectable(cards[index]):
        raise HTTPException(422, '두 엔진이 일치하게 읽은 월세 매물을 선택해 주세요.')
    draft = extraction_result(cards[index])
    draft['source_type'] = 'LOCAL_OCR_CONSENSUS'
    draft['review_messages'] = ['두 OCR 엔진이 같은 값으로 읽은 확인용 초안입니다. 원본 이미지와 금액·면적을 확인해 주세요.', '주소·주택 유형·면적 기준·관리비 포함 항목은 직접 확인해 주세요.']
    return draft

def adapt_cards(cards):
    if not isinstance(cards, list) or len(cards) > 300 or any(not isinstance(card, dict) or not isinstance(card.get('fields'), dict) for card in cards):
        raise ValueError('Invalid OCR card collection')
    if any(not isinstance(field, dict) for card in cards for field in card['fields'].values()):
        raise ValueError('Invalid OCR fields')
    result = {'schema_version': '1.1', 'source_type': 'LOCAL_OCR_CONSENSUS', 'fields': {},
              'ocr_cards': cards, 'review_messages': [],
              'extraction_status': 'MULTIPLE_LISTINGS' if cards else 'NO_LISTING_FOUND'}
    if len(cards) == 1 and selectable(cards[0]):
        result.update(choose_card(result, 0))
    return result

def runtime_status(settings):
    if not settings.local_ocr_enabled:
        return {'state': 'DISABLED', 'sites': []}
    try:
        p = subprocess.run([settings.local_ocr_python or sys.executable, '-X', 'utf8', '-m',
                            'backend.app.local_ocr', '--probe', settings.local_ocr_machine_root],
                           cwd=ROOT, capture_output=True, encoding='utf-8', timeout=15,
                           creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
        value = json.loads(p.stdout) if p.returncode == 0 else {}
        if value.get('ready'):
            for engine in ('easyocr','paddle'):
                probe = subprocess.run([settings.local_ocr_python or sys.executable,'-X','utf8','-m',
                                        'backend.app.local_ocr','--probe-engine',engine],cwd=ROOT,
                                       capture_output=True,timeout=15,
                                       creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
                if probe.returncode:
                    return {'state':'UNAVAILABLE','sites':[]}
            return {'state': 'CONFIGURED', 'sites': value['sites']}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    return {'state': 'UNAVAILABLE', 'sites': []}


def _run(data, site, settings=None):
    if not _lock.acquire(blocking=False):
        raise HTTPException(429, '다른 이미지를 읽고 있어요. 잠시 후 다시 시도해 주세요.')
    try:
        return _run_locked(data, site, settings)
    finally:
        _lock.release()


def _run_locked(data, site, settings):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as source:
                if source.format not in {'PNG', 'JPEG', 'WEBP'} or source.width * source.height > 16_000_000 or getattr(source, 'n_frames', 1) > 1:
                    raise ValueError()
                source.load()
                img = source.convert('RGB')
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(422, 'JPG·PNG·WebP 정지 이미지(1600만 화소 이하)를 사용해 주세요.') from None
    with tempfile.TemporaryDirectory(prefix='rent-ocr-') as folder:
        image = Path(folder) / 'input.png'
        img.save(image)
        try:
            python = getattr(settings, 'local_ocr_python', '') or sys.executable
            machine_root = getattr(settings, 'local_ocr_machine_root', str(ROOT / 'machine'))
            reads = {}
            for engine in ('easyocr','paddle'):
                output=Path(folder)/(engine+'.json')
                p = subprocess.run([python, '-X', 'utf8', '-m', 'backend.app.local_ocr', '--engine', engine,
                                    str(image), str(output), site, machine_root],
                                   cwd=ROOT, capture_output=True, timeout=120,
                                   creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
                if p.returncode == 3:
                    raise HTTPException(422, '설치된 분석 코드가 이 사이트를 지원하지 않습니다. 지원 사이트를 확인해 주세요.')
                if p.returncode:
                    raise ValueError('worker failed')
                rows=json.loads(output.read_text(encoding='utf-8'))['engine_reads'][engine]
                reads[engine]=[]
                for row in rows:
                    if not isinstance(row,list) or len(row)!=5:
                        raise ValueError('Invalid analyst card tuple')
                    reads[engine].append(dict(zip(('contract_type','deposit_10k_krw','rent_10k_krw','area_m2','maintenance_10k_krw'),row)))
            result=combine_cards(CardConsensusRequest(engine_reads=reads))
            return adapt_cards(result['cards'])
        except subprocess.TimeoutExpired:
            raise HTTPException(504, '이미지 읽기 시간이 초과됐어요. 목록 영역을 작게 잘라 다시 시도해 주세요.') from None
        except (OSError, ValueError, KeyError, TypeError):
            raise HTTPException(503, '로컬 이미지 읽기를 완료하지 못했어요. OCR 설치·모델 상태를 확인해 주세요.') from None

async def extract_local(data, settings, site='dabang'):
    if site not in ('dabang', 'zigbang'):
        raise HTTPException(422, '다방 또는 직방을 선택해 주세요.')
    return await asyncio.to_thread(_run, data, site, settings)


def reader(machine_root):
    root = Path(machine_root).resolve()
    target = root / 'analysis_internal/extraction/read_cards.py'
    if not target.is_file():
        raise ValueError('Analyst reader not installed')
    sys.path[:0] = [str(root.parent), str(root), str(target.parent)]
    from machine.analysis_internal.extraction.read_cards import read_image
    if Path(inspect.getfile(read_image)).resolve() != target:
        raise ValueError('Wrong analyst reader loaded')
    return read_image


def worker():
    if sys.argv[1]=='--probe-engine':
        with contextlib.redirect_stdout(sys.stderr):
            if sys.argv[2]=='paddle':
                importlib.import_module('paddleocr')
            elif sys.argv[2]=='easyocr':
                importlib.import_module('easyocr')
            else:
                return 1
        return 0
    if sys.argv[1] == '--probe':
        read_image = reader(sys.argv[2])
        ready = all(importlib.util.find_spec(name) is not None for name in ('easyocr','paddleocr','paddle','torch','cv2'))
        sites = ['dabang', 'zigbang'] if 'site' in inspect.signature(read_image).parameters else ['dabang']
        print(json.dumps({'ready': ready, 'sites': sites}))
        return 0
    engine,image_path,output_path,site,machine_root=sys.argv[2:7]
    if sys.argv[1]!='--engine' or engine not in ('easyocr','paddle'):
        return 1
    read_image = reader(machine_root)
    supports_site = 'site' in inspect.signature(read_image).parameters
    if not supports_site and site != 'dabang':
        return 3
    with Image.open(image_path) as image:
        crop = (0, 0, image.width, image.height)
    with contextlib.redirect_stdout(sys.stderr):
        result = read_image(image_path, engines=(engine,), crop=crop, **({'site': site} if supports_site else {}))
    Path(output_path).write_text(json.dumps(result, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    return 0

if __name__ == '__main__':
    try:
        raise SystemExit(worker())
    except Exception:
        raise SystemExit(1)
