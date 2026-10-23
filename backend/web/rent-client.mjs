// Frontend handoff: pass the team key at runtime; never put it in source/storage/logs.
export function createRentClient({ baseUrl, teamKey, fetchImpl = globalThis.fetch, timeoutMs = 30000, extractionTimeoutMs = 90000 }) {
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0 || timeoutMs > 300000) {
    throw new Error('요청 제한 시간은 0보다 크고 300000ms 이하여야 합니다.');
  }
  if (!Number.isFinite(extractionTimeoutMs) || extractionTimeoutMs <= 0 || extractionTimeoutMs > 300000) throw new Error('이미지 요청 제한 시간을 확인해 주세요.');
  const url = new URL(baseUrl);
  if (url.protocol !== 'https:' && !(url.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(url.hostname))) {
    throw new Error('HTTPS 서버 주소를 사용해 주세요.');
  }
  if (url.username || url.password || url.search || url.hash || url.pathname !== '/') {
    throw new Error('서버의 기본 주소만 입력해 주세요.');
  }
  let token = null;
  async function request(path, { method = 'GET', body, key, requestTimeout = timeoutMs } = {}) {
    const headers = {};
    if (teamKey) headers['X-Team-Key'] = teamKey;
    if (token) headers.Authorization = `Bearer ${token}`;
    const multipart = body instanceof FormData;
    if (body !== undefined && !multipart) headers['Content-Type'] = 'application/json';
    if (key) headers['Idempotency-Key'] = key;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), requestTimeout);
    let response;
    try {
      response = await fetchImpl(new URL(path, url), {
        method, headers, body: body === undefined ? undefined : multipart ? body : JSON.stringify(body),
        cache: 'no-store', credentials: 'omit', redirect: 'error', signal: controller.signal,
      });
      if (!response.ok) {
        const error = new Error(({401:'접속키 또는 이용표를 확인해 주세요.',409:'입력이 바뀌었습니다. 새 비교를 시작해 주세요.',422:'입력 내용을 확인해 주세요.',503:'서버의 데이터 또는 기능이 준비되지 않았습니다.'})[response.status] || '요청을 완료하지 못했습니다.');
        error.status = response.status;
        const requestId = response.headers.get('X-Request-ID');
        error.requestId = /^[0-9a-f]{32}$/.test(requestId || '') ? requestId : null;
        error.details = await response.json().catch(() => null);
        throw error;
      }
      return response.status === 204 ? null : await response.json();
    } catch (cause) {
      if (cause.status) throw cause;
      const error = new Error(controller.signal.aborted
        ? '서버 응답 시간이 초과되었습니다. 같은 작업을 다시 시도해 주세요.'
        : '서버 응답을 받지 못했습니다. 연결 상태를 확인하고 다시 시도해 주세요.');
      error.code = controller.signal.aborted ? 'TIMEOUT' : 'NETWORK_OR_RESPONSE_ERROR';
      error.status = response?.status ?? null;
      const requestId = response?.headers.get('X-Request-ID');
      error.requestId = /^[0-9a-f]{32}$/.test(requestId || '') ? requestId : null;
      // Do not attach raw transport errors, URLs, headers or request bodies.
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }
  return {
    async start() {
      // Reuse the current session; never replace it silently after a failed request.
      if (!token) token = (await request('/sessions', { method: 'POST' })).token;
      const capabilities = await request('/capabilities');
      const locations = await request('/locations');
      return { capabilities, locations };
    },
    async searchAddresses(query) {
      if (!token) throw new Error('서버에 먼저 연결해 주세요.');
      return request('/addresses/search?' + new URLSearchParams({q: query}));
    },
    async selectOcrCard(extractionId, index) {
      return request(`/extractions/${encodeURIComponent(extractionId)}/cards/${index}`, {method:"POST"});
    },
    createExtraction(file, {site=null, local=false} = {}) {
      if (!token) throw new Error('서버에 먼저 연결해 주세요.');
      let extractionId = null, running = false;
      return {async run() {
        if (running) throw new Error('이미 처리 중입니다.');
        running = true;
        try {
          if (!extractionId) {
            const form = new FormData(); form.append('file', file); if(site)form.append('site',site);
            extractionId = (await request('/extractions', {method:'POST', body:form, requestTimeout:local?270000:extractionTimeoutMs})).id;
            if (!extractionId) throw new Error('이미지 처리 결과를 확인할 수 없습니다.');
          }
          return await request('/extractions/' + encodeURIComponent(extractionId) + '/listing-draft');
        } finally { running = false; }
      }};
    },
    createComparison(input, { maintenanceScenario = null } = {}) {
      if (!token) throw new Error('먼저 사용 시작을 눌러 주세요.');
      if (input.confirmation?.user_confirmed !== true) throw new Error('입력 내용을 먼저 확인해 주세요.');
      const snapshot = structuredClone(input);
      const scenario = maintenanceScenario ? structuredClone(maintenanceScenario) : null;
      const saveKey = crypto.randomUUID(), analysisKey = crypto.randomUUID(), referenceKey = crypto.randomUUID();
      let listingId = null, analysisId = null, referenceId = null, running = false;
      return {
        // Retain this task while retrying. For edited input, create a new task.
        async run(onStep = () => {}) {
          if (running) throw new Error('이미 처리 중입니다.');
          running = true;
          try {
            if (!listingId) {
              onStep('SAVING');
              listingId = (await request('/listings', { method: 'POST', body: snapshot, key: saveKey })).id;
            }
            if (!analysisId) {
              onStep('COMPARING');
              analysisId = (await request(`/listings/${listingId}/analyses`, { method: 'POST', key: analysisKey })).id;
            }
            let referenceError = null;
            if (scenario && !referenceId) {
              onStep('ESTIMATING_MAINTENANCE');
              try {
                const result = await request(`/listings/${encodeURIComponent(listingId)}/maintenance-references`, { method:'POST', body:scenario, key:referenceKey, requestTimeout:60000 });
                if (!result?.id) throw new Error('관리비 예상 결과를 확인하지 못했습니다.');
                referenceId = result.id;
              } catch (e) {
                // A failed cost calculation must not discard a completed rent comparison.
                referenceError = {state:'FAILED',status:e.status??null,code:e.code??null};
              }
            }
            onStep('LOADING_REPORT');
            const report = await request(`/listings/${listingId}/report`);
            onStep('DONE');
            // HTTP success is not a price judgement. Render report.rent.result.status.
            return scenario ? {...report,client_maintenance:referenceError||{state:'READY'}} : report;
          } finally { running = false; }
        },
      };
    },
    // Call only after the user explicitly chooses to delete all session data.
    async deleteSessionData() {
      if (!token) return;
      await request('/sessions/current', { method: 'DELETE' });
      token = null;
    },
  };
}
