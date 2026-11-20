"""Explicit approved local corpus streams; no downloads or discovery on import."""
from .sources import Source,SourceApprovalError,bind_source,file_snapshot
from .corpus import DataLimits,load_corpus,prepare_corpus

__all__=['Source','SourceApprovalError','bind_source','file_snapshot','DataLimits','load_corpus','prepare_corpus']
