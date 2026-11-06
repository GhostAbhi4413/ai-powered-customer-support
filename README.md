# AI-Powered Customer Support

A customer-support workspace with a React frontend, FastAPI backend, SQLite persistence, and Gemini-powered tool calling.

## Features

- View customers, orders, shipments, returns, and cancellation eligibility
- Ask the support assistant questions about an order
- Propose address updates, returns, and cancellations for explicit approval
- Keep Gemini credentials on the backend only

## Run locally

From the project root:

```powershell
$env:GEMINI_API_KEY = "your-gemini-api-key"
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open the URL printed by Vite, usually `http://localhost:5173`.

## Stack

React, Vite, FastAPI, SQLite, Pydantic, and the official Google Gen AI SDK.

Never commit real API keys. Use `.env.example` as a reference for configuration.
