"""Small OOXML exporter: all free text is inlineStr, never an Excel formula."""
import io
import json
import re
import zipfile
from xml.sax.saxutils import escape

HEADERS = [('application_id', 'ID заявки'), ('candidate', 'Кандидат'), ('vk_id', 'VK ID'),
           ('status', 'Статус'), ('directions', 'Направления'), ('score', 'Балл'),
           ('summary', 'Резюме'), ('criteria_results', 'Критерии и цитаты'),
           ('interview_questions', 'Вопросы собеседования'), ('answers', 'Все ответы')]


def export_xlsx(rows):
    def cell(value):
        if value is None:
            value = ''
        if isinstance(value, (list, dict)):
            value = json.dumps(value, ensure_ascii=False)
        if isinstance(value, (float, int)):
            return f'<c><v>{value}</v></c>'
        value = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', str(value))[:32767]
        return '<c t="inlineStr"><is><t xml:space="preserve">' + escape(value) + '</t></is></c>'
    # Long answers are additionally split into separate rows, preserving all text.
    data = [[label for _, label in HEADERS]]
    for row in rows:
        values = [row.get(key) for key, _ in HEADERS]
        data.append(values)
        answers = str(row.get('answers') or '')
        for offset in range(32767, len(answers), 32767):
            data.append([row.get('application_id'), 'Продолжение ответов', '', '', '', '', '', '', '', answers[offset:offset+32767]])
    xml = '<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" state="frozen"/></sheetView></sheetViews><cols><col min="1" max="5" width="24" customWidth="1"/><col min="6" max="6" width="10" customWidth="1"/><col min="7" max="10" width="65" customWidth="1"/></cols><sheetData>'
    xml += ''.join('<row>' + ''.join(cell(v) for v in row) + '</row>' for row in data)
    xml += f'</sheetData><autoFilter ref="A1:J{len(data)}"/></worksheet>'
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        z.writestr('_rels/.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr('xl/workbook.xml', '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Анкеты" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr('xl/worksheets/sheet1.xml', xml)
    return out.getvalue()
