from pydantic import BaseModel
from typing import Optional, Any, Union, List, Dict

class DeleteResponse(BaseModel):
    success: bool
    id: str
    message: Optional[str] = None

class ApiErrorDetail(BaseModel):
    detail: Optional[Union[str, List[Dict[str, Any]]]] = None
    message: Optional[str] = None
    status: Optional[int] = None

