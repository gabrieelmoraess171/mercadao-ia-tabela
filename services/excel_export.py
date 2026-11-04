from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

from .file_manager import atomic_write
from .models import Batch, Reference
from .naming import format_identity_name


def price_range(references: list[Reference]):
    from .price_search import item_id
    # Uma referência repetida não torna a comparação suficiente.
    unique = {item_id(r.url): r.price for r in references
              if r.verified and r.compatible and r.condition == "used" and r.price is not None and item_id(r.url)}
    if len(unique) < 2:
        return None, None, None
    low, high = min(unique.values()), max(unique.values())
    return low, high, ((low + high) / Decimal("2")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def safe_cell(value):
    if isinstance(value, str):
        value = ILLEGAL_CHARACTERS_RE.sub("", value)
    # Impede que nomes, SKUs ou títulos externos virem fórmulas no Excel.
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def export_excel(batch: Batch):
    if batch.excel_layout == "company":
        from .company_workbook import export_company_workbook
        return export_company_workbook(batch)
    book = Workbook()
    sheet = book.active
    sheet.title = "PRECIFICAÇÃO"
    sheet.append(["SKU", "PEÇA", "MENOR", "MAIOR", "MÉDIA", "FINAL"])
    refs = book.create_sheet("REFERÊNCIAS")
    refs.append(["SKU", "NOME DO ANÚNCIO", "PREÇO", "LINK", "DATA DA CONSULTA", "STATUS DE COMPATIBILIDADE", "MOTIVO", "ORIGEM"])
    for product in batch.products:
        low, high, mean = price_range(product.references)
        sheet.append([safe_cell(product.sku or "REVISAR"), safe_cell(format_identity_name(product.identity)),
                      *[float(v) if v is not None else None for v in (low, high, mean, product.final)]])
        for reference in product.references:
            refs.append([safe_cell(product.sku or "REVISAR"), safe_cell(reference.title),
                         float(reference.price) if reference.price is not None else None,
                         safe_cell(reference.url), reference.consulted_at, reference.status,
                         safe_cell(reference.reason), reference.source])
    line = Side(style="thin", color="DDDDDD")
    for page, widths in [(sheet, [18, 65, 20, 20, 20, 20]), (refs, [18, 60, 20, 65, 30, 35, 65, 22])]:
        page.freeze_panes = "A2"
        page.auto_filter.ref = page.dimensions
        for row in page:
            for cell in row:
                cell.font = Font(name="Calibri", size=11, bold=cell.row == 1)
                cell.border = Border(left=line, right=line, top=line, bottom=line)
                cell.alignment = Alignment(vertical="center", wrap_text=True)
                cell.fill = PatternFill("solid", fgColor="E8F1EF" if cell.row == 1 else "FFFFFF")
                if cell.row > 1 and ((page == sheet and cell.column >= 3) or (page == refs and cell.column == 3)):
                    cell.number_format = '"R$" #,##0.00'
        for i, width in enumerate(widths, 1):
            page.column_dimensions[page.cell(1, i).column_letter].width = width
    stream = BytesIO()
    book.save(stream)
    path = batch.folder / "PLANILHA_DE_PRECIFICACAO.xlsx"
    atomic_write(path, stream.getvalue())
    return path
