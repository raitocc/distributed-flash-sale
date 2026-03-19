from typing import TypeVar, Generic, Optional
from pydantic import BaseModel

T = TypeVar("T")

class ResponseModel(BaseModel, Generic[T]):
    code: int
    message: str
    data: Optional[T] = None

def success(data: T = None, message: str = "success") -> ResponseModel[T]:
    return ResponseModel(code=200, message=message, data=data)

def error(code: int, message: str, data: T = None) -> ResponseModel[T]:
    return ResponseModel(code=code, message=message, data=data)
