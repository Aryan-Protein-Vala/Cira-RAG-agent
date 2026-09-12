import asyncio
import socket
import uuid
from typing import Any, List, Optional
from passlib.context import CryptContext
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db, Partner, Tenant, SuperAdmin, UsageLog
from auth import create_token, validate_and_extract, bearer_scheme

router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ── Pydantic Request Models ────────────────────────────────────────────────
class AdminLoginRequest(BaseModel):
    username: str
    password: str

class PartnerCreate(BaseModel):
    name: str
    email: str
    password: str
    slug: str
    brand_name: Optional[str] = None
    plan: str = "pilot"
    max_tenants: int = 3

class TenantCreate(BaseModel):
    company_name: str
    company_db: str
    sap_host: str
    sap_hana_port: int = 30013
    sap_sl_port: int = 50000
    sap_db_user: str
    sap_db_password: str
    sap_sl_user: str = "manager"
    sap_sl_password: str
    backend_type: str = "hana"
    currency: str = "INR"

# ── Pydantic Response Models (Sanitized - No Leaked Secrets) ───────────────
class PartnerResponse(BaseModel):
    id: str
    name: str
    slug: str
    email: str
    logo_url: Optional[str] = None
    brand_name: Optional[str] = None
    plan: str = "pilot"
    max_tenants: int = 3
    is_active: int = 1
    created_at: Optional[Any] = None

    class Config:
        from_attributes = True

class TenantResponse(BaseModel):
    id: str
    partner_id: str
    company_name: str
    company_db: str
    sap_host: str
    sap_hana_port: int = 30013
    sap_sl_port: int = 50000
    sap_db_user: str
    sap_sl_user: str = "manager"
    backend_type: str = "hana"
    currency: str = "INR"
    locale: str = "en-IN"
    write_enabled: int = 0
    is_active: int = 1
    created_at: Optional[Any] = None

    class Config:
        from_attributes = True

# ── Authentication Helper ──────────────────────────────────────────────────
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def require_role(roles_needed: List[str]):
    def role_checker(ctx: dict = Depends(validate_and_extract)):
        user_roles = ctx.get("roles", [])
        if not any(r in user_roles for r in roles_needed):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
        return ctx
    return role_checker

# ── SuperAdmin Routes ──────────────────────────────────────────────────────
@router.post("/superadmin/login")
async def superadmin_login(request: AdminLoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SuperAdmin).where(SuperAdmin.email == request.username))
    admin = result.scalars().first()
    
    if admin and verify_password(request.password, admin.password_hash):
        minted = create_token(admin.id, "SuperAdmin", ["superadmin"])
        return {"token": minted["token"], "expires_at": minted.get("expires_at")}
    
    raise HTTPException(status_code=401, detail="Invalid superadmin credentials")

@router.get("/superadmin/partners", response_model=List[PartnerResponse])
async def get_partners(ctx: dict = Depends(require_role(["superadmin"])), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Partner))
    return result.scalars().all()

@router.post("/superadmin/partners", response_model=PartnerResponse)
async def create_partner(partner: PartnerCreate, ctx: dict = Depends(require_role(["superadmin"])), db: AsyncSession = Depends(get_db)):
    clean_slug = partner.slug.strip().lower()
    existing = await db.execute(
        select(Partner).where((Partner.slug == clean_slug) | (Partner.email == partner.email.strip().lower()))
    )
    if existing.scalars().first():
        raise HTTPException(status_code=409, detail="Partner with this slug or email already exists")

    new_partner = Partner(
        id=str(uuid.uuid4()),
        name=partner.name,
        slug=clean_slug,
        email=partner.email.strip().lower(),
        password_hash=get_password_hash(partner.password),
        brand_name=partner.brand_name,
        plan=partner.plan,
        max_tenants=partner.max_tenants,
        is_active=1
    )
    db.add(new_partner)
    await db.commit()
    await db.refresh(new_partner)
    return new_partner

@router.get("/superadmin/tenants", response_model=List[TenantResponse])
async def superadmin_get_tenants(ctx: dict = Depends(require_role(["superadmin"])), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Tenant))
    return result.scalars().all()

# ── Partner Admin Routes ────────────────────────────────────────────────────
@router.post("/admin/login")
async def partner_login(request: AdminLoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Partner).where(Partner.email == request.username.strip().lower()))
    partner = result.scalars().first()
    
    if partner and verify_password(request.password, partner.password_hash):
        if not partner.is_active:
            raise HTTPException(status_code=403, detail="Partner account is suspended/inactive")
        minted = create_token(partner.id, partner.name, ["partner_admin"])
        return {"token": minted["token"], "expires_at": minted.get("expires_at")}
    
    raise HTTPException(status_code=401, detail="Invalid partner credentials")

