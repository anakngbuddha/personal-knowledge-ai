"""3.3 Reading a product list out of whatever the distributor sent.

No database and no API key: the reader, the column guesser, and the planner are pure,
which is the whole reason they live apart from the writing half.
"""

import io

import pytest

from app.catalog import product_list

CSV = (
    "\ufeffProduct Name,Brand,Type,Own or resold,Availability,Also known as,Where it runs\r\n"
    "Jabra PanaCast 50,Jabra,Video bar,resold,GA,PanaCast50;PC50,on premise\r\n"
    "Shure MXA920,Shure,Ceiling microphone,Partner,shipping,,appliance\r\n"
    ",Poly,Headset,own,,,\r\n"
    "jabra panacast 50,Jabra,Video bar,resold,GA,,\r\n"
).encode()


def _xlsx(rows) -> bytes:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_a_distributor_csv_maps_itself():
    table = product_list.read_table(CSV, filename="portal-export.csv")
    assert table.headers[0] == "Product Name"  # the byte-order mark is not a column title
    mapping = product_list.suggest_mapping(table.headers)
    assert mapping["0"] == "name"
    assert mapping["1"] == "vendor"
    assert mapping["3"] == "ownership"
    assert mapping["4"] == "lifecycle_status"
    assert mapping["5"] == "aliases"


def test_values_are_normalised_to_what_the_database_accepts():
    table = product_list.read_table(CSV, filename="portal-export.csv")
    plan = product_list.build_plan(table, product_list.suggest_mapping(table.headers))
    first = plan.drafts[0]
    assert first.name == "Jabra PanaCast 50"
    assert first.values["ownership"] == "resold"
    assert first.values["deployment_model"] == "on-prem"
    assert first.values["lifecycle_status"] == "GA"
    assert first.values["aliases"] == ["PanaCast50", "PC50"]
    # "Partner" and "shipping" are not vocabulary, but they are obvious.
    assert plan.drafts[1].values["ownership"] == "resold"
    assert plan.drafts[1].values["lifecycle_status"] == "GA"


def test_unusable_rows_are_reported_in_plain_words_not_dropped_silently():
    table = product_list.read_table(CSV, filename="portal-export.csv")
    plan = product_list.build_plan(table, product_list.suggest_mapping(table.headers))
    reasons = {problem.row_number: problem.reason for problem in plan.problems}
    assert reasons[3] == "No product name in this row."
    assert "row 1" in reasons[4]
    assert plan.count == 2
    for reason in reasons.values():
        assert "row" in reason.lower() or "name" in reason.lower()


def test_the_same_product_twice_in_one_file_is_imported_once():
    table = product_list.read_table(CSV, filename="portal-export.csv")
    plan = product_list.build_plan(table, product_list.suggest_mapping(table.headers))
    assert [draft.key for draft in plan.drafts] == ["jabra panacast 50", "shure mxa920"]


def test_a_semicolon_file_is_still_a_csv():
    table = product_list.read_table(b"model;manufacturer\nX100;Acme\n", filename="list.csv")
    assert table.headers == ["model", "manufacturer"]
    assert table.rows == [["X100", "Acme"]]


def test_a_spreadsheet_with_a_blank_first_row_still_reads():
    data = _xlsx(
        [
            [],
            ["SKU", "Manufacturer", "Family", "EOL"],
            ["P100", "Poly", "Headset", "end of life"],
            [None, None, None, None],
            [200, "Acme", "Camera", "yes"],
        ]
    )
    table = product_list.read_table(data, filename="catalogue.xlsx")
    assert table.headers == ["SKU", "Manufacturer", "Family", "EOL"]
    assert table.row_count == 2, "a blank row in the middle is not a product"
    plan = product_list.build_plan(table, product_list.suggest_mapping(table.headers))
    assert plan.drafts[0].values["lifecycle_status"] == "EOL"
    assert plan.drafts[1].values["lifecycle_status"] == "GA"
    assert plan.drafts[1].name == "200", "a numeric code is a name, not a float"


def test_no_name_column_is_a_question_not_a_crash():
    table = product_list.read_table(CSV, filename="portal-export.csv")
    plan = product_list.build_plan(table, {"1": "vendor"})
    assert plan.count == 0
    assert "product name" in plan.problems[0].reason.lower()


def test_one_column_per_field_so_a_second_guess_is_left_to_a_person():
    mapping = product_list.suggest_mapping(["Model", "SKU", "Brand"])
    assert mapping["0"] == "name"
    assert mapping["1"] == "", "two name-ish columns: the person picks"
    assert mapping["2"] == "vendor"


def test_a_very_long_list_is_truncated_and_says_so():
    body = "name\n" + "\n".join(f"Product {index}" for index in range(10))
    table = product_list.read_table(body.encode(), filename="long.csv", max_rows=3)
    assert table.row_count == 3
    assert table.truncated is True


def test_a_pdf_is_not_a_product_list():
    with pytest.raises(product_list.UnsupportedProductList) as excinfo:
        product_list.read_table(b"%PDF-1.4", filename="datasheet.pdf")
    assert "CSV" in str(excinfo.value)


def test_the_field_catalogue_names_one_required_column():
    required = [item for item in product_list.field_catalogue() if item["required"]]
    assert [item["key"] for item in required] == ["name"]
