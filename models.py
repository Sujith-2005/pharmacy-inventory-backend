"""
Database models
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Text, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
import enum
from database import Base


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    PHARMACY_MANAGER = "pharmacy_manager"
    PHARMACIST = "pharmacist"
    OWNER = "owner"


class TransactionType(str, enum.Enum):
    IN = "in"
    OUT = "out"
    ADJUSTMENT = "adjustment"
    RETURN = "return"
    EXPIRED = "expired"
    DAMAGED = "damaged"
    RECALLED = "recalled"


class AlertType(str, enum.Enum):
    LOW_STOCK = "low_stock"
    STOCK_OUT = "stock_out"
    EXPIRY_WARNING = "expiry_warning"
    DELAYED_DELIVERY = "delayed_delivery"


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    phone = Column(String, unique=True, index=True)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String, nullable=False)
    role = Column(SQLEnum(UserRole), default=UserRole.PHARMACIST)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class Medicine(Base):
    __tablename__ = "medicines"
    
    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=False, index=True)
    category = Column(String, index=True)  # AI-categorized or manual
    manufacturer = Column(String)
    brand = Column(String)
    mrp = Column(Float)
    cost = Column(Float)
    schedule = Column(String)  # Schedule H, OTC, etc.
    storage_requirements = Column(String)  # e.g., "cold_chain", "room_temp"
    description = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    batches = relationship("Batch", back_populates="medicine", cascade="all, delete-orphan")
    transactions = relationship("InventoryTransaction", back_populates="medicine")


class Batch(Base):
    __tablename__ = "batches"
    
    id = Column(Integer, primary_key=True, index=True)
    medicine_id = Column(Integer, ForeignKey("medicines.id"), nullable=False)
    batch_number = Column(String, nullable=False, index=True)
    quantity = Column(Integer, default=0)
    expiry_date = Column(DateTime(timezone=True), nullable=False, index=True)
    purchase_date = Column(DateTime(timezone=True))
    purchase_price = Column(Float)
    is_expired = Column(Boolean, default=False)
    is_damaged = Column(Boolean, default=False)
    is_recalled = Column(Boolean, default=False)
    is_returned = Column(Boolean, default=False)
    return_status = Column(String)  # initiated, picked, credited
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    medicine = relationship("Medicine", back_populates="batches")
    transactions = relationship("InventoryTransaction", back_populates="batch")


class Supplier(Base):
    __tablename__ = "suppliers"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String)
    phone = Column(String)
    address = Column(Text)
    lead_time_days = Column(Integer, default=7)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    purchase_orders = relationship("PurchaseOrder", back_populates="supplier")


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    
    id = Column(Integer, primary_key=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False)
    po_number = Column(String, unique=True, nullable=False)
    status = Column(String, default="draft")  # draft, sent, confirmed, received
    total_amount = Column(Float)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    supplier = relationship("Supplier", back_populates="purchase_orders")
    items = relationship("PurchaseOrderItem", back_populates="purchase_order")


class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_items"
    
    id = Column(Integer, primary_key=True, index=True)
    po_id = Column(Integer, ForeignKey("purchase_orders.id"), nullable=False)
    medicine_id = Column(Integer, ForeignKey("medicines.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Float)
    
    purchase_order = relationship("PurchaseOrder", back_populates="items")
    medicine = relationship("Medicine")


class InventoryTransaction(Base):
    __tablename__ = "inventory_transactions"
    
    id = Column(Integer, primary_key=True, index=True)
    medicine_id = Column(Integer, ForeignKey("medicines.id"), nullable=False)
    batch_id = Column(Integer, ForeignKey("batches.id"))
    transaction_type = Column(SQLEnum(TransactionType), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Float)
    notes = Column(Text)
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    medicine = relationship("Medicine", back_populates="transactions")
    batch = relationship("Batch", back_populates="transactions")


class Alert(Base):
    __tablename__ = "alerts"
    
    id = Column(Integer, primary_key=True, index=True)
    alert_type = Column(SQLEnum(AlertType), nullable=False)
    medicine_id = Column(Integer, ForeignKey("medicines.id"))
    batch_id = Column(Integer, ForeignKey("batches.id"))
    message = Column(Text, nullable=False)
    severity = Column(String, default="medium")  # low, medium, high, critical
    is_acknowledged = Column(Boolean, default=False)
    acknowledged_by = Column(Integer, ForeignKey("users.id"))
    acknowledged_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Forecast(Base):
    __tablename__ = "forecasts"
    
    id = Column(Integer, primary_key=True, index=True)
    medicine_id = Column(Integer, ForeignKey("medicines.id"), nullable=False)
    forecast_date = Column(DateTime(timezone=True), nullable=False)
    forecasted_demand = Column(Float, nullable=False)
    forecast_horizon_days = Column(Integer, default=30)
    confidence_score = Column(Float)
    reorder_point = Column(Integer)
    recommended_quantity = Column(Integer)
    reasoning = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    medicine = relationship("Medicine")


