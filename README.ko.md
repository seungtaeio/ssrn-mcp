# ssrn-mcp

OpenAlex와 Crossref에서 학술논문의 서지정보를 찾고, 수동 열람용 SSRN 링크와 허가된 개인 노트 기반 퀀트 연구 체크리스트를 만드는 **비공식** 로컬 MCP 서버입니다. Python 패키지는 `quant-paper-mcp`이며 `ssrn-mcp`와 `quant-paper-mcp` 명령 모두 서버를 실행합니다.

[English](README.md) · [권리 및 접근 정책](docs/RIGHTS.md) · [기여 안내](CONTRIBUTING.md)

SSRN, Elsevier, OpenAlex, Crossref와 제휴하거나 이들의 승인을 받은 프로젝트가 아닙니다. SSRN/Elsevier 로고를 사용하지 않습니다.

## 제공 범위

- OpenAlex/Crossref 공식 메타데이터 API로 논문 검색 및 DOI 조회
- 제목, 저자, 연도, DOI/제공자 식별자, 제공되는 인용 수·OA 표시, 수동 열람용 링크 반환
- 사용자가 입력한 SSRN ID로 공개 초록 페이지 링크 생성. 해당 페이지에 접속하거나 유효성을 확인하지 않음
- 직접 작성했거나 해당 AI 활용에 대한 별도 허가를 확인한 노트로 연구 체크리스트 생성. 입력 노트와 질문을 로컬로 반환하며 논문은 가져오지 않음
- SSRN/Elsevier로 HTTP 요청을 보내지 않음. SSRN 검색·스크래핑·로그인, PDF 다운로드, 대량 수집, 논문 본문 자동 분석 기능 없음
- 제공자 기반 도구 출력에서 초록과 본문 제외. 외부 API 응답에 추가 필드가 포함될 수 있으나 파서가 출력 대상 이외의 필드를 버림

공식 [SSRN 이용약관](https://www.ssrn.com/index.cfm/en/terms-of-use/)은 SSRN 자동 질의를 금지하고 일부 AI 활용을 포함한 콘텐츠 재사용을 제한합니다. 2026-10-25에 확인했으며 페이지 하단에는 “Last updated June 2017”이 표시되어 있었습니다. 이 서버는 위의 좁은 범위로 동작합니다. 모든 메타데이터·노트 활용이나 연결된 논문의 이용 권한을 보장하지 않습니다. 구체적인 약관 조항과 구현 범위는 [RIGHTS.md](docs/RIGHTS.md)를 참고하세요.

## 설치

Python 3.11 이상, 메타데이터 API에 연결할 인터넷, 로컬 MCP 클라이언트가 필요합니다.

```bash
git clone https://github.com/seungtaeio/ssrn-mcp.git
cd ssrn-mcp
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Windows의 가상환경 활성화 명령은 `.venv\Scripts\activate`입니다.

제공자 설정:

- `OPENALEX_API_KEY` — 선택사항. OpenAlex는 기본 익명 질의를 허용하며 무료 키를 사용하면 가용 예산이 늘어납니다. [인증 안내](https://help.openalex.org/api/authentication/)를 참고하세요.
- `CROSSREF_EMAIL` — Crossref의 polite pool 이용을 위한 연락 이메일로, 설정을 권장합니다. [메타데이터 접근 안내](https://www.crossref.org/documentation/retrieve-metadata/)를 참고하세요.

아래 예시처럼 MCP 서버 프로세스의 환경변수로 전달하세요. [.env.example](.env.example)에 변수가 정리되어 있으며, 서버는 `.env` 파일을 자동으로 읽지 않습니다. 실제 인증정보를 저장소에 커밋하지 마세요.

## MCP 클라이언트 연결

`mcpServers` 설정을 지원하는 클라이언트의 예시입니다.

```json
{
  "mcpServers": {
    "ssrn-mcp": {
      "command": "/ABSOLUTE/PATH/TO/ssrn-mcp/.venv/bin/ssrn-mcp",
      "env": {
        "OPENALEX_API_KEY": "",
        "CROSSREF_EMAIL": "you@example.edu"
      }
    }
  }
}
```

실행 파일의 절대경로와 이메일을 본인 환경에 맞게 바꾸세요. 필요하면 OpenAlex 키를 입력하고, 없으면 빈 문자열로 두세요. Windows에서는 `.venv\Scripts` 아래의 실행 파일을 사용합니다. 설정 변경 후 클라이언트를 재시작하세요.

실행 파일은 **stdio**로 MCP 클라이언트와 통신합니다. 네트워크 포트를 열거나 대화형 프롬프트를 표시하지 않습니다.

## 도구

- `search_papers(query, source, limit)` — `openalex` 또는 `crossref` 검색, 최대 20건
- `get_paper_by_doi(doi, source)` — 논문 한 건의 서지정보 조회
- `find_open_access_link(doi)` — OpenAlex의 수동 열람용 페이지 링크·OA 표시 조회, 다운로드 없음
- `get_ssrn_reference_link(abstract_id)` — SSRN 링크 문자열 생성, 네트워크 요청 없음
- `make_quant_research_checklist(paper_title, original_user_notes)` — 직접 작성했거나 명시적 허가를 받은 노트와 함께 체크리스트 질문 반환
- `source_and_rights_policy()` — 서버의 접근 제한 확인

요청 예시:

> Crossref에서 실적 발표 후 주가 지연 반응에 관한 논문 5건을 검색하고 제목과 DOI 링크를 알려줘.

> Crossref로 DOI 10.2139/ssrn.1234567을 조회해 줘. 외부 색인에 없으면 SSRN에 접속하지 말고 없다고 알려줘.

> SSRN abstract ID 1234567의 링크를 만들어 줘. 페이지에는 접속하지 마.

위 DOI는 SSRN DOI 형식의 예시이며 실제 레코드를 보장하지 않습니다. SSRN 논문의 검색 가능 여부는 외부 색인에 달려 있습니다. DOI, 공개 링크, OA 표시는 자동 접근·재배포·AI 활용의 허가가 아닙니다. 시세 데이터, 백테스트, 주문 실행 기능은 제공하지 않습니다.

## 개발

```bash
python -m pip install -e '.[dev]'
pytest -q
```

테스트는 모의 HTTP 전송을 사용합니다. [기여 안내](CONTRIBUTING.md)를 참고하세요.

## 라이선스

[MIT](LICENSE)는 프로젝트의 원본 소스코드에 적용됩니다. 외부 메타데이터, 논문, 명칭, 링크된 자료에는 각각의 권리와 이용조건이 적용됩니다.
