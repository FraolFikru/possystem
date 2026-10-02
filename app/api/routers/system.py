"""System settings, business mode switch, health."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.schemas.schemas import BusinessModeUpdate, SystemSettingOut
from app.models.models import SystemSetting, BusinessMode
from app.core.config import get_settings

router = APIRouter(prefix="/api/system", tags=["System"])


@router.get("/health")
async def health():
    return {"status": "ok", "mode": "offline-first", "version": get_settings().APP_VERSION}


@router.get("/mode")
async def get_mode(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SystemSetting).where(SystemSetting.key == "business_mode")
    )
    setting = result.scalar_one_or_none()
    if setting:
        return {"mode": setting.value}
    return {"mode": get_settings().DEFAULT_BUSINESS_MODE.value}


@router.put("/mode")
async def set_mode(payload: BusinessModeUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SystemSetting).where(SystemSetting.key == "business_mode")
    )
    setting = result.scalar_one_or_none()
    if setting:
        setting.value = payload.mode.value
    else:
        setting = SystemSetting(key="business_mode", value=payload.mode.value)
        db.add(setting)
    await db.flush()
    return {"mode": payload.mode.value, "message": "Business mode updated"}


@router.get("/settings", response_model=list[SystemSettingOut])
async def list_settings(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SystemSetting))
    return list(result.scalars().all())
