"""PersAn API - FastAPI Entry Point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import chat, health, memory, monitors, skills, tools, upload
from backend.api.routes import proactive_api
from backend.config import settings

app = FastAPI(
    title="PersAn API",
    description="AI Chatbot universale powered by Me4BrAIn",
    version="0.1.0",
)

# CORS middleware per frontend
import os

# Leggi allowed origins da environment
ALLOWED_ORIGINS = os.getenv(
    "CORS_ALLOWED_ORIGINS", "http://localhost:3020,http://127.0.0.1:3020"
).split(",")

# In produzione, aggiungi anche il dominio GIC-com
if os.getenv("ENVIRONMENT") == "production":
    ALLOWED_ORIGINS.extend(
        [
            "http://GIC-com:3020",
            "http://100.99.43.29:3020",  # Tailscale
        ]
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(upload.router, prefix="/api", tags=["upload"])
app.include_router(tools.router, prefix="/api", tags=["tools"])
app.include_router(skills.router, prefix="/api", tags=["skills"])
app.include_router(monitors.router, prefix="/api", tags=["monitors"])
app.include_router(memory.router, prefix="/api", tags=["memory"])
app.include_router(proactive_api.router)  # NL-to-Monitor API


@app.on_event("startup")
async def startup_event():
    """Log startup info."""
    print(f"🤖 PersAn API starting on {settings.persan_host}:{settings.persan_port}")
    print(f"📡 Me4BrAIn URL: {settings.me4brain_url}")


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    print("👋 PersAn API shutting down")
