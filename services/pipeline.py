from dataclasses import dataclass
from pathlib import Path

from .excel_export import export_excel, price_range
from .file_manager import atomic_write, copy_original, create_batch, relocate_sources, safe_name, save_batch
from .image_processor import ImageProcessor, open_image
from .gemini_service import AIError, AIUnavailableError
from .models import Batch, Classification, Photo, PhotoKind, Product
from .naming import standardize_identity


@dataclass
class Options:
    save_originals: bool = True
    quality: int = 92


def checkpoint(batch: Batch):
    save_batch(batch)
    export_excel(batch)
    # O exportador atualiza posição/chave das linhas e consome flags de edição.
    save_batch(batch)


def prepare_batch(paths: list[Path], destination: Path, detector, *, overrides=None, merge_labels=None, preserve=None, progress=None,
                  excel_layout="standard", workbook_template=None) -> Batch:
    from .company_workbook import attach_source, validate_source
    if workbook_template:
        workbook_template = Path(workbook_template).expanduser().resolve()
        validate_source(workbook_template)
    automatic = [path for path in paths if str(path) not in (overrides or {})]
    validate = getattr(detector, "validate_connection", None)
    if automatic and callable(validate):
        validate(automatic)
    batch = create_batch(destination)
    batch.excel_layout = excel_layout
    attach_source(batch, workbook_template)
    batch.total = len(paths)
    batch.source_paths = list(paths)
    batch.source_overrides = {str(path): value.model_copy(deep=True) for path, value in (overrides or {}).items()}
    batch.source_preserve = [str(path) for path in (preserve or [])]
    batch.source_merge_labels = [str(path) for path in (merge_labels or [])]
    current = None
    seen = set()
    for index, path in enumerate(paths):
        if progress:
            progress("Identificando SKU", index, len(paths), batch)
        photo = Photo(path=path, preserve_original=str(path) in (preserve or set()))
        try:
            with open_image(path):
                pass
            photo.classification = (overrides or {}).get(str(path)) or detector.classify(path)
            classification = photo.classification
            if classification.kind == PhotoKind.LABEL:
                if classification.sku:
                    classification.sku = classification.sku.strip() or None
                if classification.confidence < 0.8:
                    classification.sku = None
                if classification.sku and len(classification.sku) > 40:
                    classification.sku = None
            elif classification.kind == PhotoKind.PRODUCT and classification.confidence >= 0.6:
                if classification.confidence < 0.8:
                    photo.review_reason = f"Foto {path.name}: tipo Produto com confiança moderada ({classification.confidence:.0%}); confira a foto e a identificação."
            elif classification.confidence < 0.8:
                # Sem confiança no tipo, não é possível excluir uma nova etiqueta.
                photo.classification = Classification(evidence="Tipo de foto incerto; confira a sequência para não misturar peças.")
        except AIUnavailableError as exc:
            batch.error = str(exc)
            batch.issues.append(str(exc))
            checkpoint(batch)
            exc.batch = batch
            raise
        except Exception as exc:
            # Arquivo ilegível pode ser etiqueta; fecha grupo para evitar misturar peças.
            photo.error = str(exc) if isinstance(exc, AIError) else "Não foi possível ler ou classificar esta imagem. Confira o arquivo, o tamanho e a API."
            photo.classification = Classification(evidence=photo.error)
        classification = photo.classification
        merge = (str(path) in (merge_labels or set()) and classification.kind == PhotoKind.LABEL
                 and classification.sku is not None and current is not None and current.sku == classification.sku)
        photo.merge_with_previous = merge
        if (classification.kind in (PhotoKind.LABEL, PhotoKind.UNKNOWN) and not merge) or current is None:
            sku = classification.sku if classification.kind == PhotoKind.LABEL else None
            identifier = f"{len(batch.products)+1:04d}"
            folder = batch.folder / f"SKU-{safe_name(sku or 'REVISAR')}-{identifier}"
            folder.mkdir()
            current = Product(id=identifier, sku=sku, folder=folder)
            if not sku:
                current.issues.append("Grupo isolado: SKU ausente, ilegível ou foto não classificada. Revise a sequência antes de precificar.")
            if sku and sku in seen:
                current.issues.append("SKU repetido em outro grupo. Mantido separado para não misturar peças ou sobrescrever arquivos.")
            if sku:
                seen.add(sku)
            batch.products.append(current)
        current.photos.append(photo)
        if photo.review_reason:
            current.issues.append(photo.review_reason)
        if photo.error:
            current.issues.append(f"{path.name}: {photo.error}")
        batch.processed = index + 1
        save_batch(batch)
    checkpoint(batch)
    return batch


