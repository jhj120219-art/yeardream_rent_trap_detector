"""목록 카드 엔진 합의 연결 — 여러 OCR·비전 엔진이 읽은 카드 값을 받아 둘 이상이 같게 읽은 값만 자동 입력 후보로 돌려준다.
상태 없음(저장하지 않음), 외부 호출 없음. 엔진 실행은 호출하는 쪽(이미지 추출 서비스)의 몫이다. 결과는 사용자 확인 전의 초안이다.
"""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, StringConstraints

Number = StrictInt | StrictFloat


class CardRead(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    contract_type: Literal['월세', '전세']
    deposit_10k_krw: Number = Field(ge=0, le=1_000_000)
    rent_10k_krw: Number | None = Field(default=None, ge=0, le=100_000)
    area_m2: Number = Field(gt=0, le=1000)
    maintenance_10k_krw: Number = Field(ge=0, le=1000)


class CardConsensusRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    engine_reads: dict[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)], Annotated[list[CardRead], Field(max_length=300)]] = Field(min_length=2, max_length=5)

    def reads(self):
        return {e: [(r.contract_type, float(r.deposit_10k_krw), None if r.rent_10k_krw is None else float(r.rent_10k_krw), float(r.area_m2), float(r.maintenance_10k_krw))
                    for r in rs] for e, rs in self.engine_reads.items()}


class ConsensusUnavailable(RuntimeError):
    pass


def run(body: CardConsensusRequest):
    try:
        from machine.analysis_internal.extraction.consensus import consensus
    except Exception as e:
        raise ConsensusUnavailable(type(e).__name__) from e
    cards = consensus(body.reads())
    count = lambda s: sum(c['status'] == s for c in cards)
    return {'version': 'card-consensus-1', 'cards': cards,
            'summary': {'extracted': count('extracted'), 'needs_review': count('needs_review'), 'on_hold': count('on_hold')},
            'notice': '사용자 확인 전의 초안입니다. 둘 이상의 엔진이 같게 읽은 값만 채웠고, 나머지는 비워 두었습니다. 월세 비교·관리비 추정은 확인 후에만 실행하세요.'}


class CardConsensusSaveRequest(CardConsensusRequest):
    card_index: StrictInt = Field(ge=0)


def extraction_result(card):
    """Adapt agreed values to the existing review draft; no address/area basis guesses."""
    fields = {}
    for name in ('deposit_10k_krw', 'rent_10k_krw', 'area_m2', 'maintenance_10k_krw'):
        value = card['fields'][name]['value']
        fields[name] = {'value': value, 'raw_text': 'ENGINE_CONSENSUS_CANDIDATE' if value is not None else None,
                        'review_required': True}
    return {'schema_version': '1.1', 'extraction_status': 'EXTRACTED_NEEDS_REVIEW',
            'source_type': 'ENGINE_CONSENSUS', 'fields': fields, 'consensus_card': card,
            'review_messages': ['클라이언트가 전달한 판독값의 일치 결과이며 실제 엔진 실행은 검증하지 않았습니다.',
                                '주소·면적 기준·포함 항목을 확인한 뒤 매물로 등록하세요. 자동 분석하지 않습니다.']}
