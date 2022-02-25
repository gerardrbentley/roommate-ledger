from datetime import datetime, timedelta, timezone, date
import random
import sqlite3
from typing import Optional, List

import numpy as np
from pydantic import BaseModel, Field
import plotly.express as px
import pandas as pd
import altair as alt
import streamlit as st
import streamlit_pydantic as sp

from expenses import Expense, BaseExpense

rng = np.random.default_rng(47)
CHAR_LIMIT = 140
DATABASE_URI = "expenses.db"
# DATABASE_URI = ":memory:"


def main() -> None:
    """Main Streamlit App Entry"""
    connection = get_connection(DATABASE_URI)
    init_db(connection)

    st.header("Roommate Expense Tracker")
    st.subheader("Enter your spending to track who owes what to whom!")
    render_sidebar(connection)


def render_sidebar(connection: sqlite3.Connection) -> None:
    """Provides Selectbox Drop Down for which view to render"""
    views = {
        "Main Expense Feed": render_read,  # Read first for display default
        "Create an Expense": render_create,
        "Update an Expense": render_update,
        "Delete an Expense": render_delete,
    }
    choice = st.sidebar.radio("Go To Page:", views.keys())
    render_func = views.get(choice)
    render_func(connection)


@st.cache(hash_funcs={sqlite3.Connection: id}, suppress_st_warning=True)
def get_connection(connection_string: str = ":memory:") -> sqlite3.Connection:
    """Make a connection object to sqlite3 with key-value Rows as outputs
    Threading in Streamlit / Python with sqlite:
    - https://discuss.streamlit.io/t/prediction-analysis-and-creating-a-database/3504/2
    - https://stackoverflow.com/questions/48218065/programmingerror-sqlite-objects-created-in-a-thread-can-only-be-used-in-that-sa
    """
    st.error("Get Connection")
    connection = sqlite3.connect(connection_string, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


@st.cache(hash_funcs={sqlite3.Connection: id}, suppress_st_warning=True)
def init_db(connection: sqlite3.Connection) -> None:
    """Create table and seed data as needed"""
    st.warning("Init DB")
    create_expenses_table(connection)
    seed_expenses_table(connection)


def create_expenses_table(connection: sqlite3.Connection) -> None:
    """Create Expenses Table in the database if it doesn't already exist"""
    st.warning("Creating Expenses Table")
    init_expenses_query = f"""CREATE TABLE IF NOT EXISTS expenses(
   purchased_date VARCHAR(10) NOT NULL,
   purchased_by VARCHAR(120) NOT NULL,
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
            price_in_cents=random.randint(50, 100_00),
        )
        seed_expense_query = f"""REPLACE into expenses(rowid, purchased_date, purchased_by, price_in_cents)
        VALUES(:rowid, :purchased_date, :purchased_by, :price_in_cents);"""
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
        return [x['purchased_by'] for x in expense_rows]

    def list_all_expenses(
        connection: sqlite3.Connection,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        selections: Optional[list[str]] = None,
    ) -> List[sqlite3.Row]:
        """Returns rows from all expenses. Ordered in reverse creation order"""
        select = "SELECT rowid, purchased_date, purchased_by, price_in_cents FROM expenses"
        where = ""
        do_and = True
        kwargs = {}
        if any(x is not None for x in (start_date, end_date, selections)):
            where = "WHERE"
        if start_date is not None:
            where += " purchased_date >= :start_date"
            kwargs['start_date'] = start_date
            do_and = True
        if end_date is not None:
            if do_and:
                where += " and"
            where += " purchased_date <= :end_date"
            kwargs['end_date'] = end_date
            do_and = True
        if selections is not None:
            if do_and:
                where += " and"
            selection_map = {str(i): x for i, x in enumerate(selections)}
            where += f" purchased_by IN ({','.join(':' + x for x in selection_map.keys())})"
            kwargs.update(selection_map)

        order_by = "ORDER BY purchased_date DESC;"
        query = ' '.join((select, where, order_by))
        expense_rows = execute_query(connection, query, kwargs)
        return expense_rows

    def create_expense(connection: sqlite3.Connection, expense: BaseExpense) -> None:
        """Create a Expense in the database"""
        create_expense_query = f"""INSERT into expenses(purchased_date, purchased_by, price_in_cents)
    VALUES(:purchased_date, :purchased_by, :price_in_cents);"""
        execute_query(connection, create_expense_query, expense.dict())

    def update_expense(connection: sqlite3.Connection, expense: Expense) -> None:
        """Replace a Expense in the database"""
        update_expense_query = f"""UPDATE expenses SET purchased_date=:purchased_date, purchased_by=:purchased_by, price=:price WHERE rowid=:rowid;"""
        execute_query(connection, update_expense_query, expense.dict())

    def delete_expense(connection: sqlite3.Connection, expense: Expense) -> None:
        """Delete a Expense in the database"""
        delete_expense_query = f"""DELETE from expenses WHERE rowid = :rowid;"""
        execute_query(connection, delete_expense_query, {"rowid": expense.rowid})


def display_timestamp(timestamp: int) -> datetime:
    """Return python datetime from utc timestamp"""
    return datetime.fromtimestamp(timestamp, timezone.utc)


def utc_timestamp() -> int:
    """Return current utc timestamp rounded to nearest int"""
    return int(datetime.utcnow().timestamp())


def render_expense(expense: Expense) -> None:
    """Show a expense with streamlit display functions"""
    st.subheader(f"By {expense.purchased_by} at {expense.purchased_date}")
    st.caption(f"Expense #{expense.rowid}")
    st.write(f"{expense.price_in_cents / 100 :.2f}")


def do_create(connection: sqlite3.Connection, expense: BaseExpense) -> None:
    """Streamlit callback for creating a expense and showing confirmation"""
    st.warning("Creating your Expense")
    ExpenseService.create_expense(connection, expense)
    st.success(
        f"Successfully Created your Expense! Check the Read Expense Feed page to see it"
    )


def render_create(connection: sqlite3.Connection) -> None:
    """Show the form for creating a new Expense"""
    data = sp.pydantic_form(key="create_form", model=BaseExpense, clear_on_submit=True)
    if data:
        do_create(connection, data)

def prep_df_for_altair(df: pd.DataFrame) -> pd.DataFrame:
    return df.divide(100).reset_index().melt("purchased_date")

@st.cache()
def get_data(connection, start_date: date, end_date: date, selections: list[str]) -> pd.DataFrame:
    expense_rows = ExpenseService.list_all_expenses(connection, start_date, end_date, selections)
    expenses = [Expense(**row) for row in expense_rows]
    return pd.DataFrame([x.dict() for x in expenses])

def render_read(connection: sqlite3.Connection) -> None:
    """Show all of the expenses in the database in a feed"""
    st.success("Reading Expense Feed")

    render_create(connection)
    purchasers = ExpenseService.list_all_purchasers(connection)
    selections = st.multiselect("Show Spending For:", [*purchasers, 'All'], default=purchasers)
    start_date = st.date_input("Start Date", value=date.today() - timedelta(days=30*6))
    end_date = st.date_input("End Date", value=date.today())
    with st.expander("Show Raw Data"), st.echo():
        raw_df = get_data(connection, start_date, end_date, selections)
        st.write(raw_df)

    with st.expander("Data Cleaning"), st.echo():
        # Take needed columns
        df = raw_df[["purchased_date", "purchased_by", "price_in_cents"]]
        # Pivot data into columns of each purchased_by person, summing any dupes for a given day
        pivot_df = df.pivot_table(
            index="purchased_date", columns="purchased_by", aggfunc="sum", fill_value=0
        )
        # Ignore multiindex that doesn't give much in this case
        pivot_df.columns = pivot_df.columns.droplevel(0)
        # Avoid doing summation with floats and money
        if 'All' in selections:
            pivot_df["All"] = pivot_df.sum(axis=1)

        # Fill in date gaps
        min_date = pivot_df.index.min()
        max_date = pivot_df.index.max()
        all_dates = pd.date_range(min_date, max_date, freq="D", name="purchased_date")
        pivot_df = pivot_df.reindex(all_dates, fill_value=0)

        # All spending days
        spend_df = prep_df_for_altair(pivot_df)

        # Cumulative spend over time for each person and All
        cum_df = pivot_df.cumsum()
        cum_df = prep_df_for_altair(cum_df)

        # Sum of each spender
        totals = pivot_df.sum()
        totals.index.name = "purchased_by"
        totals.name = "value"
        totals = totals.div(100).reset_index()

        # 7 Day cumulative spending
        rolling_df = pivot_df.rolling(7, min_periods=1).sum()
        rolling_df = prep_df_for_altair(rolling_df)

        # 30 Day daily maxes
        maxes_df = pivot_df.rolling(30, min_periods=1).max()
        maxes_df = prep_df_for_altair(maxes_df)

    totals_chart = (
        alt.Chart(totals)
        .mark_bar()
        .encode(
            x=alt.X("value:Q", title="Total Dollars Spent"),
            y=alt.Y("purchased_by:N", sort="-x", title="Name"),
            color=alt.Color("purchased_by:N"),
        )
    )
    totals_text = (
        alt.Chart(totals)
        .mark_text(dx=-30, dy=3, color="white")
        .encode(
            x=alt.X("value:Q", title="Total Dollars Spent"),
            y=alt.Y("purchased_by:N", sort="-x", title="Name"),
            detail="purchased_by:N",
            text=alt.Text("value:Q", format="$.2f"),
        )
    )
    st.header("Total Spending Per Person")
    st.altair_chart(totals_chart + totals_text, use_container_width=True)

    spending_per_day = px.bar(spend_df, x='purchased_date', y='value',
              color='purchased_by',
             labels={'value':'Dollars spent per day'}, height=500)
    st.plotly_chart(spending_per_day)

    st.header("Cumulative Spending Per Person")

    if selections:
        st.header("Cumulative Spending To Date")
        multi_line = lambda x: px.line(x, x="purchased_date", y="value", color='purchased_by')
        fig = multi_line(cum_df)
        st.plotly_chart(fig, use_container_width=True)

        rolling_chart = multi_line(rolling_df)
        st.header("Weekly Spending Per Person")
        st.plotly_chart(rolling_chart, use_container_width=True)

        maxes_chart = multi_line(maxes_df)
        st.header("Monthly Biggest Purchase Per Person")
        st.plotly_chart(maxes_chart, use_container_width=True)
    else:
        st.warning("Select at least one person to see the charts")

    expenses = ExpenseService.list_all_expenses(connection)
    st.header("Expense Feed")
    for expense in expenses:
        render_expense(Expense(**expense))


def do_update(connection: sqlite3.Connection, new_expense: Expense) -> None:
    """Streamlit callback for updating a expense and showing confirmation"""
    st.warning(f"Updating Expense #{new_expense.rowid}")
    ExpenseService.update_expense(connection, new_expense)
    st.success(
        f"Updated Expense #{new_expense.rowid}, go to the Read Expenses Feed to see it!"
    )


def render_update(connection: sqlite3.Connection) -> None:
    """Show the form for updating an existing Expense"""
    st.success("Reading Expenses")
    expense_rows = ExpenseService.list_all_expenses(connection)
    expense_map = {row["rowid"]: Expense(**row) for row in expense_rows}
    expense_id = st.selectbox(
        "Which Expense to Update?",
        expense_map.keys(),
        format_func=lambda x: f"{expense_map[x].rowid} - by {expense_map[x].username} on {display_timestamp(expense_map[x].created_timestamp)}",
    )
    expense_to_update = expense_map[expense_id]
    with st.form("update_form"):
        st.write("Update Purchase Info")
        price = st.number_input(
            "Price",
            value=expense_to_update.price,
            min_value=0,
            max_value=1_000,
            help="Enter the Price of the expense",
        )
        purchased_date = st.date_input(
            "Purchase Date",
            value=expense_to_update.purchased_date,
            help="Enter the Purchase Date",
        )

        st.caption(
            f"Expense #{expense_id} - by {expense_to_update.price} on {display_timestamp(expense_to_update.purchased_date)}"
        )

        submitted = st.form_submit_button(
            "Submit",
            help="This will change the body of the expense, the username, or both. It also updates the updated at time.",
        )
        if submitted:
            new_expense = Expense(
                purchased_date,
                price,
                expense_to_update.rowid,
            )
            do_update(connection, new_expense)


def do_delete(connection: sqlite3.Connection, expense_to_delete: Expense) -> None:
    """Streamlit callback for deleting a expense and showing confirmation"""
    st.warning(f"Deleting Expense #{expense_to_delete.rowid}")
    ExpenseService.delete_expense(connection, expense_to_delete)
    st.success(f"Deleted Expense #{expense_to_delete.rowid}")


def render_delete(connection: sqlite3.Connection) -> None:
    """Show the form for deleting an existing Expense"""
    st.success("Reading Expenses")
    expense_rows = ExpenseService.list_all_expenses(connection)
    expense_map = {row["rowid"]: Expense(**row) for row in expense_rows}
    expense_id = st.selectbox("Which Expense to Delete?", expense_map.keys())
    expense_to_delete = expense_map[expense_id]

    render_expense(expense_to_delete)

    st.button(
        "Delete Expense (This Can't Be Undone!)",
        help="I hope you know what you're getting into!",
        on_click=do_delete,
        args=(connection, expense_to_delete),
    )


if __name__ == "__main__":
    main()
