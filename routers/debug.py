"""
Debug endpoint to check database state
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime

from database import get_db
from models import Medicine, Batch
from auth import get_current_active_user

router = APIRouter()


@router.get("/debug/inventory-state")
async def get_inventory_state(
    db: Session = Depends(get_db)
):
    """Debug endpoint to check current inventory state"""
    total_medicines = db.query(Medicine).filter(Medicine.is_active == True).count()
    total_batches = db.query(Batch).count()
    active_batches = db.query(Batch).filter(
        Batch.quantity > 0,
        Batch.is_expired == False
    ).count()
    expired_batches = db.query(Batch).filter(Batch.is_expired == True).count()
    zero_quantity_batches = db.query(Batch).filter(Batch.quantity == 0).count()
    
    # Get ALL medicines with ALL their batches (no filters)
    all_medicines = db.query(Medicine).filter(Medicine.is_active == True).limit(10).all()
    medicines_data = []
    for med in all_medicines:
        batches = db.query(Batch).filter(Batch.medicine_id == med.id).all()
        medicines_data.append({
            "id": med.id,
            "sku": med.sku,
            "name": med.name,
            "total_batches": len(batches),
            "batches": [
                {
                    "id": b.id,
                    "batch_number": b.batch_number,
                    "quantity": b.quantity,
                    "expiry_date": b.expiry_date.isoformat() if b.expiry_date else None,
                    "is_expired": b.is_expired,
                    "expiry_passed": b.expiry_date.date() < datetime.now().date() if b.expiry_date else None
                }
                for b in batches
            ]
        })
    
    # Get recent batches (last 10)
    recent_batches = db.query(Batch).order_by(Batch.created_at.desc()).limit(10).all()
    recent_batches_data = [
        {
            "id": b.id,
            "medicine_id": b.medicine_id,
            "batch_number": b.batch_number,
            "quantity": b.quantity,
            "expiry_date": b.expiry_date.isoformat() if b.expiry_date else None,
            "is_expired": b.is_expired,
            "created_at": b.created_at.isoformat() if b.created_at else None
        }
        for b in recent_batches
    ]
    
    return {
        "summary": {
            "total_medicines": total_medicines,
            "total_batches": total_batches,
            "active_batches": active_batches,
            "expired_batches": expired_batches,
            "zero_quantity_batches": zero_quantity_batches
        },
        "sample_medicines": medicines_data,
        "recent_batches": recent_batches_data
    }