@router.get("/admin/tenants", response_model=List[TenantResponse])
async def get_my_tenants(ctx: dict = Depends(require_role(["partner_admin", "superadmin"])), db: AsyncSession = Depends(get_db)):
    if "superadmin" in ctx.get("roles", []):
        result = await db.execute(select(Tenant))
    else:
        result = await db.execute(select(Tenant).where(Tenant.partner_id == ctx["employee_id"]))
    return result.scalars().all()

@router.post("/admin/tenants", response_model=TenantResponse)
async def create_tenant(tenant: TenantCreate, ctx: dict = Depends(require_role(["partner_admin", "superadmin"])), db: AsyncSession = Depends(get_db)):
    partner_id = ctx["employee_id"]
    result = await db.execute(select(Partner).where(Partner.id == partner_id))
    partner = result.scalars().first()
    if not partner and "superadmin" not in ctx.get("roles", []):
        raise HTTPException(status_code=404, detail="Partner not found")
        
    if partner:
        if not partner.is_active:
            raise HTTPException(status_code=403, detail="Partner account is inactive")
        count_res = await db.execute(select(func.count(Tenant.id)).where(Tenant.partner_id == partner_id))
        current_tenants = count_res.scalar() or 0
        if current_tenants >= partner.max_tenants:
            raise HTTPException(status_code=400, detail=f"Maximum tenants limit ({partner.max_tenants}) reached")
            
    from ssrf import is_safe_host
    if not is_safe_host(tenant.sap_host):
        raise HTTPException(status_code=400, detail="Invalid or unsafe SAP host provided. Only private network IPs or whitelisted domains are permitted for security.")

    clean_db = tenant.company_db.strip()
    dup = await db.execute(select(Tenant).where(Tenant.company_db == clean_db))
    if dup.scalars().first():
        raise HTTPException(status_code=409, detail=f"A tenant with Company DB '{clean_db}' already exists.")

    new_tenant = Tenant(
        id=str(uuid.uuid4()),
        partner_id=partner_id,
        company_name=tenant.company_name,
        company_db=clean_db,
        sap_host=tenant.sap_host,
        sap_hana_port=tenant.sap_hana_port,
        sap_sl_port=tenant.sap_sl_port,
        sap_db_user=tenant.sap_db_user,
        sap_db_password=tenant.sap_db_password,
        sap_sl_user=tenant.sap_sl_user,
        sap_sl_password=tenant.sap_sl_password,
        backend_type=tenant.backend_type,
        currency=tenant.currency,
        write_enabled=0,
        is_active=1
    )
    db.add(new_tenant)
    await db.commit()
    await db.refresh(new_tenant)
    return new_tenant

@router.delete("/admin/tenants/{tenant_id}")
async def delete_tenant(tenant_id: str, ctx: dict = Depends(require_role(["partner_admin", "superadmin"])), db: AsyncSession = Depends(get_db)):
    partner_id = ctx["employee_id"]
    query = select(Tenant).where(Tenant.id == tenant_id)
    if "superadmin" not in ctx.get("roles", []):
        query = query.where(Tenant.partner_id == partner_id)
    result = await db.execute(query)
    tenant = result.scalars().first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
        
    await db.delete(tenant)
    await db.commit()
    return {"ok": True, "deleted_id": tenant_id}

@router.post("/admin/tenants/{tenant_id}/test")
async def test_tenant_connection(tenant_id: str, ctx: dict = Depends(require_role(["partner_admin", "superadmin"])), db: AsyncSession = Depends(get_db)):
    partner_id = ctx["employee_id"]
    query = select(Tenant).where(Tenant.id == tenant_id)
    if "superadmin" not in ctx.get("roles", []):
        query = query.where(Tenant.partner_id == partner_id)
    result = await db.execute(query)
    tenant = result.scalars().first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    from ssrf import is_safe_host
    if not is_safe_host(tenant.sap_host):
        raise HTTPException(status_code=400, detail="SAP host violates network safety rules (SSRF guard).")

    probe = {
        "db_port_reachable": False,
        "service_layer_port_reachable": False,
        "host": tenant.sap_host,
        "hana_port": tenant.sap_hana_port,
        "sl_port": tenant.sap_sl_port
    }
    # Non-blocking async probe for DB port
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(tenant.sap_host, tenant.sap_hana_port), timeout=2.5
        )
        writer.close()
        await writer.wait_closed()
        probe["db_port_reachable"] = True
    except Exception as e:
        probe["db_port_error"] = str(e)

    # Non-blocking async probe for Service Layer port
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(tenant.sap_host, tenant.sap_sl_port), timeout=2.5
        )
        writer.close()
        await writer.wait_closed()
        probe["service_layer_port_reachable"] = True
    except Exception as e:
        probe["sl_port_error"] = str(e)

    probe["success"] = probe["db_port_reachable"] or probe["service_layer_port_reachable"]
    return probe

