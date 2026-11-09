from decimal import Decimal
import hashlib

from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
import pytest

from services import company_workbook as company
from services.excel_export import export_excel
from services.models import Batch, Product, Reference
from services.naming import manual_identity


def make_batch(tmp_path):
    folder = tmp_path / "lote"
    folder.mkdir()
    return Batch(folder=folder, excel_layout="company")


def part(batch, identifier="1", sku="024", name="PORTA L.D VW GOL 12-20"):
    return Product(id=identifier, sku=sku, folder=batch.folder, identity=manual_identity(name))


def base_at(tmp_path, rows):
    book = Workbook()
    book.active.append(company.HEADERS)
    for row in rows:
        book.active.append(row)
    path = tmp_path / "base.xlsx"
    book.save(path)
    return path


def references(start=123456):
    return [Reference(title="Porta", price=price,
        url=f"https://produto.mercadolivre.com.br/MLB-{start+i}-porta-_JM",
        condition="used", compatible=True, verified=True) for i, price in enumerate((100, 200))]


def test_multisku_base_is_preserved_and_individual_products_have_their_own_rows(tmp_path):
    source = base_at(tmp_path, [["101/102 - PORTA VW GOL 12-20", 100, 200, "=(B2+C2)/2", 150]])
    digest = hashlib.sha256(source.read_bytes()).digest()
    batch = make_batch(tmp_path)
    company.attach_source(batch, source)
    left, right = part(batch, "1", "101"), part(batch, "2", "102", "PORTA L.E VW GOL 12-20")
    left.final, right.final = Decimal("120"), Decimal("190")
    left.final_override = right.final_override = True
    batch.products = [left, right]
    for _ in range(3):
        output = export_excel(batch)
    sheet = load_workbook(output).active
    assert sheet.max_row == 4
    assert [sheet.cell(2, c).value for c in range(1, 6)] == ["101/102 - PORTA VW GOL 12-20", 100, 200, "=(B2+C2)/2", 150]
    assert sheet["A3"].value.startswith("101 - PORTA L.D") and sheet["E3"].value == 120
    assert sheet["A4"].value.startswith("102 - PORTA L.E") and sheet["E4"].value == 190
    assert company.reference_products(source)["101"]["final"] is None
    assert hashlib.sha256(source.read_bytes()).digest() == digest
    assert any("agrupado" in text for text in batch.issues)


@pytest.mark.parametrize("sku", ["024", None])
def test_duplicate_or_missing_sku_groups_are_never_lost_and_refs_stay_separate(tmp_path, sku):
    batch = make_batch(tmp_path)
    first, second = part(batch, "1", sku), part(batch, "2", sku, "PORTA L.E VW GOL 12-20")
    first.references, second.references = references(), references(234567)
    batch.products = [first, second]
    for _ in range(3):
        output = export_excel(batch)
    book = load_workbook(output)
    assert book.active.max_row == 3
    assert book["REFERÊNCIAS"].max_row == 5
    assert book.active["A2"].value != book.active["A3"].value
    first.references = []
    first.references_edited = True
    export_excel(batch)
    book = load_workbook(output)
    assert book["REFERÊNCIAS"].max_row == 3
    assert book["REFERÊNCIAS"]["D2"].value == second.references[0].url
    assert book.active["B2"].value is None and book.active["B3"].value == 100


def test_export_consumes_edits_so_later_excel_changes_are_preserved(tmp_path):
    batch = make_batch(tmp_path)
    product = part(batch)
    product.final = Decimal("300")
    product.final_override = product.references_edited = True
    product.references = references()
    batch.products = [product]
    output = export_excel(batch)
    assert not product.final_override and not product.references_edited
    book = load_workbook(output)
    for col, value in zip((2, 3, 4, 5), (333, 555, "=(B2+C2)/2", 777)):
        book.active.cell(2, col, value)
    book.save(output)
    export_excel(batch)
    sheet = load_workbook(output).active
    assert [sheet.cell(2, c).value for c in range(2, 6)] == [333, 555, "=(B2+C2)/2", 777]
    product.references[0].price = Decimal("80")
    export_excel(batch)
    assert load_workbook(output).active["B2"].value == 80


def test_failed_save_does_not_consume_pending_edits(tmp_path, monkeypatch):
    batch = make_batch(tmp_path)
    product = part(batch)
    product.final_override = product.references_edited = True
    product.final = Decimal("50")
    batch.products = [product]
    def fail(*args):
        raise PermissionError("Excel aberto")
    monkeypatch.setattr(company, "atomic_write", fail)
    with pytest.raises(PermissionError):
        export_excel(batch)
    assert product.final_override and product.references_edited


