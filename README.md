# CodeCommit: The Architects Network

[![Version](https://img.shields.io/badge/version-v5.9-00e5ff?style=for-the-badge)](http://74.208.227.87)
[![Status](https://img.shields.io/badge/status-online-00c853?style=for-the-badge)](http://74.208.227.87/v2/health)
[![API](https://img.shields.io/badge/api-fastapi-111827?style=for-the-badge)](http://74.208.227.87/v2/health)

**CodeCommit** is a cinematic social network for developers:

- Match by tech stack and seniority
- Send `EXEC_PR` requests instead of likes
- Unlock realtime chat and shared scratchpad on merge
- Earn karma via resources, marketplace, and bounties

## Live Production

Main app: [http://74.208.227.87](http://74.208.227.87)

Health check: [http://74.208.227.87/v2/health](http://74.208.227.87/v2/health)

## Core Features

- JWT auth + rate limiting
- WebSocket realtime chat
- Cinematic landing (boot sequence + matrix background + neon UI)
- Admin analytics dashboard
- Docker production deployment

## Quick Start (Local)

```bash
pip install -r requirements.txt
python -m unittest tests.test_v2_api -v
uvicorn src.codecommit.app_v2:app --host 0.0.0.0 --port 8080 --reload
```

## ENTER_THE_MATRIX

[![ENTER_THE_MATRIX_AT_74.208.227.87](https://img.shields.io/badge/ENTER_THE_MATRIX_AT_74.208.227.87-CLICK-7c4dff?style=for-the-badge)](http://74.208.227.87)

