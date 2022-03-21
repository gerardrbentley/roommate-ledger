from datetime import date
from pydantic import BaseModel


class BaseExpense(BaseModel):
    price_in_cents: int
    purchased_date: date
    purchased_by: str
    comment: str


class Expense(BaseExpense):
    rowid: int
