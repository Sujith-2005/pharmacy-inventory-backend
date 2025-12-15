"""
Dashboard router
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from datetime import datetime, timedelta

from database import get_db
from models import Medicine, Batch, Alert, InventoryTransaction, TransactionType
from schemas import DashboardStats
from auth import get_current_active_user
from config import settings

router = APIRouter()


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(db: Session = Depends(get_db)):
    """Get dashboard statistics"""
    # Total stock value
    total_stock_value = db.query(func.sum(Batch.quantity * Medicine.mrp)).join(
        Medicine
    ).filter(
        Batch.is_expired == False,
        Batch.is_damaged == False,
        Batch.is_recalled == False,
        Batch.quantity > 0
    ).scalar() or 0
    
    # Total SKUs
    total_skus = db.query(Medicine).filter(Medicine.is_active == True).count()
    
    # Low stock count (simplified - compare against threshold)
    low_stock_count = db.query(Medicine).join(Batch).filter(
        Batch.is_expired == False,
        Batch.is_damaged == False
    ).group_by(Medicine.id).having(
        func.sum(Batch.quantity) < 20  # Example threshold
    ).count()
    
    # Expiring soon count
    threshold_date = datetime.now().date() + timedelta(days=settings.EXPIRY_ALERT_DAYS[0])
    expiring_soon_count = db.query(Batch).filter(
        Batch.expiry_date <= threshold_date,
        Batch.is_expired == False,
        Batch.quantity > 0
    ).count()
    
    # Total alerts
    total_alerts = db.query(Alert).filter(Alert.is_acknowledged == False).count()
    
    # Wastage value (last 30 days)
    start_date = datetime.now() - timedelta(days=30)
    wasted_batches = db.query(Batch).filter(
        and_(
            (Batch.is_expired == True) | (Batch.is_damaged == True) | (Batch.is_recalled == True),
            Batch.updated_at >= start_date
        )
    ).all()
    
    wastage_value = sum([
        b.quantity * (b.medicine.mrp or 0) for b in wasted_batches
    ])
    
    return DashboardStats(
        total_stock_value=float(total_stock_value),
        total_skus=total_skus,
        low_stock_count=low_stock_count,
        expiring_soon_count=expiring_soon_count,
        total_alerts=total_alerts,
        wastage_value=float(wastage_value)
    )


@router.get("/expiry-timeline")
async def get_expiry_timeline(db: Session = Depends(get_db)):
    """Get expiry timeline (grouped by time buckets)"""
    today = datetime.now().date()
    
    buckets = [
        {"label": "0-30 days", "start": 0, "end": 30},
        {"label": "31-60 days", "start": 31, "end": 60},
        {"label": "61-90 days", "start": 61, "end": 90},
        {"label": "90+ days", "start": 91, "end": 9999}
    ]
    
    timeline = []
    for bucket in buckets:
        start_date = today + timedelta(days=bucket["start"])
        end_date = today + timedelta(days=bucket["end"])
        
        batches = db.query(Batch).filter(
            Batch.expiry_date >= start_date,
            Batch.expiry_date <= end_date,
            Batch.is_expired == False,
            Batch.quantity > 0
        ).all()
        
        total_quantity = sum([b.quantity for b in batches])
        total_value = sum([b.quantity * (b.medicine.mrp or 0) for b in batches])
        
        timeline.append({
            "bucket": bucket["label"],
            "count": len(batches),
            "quantity": total_quantity,
            "value": total_value
        })
    
    return timeline


@router.get("/inventory-by-category")
async def get_inventory_by_category(db: Session = Depends(get_db)):
    """Get inventory breakdown by category"""
    results = db.query(
        Medicine.category,
        func.count(Medicine.id).label('sku_count'),
        func.sum(Batch.quantity).label('total_quantity'),
        func.sum(Batch.quantity * Medicine.mrp).label('total_value')
    ).join(Batch).filter(
        Batch.is_expired == False,
        Batch.is_damaged == False,
        Batch.is_recalled == False,
        Batch.quantity > 0
    ).group_by(Medicine.category).all()
    
    return [
        {
            "category": r.category or "uncategorized",
            "sku_count": r.sku_count,
            "total_quantity": r.total_quantity or 0,
            "total_value": float(r.total_value or 0)
        }
        for r in results
    ]


@router.get("/sales-trends")
async def get_sales_trends(
    days: int = 30,
    db: Session = Depends(get_db)
):
    """Get sales trends (consumption trends)"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    # Get daily consumption
    transactions = db.query(
        func.date(InventoryTransaction.created_at).label('date'),
        func.sum(InventoryTransaction.quantity).label('quantity')
    ).filter(
        InventoryTransaction.transaction_type == TransactionType.OUT,
        InventoryTransaction.created_at >= start_date,
        InventoryTransaction.created_at <= end_date
    ).group_by(func.date(InventoryTransaction.created_at)).all()
    
    return [
        {
            "date": t.date.isoformat(),
            "quantity": t.quantity or 0
        }
        for t in transactions
    ]


@router.get("/top-medicines")
async def get_top_medicines(
    limit: int = 10,
    by: str = "consumption",  # consumption or value
    days: int = 30,
    db: Session = Depends(get_db)
):
    """Get top medicines by consumption or value"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    if by == "consumption":
        results = db.query(
            Medicine.id,
            Medicine.name,
            Medicine.sku,
            Medicine.category,
            func.sum(InventoryTransaction.quantity).label('total_consumption')
        ).join(InventoryTransaction).filter(
            InventoryTransaction.transaction_type == TransactionType.OUT,
            InventoryTransaction.created_at >= start_date,
            InventoryTransaction.created_at <= end_date
        ).group_by(Medicine.id).order_by(
            func.sum(InventoryTransaction.quantity).desc()
        ).limit(limit).all()
        
        return [
            {
                "medicine_id": r.id,
                "name": r.name,
                "sku": r.sku,
                "category": r.category,
                "total_consumption": r.total_consumption or 0
            }
            for r in results
        ]
    else:  # by value
        results = db.query(
            Medicine.id,
            Medicine.name,
            Medicine.sku,
            Medicine.category,
            func.sum(Batch.quantity * Medicine.mrp).label('total_value')
        ).join(Batch).filter(
            Batch.is_expired == False,
            Batch.is_damaged == False,
            Batch.quantity > 0
        ).group_by(Medicine.id).order_by(
            func.sum(Batch.quantity * Medicine.mrp).desc()
        ).limit(limit).all()
        
        return [
            {
                "medicine_id": r.id,
                "name": r.name,
                "sku": r.sku,
                "category": r.category,
                "total_value": float(r.total_value or 0)
            }
            for r in results
        ]


