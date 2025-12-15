"""
Waste analytics router
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from typing import List, Optional
from datetime import datetime, timedelta

from database import get_db
from models import Batch, Medicine, InventoryTransaction, TransactionType
from auth import get_current_active_user

router = APIRouter()


@router.get("/analytics")
async def get_waste_analytics(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    category: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get waste analytics"""
    if not end_date:
        end_date = datetime.now()
    if not start_date:
        start_date = end_date - timedelta(days=90)
    
    # Expired stock
    expired_batches = db.query(Batch).filter(
        Batch.is_expired == True,
        Batch.expiry_date >= start_date,
        Batch.expiry_date <= end_date
    )
    
    if category:
        expired_batches = expired_batches.join(Medicine).filter(Medicine.category == category)
    
    expired_batches = expired_batches.all()
    
    expired_value = sum([
        b.quantity * (b.medicine.mrp or 0) for b in expired_batches
    ])
    expired_quantity = sum([b.quantity for b in expired_batches])
    
    # Damaged stock
    damaged_batches = db.query(Batch).filter(
        Batch.is_damaged == True,
        Batch.updated_at >= start_date,
        Batch.updated_at <= end_date
    )
    
    if category:
        damaged_batches = damaged_batches.join(Medicine).filter(Medicine.category == category)
    
    damaged_batches = damaged_batches.all()
    
    damaged_value = sum([
        b.quantity * (b.medicine.mrp or 0) for b in damaged_batches
    ])
    damaged_quantity = sum([b.quantity for b in damaged_batches])
    
    # Recalled stock
    recalled_batches = db.query(Batch).filter(
        Batch.is_recalled == True,
        Batch.updated_at >= start_date,
        Batch.updated_at <= end_date
    )
    
    if category:
        recalled_batches = recalled_batches.join(Medicine).filter(Medicine.category == category)
    
    recalled_batches = recalled_batches.all()
    
    recalled_value = sum([
        b.quantity * (b.medicine.mrp or 0) for b in recalled_batches
    ])
    recalled_quantity = sum([b.quantity for b in recalled_batches])
    
    # Returned stock
    returned_batches = db.query(Batch).filter(
        Batch.is_returned == True,
        Batch.updated_at >= start_date,
        Batch.updated_at <= end_date
    )
    
    if category:
        returned_batches = returned_batches.join(Medicine).filter(Medicine.category == category)
    
    returned_batches = returned_batches.all()
    
    returned_value = sum([
        b.quantity * (b.medicine.mrp or 0) for b in returned_batches
    ])
    returned_quantity = sum([b.quantity for b in returned_batches])
    
    total_waste_value = expired_value + damaged_value + recalled_value
    total_waste_quantity = expired_quantity + damaged_quantity + recalled_quantity + returned_quantity
    
    # Get total inventory value for wastage rate
    total_inventory_value = db.query(func.sum(Batch.quantity * Medicine.mrp)).join(
        Medicine
    ).filter(
        Batch.is_expired == False,
        Batch.is_damaged == False,
        Batch.is_recalled == False
    ).scalar() or 0
    
    wastage_rate = (total_waste_value / total_inventory_value * 100) if total_inventory_value > 0 else 0
    
    return {
        "period": {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat()
        },
        "expired": {
            "quantity": expired_quantity,
            "value": expired_value,
            "count": len(expired_batches)
        },
        "damaged": {
            "quantity": damaged_quantity,
            "value": damaged_value,
            "count": len(damaged_batches)
        },
        "recalled": {
            "quantity": recalled_quantity,
            "value": recalled_value,
            "count": len(recalled_batches)
        },
        "returned": {
            "quantity": returned_quantity,
            "value": returned_value,
            "count": len(returned_batches)
        },
        "total": {
            "quantity": total_waste_quantity,
            "value": total_waste_value,
            "wastage_rate_percent": round(wastage_rate, 2)
        }
    }


@router.get("/top-waste-items")
async def get_top_waste_items(
    limit: int = 10,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db)
):
    """Get top items by waste value"""
    if not end_date:
        end_date = datetime.now()
    if not start_date:
        start_date = end_date - timedelta(days=90)
    
    # Get all wasted batches
    wasted_batches = db.query(Batch).filter(
        and_(
            (Batch.is_expired == True) | (Batch.is_damaged == True) | (Batch.is_recalled == True),
            Batch.updated_at >= start_date,
            Batch.updated_at <= end_date
        )
    ).all()
    
    # Aggregate by medicine
    waste_by_medicine = {}
    for batch in wasted_batches:
        med_id = batch.medicine_id
        if med_id not in waste_by_medicine:
            waste_by_medicine[med_id] = {
                "medicine_id": med_id,
                "medicine_name": batch.medicine.name,
                "sku": batch.medicine.sku,
                "category": batch.medicine.category,
                "quantity": 0,
                "value": 0
            }
        
        waste_by_medicine[med_id]["quantity"] += batch.quantity
        waste_by_medicine[med_id]["value"] += batch.quantity * (batch.medicine.mrp or 0)
    
    # Sort by value and return top N
    sorted_items = sorted(
        waste_by_medicine.values(),
        key=lambda x: x["value"],
        reverse=True
    )
    
    return sorted_items[:limit]


@router.get("/by-category")
async def get_waste_by_category(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: Session = Depends(get_db)
):
    """Get waste breakdown by category"""
    if not end_date:
        end_date = datetime.now()
    if not start_date:
        start_date = end_date - timedelta(days=90)
    
    wasted_batches = db.query(Batch, Medicine).join(Medicine).filter(
        and_(
            (Batch.is_expired == True) | (Batch.is_damaged == True) | (Batch.is_recalled == True),
            Batch.updated_at >= start_date,
            Batch.updated_at <= end_date
        )
    ).all()
    
    waste_by_category = {}
    for batch, medicine in wasted_batches:
        category = medicine.category or "uncategorized"
        if category not in waste_by_category:
            waste_by_category[category] = {
                "category": category,
                "quantity": 0,
                "value": 0,
                "count": 0
            }
        
        waste_by_category[category]["quantity"] += batch.quantity
        waste_by_category[category]["value"] += batch.quantity * (medicine.mrp or 0)
        waste_by_category[category]["count"] += 1
    
    return list(waste_by_category.values())


@router.post("/mark-expired/{batch_id}")
async def mark_batch_expired(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Mark a batch as expired"""
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    batch.is_expired = True
    batch.quantity = 0  # Remove from available stock
    
    # Create transaction
    transaction = InventoryTransaction(
        medicine_id=batch.medicine_id,
        batch_id=batch.id,
        transaction_type=TransactionType.EXPIRED,
        quantity=batch.quantity,
        notes="Marked as expired",
        created_by=current_user.id
    )
    db.add(transaction)
    db.commit()
    
    return {"message": "Batch marked as expired"}


@router.post("/mark-damaged/{batch_id}")
async def mark_batch_damaged(
    batch_id: int,
    quantity: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Mark a batch as damaged"""
    batch = db.query(Batch).filter(Batch.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    if quantity > batch.quantity:
        raise HTTPException(status_code=400, detail="Damaged quantity exceeds available stock")
    
    batch.is_damaged = True
    batch.quantity -= quantity
    
    # Create transaction
    transaction = InventoryTransaction(
        medicine_id=batch.medicine_id,
        batch_id=batch.id,
        transaction_type=TransactionType.DAMAGED,
        quantity=quantity,
        notes="Marked as damaged",
        created_by=current_user.id
    )
    db.add(transaction)
    db.commit()
    
    return {"message": "Batch marked as damaged"}


