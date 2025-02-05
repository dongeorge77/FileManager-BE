from fastapi import APIRouter, Depends, HTTPException
import os
import psutil
from typing import Dict

from app_constants.url import Routes, SystemAPI
from app_constants.log_module import logger
from app_constants.app_configurations import Storage
from scripts.utils.common_utils import format_size, get_storage_status
from scripts.handlers.user_management_handler import get_current_user
from scripts.models.user_management import User


router = APIRouter(prefix=Routes.system)


@router.get(SystemAPI.get_storage)
async def get_storage(current_user: User = Depends(get_current_user)) -> Dict:
    """
    Get system storage information for the disk where files are stored.
    Returns total, used, and free space with safely calculated percentages.
    """
    try:
        logger.info("Fetching storage information...")

        storage_path = os.path.abspath(Storage.PATH)

        disk_usage = psutil.disk_usage(storage_path)

        def safe_percentage(part: float, whole: float) -> float:
            """
            Safely calculate percentage handling division by zero and negative numbers
            """
            try:
                if whole <= 0 or part < 0:
                    return 0.0
                return (part / whole) * 100
            except (ZeroDivisionError, TypeError, ValueError):
                return 0.0

        # Calculate percentages safely
        used_percentage = safe_percentage(disk_usage.used, disk_usage.total)
        free_percentage = safe_percentage(disk_usage.free, disk_usage.total)

        return {
            "total_space": {
                "bytes": disk_usage.total,
                "formatted": format_size(disk_usage.total)
            },
            "used_space": {
                "bytes": disk_usage.used,
                "formatted": format_size(disk_usage.used),
                "percentage": round(used_percentage, 2)
            },
            "free_space": {
                "bytes": disk_usage.free,
                "formatted": format_size(disk_usage.free),
                "percentage": round(free_percentage, 2)
            },
            "health_status": {
                "is_critical": free_percentage < 10,
                "is_warning": free_percentage < 20,
                "status": get_storage_status(free_percentage)
            }
        }

    except Exception as e:
        logger.error(f"Error getting storage information: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve storage information: {str(e)}"
        )