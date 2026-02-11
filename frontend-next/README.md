# Frontend Next (Neural Reactor)

Next.js 14 기반 실시간 HUD 프론트엔드입니다.

## Prerequisites

- Node.js 20+
- 실행 중인 백엔드 서버:
  - `PYTHONPATH=src python3 -m brain_agent.cli serve-live-events --host 127.0.0.1 --port 8765`

## Setup

```bash
cd frontend-next
cp env.local.example .env.local
npm install
```

## Run

```bash
cd frontend-next
npm run dev
```

- 브라우저: `http://127.0.0.1:3000`
- 백엔드 API 기본값: `http://127.0.0.1:8765` (`NEXT_PUBLIC_BRAIN_API_BASE`)

## UI Features

- 3D Neural Core (`@react-three/fiber`, `@react-three/drei`)
- Command Console (`/api/control/actions`, `/api/control/jobs`)
- 실시간 이벤트 스트림 (`/ws/live`)
- Alpha Genome Map (`reactflow`)
- Simulator Pulse Chart (`recharts`)
- Cyber Terminal (event log stream)
