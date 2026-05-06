from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from passlib.context import CryptContext
from jose import jwt, JWTError
import secrets
import datetime
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
import os
from dotenv import load_dotenv
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from datetime import date
from db import get_db
from models import User
from typing import Optional

# -----------------------------
# config
# -----------------------------

load_dotenv()

SECRET_KEY = os.getenv('SECRET_KEY')
ALGORITHM = "HS256"
DATABASE_URL = os.getenv('DATABASE_URL')

pwd_context = CryptContext(schemes=["bcrypt"])

conf = ConnectionConfig(
  MAIL_USERNAME=os.getenv('MAIL_USERNAME'),
  MAIL_PASSWORD=os.getenv('MAIL_PASSWORD'),
  MAIL_FROM=os.getenv('MAIL_USERNAME'),
  MAIL_PORT=587,
  MAIL_SERVER="smtp.gmail.com",
  MAIL_STARTTLS=True,
  MAIL_SSL_TLS=False,
  USE_CREDENTIALS=True,
  VALIDATE_CERTS=True
)

# -----------------------------
# schemas
# -----------------------------

class SignupRequest(BaseModel):
  email: EmailStr
  password: str
  name: str

class LoginRequest(BaseModel):
  email: EmailStr
  password: str

class ResetRequest(BaseModel):
  email: EmailStr

class ResetPassword(BaseModel):
  token: str
  new_password: str

# -----------------------------
# helpers
# -----------------------------

def hash_password(password: str):
  return pwd_context.hash(password)

def verify_password(password: str, hash):
  return pwd_context.verify(password, hash)

def create_token(user_id: int):
  payload = {
      "user_id": user_id,
      "exp": datetime.datetime.utcnow() + datetime.timedelta(days=7)
  }
  return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

async def send_email(email: str, link: str):

  message = MessageSchema(
    subject="Account action",
    recipients=[email],
    body=f"Click this link:\n{link}",
    subtype="plain"
  )

  fm = FastMail(conf)

  await fm.send_message(message)

# -----------------------------
# router
# -----------------------------

router = APIRouter(prefix="/api")

# -----------------------------
# signup
# -----------------------------

@router.post("/signup")
async def signup(data: SignupRequest, db: Session = Depends(get_db)):

  existing = db.query(User).filter(User.email == data.email).first()

  if existing:
    raise HTTPException(400, "email already registered")

  token = secrets.token_urlsafe(32)

  user = User(
    email=data.email,
    password_hash=hash_password(data.password),
    name=data.name,
    verify_token=token,
  )

  db.add(user)
  db.commit()

  link = f"http://localhost:8000/api/verify-email?token={token}"

  await send_email(data.email, link)

  return {"message": "signup success. check email for verification link"}

# -----------------------------
# email verification
# -----------------------------

@router.get("/verify-email")
def verify_email(token: str, db: Session = Depends(get_db)):

  user = db.query(User).filter(User.verify_token == token).first()

  if not user:
    raise HTTPException(400, "invalid token")

  user.email_verified = True
  user.verify_token = None

  db.commit()

  return RedirectResponse("http://localhost:5173/login")

# -----------------------------
# login
# -----------------------------

@router.post("/login")
def login(data: LoginRequest, db: Session = Depends(get_db)):

  user = db.query(User).filter(User.email == data.email).first()

  if not user:
      raise HTTPException(400, "invalid credentials")

  if not verify_password(data.password, user.password_hash):
      raise HTTPException(400, "invalid credentials")

  if not user.email_verified:
      raise HTTPException(400, "email not verified")

  token = create_token(user.id)

  return {
    "access_token": token,
    "token_type": "bearer"
  }

# -----------------------------
# request password reset
# -----------------------------

@router.post("/request-password-reset")
async def request_reset(data: ResetRequest, db: Session = Depends(get_db)):

  user = db.query(User).filter(User.email == data.email).first()

  if not user:
    return {"message": "if email exists, reset link sent"}

  token = secrets.token_urlsafe(32)

  user.reset_token = token

  db.commit()

  link = f"http://localhost:5173/reset-password?token={token}"

  await send_email(user.email, link)

  return {"message": "if email exists, reset link sent"}

# -----------------------------
# reset password
# -----------------------------

@router.post("/reset-password")
def reset_password(data: ResetPassword, db: Session = Depends(get_db)):

  user = db.query(User).filter(User.reset_token == data.token).first()

  if not user:
    raise HTTPException(400, "invalid token")

  user.password_hash = hash_password(data.new_password)
  user.reset_token = None

  db.commit()

  return {"message": "password updated"}

# -----------------------------
# get current user
# -----------------------------

security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(401, "invalid token")
    except JWTError:
        raise HTTPException(401, "invalid token")
    
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(401, "user not found")
    return user

security_optional = HTTPBearer(auto_error=False)

def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_optional),
    db: Session = Depends(get_db)
) -> Optional[User]:
    if credentials is None:
        return None

    token = credentials.credentials

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
        if not user_id:
            return None
    except JWTError:
        return None

    user = db.query(User).filter(User.id == user_id).first()
    return user

@router.get("/me")
def me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.name
    }

# -----------------------------
# update name
# -----------------------------

class UpdateName(BaseModel):
  name: str

@router.put("/me/name")
def update_name(
    data: UpdateName,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    current_user.name = data.name
    db.commit()

    return {"name": current_user.name}