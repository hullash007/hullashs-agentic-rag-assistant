"""Isolated synthetic-fixture experiment only, not general upload parsing."""
import hashlib,io,json,zipfile
from backend.ingestion.contracts import SourceDocument
from backend.ingestion.segments import ExtractedDocument,ExtractedSegment,SegmentLocator

class OfficeRejected(ValueError):pass

def preflight(raw,source,mime):
 if not isinstance(raw,bytes) or len(raw)>2097152:raise OfficeRejected('original byte cap/type')
 if not isinstance(source,SourceDocument) or source.mime_type!=mime or source.sha256!=hashlib.sha256(raw).hexdigest():raise OfficeRejected('source mismatch')
 try:
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   infos=z.infolist()
   if len(infos)>128 or len({i.filename for i in infos})!=len(infos):raise OfficeRejected('ZIP member count/duplicates')
   if sum(i.file_size for i in infos)>16777216:raise OfficeRejected('ZIP declared total cap')
   for i in infos:
    if i.flag_bits&1 or i.file_size>4194304 or i.file_size>max(1,i.compress_size)*100:raise OfficeRejected('ZIP declared member/encryption/ratio')
 except zipfile.BadZipFile as exc:raise OfficeRejected('invalid ZIP') from exc

def docx_extract(raw,source):
 preflight(raw,source,'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
 from docx import Document
 try:
  d=Document(io.BytesIO(raw))
  # Inspection of the library's already-parsed body, not custom XML extraction.
  if d.element.body.xpath('.//w:tbl'):raise OfficeRejected('tables unsupported')
  if d.element.body.xpath('.//w:ins | .//w:del | .//w:txbxContent | .//w:drawing | .//w:object | .//w:footnoteReference | .//w:commentReference'):
   raise OfficeRejected('known unsupported body structure')
  paras=d.paragraphs
  if len(paras)>1000:raise OfficeRejected('paragraph cap')
  segments=[];total=0
  for i,p in enumerate(paras):
   text=p.text;total+=len(text)
   if len(text)>4000 or total>20000:raise OfficeRejected('extracted text cap')
   segments.append(ExtractedSegment(i,text,SegmentLocator('paragraph',paragraph_index=i)))
  return ExtractedDocument(source,'docx',tuple(segments))
 except OfficeRejected:raise
 except Exception as exc:raise OfficeRejected('DOCX parse failure') from exc

def xlsx_known_fixture_extract(raw,source,*,fixture_sheets):
 """Known generated fixtures ONLY. Manifest from fixture builder, not user input.

 ReadOnlyWorksheet cannot prove absence of merges/underreported dimensions.
 This is NOT a generic XLSX adapter: no output for unknown/unmanifested files.
 Manifest binds bytes and expected actual sheet extents/merge absence from builder.
 """
 preflight(raw,source,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
 from openpyxl import load_workbook
 from openpyxl.xml import DEFUSEDXML
 from openpyxl.utils import get_column_letter
 import datetime,math
 if not DEFUSEDXML:raise OfficeRejected('defusedxml not selected')
 if not isinstance(fixture_sheets,dict) or fixture_sheets.get('sha256')!=source.sha256:raise OfficeRejected('known fixture manifest required')
 declared=fixture_sheets.get('sheets')
 if not isinstance(declared,list) or len(declared)>4:raise OfficeRejected('sheet cap/manifest')
 for s in declared:
  if s.get('merges') or type(s.get('rows')) is not int or type(s.get('columns')) is not int or not 0<=s['rows']<=1000 or not 0<=s['columns']<=32:raise OfficeRejected('known merges/extents unsupported')
 wb=None
 try:
  wb=load_workbook(io.BytesIO(raw),read_only=True,keep_links=False,data_only=False)
  if len(wb.worksheets)>4 or [s.title for s in wb.worksheets]!=[s['name'] for s in declared]:raise OfficeRejected('sheet mismatch/cap')
  segments=[];total=0;visited_cells=0
  for ws,expected in zip(wb.worksheets,declared):
   # This comparison catches known-builder inconsistency, not arbitrary hidden overflow.
   if (ws.max_row,ws.max_column)!=(expected['rows'],expected['columns']):raise OfficeRejected('declared dimension inconsistent with known fixture')
   visited_rows=0
   for row_no,row in enumerate(ws.iter_rows(),1):
    visited_rows+=1;visited_cells+=len(row)
    if visited_rows>1000 or len(row)>32 or visited_cells>10000:raise OfficeRejected('actual visited row/column/cell cap')
    fields=[]
    for col,cell in enumerate(row,1):
     value=cell.value
     if value is None:kind='blank';value=None
     elif cell.data_type=='f':
      if not isinstance(value,str):raise OfficeRejected('unsupported formula structure')
      kind='formula_text'
     elif isinstance(value,str):kind='string'
     elif isinstance(value,bool):kind='boolean'
     elif isinstance(value,(datetime.datetime,datetime.date,datetime.time)):kind=type(value).__name__;value=value.isoformat()
     elif isinstance(value,datetime.timedelta):kind='timedelta_seconds';value=value.total_seconds()
     elif isinstance(value,(int,float)):
      if isinstance(value,float) and not math.isfinite(value):raise OfficeRejected('nonfinite cell')
      kind='number'
     else:raise OfficeRejected('unsupported cell type')
     if value is not None:fields.append({'column':get_column_letter(col),'type':kind,'value':value})
    if not fields:continue
    text=json.dumps(fields,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False);total+=len(text)
    if len(text)>4000 or total>20000:raise OfficeRejected('row/total character cap')
    segments.append(ExtractedSegment(len(segments),text,SegmentLocator('sheet',sheet_name=ws.title,row_start=row_no,row_end=row_no)))
  return ExtractedDocument(source,'xlsx',tuple(segments))
 except OfficeRejected:raise
 except Exception as exc:raise OfficeRejected('XLSX fixture parse failure') from exc
 finally:
  if wb is not None:wb.close()