def test_legacy_catalog_references_cannot_keep_old_computed_prices(tmp_path):
    source = base_at(tmp_path, [["024 - PORTA L.D VW GOL 12-20", 100, 200, 150, 300]])
    batch = make_batch(tmp_path)
    company.attach_source(batch, source)
    product = part(batch)
    product.references = [Reference(title="Catálogo", price=100,
        url=f"https://www.mercadolivre.com.br/p/MLB{identifier}",
        condition="used", compatible=True, verified=True) for identifier in (12345678, 23456789)]
    batch.products = [product]
    sheet = load_workbook(export_excel(batch)).active
    assert all(sheet.cell(2, c).value is None for c in (2, 3, 4))
    assert sheet["E2"].value == 300


def test_group_comments_survive_external_row_sorting_and_user_notes(tmp_path):
    batch = make_batch(tmp_path)
    batch.products = [part(batch, "1", "024"), part(batch, "2", "025")]
    output = export_excel(batch)
    book = load_workbook(output)
    sheet = book.active
    first = [(sheet.cell(2, c).value, sheet.cell(2, c).comment) for c in range(1, 6)]
    second = [(sheet.cell(3, c).value, sheet.cell(3, c).comment) for c in range(1, 6)]
    for row, values in ((2, second), (3, first)):
        for col, (value, comment) in enumerate(values, 1):
            sheet.cell(row, col).value = value
            sheet.cell(row, col).comment = comment
    old = sheet["A3"].comment
    sheet["A3"].comment = Comment("Nota do proprietário\n" + old.text, "Usuário")
    book.save(output)
    batch.products[0].final = Decimal("500")
    batch.products[0].final_override = True
    export_excel(batch)
    sheet = load_workbook(output).active
    assert sheet["A3"].value.startswith("024 -") and sheet["E3"].value == 500
    assert "Nota do proprietário" in sheet["A3"].comment.text


def test_ambiguous_and_unit_prices_warn_but_original_is_never_changed(tmp_path):
    source = base_at(tmp_path, [["473-39 MAÇANETA", None, None, None, 200],
                               ["024 - PORTA", "40 CADA", 100, None, "329,00 CADA"]])
    digest = hashlib.sha256(source.read_bytes()).digest()
    batch = make_batch(tmp_path)
    company.attach_source(batch, source)
    assert any("linha 2" in note and "ambíguos" in note for note in batch.issues)
    assert any("linha 3" in note and "unidade" in note for note in batch.issues)
    output = export_excel(batch)
    assert list(load_workbook(output).active.values) == list(load_workbook(source).active.values)
    assert hashlib.sha256(source.read_bytes()).digest() == digest


def test_duplicate_base_sku_never_chooses_the_last_name(tmp_path):
    source = base_at(tmp_path, [["024 - PORTA L.D", None, None, None, 100],
                               ["024 - PORTA L.E", None, None, None, 200]])
    assert "024" not in company.reference_products(source)
    batch = make_batch(tmp_path)
    company.attach_source(batch, source)
    batch.products = [part(batch)]
    output = export_excel(batch)
    sheet = load_workbook(output).active
    assert sheet.max_row == 4 and sheet["E2"].value == 100 and sheet["E3"].value == 200
    assert any("repetido" in note for note in batch.issues)


def test_previous_output_can_be_a_new_base_without_erasing_its_prices_or_orphaning_refs(tmp_path):
    first_folder = tmp_path / "primeiro"
    first_folder.mkdir()
    first = Batch(folder=first_folder, excel_layout="company")
    first.products = [part(first)]
    first.products[0].references = references()
    previous = export_excel(first)
    inherited_key = first.products[0].excel_key
    second = make_batch(tmp_path)
    company.attach_source(second, previous)
    current = part(second)
    assert current.excel_key != inherited_key
    second.products = [current]
    for _ in range(3):
        output = export_excel(second)
    book = load_workbook(output)
    assert [book.active.cell(2, c).value for c in (2, 3, 4)] == [100, 200, 150]
    assert book["REFERÊNCIAS"].max_row == 3
    assert current.excel_key == inherited_key
    # Uma pesquisa nova substitui a antiga no mesmo grupo, sem duplicá-la.
    current.references = references(345678)
    current.references[0].price = Decimal("80")
    export_excel(second)
    book = load_workbook(output)
    assert book.active["B2"].value == 80 and book["REFERÊNCIAS"].max_row == 3
    assert book["REFERÊNCIAS"]["D2"].value == current.references[0].url


def test_legacy_unmarked_refs_are_replaced_after_an_unchanged_export(tmp_path):
    batch = make_batch(tmp_path)
    batch.excel_layout = "standard"
    product = part(batch)
    product.references = references()
    batch.products = [product]
    output = export_excel(batch)
    # Legado: o lote não conhece as referências copiadas da planilha.
    product.references = []
    batch.excel_layout = "company"
    export_excel(batch)
    assert load_workbook(output)["REFERÊNCIAS"].max_row == 3
    product.references = references(345678)
    export_excel(batch)
    sheet = load_workbook(output)["REFERÊNCIAS"]
    assert sheet.max_row == 3
    assert sheet["D2"].value == product.references[0].url