def process_batch(batch: Batch, ai=None, processor=None, options=None, *, preserve=None, progress=None):
    from .company_workbook import reference_products
    from .naming import manual_identity
    known = reference_products(batch.workbook_template)
    options = options or Options()
    processor = processor or ImageProcessor(options.quality)
    previous_error = batch.error
    for index, product in enumerate(batch.products):
        if product.status == "Concluído" and product.outputs and all((product.folder / name).is_file() for name in product.outputs):
            continue
        products = [photo.path for photo in product.photos
                    if photo.classification.kind == PhotoKind.PRODUCT and not photo.error]
        if product.sku in known and product.identity.name == "Peça não identificada":
            product.identity = manual_identity(known[product.sku]["name"])
            product.identity.evidence = ["Nome importado da planilha fornecida para este SKU; aplicação informada pelo usuário."]
            product.identity_reviewed = True
            product.final = known[product.sku]["final"]
        if product.identity_reviewed and previous_error:
            product.issues = [issue for issue in product.issues if issue != previous_error]
        if progress:
            progress("Identificando produto", index, len(batch.products), batch)
        if products and ai and product.identity.name == "Peça não identificada":
            try:
                product.identity = ai.identify(products)
                if previous_error:
                    product.issues = [issue for issue in product.issues if issue != previous_error]
            except AIUnavailableError as exc:
                batch.error = str(exc)
                product.status = "Interrompido: falha na IA"
                product.issues.append(str(exc))
                checkpoint(batch)
                exc.batch = batch
                raise
            except Exception as exc:
                product.issues.append(str(exc) if isinstance(exc, AIError) else "Identificação Gemini indisponível; corrija o nome manualmente ou tente novamente.")
        if product.identity.confidence < 0.8 and not product.identity_reviewed:
            message = "Identificação incerta: confira nome e atributos antes de pesquisar preços."
            if message not in product.issues:
                product.issues.append(message)
        standardize_identity(product.identity)
        if product.identity.name != "Peça não identificada":
            title = safe_name(product.identity.name)[:40]
            target = batch.folder / f"SKU-{safe_name(product.sku or 'REVISAR')}-{title}-{product.id}"
            if product.folder != target and not target.exists():
                previous_folder = product.folder
                previous_folder.rename(target)
                product.folder = target
                renamed_paths = {}
                for photo in product.photos:
                    if photo.path.is_relative_to(previous_folder):
                        previous_path = photo.path
                        photo.path = target / photo.path.relative_to(previous_folder)
                        renamed_paths[str(previous_path)] = photo.path
                relocate_sources(batch, renamed_paths)
        product.status = "Removendo fundo"
        save_batch(batch)
        product_index = 0
        for photo_index, photo in enumerate(product.photos, 1):
            if options.save_originals and photo.path.exists():
                try:
                    copy_original(photo.path, product.folder / "ORIGINAIS", photo_index)
                except OSError:
                    product.issues.append(f"Não foi possível copiar a original {photo.path.name}.")
            if photo.classification.kind != PhotoKind.PRODUCT or photo.error:
                continue
            product_index += 1
            name = f"{product_index:02d}.jpg"
            if name in product.outputs and (product.folder / name).exists():
                continue
            if progress:
                progress("Removendo fundo", index, len(batch.products), batch)
            try:
                if preserve is not None:
                    photo.preserve_original = str(photo.path) in preserve
                data, warnings = processor.process(photo.path, preserve_original=photo.preserve_original)
                if (product.folder / name).exists():
                    raise FileExistsError("Arquivo já existente; não sobrescrito.")
                atomic_write(product.folder / name, data)
                if name not in product.outputs:
                    product.outputs.append(name)
                product.issues.extend(w for w in warnings if w not in product.issues)
            except Exception:
                product.issues.append(f"Foto {photo.path.name}: tratamento falhou. Revise a foto ou use 'Preservar fundo original' e tente novamente.")
            checkpoint(batch)
        if not products:
            product.issues.append("Nenhuma foto classificada como produto neste grupo.")
        product.status = "Revisão necessária" if product.issues or len(product.outputs) < len(products) else "Concluído"
        if ai:
            batch.usage = dict(ai.usage)
        checkpoint(batch)
    # A classificação incompleta continua pendente: retomar imagens não pode
    # fingir que os arquivos ainda não classificados foram processados.
    unresolved_error = previous_error and any(previous_error in product.issues for product in batch.products)
    if batch.processed == batch.total and not unresolved_error:
        batch.error = None
        if previous_error:
            batch.issues = [issue for issue in batch.issues if issue != previous_error]
        checkpoint(batch)
    return batch


def search_prices(batch: Batch, provider, *, progress=None):
    for index, product in enumerate(batch.products):
        if (not product.sku or product.identity.name == "Peça não identificada"
                or (product.identity.confidence < 0.8 and not product.identity_reviewed)):
            product.issues.append("Pesquisa pendente: confirme SKU e nome da peça.")
            checkpoint(batch)
            continue
        if progress:
            progress("Pesquisando preços", index, len(batch.products), batch)
        try:
            found = provider.search(product)
            had_references = bool(product.references)
            # Preserva referências manuais e substitui somente pesquisas anteriores.
            product.references = [r for r in product.references if r.source == "manual"] + found
            if found or had_references:
                product.references_edited = True
            batch.searches += 1
            if price_range(product.references)[0] is None:
                product.issues.append("Referências insuficientes: é preciso ter ao menos dois anúncios usados, verificados e compatíveis.")
        except Exception as exc:
            from .price_search import SearchUnavailable
            product.issues.append(str(exc) if isinstance(exc, (SearchUnavailable, AIError)) else "Pesquisa indisponível; confira referências manualmente.")
        checkpoint(batch)
    return batch
