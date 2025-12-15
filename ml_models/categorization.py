"""
Medicine categorization using ML/NLP
"""
import re
from typing import Dict, Optional


# Common medicine categories and keywords
MEDICINE_CATEGORIES = {
    "Antibiotics": ["antibiotic", "amoxicillin", "penicillin", "cephalexin", "azithromycin", "ciprofloxacin"],
    "Pain Relief": ["paracetamol", "acetaminophen", "ibuprofen", "aspirin", "diclofenac", "naproxen"],
    "Cardiovascular": ["atenolol", "amlodipine", "lisinopril", "metoprolol", "ramipril", "blood pressure"],
    "Diabetes": ["metformin", "insulin", "glipizide", "diabetes", "blood sugar"],
    "Respiratory": ["salbutamol", "inhaler", "asthma", "cough", "expectorant"],
    "Gastrointestinal": ["omeprazole", "ranitidine", "antacid", "laxative", "stomach"],
    "Vitamins & Supplements": ["vitamin", "calcium", "iron", "multivitamin", "supplement"],
    "Dermatology": ["ointment", "cream", "skin", "dermatitis", "eczema"],
    "Eye Care": ["eye drops", "ophthalmic", "conjunctivitis"],
    "Ear Care": ["ear drops", "otic"],
    "Antiseptics": ["antiseptic", "disinfectant", "betadine", "dettol"],
    "First Aid": ["bandage", "gauze", "plaster", "first aid"],
    "General": []  # Default category
}


def categorize_medicine(name: str, description: Optional[str] = None) -> str:
    """
    Categorize medicine based on name and description using keyword matching
    
    Args:
        name: Medicine name
        description: Optional medicine description
        
    Returns:
        Category name
    """
    if not name:
        return "General"
    
    # Combine name and description for analysis
    text = name.lower()
    if description:
        text += " " + description.lower()
    
    # Score each category
    category_scores = {}
    for category, keywords in MEDICINE_CATEGORIES.items():
        if category == "General":
            continue
        score = 0
        for keyword in keywords:
            if keyword.lower() in text:
                score += 1
        if score > 0:
            category_scores[category] = score
    
    # Return category with highest score, or General if no match
    if category_scores:
        return max(category_scores.items(), key=lambda x: x[1])[0]
    
    return "General"

