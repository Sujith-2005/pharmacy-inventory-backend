"""
Suppliers router
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime
import uuid

from database import get_db
from models import Supplier, PurchaseOrder, PurchaseOrderItem, Medicine
from schemas import SupplierCreate, SupplierResponse, PurchaseOrderCreate, PurchaseOrderResponse
from auth import get_current_active_user

router = APIRouter()


@router.get("/", response_model=List[SupplierResponse])
async def get_suppliers(
    active_only: bool = True,
    db: Session = Depends(get_db)
):
    """Get list of suppliers"""
    query = db.query(Supplier)
    if active_only:
        query = query.filter(Supplier.is_active == True)
    
    suppliers = query.all()
    return suppliers


@router.get("/{supplier_id}", response_model=SupplierResponse)
async def get_supplier(supplier_id: int, db: Session = Depends(get_db)):
    """Get supplier details"""
    supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return supplier


@router.post("/", response_model=SupplierResponse)
async def create_supplier(
    supplier: SupplierCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Create a new supplier"""
    db_supplier = Supplier(**supplier.dict())
    db.add(db_supplier)
    db.commit()
    db.refresh(db_supplier)
    return db_supplier


@router.put("/{supplier_id}", response_model=SupplierResponse)
async def update_supplier(
    supplier_id: int,
    supplier: SupplierCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Update supplier"""
    db_supplier = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if not db_supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    
    for key, value in supplier.dict().items():
        setattr(db_supplier, key, value)
    
    db.commit()
    db.refresh(db_supplier)
    return db_supplier


@router.post("/purchase-orders", response_model=PurchaseOrderResponse)
async def create_purchase_order(
    po: PurchaseOrderCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Create a purchase order"""
    supplier = db.query(Supplier).filter(Supplier.id == po.supplier_id).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")
    
    # Generate PO number
    po_number = f"PO-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"
    
    # Calculate total amount
    total_amount = 0
    for item in po.items:
        medicine = db.query(Medicine).filter(Medicine.id == item.medicine_id).first()
        if not medicine:
            raise HTTPException(status_code=404, detail=f"Medicine {item.medicine_id} not found")
        
        unit_price = item.unit_price or medicine.cost or 0
        total_amount += item.quantity * unit_price
    
    # Create PO
    db_po = PurchaseOrder(
        supplier_id=po.supplier_id,
        po_number=po_number,
        total_amount=total_amount,
        created_by=current_user.id,
        status="draft"
    )
    db.add(db_po)
    db.flush()
    
    # Create PO items
    for item in po.items:
        medicine = db.query(Medicine).filter(Medicine.id == item.medicine_id).first()
        unit_price = item.unit_price or medicine.cost or 0
        
        po_item = PurchaseOrderItem(
            po_id=db_po.id,
            medicine_id=item.medicine_id,
            quantity=item.quantity,
            unit_price=unit_price
        )
        db.add(po_item)
    
    db.commit()
    db.refresh(db_po)
    return db_po


@router.get("/purchase-orders", response_model=List[PurchaseOrderResponse])
async def get_purchase_orders(
    supplier_id: int = None,
    status: str = None,
    db: Session = Depends(get_db)
):
    """Get purchase orders"""
    query = db.query(PurchaseOrder)
    
    if supplier_id:
        query = query.filter(PurchaseOrder.supplier_id == supplier_id)
    
    if status:
        query = query.filter(PurchaseOrder.status == status)
    
    pos = query.order_by(PurchaseOrder.created_at.desc()).all()
    return pos


@router.post("/purchase-orders/{po_id}/send")
async def send_purchase_order(
    po_id: int,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Send purchase order to supplier (email/SMS)"""
    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).first()
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    
    # Update status
    po.status = "sent"
    db.commit()
    
    # TODO: Implement actual email/SMS sending
    # For now, just return success
    
    return {
        "message": f"Purchase order {po.po_number} sent to supplier",
        "po_number": po.po_number,
        "supplier_email": po.supplier.email if po.supplier.email else None
    }


