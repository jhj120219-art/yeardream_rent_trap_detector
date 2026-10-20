"""매물 전체 결과의 읽기 전용 조합. 분석 정책과 기존 API 응답은 변경하지 않는다."""
from .cost_items import cost_items
from .report_money import advertised_money as money
from .advertised_costs import advertised_costs


def build_report(listing, analysis, evidence, data_status):
    raw=listing['input']
    confirmed=raw['confirmation']['user_confirmed']
    valid=listing['validation']['ok']
    options=raw.get('options',{})
    rent=money(raw['listing'].get('rent_10k_krw'))
    fee=money(options.get('maintenance_10k_krw'))
    reasons=[]
    if not confirmed:
        reasons.append('USER_CONFIRMATION_REQUIRED')
    if not valid:
        reasons.append('INPUT_REVIEW_REQUIRED')
    if rent is None or fee is None:
        reasons.append('MONTHLY_COST_INCOMPLETE')
    result=analysis['result'] if analysis else None
    next_actions=[]
    if not confirmed or not valid:
        next_actions.append('REVIEW_LISTING')
    elif not analysis:
        next_actions.append('RUN_RENT_ANALYSIS' if data_status=='READY' else 'CONNECT_RENT_DATA')
    elif result['status']!='COMPARED':
        next_actions.append('REVIEW_RENT_RESULT')
    if fee is None:
        next_actions.append('ADD_MAINTENANCE_AMOUNT')
    if evidence['total']==0:
        next_actions.append('ADD_MAINTENANCE_EVIDENCE')
    elif any(x['comparison']['status']=='NEEDS_REVIEW' for x in evidence['items']):
        next_actions.append('REVIEW_MAINTENANCE_EVIDENCE')
    return {
        'report_version':'1.0','listing_id':listing['id'],
        'advertised_costs':advertised_costs(options,confirmed),
        'property':{'input':raw['listing'],'validation':listing['validation'],
                    'confirmation':raw['confirmation'],'links':listing['links']},
        'rent':{'state':result['status'] if result else 'NOT_ANALYZED',
                'analysis_id':analysis['id'] if analysis else None,
                'analyzed_at':analysis['created_at'] if analysis else None,'result':result,
                'comparable_transactions':None,
                'comparable_transactions_state':'NOT_PROVIDED_BY_ANALYSIS'},
        'maintenance':{'quoted_monthly_10k_krw':fee,'evidence':evidence,
                       'state':'EVIDENCE_RECORDED' if evidence['total'] else 'NO_EVIDENCE'},
        'options':{k:v for k,v in options.items() if k!='maintenance_10k_krw'},
        'utility_costs':cost_items(options,confirmed),
        'monthly_cost':{'rent_10k_krw':rent,'maintenance_10k_krw':fee,
                        'quoted_subtotal_10k_krw':round(rent+fee,6) if not reasons else None,
                        'state':'QUOTED_SUBTOTAL' if not reasons else 'NEEDS_REVIEW',
                        'reasons':reasons,
                        'notice':'입력 월세+관리비의 소계입니다. 별도 공과금·주차비·일회성 비용은 포함하지 않으며 적정 가격 평가가 아닙니다.'},
        'workflow':{'data_status':data_status,'next_actions':next_actions,
                    'notice':'월세 결과는 마지막 저장 분석입니다. 관리비·옵션은 월세 분석과 구분해 표시합니다.'},
    }
