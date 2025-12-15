"""
Alerts router
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from datetime import datetime, timedelta

from database import get_db
from models import Alert, AlertType, Medicine, Batch
from schemas import AlertResponse
from auth import get_current_active_user
from config import settings

router = APIRouter()


@router.get("/", response_model=List[AlertResponse])
async def get_alerts(
    alert_type: AlertType = None,
    acknowledged: bool = None,
    severity: str = None,
    db: Session = Depends(get_db)
):
    """Get all alerts"""
    query = db.query(Alert)
    
    if alert_type:
        query = query.filter(Alert.alert_type == alert_type)
    
    if acknowledged is not None:
        query = query.filter(Alert.is_acknowledged == acknowledged)
    
    if severity:
        query = query.filter(Alert.severity == severity)
    
    alerts = query.order_by(Alert.created_at.desc()).limit(100).all()
    return alerts


@router.get("/unacknowledged", response_model=List[AlertResponse])
async def get_unacknowledged_alerts(db: Session = Depends(get_db)):
    """Get unacknowledged alerts"""
    alerts = db.query(Alert).filter(
        Alert.is_acknowledged == False
    ).order_by(Alert.created_at.desc()).all()
    return alerts


@router.post("/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Acknowledge an alert"""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    alert.is_acknowledged = True
    alert.acknowledged_by = current_user.id
    alert.acknowledged_at = datetime.now()
    
    db.commit()
    return {"message": "Alert acknowledged"}


@router.post("/check-low-stock")
async def check_low_stock(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Manually trigger low stock check"""
    # Get all medicines with stock
    medicines = db.query(Medicine).filter(Medicine.is_active == True).all()
    
    alerts_created = 0
    for medicine in medicines:
        total_stock = sum([b.quantity for b in medicine.batches if not b.is_expired])
        
        # Check if already has active low stock alert
        existing_alert = db.query(Alert).filter(
            Alert.medicine_id == medicine.id,
            Alert.alert_type == AlertType.LOW_STOCK,
            Alert.is_acknowledged == False
        ).first()
        
        if existing_alert:
            continue
        
        # Simple threshold - in production, use forecasted demand
        if total_stock < 20:  # Example threshold
            severity = "critical" if total_stock == 0 else "high" if total_stock < 10 else "medium"
            
            alert = Alert(
                alert_type=AlertType.STOCK_OUT if total_stock == 0 else AlertType.LOW_STOCK,
                medicine_id=medicine.id,
                message=f"{medicine.name} ({medicine.sku}) has low stock: {total_stock} units remaining",
                severity=severity
            )
            db.add(alert)
            alerts_created += 1
    
    db.commit()
    return {"message": f"Created {alerts_created} low stock alerts"}


@router.get("/stats")
async def get_alert_stats(db: Session = Depends(get_db)):
    """Get alert statistics"""
    total_alerts = db.query(Alert).count()
    unacknowledged = db.query(Alert).filter(Alert.is_acknowledged == False).count()
    
    by_type = db.query(
        Alert.alert_type,
        func.count(Alert.id).label('count')
    ).group_by(Alert.alert_type).all()
    
    by_severity = db.query(
        Alert.severity,
        func.count(Alert.id).label('count')
    ).group_by(Alert.severity).all()
    
    return {
        "total_alerts": total_alerts,
        "unacknowledged": unacknowledged,
        "by_type": {str(t[0]): t[1] for t in by_type},
        "by_severity": {s[0]: s[1] for s in by_severity}
    }


