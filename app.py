from datetime import datetime, timezone
import random
import sqlite3
from typing import Optional, List
from datetime import date

import plotly.express as px
import pandas as pd
import altair as alt
import streamlit as st
import streamlit_pydantic as sp

from expenses import Expense, BaseExpense


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

    for i in range(100):
        seed_expense = Expense(
            rowid=i,
            purchased_date=date(
                random.randint(2020, 2022), random.randint(1, 12), random.randint(1, 28)
            ).strftime("%Y-%m-%d"),
            purchased_by=random.choice(["Gar", "Serena", "Mia"]),
            price_in_cents=random.randint(1, 5_000_00),
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

    def list_all_expenses(
        connection: sqlite3.Connection,
    ) -> List[sqlite3.Row]:
        """Returns rows from all expenses. Ordered in reverse creation order"""
        read_expenses_query = f"""SELECT rowid, purchased_date, purchased_by, price_in_cents
        FROM expenses ORDER BY rowid DESC;"""
        expense_rows = execute_query(connection, read_expenses_query)
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


def fill_purchased_date(df: pd.DataFrame) -> pd.DataFrame:
    df_dates = df.index.levels[df.index.names.index("purchased_date")]
    min_date = df_dates.min()
    max_date = df_dates.max()
    all_dates = pd.date_range(min_date, max_date, freq="D")


def prep_df_for_altair(df: pd.DataFrame) -> pd.DataFrame:
    return df.divide(100).reset_index().melt("purchased_date")


def altair_multi_line_with_tooltips(df: pd.DataFrame) -> alt.Chart:
    # https://altair-viz.github.io/gallery/multiline_tooltip.html
    # Create a selection that chooses the nearest point & selects based on x-value
    nearest = alt.selection(
        type="single",
        nearest=True,
        on="mouseover",
        fields=["purchased_date"],
        empty="none",
    )

    # multi Line chart
    cum_chart = (
        alt.Chart(df)
        .mark_line(interpolate="basis")
        .encode(
            x=alt.X("purchased_date:T", title="Date"),
            y=alt.Y("value:Q", title="Total Dollars Spent"),
            color="purchased_by:N",
        )
    )

    # selectors for mouse
    selectors = (
        alt.Chart(df)
        .mark_point()
        .encode(x="purchased_date:T", opacity=alt.value(0))
        .add_selection(nearest)
    )

    # Draw points on the line, and highlight based on selection
    points = cum_chart.mark_point().encode(
        opacity=alt.condition(nearest, alt.value(1), alt.value(0))
    )

    # Draw text labels near the points, and highlight based on selection
    text = cum_chart.mark_text(align="left", dx=5, dy=-5).encode(
        text=alt.condition(nearest, "value:Q", alt.value(" "))
    )
    date_text = cum_chart.mark_text(align="left", dx=5, dy=-20).encode(
        text=alt.condition(nearest, "purchased_date:T", alt.value(" "))
    )

    # Draw a rule at the location of the selection
    rules = (
        alt.Chart(df)
        .mark_rule(color="gray")
        .encode(
            x="purchased_date:T",
        )
        .transform_filter(nearest)
    )

    # Put the five layers into a chart and bind the data
    return alt.layer(cum_chart, selectors, points, rules, text, date_text)


def render_read(connection: sqlite3.Connection) -> None:
    """Show all of the expenses in the database in a feed"""
    st.success("Reading Expense Feed")

    render_create(connection)

    with st.expander("Show Raw Data"), st.echo():
        expense_rows = ExpenseService.list_all_expenses(connection)
        expenses = [Expense(**row) for row in expense_rows]
        raw_df = pd.DataFrame([x.dict() for x in expenses])
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
        totals = pivot_df.drop("All", axis=1).sum()
        totals.index.name = "purchased_by"
        totals.name = "value"
        totals = totals.reset_index()

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

    st.header("Cumulative Spending Per Person")
    options = cum_df.purchased_by.unique()
    non_all_options = [x for x in options if x != 'All']
    selections = st.multiselect("Show Spending For:", options, default=non_all_options)
    if selections:
        fig = px.line(cum_df, x="purchased_date", y="value", color='purchased_by')
        st.plotly_chart(fig, use_container_width=True)

        cum_chart = altair_multi_line_with_tooltips(
            cum_df.loc[cum_df.purchased_by.isin(selections)]
        )

        st.header("Cumulative Spending To Date")
        st.altair_chart(cum_chart, use_container_width=True)

        rolling_chart = altair_multi_line_with_tooltips(rolling_df.loc[rolling_df.purchased_by.isin(selections)])
        st.header("Weekly Spending Per Person")
        st.altair_chart(rolling_chart, use_container_width=True)

        maxes_chart = altair_multi_line_with_tooltips(maxes_df.loc[maxes_df.purchased_by.isin(selections)])
        st.header("Monthly Biggest Purchase Per Person")
        st.altair_chart(maxes_chart, use_container_width=True)
    else:
        st.warning("Select at least one person to see the charts")

    st.header("Expense Feed")
    for expense in expenses:
        render_expense(expense)


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
