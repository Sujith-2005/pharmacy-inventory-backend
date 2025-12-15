"""
Pydantic schemas for request/response validation
"""
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime
from models import UserRole, TransactionType, AlertType


# User Schemas
class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    phone: Optional[str] = None
    role: UserRole


class UserCreate(UserBase):
    password: str


class UserResponse(UserBase):
    id: int
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


# Auth Schemas
class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    email: Optional[str] = None


# Medicine Schemas
class MedicineBase(BaseModel):
    sku: str
    name: str
    category: Optional[str] = None
    manufacturer: Optional[str] = None
    brand: Optional[str] = None
    mrp: Optional[float] = None
    cost: Optional[float] = None
    schedule: Optional[str] = None
    storage_requirements: Optional[str] = None
    description: Optional[str] = None


class MedicineCreate(MedicineBase):
    pass


class MedicineResponse(MedicineBase):
    id: int
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


# Batch Schemas
class BatchBase(BaseModel):
    batch_number: str
    quantity: int
    expiry_date: datetime
    purchase_date: Optional[datetime] = None
    purchase_price: Optional[float] = None


class BatchCreate(BatchBase):
    medicine_id: int


class BatchResponse(BatchBase):
    id: int
    medicine_id: int
    is_expired: bool
    is_damaged: bool
    is_recalled: bool
    is_returned: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


# Inventory Transaction Schemas
class TransactionCreate(BaseModel):
    medicine_id: int
    batch_id: Optional[int] = None
    transaction_type: TransactionType
    quantity: int
    unit_price: Optional[float] = None
    notes: Optional[str] = None


class TransactionResponse(BaseModel):
    id: int
    medicine_id: int
    batch_id: Optional[int]
    transaction_type: TransactionType
    quantity: int
    unit_price: Optional[float]
    notes: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True


# Alert Schemas
class AlertResponse(BaseModel):
    id: int
    alert_type: AlertType
    medicine_id: Optional[int]
    batch_id: Optional[int]
    message: str
    severity: str
    is_acknowledged: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


# Forecast Schemas
class ForecastResponse(BaseModel):
    id: int
    medicine_id: int
    forecast_date: datetime
    forecasted_demand: float
    forecast_horizon_days: int
    confidence_score: Optional[float]
    reorder_point: Optional[int]
    recommended_quantity: Optional[int]
    reasoning: Optional[str]
    
    class Config:
        from_attributes = True


# Supplier Schemas
class SupplierBase(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    lead_time_days: int = 7


class SupplierCreate(SupplierBase):
    pass


class SupplierResponse(SupplierBase):
    id: int
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True


# Purchase Order Schemas
class PurchaseOrderItemCreate(BaseModel):
    medicine_id: int
    quantity: int
    unit_price: Optional[float] = None


class PurchaseOrderCreate(BaseModel):
    supplier_id: int
    items: List[PurchaseOrderItemCreate]


class PurchaseOrderResponse(BaseModel):
    id: int
    supplier_id: int
    po_number: str
    status: str
    total_amount: Optional[float]
    created_at: datetime
    
    class Config:
        from_attributes = True


# Dashboard Schemas
class DashboardStats(BaseModel):
    total_stock_value: float
    total_skus: int
    low_stock_count: int
    expiring_soon_count: int
    total_alerts: int
    wastage_value: float


# Chatbot Schemas
class ChatMessage(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    session_id: str
    suggested_actions: Optional[List[str]] = None


