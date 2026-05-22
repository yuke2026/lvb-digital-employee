"""数字员工路由：列表、详情、启用/停用"""
from fastapi import APIRouter, Depends, HTTPException, status
from app.schemas.user import EmployeeResponse, EmployeeToggleResponse
from app.core.deps import get_current_user
from app.services.db import db

router = APIRouter()


@router.get("", response_model=list[EmployeeResponse])
async def list_employees():
    """获取所有数字员工列表"""
    employees = db.list_employees()
    return [
        EmployeeResponse(
            id=emp.id,
            name=emp.name,
            category=emp.category,
            description=emp.description,
            avatar=emp.avatar,
            skills=emp.skills,
            is_active=emp.is_active,
        )
        for emp in employees
    ]


@router.get("/{employee_id}", response_model=EmployeeResponse)
async def get_employee(employee_id: str):
    """获取单个数字员工详情"""
    emp = db.get_employee(employee_id)
    if not emp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="数字员工不存在",
        )
    return EmployeeResponse(
        id=emp.id,
        name=emp.name,
        category=emp.category,
        description=emp.description,
        avatar=emp.avatar,
        skills=emp.skills,
        is_active=emp.is_active,
    )


@router.post("/{employee_id}/toggle", response_model=EmployeeToggleResponse)
async def toggle_employee(
    employee_id: str,
    current_user: dict = Depends(get_current_user),
):
    """启用/停用数字员工（需认证）"""
    emp = db.toggle_employee(employee_id)
    if not emp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="数字员工不存在",
        )
    status_text = "已启用" if emp.is_active else "已停用"
    return EmployeeToggleResponse(
        id=emp.id,
        is_active=emp.is_active,
        message=f"数字员工「{emp.name}」{status_text}",
    )
