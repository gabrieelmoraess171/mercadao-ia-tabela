"""Excel no padrão da empresa; a planilha-base fica local e nunca é publicada."""
from copy import copy
from collections import Counter, defaultdict
from decimal import Decimal
from io import BytesIO
from pathlib import Path
import re
import hashlib
import shutil

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.comments import Comment

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
        for notice in source_issues(target):
            _warn(batch, notice)


def _entry(value):
    match = re.match(r"^\s*([A-Za-z0-9][A-Za-z0-9._/-]*)\s*-\s*(.+)$", str(value or ""))
    if not match or not match[2].strip() or match[2].lstrip()[0].isdigit():
        return None
    return match[1], match[2].strip()


def source_issues(path: Path) -> list[str]:
    """Sinaliza dados ambíguos sem corrigir códigos ou preços por suposição."""
    notices = []
    book = load_workbook(path, data_only=False)
    try:
        sheet = _company_sheet(book)
        if sheet is None:
            return notices
        seen = defaultdict(list)
        for row in sheet.iter_rows(min_row=2):
            if row[0].value is None:
                continue
            number = row[0].row
            entry = _entry(row[0].value)
            if entry is None:
                notices.append(f"Planilha-base, linha {number}: SKU/descrição ambíguos; linha preservada, sem presumir um código.")
            else:
                for sku in {entry[0], *entry[0].split('/')}:
                    seen[sku].append(number)
            if any(isinstance(cell.value, str) and cell.data_type != "f" for cell in row[1:5]):
                notices.append(f"Planilha-base, linha {number}: preço com texto ou unidade; valor preservado sem conversão automática.")
            if any(isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool) and cell.value < 0 for cell in row[1:5]):
                notices.append(f"Planilha-base, linha {number}: preço negativo; confira o valor original antes de precificar.")
        for sku, rows in seen.items():
            if len(rows) > 1:
                notices.append(f"Planilha-base: SKU {sku} repetido nas linhas {', '.join(map(str, rows))}; confira os grupos antes de atualizar.")
    finally:
        book.close()
    return notices


def reference_products(path: Path | None):
    if not path or not path.is_file():
        return {}
    book = load_workbook(path, data_only=False)
    try:
        sheet = _company_sheet(book)
        candidates = defaultdict(list)
        if sheet:
            for row in sheet.iter_rows(min_row=2):
                entry = _entry(row[0].value)
                if not entry:
                    continue
                prefix, name = entry
                final = row[4].value if len(row) > 4 else None
                value = Decimal(str(final)) if isinstance(final, (int, float)) and not isinstance(final, bool) and final >= 0 else None
                for sku in {prefix, *prefix.split("/")}:
                    # Um preço da linha 101/102 não comprova o valor individual.
                    candidates[sku].append({"name": name, "final": value if sku == prefix else None})
        # Uma inscrição duplicada não escolhe silenciosamente a última descrição.
        return {sku: values[0] for sku, values in candidates.items() if len(values) == 1}
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


_KEY = re.compile(r"^PRECIFICADOR_GRUPO=([a-zA-Z0-9-]+)$", re.MULTILINE)
_SIGNATURE = re.compile(r"^PRECIFICADOR_REFERENCIAS=([a-f0-9]+)$", re.MULTILINE)


def _row_key(cell):
    match = _KEY.search(cell.comment.text) if cell.comment else None
    return match[1] if match else None


def _reference_signature(product):
    payload = "\n".join(reference.model_dump_json() for reference in product.references)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _stored_signature(cell):
    match = _SIGNATURE.search(cell.comment.text) if cell.comment else None
    return match[1] if match else None


def _mark(cell, product, signature=None):
    original = cell.comment
    note = original.text if original else ""
    note = _KEY.sub("", note)
    if signature is not None:
        note = _SIGNATURE.sub("", note)
    note = note.strip()
    metadata = f"PRECIFICADOR_GRUPO={product.excel_key}"
    if signature is not None:
        metadata += f"\nPRECIFICADOR_REFERENCIAS={signature}"
    cell.comment = Comment((note + "\n" if note else "") + metadata,
                           original.author if original else "Precificador")


def _warn(batch, text):
    if text not in batch.issues:
        batch.issues.append(text)


def _refs_sheet(book, batch, dirty_keys, legacy_skus):
    from .excel_export import safe_cell
    sheet = book["REFERÊNCIAS"] if "REFERÊNCIAS" in book.sheetnames else book.create_sheet("REFERÊNCIAS")
    headers = ["SKU", "NOME DO ANÚNCIO", "PREÇO", "LINK", "DATA DA CONSULTA", "STATUS DE COMPATIBILIDADE", "MOTIVO", "ORIGEM"]
    for i, value in enumerate(headers, 1):
        sheet.cell(1, i, value)
    for product in batch.products:
        if product.excel_key not in dirty_keys:
            continue
        sku = product.sku or "REVISAR"
        for row in range(sheet.max_row, 1, -1):
            cell = sheet.cell(row, 1)
            key = _row_key(cell)
            if key == product.excel_key or (key is None and sku in legacy_skus and str(cell.value or "") == sku):
                sheet.delete_rows(row)
        for ref in product.references:
            sheet.append([safe_cell(sku), safe_cell(ref.title),
                          float(ref.price) if ref.price is not None else None, safe_cell(ref.url),
                          ref.consulted_at, ref.status, safe_cell(ref.reason), ref.source])
            _mark(sheet.cell(sheet.max_row, 1), product)
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions


