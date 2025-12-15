"""
Demand forecasting using historical data and ML algorithms
"""
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from typing import Dict, List
from models import Medicine, InventoryTransaction, TransactionType, Batch


def calculate_demand_forecast(db: Session, medicine_id: int, horizon_days: int = 30) -> Dict:
    """
    Calculate demand forecast for a medicine based on historical transactions
    
    Args:
        db: Database session
        medicine_id: Medicine ID
        horizon_days: Forecast horizon in days
        
    Returns:
        Dictionary with forecast data
    """
    medicine = db.query(Medicine).filter(Medicine.id == medicine_id).first()
    if not medicine:
        return {
            "forecasted_demand": 0,
            "confidence_score": 0.0,
            "reorder_point": 0,
            "recommended_quantity": 0,
            "reasoning": "Medicine not found"
        }
    
    # Get historical transactions (last 90 days)
    cutoff_date = datetime.now() - timedelta(days=90)
    transactions = db.query(InventoryTransaction).filter(
        InventoryTransaction.medicine_id == medicine_id,
        InventoryTransaction.transaction_type == TransactionType.OUT,
        InventoryTransaction.created_at >= cutoff_date
    ).all()
    
    if not transactions:
        # No historical data - use simple heuristic
        current_stock = sum(batch.quantity for batch in medicine.batches if not batch.is_expired)
        return {
            "forecasted_demand": current_stock * 0.3,  # Conservative estimate
            "confidence_score": 0.3,
            "reorder_point": max(10, int(current_stock * 0.2)),
            "recommended_quantity": max(20, int(current_stock * 0.5)),
            "reasoning": "No historical data available. Using conservative estimates."
        }
    
    # Calculate average daily demand
    total_demand = sum(txn.quantity for txn in transactions)
    days_covered = (datetime.now() - cutoff_date).days
    avg_daily_demand = total_demand / days_covered if days_covered > 0 else 0
    
    # Forecast for horizon
    forecasted_demand = avg_daily_demand * horizon_days
    
    # Calculate confidence based on data points
    confidence_score = min(0.95, 0.5 + (len(transactions) / 100))
    
    # Calculate reorder point (safety stock + lead time demand)
    lead_time_days = 7  # Default lead time
    safety_stock_multiplier = 1.5
    reorder_point = int(avg_daily_demand * lead_time_days * safety_stock_multiplier)
    
    # Recommended order quantity (EOQ-like calculation)
    current_stock = sum(batch.quantity for batch in medicine.batches if not batch.is_expired)
    recommended_quantity = max(
        int(forecasted_demand * 0.3),  # 30% of forecast
        reorder_point - current_stock if current_stock < reorder_point else 0
    )
    
    reasoning = f"Based on {len(transactions)} transactions over {days_covered} days. "
    reasoning += f"Average daily demand: {avg_daily_demand:.2f} units. "
    reasoning += f"Forecasted demand for {horizon_days} days: {forecasted_demand:.2f} units."
    
    return {
        "forecasted_demand": round(forecasted_demand, 2),
        "confidence_score": round(confidence_score, 2),
        "reorder_point": max(1, reorder_point),
        "recommended_quantity": max(0, recommended_quantity),
        "reasoning": reasoning
    }


def batch_forecast_all_medicines(db: Session) -> List[Dict]:
    """
    Generate forecasts for all active medicines
    
    Args:
        db: Database session
        
    Returns:
        List of forecast dictionaries
    """
    medicines = db.query(Medicine).filter(Medicine.is_active == True).all()
    forecasts = []
    
    for medicine in medicines:
        forecast_data = calculate_demand_forecast(db, medicine.id, 30)
        forecast_data["medicine_id"] = medicine.id
        forecasts.append(forecast_data)
    
    return forecasts

