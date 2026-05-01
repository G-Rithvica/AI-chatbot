from pydantic import BaseModel, EmailStr


class UserOut(BaseModel):
    id: str
    email: EmailStr
    name: str | None = None
    picture: str | None = None


class AuthStatusOut(BaseModel):
    authenticated: bool
    user: UserOut | None = None


class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    name: str | None = None


class LoginIn(BaseModel):
    email: EmailStr
    password: str
