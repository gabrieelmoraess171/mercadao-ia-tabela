import os
import tempfile
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import quote

import streamlit as st
from dotenv import load_dotenv

from services.excel_export import export_excel, price_range
from services.file_manager import list_images, load_batch, natural_key, save_batch, store_upload
from services.gemini_service import AIError, AIUnavailableError, DEFAULT_MODEL, GeminiService, normalize_model
from services.image_processor import analysis_bytes
from services.local_ui import choose_folder, choose_workbook, open_local
from services.models import Batch, Classification, Identity, PhotoKind, Reference
from services.pipeline import Options, prepare_batch, process_batch, search_prices
from services.price_search import MercadoLivreProvider, item_id
from services.sku_detector import SkuDetector
from services.mercadolivre_auth import AuthorizationError
from services.mercadolivre_auth_ui import access_token, connection_ui
from services.naming import format_identity_name, manual_identity, standardize_identity

load_dotenv()
APP_VERSION = "1.2.0"
st.set_page_config(page_title="Precificador de peças — IA", page_icon="⚙️", layout="wide")


def money(value):
    if value is None or str(value).lower() in ("nan", "none", ""):
        return None
    try:
        number = Decimal(str(value).replace(",", "."))
    except InvalidOperation:
        raise ValueError("Informe um valor monetário válido.") from None
    if not number.is_finite() or number < 0:
        raise ValueError("Os preços devem ser números positivos.")
    try:
        return number.quantize(Decimal("0.01"))
    except InvalidOperation:
        raise ValueError("Valor monetário muito grande. Confira o preço informado.") from None


def native_folder(key):
    try:
        selected = choose_folder()
        if selected:
            st.session_state[key] = selected
    except Exception:
        st.session_state["dialog_notice"] = "Seletor nativo indisponível. Digite o caminho da pasta no computador que executa o aplicativo."


def open_button(label, path, key):
    if st.button(label, key=key):
        try:
            open_local(path)
        except Exception:
            st.info(f"Abra manualmente: {path}")


def native_workbook():
    try:
        selected = choose_workbook()
        if selected:
            st.session_state["workbook_source"] = selected
    except Exception:
        st.session_state["dialog_notice"] = "Digite o caminho completo da planilha XLSX no campo Planilha existente."


