"""Experiment-only real pypdf adapter. Caller MUST use approved bounded child."""
import logging
import warnings
from .pdf_boundary import PDFLimits, PDFRejected, parse_pdf_with_reader


class _RejectPypdfWarning(logging.Handler):
    def emit(self, record):
        raise PDFRejected('pypdf logged a warning or error')


def parse_pdf_experiment(raw_bytes, source):
    """No passwords/OCR. Not an upload service or production parser boundary."""
    logger = logging.getLogger('pypdf')
    handler = _RejectPypdfWarning(logging.WARNING)
    previous_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.WARNING)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error')
            from pypdf import PdfReader
            return parse_pdf_with_reader(raw_bytes, source,
                PDFLimits(2*1024*1024,20,200000,1024*1024),PdfReader)
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
        handler.close()
