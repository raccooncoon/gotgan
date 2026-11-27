# gotgan (곳간)

원천 자료를 **검증 가능한 지식**으로 바꾸고, 사람과 에이전트가 함께 쓰는 Local-First 지식 창고.

> 상태: 기획 단계. 아직 실행 가능한 코드는 없다.

## 핵심 원칙

- **Evidence-First**: 모든 주장은 원본의 버전과 위치를 근거로 가진다.
- **Local-First**: 외부 API 없이 폐쇄망에서 수집·검색·편집이 가능하다.
- **정본과 파생의 분리**: Vault(파일)가 정본이고 DB·검색 인덱스·그래프는 재구축 가능한 파생 데이터다.
- **변경안 기반 쓰기**: 에이전트는 정본에 직접 쓰지 않고 변경안을 제출한다.
- **Selective Curation**: 모든 원본을 정리하지 않는다. 재사용·검증 가치가 확인된 지식만 승격한다.
- **Agent-Agnostic**: CLI와 MCP로 에이전트를 교체할 수 있다.

## 문서

- [개발 계획](docs/plan.md)
- [계획 수립과 검토 절차](docs/planning-process.md)
- [아키텍처 결정 기록(ADR)](docs/adr/)

## 기술 후보

Java / Spring Boot(모듈러 모놀리스, Hexagonal), React, 내장 검색 인덱스(SQLite FTS 또는 Lucene). 확정 전 후보이며 결정은 ADR로 기록한다.
