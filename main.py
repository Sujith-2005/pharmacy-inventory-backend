"""
Smart Pharmacy Inventory Management System - Main API
"""
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
import uvicorn

from database import get_db, engine, Base
from models import User, Medicine, Batch, InventoryTransaction
from routers import auth, inventory, forecasting, alerts, waste, dashboard, chatbot, suppliers, debug
from config import settings

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Smart Pharmacy Inventory API",
    description="AI-powered pharmacy inventory management system",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(inventory.router, prefix="/api/inventory", tags=["Inventory"])
app.include_router(forecasting.router, prefix="/api/forecasting", tags=["Forecasting"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["Alerts"])
app.include_router(waste.router, prefix="/api/waste", tags=["Waste Analytics"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])
app.include_router(chatbot.router, prefix="/api/chatbot", tags=["Chatbot"])
app.include_router(suppliers.router, prefix="/api/suppliers", tags=["Suppliers"])
app.include_router(debug.router, prefix="/api", tags=["Debug"])


@app.get("/")
async def root():
    return {
        "message": "Smart Pharmacy Inventory Management System API",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/api/health")
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )


