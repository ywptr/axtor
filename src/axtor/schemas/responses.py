from typing import Literal

from pydantic import BaseModel


class StatusResponse(BaseModel):
    status: Literal["ok", "ready"]


class ErrorDetail(BaseModel):
    code: str
    message: str
    correlation_id: str


class ErrorResponse(BaseModel):
    error: ErrorDetail