def _append_row(sheet):
    row = sheet.max_row + 1
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
    return row


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
            # O layout anterior tinha uma coluna SKU separada.
            sheet = book.active
            combined = [f"{sheet.cell(r,1).value or 'REVISAR'} - {sheet.cell(r,2).value or ''}" for r in range(2, sheet.max_row+1)]
            sheet.delete_cols(1)
            for row, value in enumerate(combined, 2):
                sheet.cell(row, 1, value)
            for col, value in enumerate(HEADERS, 1):
                sheet.cell(1, col, value)
                sheet.cell(1, col).fill = PatternFill("solid", fgColor="92D050")
        if sheet is None:
            book.close()
            raise ValueError("Formato de planilha-base não reconhecido.")
    else:
        book, sheet = _new_book()
    indexed, owned = defaultdict(list), defaultdict(list)
    for row in range(2, sheet.max_row + 1):
        cell = sheet.cell(row, 1)
        entry = _entry(cell.value)
        if entry:
            for sku in {entry[0], *entry[0].split("/")}:
                indexed[sku].append((row, entry[0]))
        if key := _row_key(cell):
            owned[key].append(row)
    counts = Counter(p.sku for p in batch.products if p.sku)
    dirty_keys, legacy_skus = set(), set()
    for product in batch.products:
        sku = product.sku or "REVISAR"
        matches = indexed.get(product.sku or "", [])
        mine = [row for row in owned[product.excel_key]
                if (entry := _entry(sheet.cell(row, 1).value)) and entry[0] == sku]
        existing = False
        inherited = False
        if len(mine) == 1:
            row = mine[0]
            existing = True
        elif product.sku and counts[product.sku] == 1 and len(matches) == 1 and matches[0][1] == product.sku:
            row = matches[0][0]
            existing = True
            # A planilha-base pode ter sido produzida por outro lote. A linha e
            # suas referências continuam sendo do mesmo SKU, mas os preços
            # herdados não são uma nova pesquisa deste lote.
            previous_key = _row_key(sheet.cell(row, 1))
            if previous_key and previous_key != product.excel_key:
                product.excel_key = previous_key
                inherited = True
            # Legado sem metadados: um SKU único ainda identifica suas referências.
            legacy_skus.add(product.sku)
        else:
            row = _append_row(sheet)
            indexed[sku].append((row, sku))
            if matches or (product.sku and counts[product.sku] > 1):
                _warn(batch, f"SKU {sku} repetido ou agrupado: linhas existentes foram preservadas; grupo {product.id} exportado em linha própria para revisão.")
        product.excel_row = row
        if (product.sku and counts[product.sku] == 1 and len(matches) == 1
                and matches[0] == (row, product.sku)):
            # A primeira exportação pode ter mantido referências legadas sem
            # comentário. Elas continuam atribuíveis ao SKU único em pesquisas
            # posteriores, mesmo depois de a linha principal ganhar sua chave.
            legacy_skus.add(product.sku)
        cell = sheet.cell(row, 1)
        signature = _reference_signature(product)
        previous_signature = _stored_signature(cell)
        references_changed = signature != previous_signature
        inherited_untouched = inherited and not product.references and not product.references_edited
        recalculate = not inherited_untouched and (product.references_edited or (
            references_changed and (bool(product.references) or previous_signature is not None)))
        name = format_identity_name(product.identity)
        if not existing or name != "Peça não identificada":
            cell.value = safe_cell(f"{sku} - {name}")
        low, high, average = price_range(product.references)
        if recalculate or (not existing and low is not None):
            for col, value in zip((2, 3, 4), (low, high, average)):
                sheet.cell(row, col).value = float(value) if value is not None else None
        if (not existing and product.final is not None) or product.final_override:
            sheet.cell(row, 5).value = float(product.final) if product.final is not None else None
        if recalculate or (references_changed and product.references):
            dirty_keys.add(product.excel_key)
        _mark(cell, product, signature)
    sheet.freeze_panes = sheet.freeze_panes or "A2"
    sheet.auto_filter.ref = sheet.dimensions
    for col, width in enumerate(WIDTHS, 1):
        sheet.column_dimensions[sheet.cell(1, col).column_letter].width = width
    _refs_sheet(book, batch, dirty_keys, legacy_skus)
    buffer = BytesIO()
    book.save(buffer)
    book.close()
    atomic_write(output, buffer.getvalue())
    # Limpar somente após uma gravação concluída. Não reaplicar uma edição antiga
    # por cima de preços que o usuário alterou depois diretamente no Excel.
    for product in batch.products:
        product.final_override = False
        product.references_edited = False
    return output