def main():
    st.title("PRECIFICADOR DE PEÇAS — IA")
    st.caption(f"Versão {APP_VERSION} · Suas fotos organizadas por SKU. Imagens prontas e planilha salva no seu computador.")
    with st.expander("Configurações", expanded=True):
        left, right = st.columns(2)
        with left:
            api_key = st.text_input("Chave da API Gemini", value=os.getenv("GEMINI_API_KEY", ""), type="password")
            st.text_input("Pasta de destino", value=str(Path.cwd() / "resultados"), key="destination")
            st.button("Escolher pasta de destino", on_click=native_folder, args=("destination",))
            do_search = st.checkbox("Pesquisar preços", value=True)
        with right:
            model = st.text_input("Modelo Gemini", value=normalize_model(os.getenv("GEMINI_MODEL", DEFAULT_MODEL)))
            originals = st.checkbox("Salvar imagens originais", value=True)
            grounding = st.checkbox("Usar Google Search para descobrir anúncios", value=False,
                help="Pode gerar cobrança adicional no Gemini. Links só entram no cálculo após verificação de preço e compatibilidade.")
            review_names = st.checkbox("Conferir nomes antes da pesquisa", value=True)
        st.caption("Padrão de nomes: PORTA L.D RENAULT DUSTER 14-20 · dianteira/traseira: D.D, D.E, T.D e T.E. Marca e ano só entram quando confirmados.")
        st.text_input("Planilha existente (opcional)", key="workbook_source",
            help="Selecione PECAS AVULSAS 34.xlsx para continuar seu estoque. O programa trabalha em uma cópia e aproveita os nomes dos SKUs já cadastrados.")
        st.button("Escolher planilha existente", on_click=native_workbook)
        st.caption("Excel: PECAS AVULSAS · MENOR VALOR · MAIOR VALOR · VALOR MEDIO · VALOR FINAL. O SKU fica junto do nome, como na sua planilha.")
        with st.expander("Ajustes de processamento"):
            quality = st.slider("Qualidade JPG", 80, 100, 92)
            limit = st.number_input("Máximo de chamadas Gemini por operação", 1, 10000, 1000)
            interval = st.number_input("Pausa entre chamadas (segundos)", 0.0, 60.0, 1.0)
            token = st.text_input("Token oficial do Mercado Livre (opcional)", value=os.getenv("MELI_ACCESS_TOKEN", ""), type="password")
    st.caption("O Gemini recebe versões otimizadas das fotos para análise. Consultas externas podem gerar custos. "
               "Fotos e resultados ficam locais; não há sincronização com armazenamento online.")
    if st.session_state.get("dialog_notice"):
        st.info(st.session_state.pop("dialog_notice"))
    connection_ui()

    def get_ai():
        return GeminiService(api_key, model, max_calls=int(limit), interval=float(interval)) if api_key else None

    def run_search(batch, ai):
        try:
            authorized_token = access_token(token)
        except AuthorizationError as exc:
            st.warning(str(exc))
            authorized_token = token
        provider = MercadoLivreProvider(ai, authorized_token, use_grounding=grounding)
        try:
            search_prices(batch, provider, progress=update_progress)
        finally:
            provider.close()

    st.subheader("1. Selecionar imagens")
    source = st.radio("Origem", ["Pasta local (recomendado para lotes grandes)", "Selecionar imagens"], horizontal=True)
    if source.startswith("Pasta"):
        st.text_input("Pasta com fotografias", key="source_folder")
        st.button("Selecionar pasta com fotografias", on_click=native_folder, args=("source_folder",))
        if st.button("Carregar fotografias da pasta"):
            try:
                st.session_state["paths"] = list_images(Path(st.session_state.source_folder).expanduser())
                st.session_state["sequence_version"] = st.session_state.get("sequence_version", 0) + 1
                st.session_state.pop("review_sequence", None)
            except (ValueError, OSError) as exc:
                st.error(str(exc))
    else:
        uploaded = st.file_uploader("Selecionar imagens", type=["jpg", "jpeg", "png", "heic", "heif"], accept_multiple_files=True)
        st.caption("Até 100 MB por arquivo. O navegador mantém uploads em memória; para centenas de fotos pesadas, use uma pasta local.")
        if st.button("Carregar imagens selecionadas", disabled=not uploaded):
            # TemporaryDirectory permanece na sessão; é eliminado quando a sessão é descartada.
            temporary = tempfile.TemporaryDirectory(prefix="precificador-")
            paths = []
            for index, upload in enumerate(sorted(uploaded, key=lambda f: natural_key(Path(f.name))), 1):
                try:
                    paths.append(store_upload(upload, Path(temporary.name), index))
                except (ValueError, OSError) as exc:
                    st.error(f"{upload.name}: {exc}")
            st.session_state["upload_dirs"] = st.session_state.get("upload_dirs", []) + [temporary]
            st.session_state["paths"] = paths
            st.session_state["sequence_version"] = st.session_state.get("sequence_version", 0) + 1
            st.session_state.pop("review_sequence", None)

    paths = st.session_state.get("paths", [])
    overrides, preserve, merge_labels = {}, set(), set()
    if paths:
        total_bytes = sum(p.stat().st_size for p in paths if p.exists())
        st.write(f"**{len(paths)} fotografias** · {total_bytes / (1024*1024):,.1f} MB no total")
        st.subheader("2. Conferir a sequência")
        st.caption("Ordenação natural dos nomes aplicada. Altere ORDEM para mover fotos. "
                   "TIPO e SKU são opcionais; preencha-os para corrigir a leitura automática. "
                   "O SKU só deve aparecer nas linhas de etiqueta. Sem chave Gemini, classifique os tipos manualmente.")
        rows = st.session_state.get("review_sequence") or [
            {"ORDEM": i, "ARQUIVO": p.name, "TIPO": "Automático", "SKU": "", "PRESERVAR FUNDO ORIGINAL": False,
             "ETIQUETA REPETIDA DA MESMA PEÇA": False}
            for i, p in enumerate(paths, 1)]
        edited = st.data_editor(rows, hide_index=True, width="stretch", disabled=["ARQUIVO"],
            column_config={"TIPO": st.column_config.SelectboxColumn(options=["Automático"] + [k.value for k in PhotoKind]),
                           "SKU": st.column_config.TextColumn(),
                           "ORDEM": st.column_config.NumberColumn(min_value=1, step=1)},
            key=f"sequence-{st.session_state.get('sequence_version', 0)}")
        valid_order = all(isinstance(r["ORDEM"], (int, float)) and r["ORDEM"] > 0 for r in edited)
        valid_order = valid_order and len({r["ORDEM"] for r in edited}) == len(paths)
        if not valid_order:
            st.error("Informe uma ordem positiva e sem números repetidos para todas as fotos.")
        ordered_pairs = sorted(zip(edited, paths), key=lambda pair: pair[0]["ORDEM"] or 0)
        ordered_paths = [p for _, p in ordered_pairs]
        for row, path in ordered_pairs:
            kind = row["TIPO"] or "Automático"
            if kind != "Automático":
                overrides[str(path)] = Classification(kind=PhotoKind(kind), sku=str(row["SKU"] or "").strip() or None,
                    confidence=1, evidence="Classificação conferida manualmente.")
            if row["PRESERVAR FUNDO ORIGINAL"]:
                preserve.add(str(path))
            if row.get("ETIQUETA REPETIDA DA MESMA PEÇA"):
                merge_labels.add(str(path))
        with st.expander("Miniaturas e conferência visual"):
            page = st.number_input("Página de miniaturas", 1, max(1, (len(paths)+11)//12), 1)
            preview = ordered_paths[(int(page)-1)*12:int(page)*12]
            columns = st.columns(4)
            for i, path in enumerate(preview):
                try:
                    columns[i % 4].image(analysis_bytes(path, 360), caption=path.name, width="stretch")
                except Exception:
                    columns[i % 4].warning(f"{path.name}: imagem inválida.")

    progress = st.progress(0, text="Aguardando")
    counters = st.empty()

    def update_progress(state, current, total, batch):
        progress.progress(min(1.0, current / max(1, total)), text=f"{state}: {current}/{total}")
        counters.caption(f"Imagens: {batch.processed}/{batch.total} · SKUs: {len({p.sku for p in batch.products if p.sku})} · "
                         f"Peças identificadas: {sum(p.identity.name != 'Peça não identificada' for p in batch.products)} · Pesquisas: {batch.searches}")

    def execute_processing(input_paths, destination, classifications=None, preserve_photos=None, merge_photos=None, previous_template=None):
        ai, active_batch = None, None
        st.session_state.pop("processing_error", None)
        try:
            automatic = [path for path in input_paths if str(path) not in (classifications or {})]
            if automatic and not api_key.strip():
                raise AIUnavailableError("Preencha a chave Gemini para identificar as fotos automaticamente. Sem chave, informe TIPO e SKU de todas as fotos na sequência antes de processar.")
            ai = get_ai()
            if automatic:
                progress.progress(0, text="Validando a análise Gemini com a primeira foto…")
            active_batch = prepare_batch(input_paths, destination, SkuDetector(ai),
                overrides=classifications, merge_labels=merge_photos, preserve=preserve_photos, progress=update_progress,
                excel_layout="company", workbook_template=st.session_state.workbook_source.strip() or previous_template)
            st.session_state["batch"] = active_batch
            process_batch(active_batch, ai, options=Options(originals, quality), preserve=preserve_photos, progress=update_progress)
            if do_search and not review_names:
                run_search(active_batch, ai)
            identified = sum(p.identity.name != "Peça não identificada" for p in active_batch.products)
            progress.progress(1.0, text=f"Análise terminada: {identified} peças identificadas. Confira as pendências abaixo.")
            if not identified:
                active_batch.issues.append("Nenhuma peça foi identificada. Confira as classificações e os erros da análise antes de continuar.")
        except AIError as exc:
            active_batch = active_batch or getattr(exc, "batch", None)
            st.session_state["processing_error"] = str(exc)
            if active_batch:
                active_batch.error = str(exc)
                st.session_state["batch"] = active_batch
            progress.progress(0, text="Análise interrompida. Veja o erro abaixo.")
        except ValueError as exc:
            st.session_state["processing_error"] = str(exc)
        except Exception:
            st.session_state["processing_error"] = "Processamento interrompido. Os resultados já gravados foram preservados. Confira espaço, permissão da pasta e se o Excel está fechado."
        finally:
            if active_batch:
                if ai:
                    active_batch.usage = dict(ai.usage)
                    active_batch.ai_model = getattr(ai, "model", model)
                    active_batch.issues.extend(n for n in getattr(ai, "notices", []) if n not in active_batch.issues)
                save_batch(active_batch)
            if ai:
                ai.close()

    def reanalyze_saved_batch(batch):
        photos = [photo for product in batch.products for photo in product.photos]
        manual = dict(batch.source_overrides)
        manual.update({str(photo.path): photo.classification for photo in photos
                       if photo.classification.evidence == "Classificação conferida manualmente."})
        keep = set(batch.source_preserve) | {str(photo.path) for photo in photos if photo.preserve_original}
        merge = set(batch.source_merge_labels) | {str(photo.path) for photo in photos if photo.merge_with_previous}
        source_paths = batch.source_paths or [photo.path for photo in photos]
        execute_processing(source_paths, batch.folder.parent, manual, keep, merge, batch.workbook_template)

    if paths and st.button("INICIAR PROCESSAMENTO", type="primary", disabled=not valid_order):
        execute_processing(ordered_paths, Path(st.session_state.destination), overrides, preserve, merge_labels)
    if st.session_state.get("processing_error"):
        st.error(st.session_state.processing_error)

    with st.expander("Abrir lote salvo"):
        resume_path = st.text_input("Pasta do lote (contendo lote.json)")
        if st.button("Abrir resultados salvos"):
            try:
                st.session_state["batch"] = load_batch(Path(resume_path))
                st.session_state.pop("processing_error", None)
                st.rerun()
            except Exception:
                st.error("Não foi possível abrir esse lote. Escolha uma pasta com um lote.json válido.")

    batch = st.session_state.get("batch")
    if not batch:
        return
    if not isinstance(batch, Batch):
        batch = Batch.model_validate(batch.model_dump(mode="json"))
        st.session_state["batch"] = batch
    st.subheader("3. Resultados e revisão")
    st.caption(str(batch.folder))
    if batch.ai_model:
        st.caption(f"Modelo usado na análise: {batch.ai_model}")
    if batch.error:
        st.error(batch.error)
    for issue in dict.fromkeys(batch.issues):
        st.warning(issue)
    if not batch.products:
        st.info("O lote ainda não tem grupos identificados.")
        if batch.source_paths and st.button("Reanalisar lote com a IA", type="primary"):
            reanalyze_saved_batch(batch)
            st.rerun()
        return
    if not any(p.identity.name != "Peça não identificada" for p in batch.products):
        st.error("Este lote ainda não tem peças identificadas. Use Reanalisar lote com a IA para refazer a leitura e o agrupamento com a conexão corrigida.")
        errors = [photo.error for p in batch.products for photo in p.photos if photo.error]
        if errors:
            st.error("Causa registrada no lote: " + errors[0])
    data = []
    for product in batch.products:
        low, high, average = price_range(product.references)
        data.append({"SKU": product.sku or "REVISAR", "PEÇA": format_identity_name(product.identity),
            "MENOR": float(low) if low is not None else float("nan"), "MAIOR": float(high) if high is not None else float("nan"),
            "MÉDIA": float(average) if average is not None else float("nan"),
            "FINAL": float(product.final) if product.final is not None else float("nan"),
            "SITUAÇÃO": product.status,
            "PESQUISA": "Pesquisa pendente" if low is None else "Referências disponíveis"})
    final_rows = st.data_editor(data, hide_index=True, width="stretch", key=f"final-{batch.folder.name}",
        disabled=["SKU", "MENOR", "MAIOR", "MÉDIA", "SITUAÇÃO", "PESQUISA"],
        column_config={"FINAL": st.column_config.NumberColumn(min_value=0, format="R$ %.2f"),
                       "MENOR": st.column_config.NumberColumn(format="R$ %.2f"),
                       "MAIOR": st.column_config.NumberColumn(format="R$ %.2f"),
                       "MÉDIA": st.column_config.NumberColumn(format="R$ %.2f"),
                       "PEÇA": st.column_config.TextColumn(required=True)})
    st.caption("Salve para confirmar os nomes antes da pesquisa. Ao alterar um nome, as referências anteriores "
               "precisam de nova conferência de compatibilidade e os atributos da identificação anterior são descartados.")
    if st.button("Salvar nomes e valores finais no Excel"):
        try:
            values = [money(row["FINAL"]) for row in final_rows]
            names = [str(row["PEÇA"] or "").strip() for row in final_rows]
            if not all(names):
                raise ValueError("Informe um nome para todas as peças antes de salvar.")
            for product, name, value in zip(batch.products, names, values):
                corrected = manual_identity(name)
                if format_identity_name(product.identity) != corrected.name:
                    product.identity = corrected
                    for reference in product.references:
                        reference.compatible = False
                        reference.status = "Revisão necessária: nome da peça alterado"
                    if product.references:
                        product.issues.append("Nome alterado: confira novamente a compatibilidade das referências anteriores.")
                        product.references_edited = True
                else:
                    standardize_identity(product.identity)
                product.identity_reviewed = product.identity.name != "Peça não identificada"
                if product.final != value:
                    product.final_override = True
                product.final = value
            batch.excel_layout = "company"
            export_excel(batch)
            save_batch(batch)
            st.success("Excel atualizado na pasta do lote.")
            st.rerun()
        except Exception:
            st.error("Não foi possível salvar. Confira valores e feche a planilha no Excel antes de tentar novamente.")
    if st.button("Padronizar nomes e Excel deste lote"):
        try:
            for product in batch.products:
                standardize_identity(product.identity)
            batch.excel_layout = "company"
            export_excel(batch)
            save_batch(batch)
            st.rerun()
        except Exception:
            st.error("Feche a planilha no Excel e confira a permissão da pasta antes de tentar novamente.")
    if do_search and st.button("Pesquisar preços dos nomes salvos", type="primary"):
        st.session_state.pop("processing_error", None)
        ai = None
        try:
            ai = get_ai()
            run_search(batch, ai)
            if ai:
                batch.usage = dict(ai.usage)
            save_batch(batch)
        except AIError as exc:
            st.session_state["processing_error"] = str(exc)
        except Exception:
            st.session_state["processing_error"] = "Não foi possível concluir a pesquisa. As referências salvas foram preservadas; confira a conexão e tente novamente."
        finally:
            if ai:
                ai.close()
        st.rerun()
    if st.button("Levar classificações à conferência da sequência"):
        photos = [photo for product in batch.products for photo in product.photos]
        st.session_state["paths"] = [photo.path for photo in photos]
        st.session_state["review_sequence"] = [{"ORDEM": i, "ARQUIVO": photo.path.name,
            "TIPO": photo.classification.kind.value, "SKU": photo.classification.sku or "",
            "PRESERVAR FUNDO ORIGINAL": photo.preserve_original,
            "ETIQUETA REPETIDA DA MESMA PEÇA": photo.merge_with_previous} for i, photo in enumerate(photos, 1)]
        st.session_state["sequence_version"] = st.session_state.get("sequence_version", 0) + 1
        st.rerun()
    if st.button("Reanalisar lote com a IA", type="primary"):
        reanalyze_saved_batch(batch)
        st.rerun()
    if st.button("Retomar identificação e fotos pendentes do lote"):
        st.session_state.pop("processing_error", None)
        ai = None
        try:
            if batch.processed < batch.total and batch.source_paths:
                reanalyze_saved_batch(batch)
            else:
                ai = get_ai()
                process_batch(batch, ai, options=Options(originals, quality), progress=update_progress)
        except AIError as exc:
            st.session_state["processing_error"] = str(exc)
        except Exception:
            st.session_state["processing_error"] = "Não foi possível retomar. Confira os arquivos originais, a permissão da pasta e se o Excel está fechado."
        finally:
            if ai:
                ai.close()
        st.rerun()
    st.caption("Para corrigir agrupamentos, leve as classificações à sequência, ajuste etiqueta/tipo/SKU e inicie um novo lote. O anterior é preservado.")

    product_by_id = {product.id: product for product in batch.products}
    selected_id = st.selectbox("Conferir peça", list(product_by_id), key=f"product-{batch.folder.name}",
        format_func=lambda identifier: f"{product_by_id[identifier].sku or 'REVISAR'} · {product_by_id[identifier].identity.name} · grupo {identifier}")
    selected = product_by_id[selected_id]
    with st.expander("Detalhes, fotos e pendências da peça", expanded=True):
        st.write(f"Confiança da IA: {selected.identity.confidence:.0%}")
        if selected.identity_reviewed:
            st.caption("Nome conferido manualmente.")
        if selected.identity.evidence:
            st.write("Evidências: " + "; ".join(selected.identity.evidence))
        labels = {"manufacturer": "Fabricante da peça", "vehicle_brand": "Marca do veículo", "vehicle_model": "Modelo",
                  "version": "Versão", "years": "Ano / aplicação", "side": "Lado", "position": "Posição",
                  "oem": "Código OEM", "part_number": "Referência da peça"}
        st.dataframe([{"ATRIBUTO": label, "INFORMAÇÃO": getattr(selected.identity, field) or "Não confirmado"}
                      for field, label in labels.items()], hide_index=True, width="stretch")
        if selected.identity.inscriptions:
            st.write("Inscrições visíveis: " + "; ".join(selected.identity.inscriptions))
        for issue in dict.fromkeys(selected.issues):
            st.warning(issue)
        for name in selected.outputs:
            if (selected.folder / name).exists():
                st.image(str(selected.folder / name), caption=name, width=240)
        st.caption("Revise contornos e detalhes da peça. Para usar a original sem remoção, escolha essa opção na sequência e gere novo lote.")

    st.link_button("Abrir busca manual no Mercado Livre", "https://lista.mercadolivre.com.br/" + quote(selected.identity.query()))
    st.caption("Referências manuais: marque VERIFICADO somente depois de conferir preço e condição no anúncio; "
               "marque COMPATÍVEL após conferir aplicação, lado, códigos e fotos. São necessários dois links distintos para calcular preços.")
    reference_rows = [{"TÍTULO": r.title, "PREÇO": float(r.price) if r.price is not None else None,
        "LINK": r.url, "CONDIÇÃO": "Usada" if r.condition == "used" else "Nova" if r.condition == "new" else "Desconhecida",
        "VERIFICADO": r.verified, "COMPATÍVEL": r.compatible, "OBSERVAÇÃO": r.reason} for r in selected.references]
    reference_rows = reference_rows or [{"TÍTULO": "", "PREÇO": None, "LINK": "", "CONDIÇÃO": "Usada",
        "VERIFICADO": False, "COMPATÍVEL": False, "OBSERVAÇÃO": ""}]
    ref_edit = st.data_editor(reference_rows, hide_index=True, num_rows="dynamic", width="stretch",
        key=f"refs-{batch.folder.name}-{selected.id}-{len(selected.references)}",
        column_config={"PREÇO": st.column_config.NumberColumn(min_value=0.01, format="R$ %.2f"),
            "CONDIÇÃO": st.column_config.SelectboxColumn(options=["Usada", "Nova", "Desconhecida"]),
            "VERIFICADO": st.column_config.CheckboxColumn(), "COMPATÍVEL": st.column_config.CheckboxColumn()})
    if st.button("Salvar referências e recalcular Excel"):
        try:
            new_refs = []
            for row in ref_edit:
                if not row.get("LINK") and not row.get("TÍTULO"):
                    continue
                if not item_id(row["LINK"]):
                    raise ValueError("Informe o link HTTPS de um anúncio individual do Mercado Livre Brasil, com código MLB.")
                value = money(row["PREÇO"])
                if row["VERIFICADO"] and (value is None or value <= 0):
                    raise ValueError("Referências verificadas precisam de preço positivo conferido.")
                accepted = bool(row["VERIFICADO"] and row["COMPATÍVEL"] and row["CONDIÇÃO"] == "Usada")
                new_refs.append(Reference(title=row["TÍTULO"] or "Anúncio", price=value, url=row["LINK"],
                    condition={"Usada": "used", "Nova": "new"}.get(row["CONDIÇÃO"], "unknown"),
                    verified=bool(row["VERIFICADO"]), compatible=bool(row["COMPATÍVEL"]),
                    status="Compatível (conferência manual)" if accepted else "Revisão necessária", reason=row["OBSERVAÇÃO"] or ""))
            selected.references = new_refs
            selected.references_edited = True
            export_excel(batch)
            save_batch(batch)
            st.success("Referências salvas.")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
        except OSError:
            st.error("Feche a planilha no Excel e confira a permissão da pasta.")
    col1, col2, col3 = st.columns(3)
    with col1:
        open_button("Abrir pasta de resultados", batch.folder, "open-folder")
    excel = batch.folder / "PLANILHA_DE_PRECIFICACAO.xlsx"
    if excel.exists():
        with col2:
            open_button("Abrir planilha no computador", excel, "open-excel")
        with col3:
            st.download_button("Exportar planilha Excel", excel.read_bytes(), excel.name,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    if batch.usage:
        st.caption(f"Última operação Gemini: {batch.usage.get('calls', 0)} chamadas · "
                   f"{batch.usage.get('input_tokens', 0)} tokens de entrada · {batch.usage.get('output_tokens', 0)} tokens de saída · "
                   f"{batch.usage.get('grounding_calls', 0)} chamadas com pesquisa. Custo em reais depende do modelo e da tabela do Google.")
    if st.session_state.get("upload_dirs") and st.button("Encerrar uso dos uploads e limpar cópias temporárias"):
        for directory in st.session_state.pop("upload_dirs"):
            directory.cleanup()
        st.session_state.pop("paths", None)
        st.session_state.pop("review_sequence", None)
        st.session_state["batch"] = load_batch(batch.folder)
        st.info("Cópias temporárias removidas. Suas fotos de origem e resultados salvos foram preservados. "
                "Para reprocessar sem ORIGINAIS salvos, selecione as fotos novamente.")
        st.rerun()


if __name__ == "__main__":
    main()
