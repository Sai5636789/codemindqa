#!/bin/bash

# CodeMind — Start Script
# This script starts both the FastAPI backend and the React frontend.

# 1. Start Backend
echo "🚀 Starting Backend (FastAPI)..."
cd backend
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment and installing dependencies..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

# Run backend in background
uvicorn src.main:app --reload --port 8000 &
BACKEND_PID=$!

# 2. Start Frontend
echo "💻 Starting Frontend (React/Vite)..."
cd ../frontend
if [ ! -d "node_modules" ]; then
    echo "📦 Installing npm dependencies..."
    npm install
fi

# Run frontend
npm run dev &
FRONTEND_PID=$!

echo "✅ Both services are starting!"
echo "📡 Backend: http://localhost:8000"
echo "🌐 Frontend: http://localhost:5173"
echo "Press Ctrl+C to stop both services."

# Wait for Ctrl+C
trap "kill $BACKEND_PID $FRONTEND_PID; exit" INT
wait
