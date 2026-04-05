from __future__ import annotations

from typing import Any, Dict, Optional


def validation_result(is_valid: bool, error: Optional[str], data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "is_valid": is_valid,
        "error": error,
        "data": data or {},
    }