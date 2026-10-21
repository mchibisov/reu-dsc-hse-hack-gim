"""Small OOXML exporter: all free text is inlineStr, never an Excel formula."""
import io
import json
import re
import zipfile
from xml.sax.saxutils import escape

HEADERS = [('application_id', 'ID заявки'), ('candidate', 'Кандидат'), ('vk_id', 'VK ID'),
           ('status', 'Статус'), ('directions', 'Направления'), ('score', 'Балл'),
           ('summary', 'Резюме'), ('criteria_results', 'Критерии модели и цитаты'),
           ('interview_questions', 'Вопросы собеседования'), ('answers', 'Все ответы'),
           ('recommended_directions', 'Рекомендованные направления'), ('source', 'Источник оценки'),
           ('files', 'Резюме и документы'), ('manual_reason', 'Обоснование куратора')]


def export_xlsx(rows):
    def cell(value, header=False):
        style = ' s="1"' if header else ' s="0"'
        if value is None:
            value = ''
        if isinstance(value, (list, dict)):
            value = json.dumps(value, ensure_ascii=False)
        if isinstance(value, (float, int)):
            return f'<c{style}><v>{value}</v></c>'
        value = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', str(value))[:32767]
        return '<c' + style + ' t="inlineStr"><is><t xml:space="preserve">' + escape(value) + '</t></is></c>'
    # Every long field gets continuation rows; Excel's per-cell limit is 32767.
    data = [[label for _, label in HEADERS]]
    for row in rows:
        values = [row.get(key) for key, _ in HEADERS]
        data.append(values)
        for index, value in enumerate(values):
            if isinstance(value, (list, dict)):
                value = json.dumps(value, ensure_ascii=False)
            if not isinstance(value, str):
                continue
            for offset in range(32767, len(value), 32767):
                extra = [''] * len(HEADERS)
                extra[0], extra[1], extra[index] = row.get('application_id'), 'Продолжение: ' + HEADERS[index][1], value[offset:offset+32767]
                data.append(extra)
    xml = '<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" state="frozen"/></sheetView></sheetViews><cols><col min="1" max="5" width="24" customWidth="1"/><col min="6" max="6" width="10" customWidth="1"/><col min="7" max="10" width="65" customWidth="1"/><col min="11" max="14" width="32" customWidth="1"/></cols><sheetData>'
    xml += ''.join(f'<row ht="{36 if index == 0 else 90}" customHeight="1">' + ''.join(cell(v, header=index == 0) for v in row) + '</row>' for index, row in enumerate(data))
    xml += f'</sheetData><autoFilter ref="A1:N{len(data)}"/></worksheet>'
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>')
        z.writestr('_rels/.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr('xl/workbook.xml', '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Анкеты" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        z.writestr('xl/worksheets/sheet1.xml', xml)
        z.writestr('xl/styles.xml', '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF173C4D"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="2"><xf fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf><xf fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf></cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
    return out.getvalue()
