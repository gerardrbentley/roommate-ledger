from datetime import date
import random
import sqlite3
from typing import Optional, List
import streamlit as st

from models import Expense, BaseExpense


def create_expenses_table(connection: sqlite3.Connection) -> None:
    """Create Expenses Table in the database if it doesn't already exist"""
    st.warning("Creating Expenses Table")
    init_expenses_query = f"""CREATE TABLE IF NOT EXISTS expenses(
   purchased_date VARCHAR(10) NOT NULL,
   purchased_by VARCHAR(120) NOT NULL,
   comment VARCHAR(120),
   price_in_cents INT NOT NULL);"""
    execute_query(connection, init_expenses_query)


def seed_expenses_table(connection: sqlite3.Connection) -> None:
    """Insert a sample Expense row into the database"""
    st.warning("Seeding Expenses Table")

    for i in range(200):
        seed_expense = Expense(
            rowid=i,
            purchased_date=date(
                random.randint(2020, 2022), random.randint(1, 12), random.randint(1, 28)
            ).strftime("%Y-%m-%d"),
            purchased_by=random.choice(["Alice", "Bob", "Chuck"]),
            comment=random.choice(('Computer Parts 💻', 'Neatflicks Subscription 🍿', 'Food 🍜', '"Food" 🍻')),
            price_in_cents=random.randint(50, 100_00),
        )
        seed_expense_query = f"""REPLACE into expenses(rowid, purchased_date, purchased_by, price_in_cents, comment)
        VALUES(:rowid, :purchased_date, :purchased_by, :price_in_cents, :comment);"""
        execute_query(connection, seed_expense_query, seed_expense.dict())


def execute_query(
    connection: sqlite3.Connection, query: str, args: Optional[dict] = None
) -> list:
    """Given sqlite3.Connection and a string query (and optionally necessary query args as a dict),
    Attempt to execute query with cursor, commit transaction, and return fetched rows"""
    cur = connection.cursor()
    if args is not None:
        cur.execute(query, args)
    else:
        cur.execute(query)
    connection.commit()
    results = cur.fetchall()
    cur.close()
    return results


class ExpenseService:
    """Namespace for Database Related Expense Operations"""

    def list_all_purchasers(connection: sqlite3.Connection) -> List[str]:
        select_purchasers = "SELECT DISTINCT purchased_by FROM expenses"
        expense_rows = execute_query(connection, select_purchasers)
        return [x["purchased_by"] for x in expense_rows]

    def list_all_expenses(
        connection: sqlite3.Connection,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        selections: Optional[list[str]] = None,
    ) -> List[sqlite3.Row]:
        """Returns rows from all expenses. Ordered in reverse creation order"""
        select = (
            "SELECT rowid, purchased_date, purchased_by, price_in_cents, comment FROM expenses"
        )
        where = ""
        do_and = False
        kwargs = {}
        if any(x is not None for x in (start_date, end_date, selections)):
            where = "WHERE"
        if start_date is not None:
            where += " purchased_date >= :start_date"
            kwargs["start_date"] = start_date
            do_and = True
        if end_date is not None:
            if do_and:
                where += " and"
            where += " purchased_date <= :end_date"
            kwargs["end_date"] = end_date
            do_and = True
        if selections is not None:
            if do_and:
                where += " and"
            selection_map = {str(i): x for i, x in enumerate(selections)}
            where += (
                f" purchased_by IN ({','.join(':' + x for x in selection_map.keys())})"
            )
            kwargs.update(selection_map)

        order_by = "ORDER BY purchased_date DESC;"
        query = " ".join((select, where, order_by))
        expense_rows = execute_query(connection, query, kwargs)
        return expense_rows

    def create_expense(connection: sqlite3.Connection, expense: BaseExpense) -> None:
        """Create a Expense in the database"""
        create_expense_query = f"""INSERT into expenses(purchased_date, purchased_by, price_in_cents, comment)
    VALUES(:purchased_date, :purchased_by, :price_in_cents, :comment);"""
        execute_query(connection, create_expense_query, expense.dict())

    def update_expense(connection: sqlite3.Connection, expense: Expense) -> None:
        """Replace a Expense in the database"""
        update_expense_query = f"""UPDATE expenses SET purchased_date=:purchased_date, purchased_by=:purchased_by, price_in_cents=:price_in_cents, comment=:comment WHERE rowid=:rowid;"""
        execute_query(connection, update_expense_query, expense.dict())

    def delete_expense(connection: sqlite3.Connection, expense: Expense) -> None:
        """Delete a Expense in the database"""
        delete_expense_query = f"""DELETE from expenses WHERE rowid = :rowid;"""
        execute_query(connection, delete_expense_query, {"rowid": expense.rowid})
