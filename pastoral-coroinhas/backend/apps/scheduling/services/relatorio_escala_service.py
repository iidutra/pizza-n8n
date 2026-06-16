import csv
import io
from pathlib import Path

from PIL import Image as PILImage, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image as RLImage, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.scheduling.models import Escala, FUNCOES_ESCALA_ORDEM, FuncaoEscala

MESES_PT = [
    "",
    "Janeiro",
    "Fevereiro",
    "Março",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
]

FOTO_MM = 12
FOTO_PT = FOTO_MM * mm


class RelatorioEscalaService:
    @staticmethod
    def _escalas_mes(ano: int, mes: int):
        return (
            Escala.objects.filter(data__year=ano, data__month=mes)
            .select_related("missa")
            .prefetch_related("itens__coroinha")
            .order_by("data", "missa__horario")
        )

    @staticmethod
    def _itens_ordenados(itens):
        por_funcao = {item.funcao: item for item in itens if item.funcao}
        ordenados = []
        for funcao in FUNCOES_ESCALA_ORDEM:
            item = por_funcao.get(funcao.value)
            if item:
                ordenados.append(item)
        for item in itens:
            if not item.funcao:
                ordenados.append(item)
        return ordenados

    @staticmethod
    def _foto_flowable(coroinha) -> RLImage:
        if coroinha.foto and coroinha.foto.name:
            path = Path(coroinha.foto.path)
            if path.is_file():
                try:
                    return RLImage(str(path), width=FOTO_PT, height=FOTO_PT, kind="proportional")
                except Exception:
                    pass

        inicial = (coroinha.nome or "?")[0].upper()
        img = PILImage.new("RGB", (128, 128), color=(181, 142, 74))
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("arial.ttf", 56)
        except OSError:
            font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), inicial, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(((128 - tw) / 2, (128 - th) / 2 - 4), inicial, fill=(92, 28, 40), font=font)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return RLImage(buf, width=FOTO_PT, height=FOTO_PT)

    @staticmethod
    def exportar_mes_pdf(ano: int, mes: int) -> bytes:
        escalas = list(RelatorioEscalaService._escalas_mes(ano, mes))
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=14 * mm,
            rightMargin=14 * mm,
            topMargin=14 * mm,
            bottomMargin=14 * mm,
            title=f"Escala {MESES_PT[mes]}/{ano}",
        )

        styles = getSampleStyleSheet()
        titulo_style = ParagraphStyle(
            "TituloEscala",
            parent=styles["Heading1"],
            fontSize=16,
            textColor=colors.HexColor("#5C1C24"),
            spaceAfter=8,
        )
        subtitulo_style = ParagraphStyle(
            "SubEscala",
            parent=styles["Normal"],
            fontSize=10,
            textColor=colors.HexColor("#666666"),
            spaceAfter=12,
        )
        missa_style = ParagraphStyle(
            "MissaEscala",
            parent=styles["Heading2"],
            fontSize=12,
            textColor=colors.HexColor("#5C1C24"),
            spaceBefore=10,
            spaceAfter=6,
        )
        cell_style = ParagraphStyle(
            "Celula",
            parent=styles["Normal"],
            fontSize=9,
            leading=11,
        )

        elementos = [
            Paragraph(f"Escala do mês — {MESES_PT[mes]} de {ano}", titulo_style),
            Paragraph("Pastoral dos Coroinhas", subtitulo_style),
        ]

        if not escalas:
            elementos.append(Paragraph("Nenhuma escala montada neste período.", styles["Normal"]))
        else:
            for escala in escalas:
                cabecalho = (
                    f"{escala.data.strftime('%d/%m/%Y')} · {escala.missa.nome} "
                    f"({escala.missa.horario.strftime('%H:%M')})"
                )
                elementos.append(Paragraph(cabecalho, missa_style))

                itens = RelatorioEscalaService._itens_ordenados(list(escala.itens.all()))
                if not itens:
                    elementos.append(Paragraph("Sem coroinhas escalados.", cell_style))
                    elementos.append(Spacer(1, 6))
                    continue

                linhas = [["Função", "", "Coroinha"]]
                for item in itens:
                    funcao_txt = item.get_funcao_display() if item.funcao else "—"
                    linhas.append(
                        [
                            Paragraph(funcao_txt, cell_style),
                            RelatorioEscalaService._foto_flowable(item.coroinha),
                            Paragraph(item.coroinha.nome, cell_style),
                        ]
                    )

                tabela = Table(linhas, colWidths=[42 * mm, FOTO_MM * mm + 4, None])
                tabela.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#5C1C24")),
                            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                            ("FONTSIZE", (0, 0), (-1, 0), 9),
                            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FAF8F5")]),
                            ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#DDDDDD")),
                            ("LEFTPADDING", (0, 0), (-1, -1), 6),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                            ("TOPPADDING", (0, 1), (-1, -1), 5),
                            ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
                        ]
                    )
                )
                elementos.append(tabela)
                elementos.append(Spacer(1, 10))

        doc.build(elementos)
        return buffer.getvalue()

    @staticmethod
    def exportar_mes_csv(ano: int, mes: int) -> str:
        escalas = RelatorioEscalaService._escalas_mes(ano, mes)

        headers = ["Data", "Missa", "Horário"]
        headers += [f.label for f in FUNCOES_ESCALA_ORDEM]
        headers.append("Demais coroinhas")

        buffer = io.StringIO()
        writer = csv.writer(buffer, delimiter=";")
        writer.writerow(headers)

        for escala in escalas:
            itens = list(escala.itens.all())
            por_funcao = {item.funcao: item.coroinha.nome for item in itens if item.funcao}
            demais = [item.coroinha.nome for item in itens if not item.funcao]

            row = [
                escala.data.strftime("%d/%m/%Y"),
                escala.missa.nome,
                escala.missa.horario.strftime("%H:%M"),
            ]
            for funcao in FUNCOES_ESCALA_ORDEM:
                row.append(por_funcao.get(funcao.value, ""))
            row.append(", ".join(demais))
            writer.writerow(row)

        return "\ufeff" + buffer.getvalue()

    @staticmethod
    def exportar_mes_json(ano: int, mes: int) -> dict:
        escalas = RelatorioEscalaService._escalas_mes(ano, mes)

        linhas = []
        for escala in escalas:
            itens = list(escala.itens.all())
            funcoes_label = {
                FuncaoEscala(item.funcao).label: item.coroinha.nome
                for item in itens
                if item.funcao
            }
            linhas.append(
                {
                    "data": escala.data.isoformat(),
                    "missa": escala.missa.nome,
                    "horario": escala.missa.horario.strftime("%H:%M"),
                    "funcoes": funcoes_label,
                    "demais": [item.coroinha.nome for item in itens if not item.funcao],
                }
            )

        return {"ano": ano, "mes": mes, "escalas": linhas}
