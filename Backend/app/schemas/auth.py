from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field

from app.schemas.user import NewPassword, UserRead


class LoginRequest(BaseModel):
    email: Annotated[str, Field(max_length=255), AfterValidator(lambda v: v.strip().lower())]
    password: str = Field(max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserRead


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: NewPassword
