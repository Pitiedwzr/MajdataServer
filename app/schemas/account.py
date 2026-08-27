from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, EmailStr

class UserRegisterForm(BaseModel):
    username: str
    password: str
    email: EmailStr
    cf_turnstile_response: Optional[str] = None

class UserLoginForm(BaseModel):
    username: str
    password: str
    rememberMe: bool = False

class UserInfoResponse(BaseModel):
    username: str
    email: Optional[str] = None
    intro: Optional[str] = ""
    is_active: bool = True
    created_at: Optional[datetime] = None

class SessionInfoResponse(BaseModel):
    sessionId: str
    username: str
    createdAt: datetime
    expiresAt: datetime
    userAgent: Optional[str] = ""
    ipAddress: Optional[str] = ""

class ForgetPasswordRequest(BaseModel):
    username: str
    email: str

class ResetPasswordRequest(BaseModel):
    otp: str
    newpassword: str

class ApiResponse(BaseModel):
    code: int = 114514
    message: str = "success"
