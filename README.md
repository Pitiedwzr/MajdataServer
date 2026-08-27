# MajdataServer (Python)

> [!WARNING]
> This project is build with vibe-code, intentioanl used for private personal cloud instance. USE AT YOUR OWN RISK.

A modern, high-performance asynchronous backend server for **MajdataNet** and game clients, built with **FastAPI**, **SQLAlchemy**, and **uv**.

It serves as a drop-in replacement for the lightweight Go `MajdataProvider` while implementing all missing endpoints from `Online_Net_API.md`.

---

## Features

- **Seamless Drop-in Compatibility with MajdataProvider**:
  - Exact same Base64 URL-safe chart ID encoding.
  - MD5 hashing of `maidata.txt` for integrity verification.
  - SHA-256 base64 headers (`hash`) for asset streaming.
  - Automatic thumbnail generation (max 512px, Lanczos scaling).
  - Multi-threaded chart folder scanning and startup sync.
- **Account API**:
  - Registration, Login, Logout with database-backed session management.
  - Profile intro and avatar upload/serving with fallback SVG.
  - Password reset and OTP verification.
- **MaiChart API**:
  - List charts with keyword search (`search`), tag search (`search="tag:..."`), and sorting.
  - Full metadata summary (`/summary`).
  - File streaming (`/chart`, `/track`, `/image`, `/video`) with HTTP range and cache headers.
  - Chart upload (multi-file or ZIP archive extraction) and deletion.
  - Tag management.
- **Score API**:
  - Multi-difficulty leaderboard ranking (`/score`).
  - Score submission with DX/Classic accuracy, combo state, and DX score.
- **Interaction API**:
  - Likes, dislikes, play counts.
  - Nested comments with replies.
- **Collection API**:
  - User collection creation, visibility controls (Public / Private).
  - Song hash list and populated song list.
- **Machine & Persist API**:
  - Arcade machine registration and QR authorization.
  - Persistent application data and settings storage.

---

## Quick Start

### 1. Requirements
- Python 3.10+
- [uv](https://docs.astral.sh/uv/)

### 2. Installation
```bash
# Clone or navigate into MajdataServer directory
cd MajdataServer

# Install dependencies with uv
uv sync
```

### 3. Running the Server (Local)
```bash
# Start server on http://localhost:8080
uv run uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

### 4. Running with Docker / Docker Compose
```bash
# Build and run with docker compose
docker compose up -d --build
```

Interactive API documentation (Swagger UI) is available at:
👉 **`http://localhost:8080/docs`**

---

## Directory Structure

```
MajdataServer/
├── app/
│   ├── main.py              # FastAPI application entry & router registration
│   ├── config.py            # Settings and paths configuration
│   ├── database.py          # SQLAlchemy async session and engine
│   ├── models/              # Database models (User, Chart, Score, Collection, etc.)
│   ├── schemas/             # Pydantic request & response models
│   ├── services/            # Core business logic (chart scanner, auth, file/image handlers)
│   └── routers/             # API endpoint handlers (/account, /maichart, /collection, etc.)
├── data/                    # SQLite database & uploaded avatars
├── tests/                   # Pytest test suite
├── pyproject.toml           # Project configuration & dependencies
└── README.md                # Documentation
```

---

## Smooth Migration from Go `MajdataProvider`

1. The server by default reads charts from `../MajdataProvider/charts`. You can also configure `CHARTS_DIR` in `.env`.
2. All chart IDs, asset paths, and integrity hashes match 100% with the Go provider, allowing game clients and web frontends to switch over seamlessly.
