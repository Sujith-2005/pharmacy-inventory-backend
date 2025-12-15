"""
Inventory management router
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status, Response
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from datetime import datetime, timedelta
import pandas as pd
import json
import csv
from io import BytesIO, StringIO
import os

from database import get_db
from models import Medicine, Batch, InventoryTransaction, TransactionType, Alert, AlertType
from schemas import MedicineCreate, MedicineResponse, BatchResponse, TransactionCreate, TransactionResponse
from auth import get_current_active_user
from config import settings
from ml_models.categorization import categorize_medicine

# Debug: Print database path on import
print(f"DEBUG: Database URL: {settings.DATABASE_URL}")

router = APIRouter()


def parse_upload_file(file: UploadFile, contents: bytes) -> pd.DataFrame:
    """Parse uploaded file based on its extension"""
    filename = file.filename.lower()
    
    if filename.endswith(('.xlsx', '.xls')):
        # Excel file
        return pd.read_excel(BytesIO(contents))
    elif filename.endswith('.csv'):
        # CSV file - try multiple encodings
        encodings = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']
        for encoding in encodings:
            try:
                return pd.read_csv(BytesIO(contents), encoding=encoding)
            except (UnicodeDecodeError, UnicodeError):
                continue
        # If all encodings fail, try utf-8 with error handling
        return pd.read_csv(BytesIO(contents), encoding='utf-8', errors='ignore')
    elif filename.endswith('.json'):
        # JSON file
        data = json.loads(contents.decode('utf-8'))
        # Handle both list of objects and single object
        if isinstance(data, list):
            return pd.DataFrame(data)
        elif isinstance(data, dict) and 'items' in data:
            return pd.DataFrame(data['items'])
        else:
            return pd.DataFrame([data])
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file format. Please upload Excel (.xlsx, .xls), CSV (.csv), or JSON (.json) files."
        )


def detect_data_type(df: pd.DataFrame) -> str:
    """Detect the type of data in the uploaded file"""
    columns_lower = [col.lower().strip() for col in df.columns]
    
    # Check for inventory/medicine data
    inventory_keywords = ['sku', 'medicine', 'batch', 'quantity', 'expiry', 'mrp', 'cost']
    if any(keyword in ' '.join(columns_lower) for keyword in inventory_keywords):
        return 'inventory'
    
    # Check for doctor/physician data
    doctor_keywords = ['physid', 'doctor', 'physician', 'address', 'phone']
    if any(keyword in ' '.join(columns_lower) for keyword in doctor_keywords):
        return 'doctor'
    
    # Check for supplier data
    supplier_keywords = ['supplier', 'vendor', 'distributor']
    if any(keyword in ' '.join(columns_lower) for keyword in supplier_keywords):
        return 'supplier'
    
    # Default to generic data
    return 'generic'


def normalize_column_names(df: pd.DataFrame, data_type: str = 'inventory') -> pd.DataFrame:
    """Normalize column names to handle variations based on data type"""
    df_normalized = df.copy()
    df_normalized.columns = df_normalized.columns.str.strip()
    
    if data_type == 'inventory':
        column_mapping = {
            'sku': 'SKU',
            'medicine_name': 'Medicine Name',
            'medicine name': 'Medicine Name',
            'name': 'Medicine Name',
            'batch_no': 'Batch No',
            'batch number': 'Batch No',
            'batch': 'Batch No',
            'quantity': 'Quantity',
            'qty': 'Quantity',
            'expiry_date': 'Expiry Date',
            'expiry date': 'Expiry Date',
            'expiry': 'Expiry Date',
            'exp_date': 'Expiry Date',
            'manufacturer': 'Manufacturer',
            'brand': 'Brand',
            'mrp': 'MRP',
            'cost': 'Cost',
            'purchase_price': 'Purchase Price',
            'purchase price': 'Purchase Price',
            'purchase_date': 'Purchase Date',
            'purchase date': 'Purchase Date',
            'schedule': 'Schedule',
            'storage_requirements': 'Storage Requirements',
            'storage requirements': 'Storage Requirements',
            'storage': 'Storage Requirements',
        }
    elif data_type == 'doctor':
        column_mapping = {
            'physid': 'physID',
            'phys_id': 'physID',
            'doctor_id': 'physID',
            'name': 'name',
            'doctor_name': 'name',
            'physician_name': 'name',
            'address': 'address',
            'phone': 'phone',
            'phone_number': 'phone',
            'contact': 'phone',
        }
    else:
        # Generic mapping - just normalize case
        column_mapping = {}
    
    for old_name, new_name in column_mapping.items():
        if old_name.lower() in [col.lower() for col in df_normalized.columns]:
            df_normalized.rename(columns={
                col: new_name for col in df_normalized.columns 
                if col.lower() == old_name.lower()
            }, inplace=True)
    
    return df_normalized


@router.post("/upload", response_model=dict)
async def upload_inventory_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Upload inventory file (Excel, CSV, or JSON) to update inventory"""
    try:
        # Check file size
        contents = await file.read()
        if len(contents) > settings.MAX_UPLOAD_SIZE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File size exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE / (1024*1024):.1f}MB"
            )
        
        # Parse file based on format
        try:
            df = parse_upload_file(file, contents)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Error parsing file: {str(e)}"
            )
        
        if df.empty:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File is empty or contains no data"
            )
        
        # Detect data type
        data_type = detect_data_type(df)
        
        # Normalize column names based on data type
        df = normalize_column_names(df, data_type)
        
        # Handle different data types
        if data_type == 'inventory':
            # Validate required columns for inventory
            required_columns = ['SKU', 'Medicine Name', 'Batch No', 'Quantity', 'Expiry Date']
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Missing required columns for inventory data: {missing_columns}. Found columns: {list(df.columns)}"
                )
        elif data_type == 'doctor':
            # For doctor data, we'll just validate and return success
            # You can extend this to store in a doctors table if needed
            return {
                "message": "Doctor data file uploaded successfully",
                "data_type": "doctor",
                "success_count": len(df),
                "error_count": 0,
                "warning_count": 0,
                "errors": [],
                "warnings": [],
                "total_rows": len(df),
                "preview": df.head(10).to_dict(orient='records')
            }
        elif data_type == 'generic':
            # For generic data, return the parsed data
            return {
                "message": "File uploaded and parsed successfully",
                "data_type": "generic",
                "success_count": len(df),
                "error_count": 0,
                "warning_count": 0,
                "errors": [],
                "warnings": [],
                "total_rows": len(df),
                "columns": list(df.columns),
                "preview": df.head(10).to_dict(orient='records')
            }
        
        errors = []
        success_count = 0
        warnings = []
        
        for idx, row in df.iterrows():
            try:
                # Validate and extract data
                sku = str(row['SKU']).strip()
                if not sku or sku == 'nan':
                    errors.append(f"Row {idx + 2}: SKU is required")
                    continue
                
                name = str(row['Medicine Name']).strip()
                if not name or name == 'nan':
                    errors.append(f"Row {idx + 2}: Medicine Name is required")
                    continue
                
                batch_no = str(row['Batch No']).strip()
                if not batch_no or batch_no == 'nan':
                    errors.append(f"Row {idx + 2}: Batch No is required")
                    continue
                
                try:
                    quantity = int(float(row['Quantity']))
                    if quantity < 0:
                        errors.append(f"Row {idx + 2}: Quantity cannot be negative")
                        continue
                except (ValueError, TypeError):
                    errors.append(f"Row {idx + 2}: Invalid quantity value: {row['Quantity']}")
                    continue
                
                # Parse expiry date - handle various formats
                try:
                    expiry_date_raw = pd.to_datetime(row['Expiry Date'], errors='coerce')
                    if pd.isna(expiry_date_raw):
                        errors.append(f"Row {idx + 2}: Invalid expiry date: {row['Expiry Date']}")
                        continue
                    
                    # Convert to Python datetime, ensuring no timezone
                    if isinstance(expiry_date_raw, pd.Timestamp):
                        expiry_date = expiry_date_raw.to_pydatetime()
                    else:
                        expiry_date = expiry_date_raw
                    
                    # Remove timezone if present (SQLite doesn't handle timezones well)
                    if hasattr(expiry_date, 'tzinfo') and expiry_date.tzinfo is not None:
                        expiry_date = expiry_date.replace(tzinfo=None)
                    
                    # Ensure it's a datetime object
                    if not isinstance(expiry_date, datetime):
                        expiry_date = pd.to_datetime(expiry_date).to_pydatetime()
                        if hasattr(expiry_date, 'tzinfo') and expiry_date.tzinfo is not None:
                            expiry_date = expiry_date.replace(tzinfo=None)
                            
                except Exception as e:
                    errors.append(f"Row {idx + 2}: Could not parse expiry date '{row['Expiry Date']}': {str(e)}")
                    continue
                
                # Get or create medicine
                medicine = db.query(Medicine).filter(Medicine.sku == sku).first()
                if not medicine:
                    # Auto-categorize using AI
                    description = f"{row.get('Manufacturer', '')} {row.get('Brand', '')}".strip()
                    category = categorize_medicine(name, description if description else None)
                    
                    medicine = Medicine(
                        sku=sku,
                        name=name,
                        category=category,
                        manufacturer=row.get('Manufacturer', '') if pd.notna(row.get('Manufacturer')) else None,
                        brand=row.get('Brand', '') if pd.notna(row.get('Brand')) else None,
                        mrp=float(row['MRP']) if pd.notna(row.get('MRP')) and str(row.get('MRP')).strip() else None,
                        cost=float(row['Cost']) if pd.notna(row.get('Cost')) and str(row.get('Cost')).strip() else None,
                        schedule=row.get('Schedule', '') if pd.notna(row.get('Schedule')) else None,
                        storage_requirements=row.get('Storage Requirements', '') if pd.notna(row.get('Storage Requirements')) else None,
                        is_active=True  # Explicitly set to active
                    )
                    db.add(medicine)
                    db.flush()
                else:
                    # Update existing medicine if new data provided
                    if pd.notna(row.get('Manufacturer')) and row.get('Manufacturer'):
                        medicine.manufacturer = row.get('Manufacturer')
                    if pd.notna(row.get('Brand')) and row.get('Brand'):
                        medicine.brand = row.get('Brand')
                    if pd.notna(row.get('MRP')) and str(row.get('MRP')).strip():
                        medicine.mrp = float(row['MRP'])
                    if pd.notna(row.get('Cost')) and str(row.get('Cost')).strip():
                        medicine.cost = float(row['Cost'])
                
                # Create or update batch
                batch = db.query(Batch).filter(
                    Batch.medicine_id == medicine.id,
                    Batch.batch_number == batch_no
                ).first()
                
                if batch:
                    print(f"DEBUG: Updating existing batch {batch_no} for {name}, old qty: {batch.quantity}, new qty: {quantity}")
                    old_quantity = batch.quantity
                    batch.quantity = quantity
                    
                    # expiry_date is already processed above, just ensure it's set correctly
                    batch.expiry_date = expiry_date
                    
                    if pd.notna(row.get('Purchase Date')):
                        try:
                            purchase_date_raw = pd.to_datetime(row.get('Purchase Date'))
                            if isinstance(purchase_date_raw, pd.Timestamp):
                                purchase_date_dt = purchase_date_raw.to_pydatetime()
                            else:
                                purchase_date_dt = purchase_date_raw
                            if hasattr(purchase_date_dt, 'tzinfo') and purchase_date_dt.tzinfo is not None:
                                purchase_date_dt = purchase_date_dt.replace(tzinfo=None)
                            batch.purchase_date = purchase_date_dt
                        except:
                            pass
                    if pd.notna(row.get('Purchase Price')) and str(row.get('Purchase Price')).strip():
                        try:
                            batch.purchase_price = float(row.get('Purchase Price'))
                        except:
                            pass
                    
                    # Check if batch is expired (only mark as expired if expiry date has passed)
                    # expiry_date is already processed above as a datetime without timezone
                    today = datetime.now().date()
                    expiry_date_only = expiry_date.date() if hasattr(expiry_date, 'date') else expiry_date
                    
                    if expiry_date_only < today:
                        batch.is_expired = True
                        warnings.append(f"Row {idx + 2}: Batch {batch_no} for {name} has already expired (Expiry: {expiry_date_only})")
                    else:
                        # Ensure batch is not marked as expired if it hasn't expired yet
                        batch.is_expired = False
                    
                    # Create transaction for quantity change
                    if old_quantity != quantity:
                        transaction = InventoryTransaction(
                            medicine_id=medicine.id,
                            batch_id=batch.id,
                            transaction_type=TransactionType.ADJUSTMENT,
                            quantity=quantity - old_quantity,
                            notes=f"File upload adjustment - {file.filename}",
                            created_by=current_user.id
                        )
                        db.add(transaction)
                else:
                    # expiry_date is already processed above as a datetime without timezone
                    # Check if batch is expired (only mark as expired if expiry date has passed)
                    today = datetime.now().date()
                    expiry_date_only = expiry_date.date() if hasattr(expiry_date, 'date') else expiry_date
                    
                    is_expired = False
                    if expiry_date_only < today:
                        is_expired = True
                        warnings.append(f"Row {idx + 2}: Batch {batch_no} for {name} has already expired (Expiry: {expiry_date_only})")
                    
                    # Handle purchase date
                    purchase_date_dt = None
                    if pd.notna(row.get('Purchase Date')):
                        try:
                            purchase_date_raw = pd.to_datetime(row.get('Purchase Date'))
                            if isinstance(purchase_date_raw, pd.Timestamp):
                                purchase_date_dt = purchase_date_raw.to_pydatetime()
                            else:
                                purchase_date_dt = purchase_date_raw
                            if hasattr(purchase_date_dt, 'tzinfo') and purchase_date_dt.tzinfo is not None:
                                purchase_date_dt = purchase_date_dt.replace(tzinfo=None)
                        except:
                            pass
                    
                    batch = Batch(
                        medicine_id=medicine.id,
                        batch_number=batch_no,
                        quantity=quantity,
                        expiry_date=expiry_date,  # Already processed as datetime without timezone above
                        purchase_date=purchase_date_dt,
                        purchase_price=float(row.get('Purchase Price')) if pd.notna(row.get('Purchase Price')) and str(row.get('Purchase Price')).strip() else None,
                        is_expired=is_expired
                    )
                    
                    print(f"DEBUG: Creating new batch {batch_no} for {name}, qty: {quantity}, expired: {is_expired}, expiry: {expiry_date_only}")
                    db.add(batch)
                    db.flush()  # Flush to get batch.id
                    
                    # Create transaction
                    transaction = InventoryTransaction(
                        medicine_id=medicine.id,
                        batch_id=batch.id,
                        transaction_type=TransactionType.IN,
                        quantity=quantity,
                        notes=f"File upload - {file.filename}",
                        created_by=current_user.id
                    )
                    db.add(transaction)
                
                success_count += 1
                
            except Exception as e:
                import traceback
                error_msg = f"Row {idx + 2}: {str(e)}"
                errors.append(error_msg)
                # Log full traceback for debugging
                error_trace = traceback.format_exc()
                print(f"ERROR: Upload error at row {idx + 2}: {error_msg}")
                print(f"ERROR: Traceback: {error_trace}")
                # Continue processing other rows - don't stop the entire upload
        
        # Commit all changes in a single transaction
        print(f"DEBUG: About to commit. Success count: {success_count}, Errors: {len(errors)}")
        print(f"DEBUG: Total rows processed: {len(df)}, Success: {success_count}, Failed: {len(errors)}")
        
        if success_count == 0:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"No valid rows to save. All {len(df)} rows had errors. First few errors: {errors[:5]}"
            )
        
        try:
            db.commit()
            print(f"DEBUG: Commit successful - committed {success_count} items")
        except Exception as e:
            db.rollback()
            import traceback
            error_trace = traceback.format_exc()
            print(f"DEBUG: Commit failed: {e}")
            print(f"DEBUG: Traceback: {error_trace}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Database commit failed: {str(e)}"
            )
        
        # Verify data was saved by querying back using the same session
        # Refresh the session to ensure we see committed data
        db.expire_all()
        try:
            # Check all medicines (including inactive) for debugging
            total_medicines_all = db.query(Medicine).count()
            saved_medicines = db.query(Medicine).filter(Medicine.is_active == True).count()
            inactive_medicines = db.query(Medicine).filter(Medicine.is_active == False).count()
            saved_batches = db.query(Batch).filter(
                Batch.quantity > 0, 
                Batch.is_expired == False
            ).count()
            all_batches = db.query(Batch).count()
            expired_batches = db.query(Batch).filter(Batch.is_expired == True).count()
            zero_qty_batches = db.query(Batch).filter(Batch.quantity == 0).count()
            print(f"DEBUG: After commit - Total medicines: {total_medicines_all} (Active: {saved_medicines}, Inactive: {inactive_medicines})")
            print(f"DEBUG: After commit - Batches: {all_batches} (Active: {saved_batches}, Expired: {expired_batches}, Zero qty: {zero_qty_batches})")
        except Exception as e:
            import traceback
            print(f"ERROR: Could not verify saved data: {e}")
            print(f"ERROR: Traceback: {traceback.format_exc()}")
            saved_medicines = 0
            saved_batches = 0
            all_batches = 0
            expired_batches = 0
        
        # Check for expiries and create alerts (don't fail if this errors)
        try:
            check_expiry_alerts(db)
            db.commit()  # Commit alerts
        except Exception as e:
            print(f"Warning: Error checking expiry alerts: {e}")
            db.rollback()  # Rollback only the alerts, not the main data
        
        # Check for low stock and create alerts (don't fail if this errors)
        try:
            check_low_stock_alerts(db)
            db.commit()  # Commit alerts
        except Exception as e:
            print(f"Warning: Error checking low stock alerts: {e}")
            db.rollback()  # Rollback only the alerts, not the main data
        
        # Get detailed verification info (query again to be sure)
        try:
            # Query again to ensure we have latest counts
            final_medicines = db.query(Medicine).filter(Medicine.is_active == True).count()
            final_active_batches = db.query(Batch).filter(
                Batch.quantity > 0, 
                Batch.is_expired == False
            ).count()
            final_all_batches = db.query(Batch).count()
            final_expired_batches = db.query(Batch).filter(Batch.is_expired == True).count()
            
            verification_details = {
                "total_medicines": final_medicines,
                "active_batches": final_active_batches,
                "all_batches": final_all_batches,
                "expired_batches": final_expired_batches
            }
            print(f"DEBUG: Final verification - Medicines: {final_medicines}, Active batches: {final_active_batches}, All batches: {final_all_batches}, Expired: {final_expired_batches}")
        except Exception as e:
            import traceback
            print(f"ERROR: Could not get verification details: {e}")
            print(f"ERROR: Traceback: {traceback.format_exc()}")
            verification_details = {
                "total_medicines": saved_medicines if 'saved_medicines' in locals() else 0,
                "active_batches": saved_batches if 'saved_batches' in locals() else 0,
                "all_batches": all_batches if 'all_batches' in locals() else 0,
                "expired_batches": expired_batches if 'expired_batches' in locals() else 0
            }
        
        return {
            "message": "Upload completed",
            "success_count": success_count,
            "error_count": len(errors),
            "warning_count": len(warnings),
            "errors": errors[:50],  # Return first 50 errors
            "warnings": warnings[:20],  # Return first 20 warnings
            "total_rows": len(df),
            "data_type": "inventory",
            "verification": verification_details
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        error_trace = traceback.format_exc()
        print(f"ERROR: Exception in upload_inventory_file: {e}")
        print(f"ERROR: Traceback: {error_trace}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing file: {str(e)}"
        )


@router.post("/upload-excel", response_model=dict)
async def upload_inventory_excel(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Upload Excel file to update inventory (legacy endpoint for backward compatibility)"""
    return await upload_inventory_file(file, db, current_user)


def check_expiry_alerts(db: Session):
    """Check for upcoming expiries and create alerts"""
    today = datetime.now().date()
    for days in settings.EXPIRY_ALERT_DAYS:
        threshold_date = today + timedelta(days=days)
        # Convert threshold_date to datetime for comparison
        threshold_datetime = datetime.combine(threshold_date, datetime.min.time())
        batches = db.query(Batch).filter(
            Batch.expiry_date <= threshold_datetime,
            Batch.is_expired == False,
            Batch.quantity > 0
        ).all()
        
        for batch in batches:
            # Check if alert already exists
            existing_alert = db.query(Alert).filter(
                Alert.batch_id == batch.id,
                Alert.alert_type == AlertType.EXPIRY_WARNING,
                Alert.is_acknowledged == False
            ).first()
            
            if not existing_alert:
                # Handle both date and datetime expiry_date
                if isinstance(batch.expiry_date, datetime):
                    expiry_date_only = batch.expiry_date.date()
                else:
                    expiry_date_only = batch.expiry_date
                
                days_until_expiry = (expiry_date_only - today).days
                if days_until_expiry >= 0:  # Only alert for future expiries
                    alert = Alert(
                        alert_type=AlertType.EXPIRY_WARNING,
                        medicine_id=batch.medicine_id,
                        batch_id=batch.id,
                        message=f"{batch.medicine.name} (Batch: {batch.batch_number}) expires in {days_until_expiry} days",
                        severity="high" if days_until_expiry <= 30 else "medium"
                    )
                    db.add(alert)
    
    db.commit()


def check_low_stock_alerts(db: Session):
    """Check for low stock items and create alerts"""
    # Get stock levels
    stock_levels = db.query(
        Medicine.id,
        Medicine.name,
        func.sum(Batch.quantity).label('total_quantity')
    ).join(Batch).filter(
        Batch.quantity > 0,
        Batch.is_expired == False
    ).group_by(Medicine.id).all()
    
    for medicine_id, medicine_name, total_quantity in stock_levels:
        # Simple threshold - in production, compare against forecasted demand
        if total_quantity < 20:  # Low stock threshold
            # Check if alert already exists
            existing_alert = db.query(Alert).filter(
                Alert.medicine_id == medicine_id,
                Alert.alert_type == AlertType.LOW_STOCK,
                Alert.is_acknowledged == False
            ).first()
            
            if not existing_alert:
                alert = Alert(
                    alert_type=AlertType.LOW_STOCK,
                    medicine_id=medicine_id,
                    message=f"{medicine_name} is running low (Stock: {total_quantity})",
                    severity="high" if total_quantity == 0 else "medium"
                )
                db.add(alert)
    
    db.commit()


@router.get("/download-template")
async def download_template(format: str = "excel"):
    """Download inventory upload template in specified format"""
    # Create sample data
    sample_data = {
        'SKU': ['MED001', 'MED002', 'MED003'],
        'Medicine Name': ['Paracetamol 500mg', 'Azithromycin 500mg', 'Metformin 500mg'],
        'Batch No': ['BATCH001', 'BATCH002', 'BATCH003'],
        'Quantity': [100, 50, 75],
        'Expiry Date': ['2025-12-31', '2025-11-30', '2026-01-15'],
        'Manufacturer': ['ABC Pharma', 'XYZ Pharma', 'DEF Pharma'],
        'Brand': ['Brand A', 'Brand B', 'Brand C'],
        'MRP': [10.50, 25.00, 5.75],
        'Cost': [8.00, 20.00, 4.50],
        'Purchase Date': ['2024-01-15', '2024-01-20', '2024-01-25'],
        'Purchase Price': [8.00, 20.00, 4.50],
        'Schedule': ['OTC', 'Schedule H', 'Schedule H'],
        'Storage Requirements': ['Room Temperature', 'Room Temperature', 'Room Temperature']
    }
    
    df = pd.DataFrame(sample_data)
    
    if format.lower() == "csv":
        # Generate CSV
        output = StringIO()
        df.to_csv(output, index=False)
        output.seek(0)
        
        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={
                "Content-Disposition": "attachment; filename=inventory_template.csv"
            }
        )
    elif format.lower() == "json":
        # Generate JSON
        json_data = df.to_dict(orient='records')
        return Response(
            content=json.dumps(json_data, indent=2, default=str),
            media_type="application/json",
            headers={
                "Content-Disposition": "attachment; filename=inventory_template.json"
            }
        )
    else:
        # Generate Excel (default)
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Inventory')
        
        output.seek(0)
        return Response(
            content=output.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": "attachment; filename=inventory_template.xlsx"
            }
        )


@router.get("/medicines", response_model=List[MedicineResponse])
async def get_medicines(
    skip: int = 0,
    limit: int = 100,
    category: str = None,
    search: str = None,
    db: Session = Depends(get_db)
):
    """Get list of medicines"""
    # First check total medicines (including inactive) for debugging
    total_all = db.query(Medicine).count()
    total_active = db.query(Medicine).filter(Medicine.is_active == True).count()
    total_inactive = db.query(Medicine).filter(Medicine.is_active == False).count()
    print(f"DEBUG: get_medicines - Total medicines: {total_all} (Active: {total_active}, Inactive: {total_inactive})")
    
    query = db.query(Medicine).filter(Medicine.is_active == True)
    
    if category:
        query = query.filter(Medicine.category == category)
    
    if search:
        query = query.filter(
            (Medicine.name.ilike(f"%{search}%")) |
            (Medicine.sku.ilike(f"%{search}%"))
        )
    
    medicines = query.order_by(Medicine.created_at.desc()).offset(skip).limit(limit).all()
    
    # Debug logging
    total_count = db.query(Medicine).filter(Medicine.is_active == True).count()
    print(f"DEBUG: get_medicines - Total in DB: {total_count}, Returning: {len(medicines)} (skip={skip}, limit={limit}, category={category}, search={search})")
    if len(medicines) > 0:
        print(f"DEBUG: First medicine: {medicines[0].name} (SKU: {medicines[0].sku}, ID: {medicines[0].id})")
    elif total_count > 0:
        print(f"WARNING: Database has {total_count} medicines but query returned 0. Check filters!")
    
    return medicines


@router.get("/medicines/{medicine_id}", response_model=MedicineResponse)
async def get_medicine(medicine_id: int, db: Session = Depends(get_db)):
    """Get medicine details"""
    medicine = db.query(Medicine).filter(Medicine.id == medicine_id).first()
    if not medicine:
        raise HTTPException(status_code=404, detail="Medicine not found")
    return medicine


@router.post("/medicines", response_model=MedicineResponse)
async def create_medicine(
    medicine: MedicineCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Create a new medicine"""
    # Check if SKU already exists
    existing = db.query(Medicine).filter(Medicine.sku == medicine.sku).first()
    if existing:
        raise HTTPException(status_code=400, detail="SKU already exists")
    
    # Auto-categorize if not provided
    if not medicine.category:
        medicine.category = categorize_medicine(medicine.name, medicine.manufacturer or "", medicine.brand or "")
    
    db_medicine = Medicine(**medicine.dict())
    db.add(db_medicine)
    db.commit()
    db.refresh(db_medicine)
    return db_medicine


@router.get("/medicines/{medicine_id}/batches", response_model=List[BatchResponse])
async def get_medicine_batches(
    medicine_id: int,
    db: Session = Depends(get_db)
):
    """Get batches for a medicine"""
    medicine = db.query(Medicine).filter(Medicine.id == medicine_id).first()
    if not medicine:
        raise HTTPException(status_code=404, detail="Medicine not found")
    
    # Get all batches, including expired ones (for complete view)
    # Frontend can filter if needed
    batches = db.query(Batch).filter(
        Batch.medicine_id == medicine_id
    ).order_by(Batch.expiry_date).all()
    
    return batches


@router.get("/stock-levels")
async def get_stock_levels(
    low_stock_only: bool = False,
    db: Session = Depends(get_db)
):
    """Get stock levels for all medicines"""
    # Use subquery to get stock levels for active batches only
    from sqlalchemy import and_
    
    # First, get all active medicines
    medicines = db.query(Medicine).filter(Medicine.is_active == True).all()
    
    print(f"DEBUG: get_stock_levels - Processing {len(medicines)} medicines, low_stock_only={low_stock_only}")
    
    total_batches_in_db = db.query(Batch).count()
    active_batches_in_db = db.query(Batch).filter(
        Batch.quantity > 0,
        Batch.is_expired == False
    ).count()
    
    print(f"DEBUG: Total batches in DB: {total_batches_in_db}, Active batches: {active_batches_in_db}")
    
    results = []
    for medicine in medicines:
        # Get active batches for this medicine
        active_batches = db.query(Batch).filter(
            and_(
                Batch.medicine_id == medicine.id,
                Batch.quantity > 0,
                Batch.is_expired == False
            )
        ).all()
        
        # Also get all batches for debugging
        all_batches = db.query(Batch).filter(Batch.medicine_id == medicine.id).all()
        
        total_quantity = sum([b.quantity for b in active_batches])
        nearest_expiry = min([b.expiry_date for b in active_batches]) if active_batches else None
        
        # Debug logging for first few medicines
        if len(results) < 3:
            print(f"DEBUG: Medicine {medicine.name} (ID: {medicine.id}) - All batches: {len(all_batches)}, Active: {len(active_batches)}, Total qty: {total_quantity}")
            if all_batches:
                for b in all_batches:
                    print(f"  Batch {b.batch_number}: qty={b.quantity}, expired={b.is_expired}, expiry={b.expiry_date.date() if b.expiry_date else None}")
        
        # Apply low stock filter if needed
        if low_stock_only and total_quantity >= 50:
            continue
        
        results.append({
            "medicine_id": medicine.id,
            "sku": medicine.sku,
            "name": medicine.name,
            "category": medicine.category,
            "total_quantity": total_quantity,
            "nearest_expiry": nearest_expiry.isoformat() if nearest_expiry else None
        })
    
    print(f"DEBUG: get_stock_levels - Returning {len(results)} stock levels")
    if len(medicines) > 0 and len(results) == 0:
        print(f"WARNING: {len(medicines)} medicines exist but 0 stock levels returned. All batches might be expired or have 0 quantity!")
    
    return results


@router.post("/transactions", response_model=TransactionResponse)
async def create_transaction(
    transaction: TransactionCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_active_user)
):
    """Create an inventory transaction"""
    medicine = db.query(Medicine).filter(Medicine.id == transaction.medicine_id).first()
    if not medicine:
        raise HTTPException(status_code=404, detail="Medicine not found")
    
    # Update batch quantity if batch_id provided
    if transaction.batch_id:
        batch = db.query(Batch).filter(Batch.id == transaction.batch_id).first()
        if not batch:
            raise HTTPException(status_code=404, detail="Batch not found")
        
        if transaction.transaction_type == TransactionType.OUT:
            if batch.quantity < transaction.quantity:
                raise HTTPException(status_code=400, detail="Insufficient stock")
            batch.quantity -= transaction.quantity
        elif transaction.transaction_type == TransactionType.IN:
            batch.quantity += transaction.quantity
    
    db_transaction = InventoryTransaction(
        **transaction.dict(),
        created_by=current_user.id
    )
    db.add(db_transaction)
    db.commit()
    db.refresh(db_transaction)
    return db_transaction


