"""Controlled version-bound library inspection; not hostile-file security."""
import io,json,hashlib,inspect,importlib.metadata,datetime,math
from pathlib import Path
from .office_adapter import OfficeRejected,preflight
from backend.ingestion.segments import ExtractedDocument,ExtractedSegment,SegmentLocator
EXPECTED={'worksheet/_reader.py':'be9fc3ef0e038800cc77236b62942096b095bd52d3f7f0ec4998a439dfbe9f67','worksheet/_read_only.py':'e8a77843eef752824363aeac911272fe4b3ec021cdb6d94686c0f1bc1f7d3ee6','xml/functions.py':'8c1b5f6bcfffc388019443c61cb18202d26268d28fca28532ec7e68a0caadbf4'}
class Meter:
 def __init__(self):self.total=0;self.reads=[]
class ReadCap:
 def __init__(self,stream,meter,label):self.stream=stream;self.meter=meter;self.label=label;self.count=0;self.eof=False
 def read(self,size=-1):
  remaining=min(4194304-self.count,16777216-self.meter.total)
  if remaining<0:raise OfficeRejected('actual decompressed byte cap')
  request=remaining+1 if size is None or size<0 else min(size,remaining+1)
  data=self.stream.read(request);self.count+=len(data);self.meter.total+=len(data)
  if self.count>4194304 or self.meter.total>16777216:raise OfficeRejected('actual decompressed byte cap')
  if not data:self.eof=True
  return data
 def close(self):
  if not self.stream.closed:self.stream.close();self.meter.reads.append({'member':self.label,'bytes':self.count,'eof':self.eof,'closed':True})
 def __enter__(self):return self
 def __exit__(self,*a):self.close()

def checked_api():
 import openpyxl
 from openpyxl.worksheet._reader import WorkSheetParser
 from openpyxl.xml import DEFUSEDXML
 if importlib.metadata.version('openpyxl')!='3.1.5' or not DEFUSEDXML:raise OfficeRejected('unsupported parser version/configuration')
 root=Path(openpyxl.__file__).parent
 for path,digest in EXPECTED.items():
  if hashlib.sha256((root/path).read_bytes()).hexdigest()!=digest:raise OfficeRejected('private parser source mismatch')
 if tuple(inspect.signature(WorkSheetParser).parameters)!=('src','shared_strings','data_only','epoch','date_formats','timedelta_formats','rich_text'):raise OfficeRejected('private parser interface mismatch')
 return WorkSheetParser

def typed(cell,column):
 v=cell.value
 if v is None:return None
 if cell.data_type=='f':
  if not isinstance(v,str):raise OfficeRejected('unsupported formula structure')
  kind='formula_text'
 elif cell.data_type=='e':kind='error_text'
 elif isinstance(v,str):kind='string'
 elif isinstance(v,bool):kind='boolean'
 elif isinstance(v,(datetime.datetime,datetime.date,datetime.time)):kind=type(v).__name__;v=v.isoformat()
 elif isinstance(v,datetime.timedelta):kind='timedelta_seconds';v=v.total_seconds()
 elif isinstance(v,(int,float)):
  if isinstance(v,float) and not math.isfinite(v):raise OfficeRejected('nonfinite cell')
  kind='number'
 else:raise OfficeRejected('unsupported cell type')
 return {'column':column,'type':kind,'value':v}

def extract_xlsx(raw,source,*,audit=None):
 preflight(raw,source,'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
 Parser=checked_api()
 from openpyxl import load_workbook
 from openpyxl.utils import get_column_letter
 wb=None;meter=Meter();opened=[]
 try:
  # Initial shared-string/style/workbook reads precede coverage of this meter.
  wb=load_workbook(io.BytesIO(raw),read_only=True,keep_links=False,data_only=False)
  if len(wb.worksheets)>4:raise OfficeRejected('sheet cap')
  expected=[];total_cells=0
  for ws in wb.worksheets:
   original=ws._get_source
   def get_source(original=original,title=ws.title):
    stream=ReadCap(original(),meter,title);opened.append(stream);return stream
   ws._get_source=get_source
   stream=ws._get_source();previous_row=0;coords=[];row_records=0;maxcol=0
   try:
    parser=Parser(stream,ws._shared_strings,data_only=False,epoch=wb.epoch,date_formats=wb._date_formats,timedelta_formats=wb._timedelta_formats)
    for row_index,row in parser.parse():
     row_records+=1
     if type(row_index) is not int or not 0<row_index<=1000 or row_index<=previous_row or row_records>1000:raise OfficeRejected('invalid/out-of-order row coordinate or cap')
     previous_row=row_index;previous_col=0;total_cells+=len(row)
     if total_cells>10000:raise OfficeRejected('actual cell cap')
     for cell in row:
      r=cell['row'];c=cell['column']
      if type(r) is not int or type(c) is not int or r!=row_index or not 0<c<=32 or c<=previous_col:raise OfficeRejected('duplicate/mismatched/out-of-order cell coordinate or cap')
      previous_col=c;maxcol=max(maxcol,c);coords.append((r,c))
    # parse exhausted; consume any library-unread tail through the same meter.
    while stream.read(65536):pass
    if parser.merged_cells is not None and parser.merged_cells.mergeCell:raise OfficeRejected('merged cells unsupported')
    expected.append({'sheet':ws,'coords':tuple(coords),'maxrow':previous_row,'maxcol':maxcol,'row_records':row_records})
   finally:stream.close()
  # No reset/extraction until every worksheet's full inspection succeeded.
  segments=[];chars=0;visited=0
  for info in expected:
   ws=info['sheet'];ws.reset_dimensions();coords=[];lastrow=0;maxcol=0
   for row_index,row in enumerate(ws.iter_rows(),1):
    lastrow=row_index;visited+=len(row)
    if row_index>1000 or len(row)>32 or visited>10000:raise OfficeRejected('extraction visited cap')
    fields=[]
    for col,cell in enumerate(row,1):
     if hasattr(cell,'row'):
      if cell.row!=row_index or cell.column!=col:raise OfficeRejected('extraction coordinate mismatch')
      coords.append((cell.row,cell.column));maxcol=max(maxcol,col)
     value=typed(cell,get_column_letter(col))
     if value is not None:fields.append(value)
    if fields:
     text=json.dumps(fields,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False);chars+=len(text)
     if len(text)>4000 or chars>20000:raise OfficeRejected('row/total character cap')
     segments.append(ExtractedSegment(len(segments),text,SegmentLocator('sheet',sheet_name=ws.title,row_start=row_index,row_end=row_index)))
   if tuple(coords)!=info['coords'] or lastrow!=info['maxrow'] or maxcol!=info['maxcol']:raise OfficeRejected('inspection/extraction observed extent mismatch')
  if len(meter.reads)!=2*len(expected) or not all(r['eof'] and r['closed'] for r in meter.reads):raise OfficeRejected('worksheet read completion mismatch')
  if audit is not None:audit.update(actual_worksheet_bytes=meter.total,reads=meter.reads,inspected_sheets=len(expected),inspection_cells=total_cells,extraction_visited_cells=visited,coverage='worksheet inspection+extraction reads only; initial workbook/sharedStrings/styles NOT metered')
  return ExtractedDocument(source,'xlsx',tuple(segments))
 except OfficeRejected:raise
 except Exception as exc:raise OfficeRejected('controlled XLSX parse failure') from exc
 finally:
  for stream in opened:stream.close()
  if wb is not None:wb.close()
