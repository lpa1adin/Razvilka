from pydantic import BaseModel, Field

from app.modules.auth.models import Role


class LoginIn(BaseModel):
    login: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class UserOut(BaseModel):
    id: int
    login: str
    display_name: str
    role: Role

    model_config = {"from_attributes": True}


class SessionOut(BaseModel):
    user: UserOut | None

