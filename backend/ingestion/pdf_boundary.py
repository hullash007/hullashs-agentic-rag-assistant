"""Injected-reader PDF boundary preparation. No PDF library or real parsing here."""
from dataclasses import dataclass
import hashlib
import io
import warnings
from .contracts import SourceDocument
from .segments import ExtractedDocument, ExtractedSegment, SegmentLocator


class PDFRejected(ValueError):pass


@dataclass(frozen=True)
class PDFLimits:
    max_bytes: int
    max_pages: int
    max_text_chars: int
    max_page_stream_bytes: int

    def __post_init__(self):
        for value in (self.max_bytes,self.max_pages,self.max_text_chars,self.max_page_stream_bytes):
            if type(value) is not int or value<=0:
                raise ValueError('all PDF limits must be explicit positive integers')


def parse_pdf_with_reader(raw_bytes, source, limits, reader_factory):
    """Test the policy seam with synthetic reader doubles only.

    A future real reader adapter needs package review, log-warning policy,
    process resource limits and fixtures. strict=True is not a security claim.
    """
    if not isinstance(raw_bytes,bytes):raise TypeError('input must be bytes')
    if not isinstance(source,SourceDocument) or not isinstance(limits,PDFLimits):
        raise PDFRejected('source and explicit limits required')
    if source.mime_type!='application/pdf':raise PDFRejected('PDF MIME required')
    if len(raw_bytes)>limits.max_bytes:raise PDFRejected('original bytes exceed limit')
    if hashlib.sha256(raw_bytes).hexdigest()!=source.sha256:
        raise PDFRejected('source fingerprint does not match original bytes')
    with io.BytesIO(raw_bytes) as stream:
        with warnings.catch_warnings():
            warnings.simplefilter('error')
            try:
                reader=reader_factory(stream,strict=True)
                if reader.is_encrypted:raise PDFRejected('encrypted PDFs unsupported; no password attempts')
                pages=reader.pages
                if len(pages)>limits.max_pages:raise PDFRejected('page count exceeds limit')
                segments=[];total=0
                for i,page in enumerate(pages):
                    contents=page.get_contents()
                    if contents is not None and len(contents.get_data())>limits.max_page_stream_bytes:
                        raise PDFRejected('decoded page stream exceeds limit')
                    text=page.extract_text()
                    if text is None:text=''
                    if not isinstance(text,str):raise PDFRejected('reader returned non-text')
                    total+=len(text)
                    if total>limits.max_text_chars:raise PDFRejected('extracted text exceeds limit')
                    segments.append(ExtractedSegment(i,text,SegmentLocator('page',page_number=i+1)))
                return ExtractedDocument(source,'pdf',tuple(segments))
            except PDFRejected:raise
            except Exception as exc:
                raise PDFRejected('PDF reader rejected input or extraction') from exc
