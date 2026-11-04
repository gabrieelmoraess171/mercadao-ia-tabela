"""Excel no padrão da empresa; a planilha-base fica local e nunca é publicada."""
from copy import copy
from collections import Counter
from decimal import Decimal
from io import BytesIO
from pathlib import Path
import re
import shutil

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from .file_manager import atomic_write

HEADERS = ["PECAS AVULSAS", "MENOR VALOR", "MAIOR VALOR", "VALOR MEDIO", "VALOR FINAL"]
WIDTHS = [71, 14.7109375, 13.7109375, 14, 13.140625]
MONEY = '"R$" #,##0.00'


def _company_sheet(book):
    for sheet in book:
        first = str(sheet.cell(1, 1).value or "").strip().upper()
        if first in ("PECAS AVULSAS", "PEÇAS AVULSAS", "PEÇA", "PEÇAS", "DESCRIÇÃO", "DESCRICAO"):
            return sheet
    return None


def _valid_headers(sheet):
    aliases = [{"MENOR VALOR", "MENOR"}, {"MAIOR VALOR", "MAIOR"},
               {"VALOR MEDIO", "VALOR MÉDIO", "MÉDIA", "MEDIA"}, {"VALOR FINAL", "FINAL"}]
    return all(str(sheet.cell(1, col).value or "").strip().upper() in allowed
               for col, allowed in enumerate(aliases, 2))


def validate_source(path: Path):
    if not path.is_file() or path.suffix.lower() != ".xlsx":
        raise ValueError("Selecione uma planilha XLSX existente.")
    if path.stat().st_size > 25 * 1024 * 1024:
        raise ValueError("A planilha-base deve ter até 25 MB.")
    book = load_workbook(path, read_only=False)
    try:
        sheet = _company_sheet(book)
        if sheet is None or not _valid_headers(sheet):
            raise ValueError("A planilha precisa ter a coluna PECAS AVULSAS seguida de menor, maior, médio e final.")
    finally:
        book.close()


def attach_source(batch, source: Path | None):
    if source:
        target = batch.folder / "BASE_PLANILHA.xlsx"
        shutil.copy2(source, target)
        batch.workbook_template = target


def _entry(value):
    match = re.match(r"^\s*([A-Za-z0-9][A-Za-z0-9._/-]*)\s*-\s*(.+)$", str(value or ""))
    if not match or not match[2].strip() or match[2].lstrip()[0].isdigit():
        return None
    return match[1], match[2].strip()


def reference_products(path: Path | None):
    if not path or not path.is_file():
        return {}
    book = load_workbook(path, data_only=False)
    try:
        sheet = _company_sheet(book)
        result = {}
        if sheet:
            for row in sheet.iter_rows(min_row=2):
                entry = _entry(row[0].value)
                if not entry:
                    continue
                prefix, name = entry
                final = row[4].value if len(row) > 4 else None
                value = Decimal(str(final)) if isinstance(final, (int, float)) and not isinstance(final, bool) else None
                for sku in {prefix, *prefix.split("/")}:
                    result[sku] = {"name": name, "final": value}
        return result
    finally:
        book.close()


def _new_book():
    book = Workbook()
    sheet = book.active
    sheet.title = "Planilha1"
    sheet.append(HEADERS)
    side = Side(style="thin", color="000000")
    for col, width in enumerate(WIDTHS, 1):
        header = sheet.cell(1, col)
        header.font = Font(name="Calibri", size=11)
        header.fill = PatternFill("solid", fgColor="92D050")
        header.border = Border(left=side, right=side, top=side, bottom=side)
        sheet.column_dimensions[header.column_letter].width = width
    return book, sheet


def _refs_sheet(book, batch):
    from .excel_export import safe_cell
    sheet = book["REFERÊNCIAS"] if "REFERÊNCIAS" in book.sheetnames else book.create_sheet("REFERÊNCIAS")
    headers = ["SKU", "NOME DO ANÚNCIO", "PREÇO", "LINK", "DATA DA CONSULTA", "STATUS DE COMPATIBILIDADE", "MOTIVO", "ORIGEM"]
    for i, value in enumerate(headers, 1):
        sheet.cell(1, i, value)
    for product in batch.products:
        if not product.references and not product.references_edited:
            continue
        for row in range(sheet.max_row, 1, -1):
            if str(sheet.cell(row, 1).value or "") == (product.sku or "REVISAR"):
                sheet.delete_rows(row)
        for ref in product.references:
            sheet.append([safe_cell(product.sku or "REVISAR"), safe_cell(ref.title),
                          float(ref.price) if ref.price is not None else None, safe_cell(ref.url),
                          ref.consulted_at, ref.status, safe_cell(ref.reason), ref.source])
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions


def export_company_workbook(batch):
    from .excel_export import price_range, safe_cell
    from .naming import format_identity_name
    output = batch.folder / "PLANILHA_DE_PRECIFICACAO.xlsx"
    source = output if output.exists() else batch.workbook_template
    if source:
        if not source.is_file():
            raise ValueError("A cópia da planilha-base não foi encontrada; selecione o arquivo novamente.")
        book = load_workbook(source, data_only=False)
        sheet = _company_sheet(book)
        if sheet is None and str(book.active.cell(1, 1).value).upper() == "SKU":
            # Converte o layout anterior, preservando seus dados e valores finais.
            sheet = book.active
            combined = [f"{sheet.cell(r,1).value or 'REVISAR'} - {sheet.cell(r,2).value or ''}" for r in range(2, sheet.max_row+1)]
            sheet.delete_cols(1)
            for row, value in enumerate(combined, 2):
                sheet.cell(row, 1, value)
            for col, value in enumerate(HEADERS, 1):
                sheet.cell(1, col, value)
                sheet.cell(1, col).fill = PatternFill("solid", fgColor="92D050")
        if sheet is None:
            raise ValueError("Formato de planilha-base não reconhecido.")
    else:
        book, sheet = _new_book()
    indexed = {}
    for row in range(2, sheet.max_row + 1):
        entry = _entry(sheet.cell(row, 1).value)
        if entry:
            for sku in {entry[0], *entry[0].split("/")}:
                indexed.setdefault(sku, []).append((row, entry[0]))
    counts = Counter(p.sku for p in batch.products if p.sku)
    for product in batch.products:
        existing = indexed.get(product.sku or "", [])
        if len(existing) > 1 or (product.sku and counts[product.sku] > 1):
            message = f"SKU {product.sku} repetido na planilha-base; nenhuma linha existente foi sobrescrita."
            if message not in batch.issues:
                batch.issues.append(message)
            continue
        if not product.sku and product.excel_row and product.excel_row <= sheet.max_row:
            entry = _entry(sheet.cell(product.excel_row, 1).value)
            if entry and entry[0] == "REVISAR":
                existing = [(product.excel_row, "REVISAR")]
        if existing:
            row, prefix = existing[0]
        else:
            row, prefix = sheet.max_row + 1, product.sku or "REVISAR"
            if product.sku:
                indexed[product.sku] = [(row, prefix)]
            for col in range(1, 6):
                cell = sheet.cell(row, col)
                if row > 2:
                    cell._style = copy(sheet.cell(2, col)._style)
                else:
                    line = Side(style="thin", color="000000")
                    cell.font = Font(name="Calibri", size=11)
                    cell.border = Border(left=line, right=line, top=line, bottom=line)
                if col > 1:
                    cell.number_format = MONEY
                cell.fill = PatternFill("solid", fgColor="FFFFFF")
                cell.alignment = Alignment(vertical="center", horizontal="left" if col == 1 else "right", wrap_text=col == 1)
        product.excel_row = row
        name = format_identity_name(product.identity)
        if not existing or name != "Peça não identificada":
            sheet.cell(row, 1, safe_cell(f"{prefix} - {name}"))
        low, high, average = price_range(product.references)
        if low is not None or product.references_edited:
            for col, value in zip((2, 3, 4), (low, high, average)):
                sheet.cell(row, col).value = float(value) if value is not None else None
        if (not existing and product.final is not None) or product.final_override:
            sheet.cell(row, 5).value = float(product.final) if product.final is not None else None
    sheet.freeze_panes = sheet.freeze_panes or "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for col, width in enumerate(WIDTHS, 1):
        sheet.column_dimensions[sheet.cell(1, col).column_letter].width = width
    _refs_sheet(book, batch)
    buffer = BytesIO()
    book.save(buffer)
    book.close()
    atomic_write(output, buffer.getvalue())
    return output
